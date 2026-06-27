# Maui AI Gajah Terbang 🐘

Pembantu penyelidikan berasaskan **Streamlit** yang menggunakan **LLM tempatan** (LM Studio) untuk menjawab soalan. Untuk setiap soalan, ia akan:

1. Mencari di **DuckDuckGo**,
2. Membaca dan mengekstrak teks dari page teratas (guna `trafilatura`),
3. Membahagikan kandungan kepada blok dan markah kerelevanan,
4. Menghantar blok terbaik ke LLM tempatan untuk hasilkan jawapan dalam bahasa pengguna.

Sejarah chat disimpan secara tempatan dalam fail `maui_chats.json`.

---

## Prerequisites

App ni bergantung pada **LLM tempatan** yang berjalan di mesin anda melalui LM Studio. Setup penuh di bawah.

### Langkah 1 — Pasang LM Studio

- Download dari **[lmstudio.ai](https://lmstudio.ai/)** (Windows / macOS / Linux) dan pasang.
- Buka LM Studio.

### Langkah 2 — Download model

- Pergi ke tab **Discover** (icon kaca mata di sidebar kiri).
- Cari model. Skrip ni diconfigure untuk **`google/gemma-4-2b-qat`** (boleh cari kata kunci `gemma` / `qat`).
- Pilih fail dalam format **GGUF** yang sesuai dengan RAM/VRAM mesin anda (size kecil = ringan & pantas, size besar = lebih pandai tapi perlukan lebih banyak memory).
- Klik **Download** dan tunggu sampai siap (model boleh beberapa GB, bergantung pada size).

> Tip: kalau mesin anda kurang RAM/V RAM, pilih varian model yang lebih kecil (cth. versi `2b`). Varian besar (7b+) mungkin perlukan GPU.

### Langkah 3 — Hidupkan server

- Pergi ke tab **Developer** (icon `</>` di sidebar kiri) → bahagian **Server**.
- Daripada dropdown model, pilih model yang baru anda download.
- Klik **Load** untuk muatkan model ke dalam server.
- Klik **Start Server**. Server akan hidup (secara default) di:

  ```
  http://localhost:1234
  ```

- (Server ni OpenAI-compatible, jadi `langchain-openai` boleh terus guna.) Pastikan status server = **Running**.
- Boleh verify: buka `http://localhost:1234/v1/models` dalam browser — patut nampak senarai model yang diload.

### Langkah 4 — Padankan nama model dengan skrip

Skrip menghantar nama model ini (dalam bahagian `# --- CONFIGURATION ---`):

```python
MODEL_NAME = "google/gemma-4-2b-qat"
BASE_URL   = "http://localhost:1234/v1"
```

- Nilai `MODEL_NAME` **KENA sama** dengan **identifier** model yang diload dalam LM Studio (tengok nama model yang terpapar di tab **Developer**).
- Kalau anda download model **lain**, kemaskini `MODEL_NAME` dalam skrip supaya sepadan dengan identifier di LM Studio.
- `BASE_URL` biarkan default kecuali anda ubah port di LM Studio.

> Tanpa LM Studio berjalan di `localhost:1234`, app takkan dapat jawab soalan.

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
