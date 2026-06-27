import streamlit as st
import json
import os
import re
import time
from datetime import datetime
import requests
import tiktoken
from langchain_openai import ChatOpenAI
try:
    from ddgs import DDGS              # library baharu (masih di-maintain)
except ImportError:
    from duckduckgo_search import DDGS  # fallback kalau 'ddgs' tak dipasang
from langchain_core.messages import HumanMessage, SystemMessage
import trafilatura

# --- CONFIGURATION ---
BASE_URL = "http://localhost:1234/v1"
CHAT_HISTORY_FILE = "maui_chats.json"
DIRECT_ANSWER_FIRST = True   # True = model jawab dulu dari pengetahuan sendiri, search internet hanya bila perlu. False = sentiasa search (behavior lama)

# --- RESEARCH CONFIG ---
SEARCH_RESULTS = 8          # jumlah hasil carian dari DuckDuckGo
FETCH_PAGES = 3             # bilangan page yang betul-betul dibaca (fetch + extract)
CHUNK_TOKENS = 500          # saiz satu blok dalam token (besar = satu blok cover banyak content)
MAX_CHUNKS = 3              # HAD KERAS: maksimum 3 blok diproses (cepat, tak berat)
MAX_CHARS_PER_PAGE = 25000  # had teks setiap page (cukup utk cover page besar seperti wiki)
SEARCH_RETRIES = 5          # cubaan carian (DDG block response secara rawak)
FETCH_TIMEOUT = 8           # timeout fetch page (saat)
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}


# --- CUSTOM CSS (The Perfect Maui Look - No White Box) ---
st.markdown("""
<style>
    .stApp { background-color: #05070a; color: #ffffff; }
    .main-header {
        font-size: 3.5rem;
        font-weight: 900;
        text-align: center;
        margin-bottom: 0;
        letter-spacing: -1px;
    }
    .grad-text {
        background: linear-gradient(90deg, #ffffff 0%, #8e8e8e 100%);
        -webkit-background-clip: text;
        background-clip: text;
        -webkit-text-fill-color: transparent;
        color: transparent;
        display: inline-block;
    }
    .ai-highlight {
        color: #FFD700 !important;
        -webkit-text-fill-color: #FFD700 !important;
        text-shadow: 0 0 15px rgba(255, 215, 0, 0.6);
        font-weight: 900;
        display: inline-block;
    }
    .sub-header {
        color: #4e5d6c;
        font-size: 1rem;
        text-align: center;
        text-transform: uppercase;
        letter-spacing: 4px;
        margin-bottom: 2rem;
    }
    .stChatMessage {
        border-radius: 15px;
        background-color: #161b22 !important;
        border: 1px solid #30363d !important;
    }
    .stSidebar { background-color: #0d1117 !important; }
</style>
""", unsafe_allow_html=True)


