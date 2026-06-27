# Maui AI Gajah Terbang 🐘

Pembantu penyelidikan berasaskan **Streamlit** yang menggunakan **LLM tempatan** (LM Studio) untuk menjawab soalan. Untuk setiap soalan, ia akan:

1. Mencari di **DuckDuckGo**,
2. Membaca dan mengekstrak teks dari page teratas (guna `trafilatura`),
3. Membahagikan kandungan kepada blok dan markah kerelevanan,
4. Menghantar blok terbaik ke LLM tempatan untuk hasilkan jawapan dalam bahasa pengguna.

Sejarah chat disimpan secara tempatan dalam fail `maui_chats.json`.

---

## Prerequisites

App ni bergantung pada **LLM tempatan** yang berjalan di mesin anda:

- Pasang dan jalankan **[LM Studio](https://lmstudio.ai/)**.
- Mulakan **Local Server** (OpenAI-compatible) pada `http://localhost:1234/v1`.
- Load satu model (cth. keluarga **Gemma** seperti `google/gemma-4-2b-qat`).

Tanpa LM Studio berjalan di `localhost:1234`, app takkan dapat jawab soalan.

## Install

```bash
pip install -r requirements.txt
```

## Run

```bash
streamlit run Maui_AI_Gajah_Terbang.py
```

Browser akan terbuka dengan app tersebut.

## Cara ia berfungsi

- **Carian:** DuckDuckGo (tiada API key diperlukan).
- **Ekstraksi page:** `trafilatura`.
- **Tokenisasi:** `tiktoken`.
- **LLM:** melalui `langchain-openai` ke server LM Studio tempatan.
- **Sejarah chat:** disimpan ke `maui_chats.json` (tempatan, jangan dikongsikan).

## Konfigurasi

Tetapan utama ada di bahagian `# --- CONFIGURATION ---` dalam skrip:

- `MODEL_NAME` — model yang diload dalam LM Studio.
- `BASE_URL` — URL server LM Studio (default `http://localhost:1234/v1`).
- `CHAT_HISTORY_FILE` — fail simpanan sejarah chat.

## License

Dilesenkan di bawah **BSD 2-Clause License** — lihat fail [LICENSE](LICENSE).