# --- DATA PERSISTENCE ---
def load_chats():
    if os.path.exists(CHAT_HISTORY_FILE):
        try:
            with open(CHAT_HISTORY_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_chats(chats):
    with open(CHAT_HISTORY_FILE, "w") as f:
        json.dump(chats, f, indent=4)


# --- AUTO-DETECT MODEL (pakai model yang tengah diload dalam LM Studio) ---
def detect_model():
    try:
        r = requests.get(f"{BASE_URL}/models", timeout=5)
        models = [m.get("id") for m in r.json().get("data", []) if m.get("id")]
        if models:
            return models[0]
    except Exception:
        pass
    return None   # tak ada model diload / server tak respon


# --- TOKENIZER (anggaran; tiktoken cl100k_base cukup dekat utk Gemma) ---
_ENC = None
def _enc():
    global _ENC
    if _ENC is None:
        try:
            _ENC = tiktoken.get_encoding("cl100k_base")
        except Exception:
            _ENC = False
    return _ENC

def count_tokens(text):
    e = _enc()
    if e:
        try:
            return len(e.encode(text))
        except Exception:
            pass
    return len(text) // 4   # fallback kasar


# --- RELEVANCE SCORING (prioriti chunk yang ada kaitan dgn soalan) ---
def query_keywords(query):
    """Token soalan -> {'words': set kata kunci, 'versions': set versi bintik (cth '15.1')}.
    Versi bintik ialah signal paling kuat utk cari row/version sebenar."""
    ql = query.lower()
    toks = re.findall(r'[a-zA-Z0-9]+', ql)
    words = {t for t in toks if (t.isdigit() and len(t) >= 2) or len(t) > 2}
    versions = set(re.findall(r'\d+(?:\.\d+)+', ql))   # cth 15.1, 14.4.2
    return {"words": words, "versions": versions}

def score_chunk(chunk, keywords):
    """Skor relevan: kata kunci (word-boundary) + VERSI exact (weight tinggi).
    Versi exact (cth '15.1') ialah signal paling kuat -> row/version sebenar menang
    lawan boilerplate/intro mahupun senarai versi lama yang padat tarikh."""
    cl = chunk.lower()
    words = keywords["words"]
    versions = keywords["versions"]
    base = sum(1 for k in words if re.search(r'\b' + re.escape(k) + r'\b', cl))
    ver = sum(10 for v in versions if re.search(r'\b' + re.escape(v) + r'\b', cl))
    return base + ver


# --- CHUNKING (pecah teks ikut bajet token) ---
def chunk_by_tokens(text, max_tokens):
    sentences = re.split(r'(?<=[.!?])\s+|\n+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    chunks, cur, cur_len = [], [], 0
    for s in sentences:
        slen = count_tokens(s)
        if slen > max_tokens:
            # ayat terlalu panjang -> pecah ikut perkataan
            if cur:
                chunks.append(" ".join(cur)); cur, cur_len = [], 0
            wbuf, wlen = [], 0
            for w in s.split():
                wl = count_tokens(w + " ")
                if wlen + wl > max_tokens:
                    if wbuf:
                        chunks.append(" ".join(wbuf))
                    wbuf, wlen = [w], wl
                else:
                    wbuf.append(w); wlen += wl
            if wbuf:
                chunks.append(" ".join(wbuf))
            continue
        if cur_len + slen > max_tokens:
            chunks.append(" ".join(cur))
            cur, cur_len = [s], slen
        else:
            cur.append(s); cur_len += slen
    if cur:
        chunks.append(" ".join(cur))
    return chunks


# --- SEARCH LAYER (DuckDuckGo + backoff) ---
def web_search(query):
    for attempt in range(SEARCH_RETRIES):
        try:
            with DDGS() as ddgs:
                items = list(ddgs.text(query, max_results=SEARCH_RESULTS))
            if items:
                return items
        except Exception:
            pass
        time.sleep(1.5 * (attempt + 1))   # backoff menaik
    return []


# --- FETCH + EXTRACT (page sebenar, bukan snippet) ---
def strip_html(html):
    """Fallback kasar: buang tag HTML -> teks kosong."""
    html = re.sub(r'(?is)<(script|style|nav|footer|header)[^>]*>.*?</\1>', ' ', html)
    text = re.sub(r'(?s)<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def fetch_page_text(url):
    # Cuba 1: trafilatura (extractor kandungan utama)
    try:
        html = trafilatura.fetch_url(url) or ""
        if html:
            text = trafilatura.extract(
                html,
                include_comments=False,
                include_tables=True,      # EOL / versi selalu ada dalam table
                favor_recall=True,        # prioritikan recall: jangan gugurkan table/data (favor_precision buang table kadang2)
            )
            if text and len(text) > 120:
                return text[:MAX_CHARS_PER_PAGE]
    except Exception:
        pass
    # Cuba 2: requests + strip HTML kasar
    try:
        r = requests.get(url, timeout=FETCH_TIMEOUT, headers=HTTP_HEADERS)
        if r.status_code == 200 and r.text:
            text = strip_html(r.text)
            if len(text) > 120:
                return text[:MAX_CHARS_PER_PAGE]
    except Exception:
        pass
    return ""


# --- DIRECT ANSWER (fikir dulu, search bila perlu) ---
def try_direct_answer(llm, user_query):
    """Cuba jawab terus dari pengetahuan model. Pulang (answer, needs_search).
    needs_search=True bila model bagi isyarat SEARCH_NEEDED, jawapan kosong, atau invoke gagal."""
    prompt = (
        f"SOALAN PENGGUNA: {user_query}\n\n"
        f"TUGASAN: Tentukan anda boleh jawab dengan tepat dari pengetahuan sendiri, "
        f"atau perlu carian internet. Pilih SALAH SATU:\n\n"
        f"A) Jawab terus, HANYA kalau ilmu umum stabil (definisi, konsep, matematik, "
        f"logik, terjemahan, nasihat, teori). Jawab lengkap dalam bahasa soalan.\n"
        f"B) Taip HANYA: SEARCH_NEEDED, kalau soalan libatkan versi software, tarikh, "
        f"harga, berita, peristiwa semasa, statistik terkini, data berubah, atau fakta "
        f"yang anda tak pasti.\n\n"
        f"Jangan campur A dan B. Kalau ragu, pilih B."
    )
    try:
        resp = llm.invoke(prompt)
        text = (resp.content or "").strip()
    except Exception:
        return None, True
    if not text or text.upper().strip().startswith("SEARCH_NEEDED"):
        return None, True
    return text, False


# --- ENTRY POINT (pilih: jawab terus atau search) ---
def answer_query(user_query):
    """Detect model sekali, cuba direct answer dulu (kalau DIRECT_ANSWER_FIRST),
    fallback ke deep_chunked_research bila perlu search."""
    model = detect_model()
    if not model:
        return ("⚠️ Tak dapat model dari LM Studio. Pastikan LM Studio running di "
                f"{BASE_URL} dan ada model diload, kemudian cuba lagi.")
    llm = ChatOpenAI(
        base_url=BASE_URL,
        api_key="lm-studio",
        model_name=model,
        temperature=0.0,
    )

    if DIRECT_ANSWER_FIRST:
        status = st.empty()
        try:
            status.markdown("🧠 *Memikir jawapan, tengok perlu search ke tak...*")
            direct, needs_search = try_direct_answer(llm, user_query)
        finally:
            status.empty()
        if not needs_search and direct:
            return (direct +
                    "\n\n_(Jawapan dari pengetahuan model, tanpa carian internet. "
                    "Verify jika perlu.)_")

    return deep_chunked_research(user_query, llm)


# --- THE RESEARCH ENGINE (Map-Reduce atas page sebenar) ---
def deep_chunked_research(user_query, llm):
    # llm di-detect & dibuat sekali oleh answer_query(), pass masuk supaya tak duplicate.

    # Status tunjuk semasa proses je (satu baris, update in-place),
    # lepas habis dikosongkan dgn finally -> tak tinggal dalam chat.
    status = st.empty()
    try:
        # Step 1: Cari sumber di internet
        status.markdown("🔍 *Mencari sumber di internet...*")
        items = web_search(user_query)
        if not items:
            return ("⚠️ DuckDuckGo tak bagi result sekarang (kemungkinan rate-limit). "
                    "Cuba lagi sebentar atau ubah soalan sikit.")

        # Step 2: Fetch + extract kandungan page sebenar
        status.markdown(f"🌐 *Membaca kandungan {FETCH_PAGES} page paling atas...*")
        pages = []
        for it in items[:FETCH_PAGES]:
            url = it.get("href") or it.get("url") or ""
            if not url:
                continue
            title = it.get("title", "")
            text = fetch_page_text(url)
            if text:
                pages.append({"title": title, "url": url, "text": text})

        # SENTIASA masukkan ringkasan carian DDG (snippet) sebagai sumber #1, bukan
        # fallback je. Snippet ialah penilaian relevan DDG sendiri:通用 utk soalan apa
        # pun, kerap ada jawapan terus, tak bergantung pada heuristik ranking chunk.
        snip_text = "\n".join(
            f"{it.get('title', '')}. {it.get('body', '')}"
            for it in items if it.get("body")
        )
        if snip_text:
            pages.insert(0, {"title": "Ringkasan carian DuckDuckGo",
                             "url": "", "text": snip_text})

        if not pages:
            return "⚠️ Tiada sumber yang boleh dibaca untuk soalan ini."

        # Step 3: Chunking PER-PAGE -> ambik chunk TERBAIK tiap source -> rank semula
        # -> potong ke MAX_CHUNKS. Camni: jumlah blok PASTI <= MAX_CHUNKS, tiap source
        # (snippet + page) dapat peluang, dan chunk paling relevan (cth row versi sebenar)
        # tak kena halau walau ia datang dari source terakhir (endoflife dsb).
        keywords = query_keywords(user_query)
        best_per_page = []
        for p in pages:
            pc = chunk_by_tokens(p["text"], CHUNK_TOKENS)
            if pc:
                pc.sort(key=lambda c: score_chunk(c, keywords), reverse=True)
                best_per_page.append(pc[0])   # chunk terbaik dari source ni
        best_per_page.sort(key=lambda c: score_chunk(c, keywords), reverse=True)
        chunks = best_per_page[:MAX_CHUNKS]   # HAD KERAS: potong ke MAX_CHUNKS

        # Step 4: JAWAPAN TERUS: hantar SEMUA chunk terpilih ke model dalam SATU
        # panggilan. Versi lama ada langkah MAP per-chunk dgn gate "NONE": bila model
        # tak berani petik fakta dari table, jawapan sebenar kena reject sebagai NONE
        # -> tarikh hilang -> "tak jumpa fakta". Model 26B cukup mampu baca semua chunk
        # kecil sekali gus, jadi buang gate tu. Lagi cepat (1 call), lagi teguh.
        if not chunks:
            return "⚠️ Tiada kandungan sumber yang boleh dibaca untuk soalan ini."

        status.markdown("🧠 *Menyusun jawapan daripada sumber...*")
        combined = "\n\n---\n\n".join(chunks)
        final_prompt = (
            f"SUMBER INTERNET (petikan):\n{combined}\n\n"
            f"SOALAN PENGGUNA: {user_query}\n\n"
            f"TUGASAN: Jawab soalan pengguna berdasarkan sumber di atas sahaja, ikut apa "
            f"yang ditanya, beri tarikh kalau soal tarikh, nombor kalau soal nombor, atau "
            f"apa sahaja maklumat berkaitan yang sesuai. Petik tepat dari sumber (termasuk "
            f"dari jadual/table). Jika sumber tak cukup, beritahu apa yang ada dan apa yang "
            f"tertinggal. Jawab dalam bahasa soalan."
        )
        try:
            final_resp = llm.invoke(final_prompt)
            answer = final_resp.content.strip()
        except Exception:
            answer = "⚠️ Model tak boleh jana jawapan sekarang. Cuba lagi."

        # Step 6: Lampir sumber (utk verify)
        src_lines = [f"- {p['title']}, {p['url']}" for p in pages[:5] if p.get("url")]
        if src_lines:
            answer += "\n\n**Sumber:**\n" + "\n".join(src_lines)

        return answer
    finally:
        status.empty()   # kosongkan semua status -> cuma jawapan tinggal


# --- MAIN APP LOGIC ---
if 'chats' not in st.session_state:
    st.session_state.chats = load_chats()

if 'current_chat_id' not in st.session_state:
    st.session_state.current_chat_id = None

if 'renaming_id' not in st.session_state:
    st.session_state.renaming_id = None

# --- SIDEBAR ---
with st.sidebar:
    st.markdown("## 🛰️ Control Terbang")
    if st.button("➕ New Chat", use_container_width=True):
        new_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        st.session_state.chats[new_id] = {"title": f"Chat {datetime.now().strftime('%H:%M:%S')}", "messages": []}
        st.session_state.current_chat_id = new_id
        save_chats(st.session_state.chats)
        st.rerun()

    st.markdown("---")
    st.subheader("Sembang Lepas")
    for chat_id in reversed(list(st.session_state.chats.keys())):
        chat_data = st.session_state.chats[chat_id]
        col1, col2, col3 = st.columns([4, 1, 1])
        with col1:
            if st.button(f"💬 {chat_data['title'][:10]}...", key=f"btn_{chat_id}", use_container_width=True):
                st.session_state.current_chat_id = chat_id
                st.rerun()
        with col2:
            if st.button("✏️", key=f"ren_{chat_id}"):
                st.session_state.renaming_id = chat_id
                st.rerun()
        with col3:
            if st.button("🗑️", key=f"del_{chat_id}"):
                del st.session_state.chats[chat_id]
                save_chats(st.session_state.chats)
                if st.session_state.current_chat_id == chat_id: st.session_state.current_chat_id = None
                st.rerun()
        if st.session_state.renaming_id == chat_id:
            new_name = st.text_input("Nama Baru:", value=chat_data['title'], key=f"in_{chat_id}")
            if st.button("Simpan", key=f"sv_{chat_id}"):
                st.session_state.chats[chat_id]['title'] = new_name
                save_chats(st.session_state.chats)
                st.session_state.renaming_id = None
                st.rerun()
        st.markdown("---")
    if st.button("🗑️ Padam Semua", use_container_width=True):
        st.session_state.chats = {}
        st.session_state.current_chat_id = None
        save_chats({})
        st.rerun()

# --- MAIN UI ---
if st.session_state.current_chat_id is None:
    st.markdown("<div style='text-align: center; margin-top: 20vh;'><h1 class='main-header'><span class='grad-text'>M<span class='ai-highlight'>a</span>u<span class='ai-highlight'>i</span> AI Gajah Terbang</h1><p class='sub-header'>Sila mula chat baru untuk mula buat research</p></div>", unsafe_allow_html=True)
else:
    st.markdown("<div style='text-align: center;'><h1 class='main-header'><span class='grad-text'>M<span class='ai-highlight'>a</span>u<span class='ai-highlight'>i</span> AI Gajah Terbang</h1><p class='sub-header'>Gajah Gila Googling</p></div>", unsafe_allow_html=True)
    current_chat = st.session_state.chats[st.session_state.current_chat_id]
    for msg in current_chat["messages"]:
        with st.chat_message(msg["role"]): st.markdown(msg["content"])

    if prompt_input := st.chat_input("Tanya Maui apa-apa..."):
        current_chat["messages"].append({"role": "user", "content": prompt_input})
        with st.chat_message("user"): st.markdown(prompt_input)
        with st.chat_message("assistant"):
            with st.spinner("Menganalisis Intelligence..."):
                ans = answer_query(prompt_input)
                st.markdown(ans)
                current_chat["messages"].append({"role": "assistant", "content": ans})
                save_chats(st.session_state.chats)
