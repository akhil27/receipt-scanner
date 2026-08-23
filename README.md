# 🧾 Receipt Scanner

A local-first receipt scanner and expense tracker powered by **NVIDIA NIM Vision LLMs**.

Upload a photo (or PDF) of any receipt → the vision model extracts merchant, date, items, prices, and categories → arithmetic is validated → data is saved to SQLite → a dashboard shows your spending by category, merchant, and date range.

---

## Features

- **One-call extraction** — each receipt is processed by a single NVIDIA NIM Vision LLM call, no OCR, no multi-agent pipeline
- **Structured output** — the LLM returns JSON; Pydantic validates it against a strict schema
- **Arithmetic validation** — checks `subtotal + tax ≈ total` (±$0.02) and `sum(items) ≈ subtotal` (±$0.05); flags mismatches as `needs_review`
- **Merchant normalization** — maps receipt variants (`wal-mart`, `amzn mktp us`, `costco wholesale corp`) to clean names via a simple dict
- **Duplicate detection** — exact image SHA-256 hash rejects re-uploads (HTTP 409); fingerprint match (same merchant + date + total) flags probable duplicates
- **PDF support** — PDF receipts are rendered to PNG (first page) via PyMuPDF before extraction
- **Model fallback** — if the primary model fails, a configurable fallback model is tried automatically
- **Bring-your-own-key** — pass `X-Api-Key` header on upload to use a different NVIDIA API key per request
- **Manual correction** — edit any field (merchant, date, totals, item names/prices/categories) from the dashboard or API
- **Analytics** — spend by category, merchant, and day; filterable by custom date range
- **Streamlit dashboard** — upload, analytics charts, and receipt vault/editor in a single app
- **11 automated tests** — schema validation, normalization, arithmetic tolerances, JSON parsing resilience, SQLite CRUD, API integration, duplicate detection, PDF rendering

---

## Architecture

```
Receipt Image / PDF
        ↓
NVIDIA NIM Vision LLM  (single API call)
        ↓
Structured JSON response
        ↓
clean_json_response()   (strips markdown fences, <think> tags, isolates JSON)
        ↓
Pydantic validation     (Receipt schema)
        ↓
normalize_merchant()    (dict lookup)
        ↓
validate_totals()       (arithmetic check, flags needs_review on mismatch)
        ↓
Duplicate detection     (SHA-256 hash → hard reject, fingerprint → soft flag)
        ↓
SQLite                  (single file, items stored as JSON column)
        ↓
FastAPI REST API + Streamlit Dashboard
```

---

## Project Structure

```
receipt-scanner/
├── .env                  # API keys (gitignored)
├── .env.example          # Template
├── .gitignore
├── requirements.txt
├── models.py             # Pydantic schemas
├── nim_client.py         # NVIDIA NIM API client, validation, normalization
├── db.py                 # SQLite setup, CRUD, analytics, duplicate detection
├── main.py               # FastAPI endpoints
├── dashboard.py          # Streamlit dashboard
├── receipts/             # Uploaded images (gitignored)
├── receipts.db           # SQLite database (gitignored)
└── tests/
    └── test_receipt_scanner.py
```

---

## Quickstart

### 1. Clone & install

```bash
git clone https://github.com/akhil27/receipt-scanner.git
cd receipt-scanner
pip install -r requirements.txt
```

### 2. Configure

Copy `.env.example` to `.env` and add your NVIDIA API key:

```bash
cp .env.example .env
```

```env
NVIDIA_API_KEY=nvapi-your-key-here
NVIDIA_MODEL=meta/llama-3.2-11b-vision-instruct
NVIDIA_MODEL_FALLBACK=meta/llama-3.2-90b-vision-instruct
```

Get a free API key at [build.nvidia.com](https://build.nvidia.com).

### 3. Run

**Streamlit dashboard** (recommended for v1):

```bash
streamlit run dashboard.py
```

**FastAPI server** (if you want the REST API directly):

```bash
uvicorn main:app --reload --port 8000
```

Interactive API docs at `http://localhost:8000/docs`.

---

## API Reference

| Method   | Endpoint                | Description                                                       |
| :------- | :---------------------- | :---------------------------------------------------------------- |
| `POST`   | `/receipts`             | Upload image/PDF → extract → validate → save (accepts `X-Api-Key` header) |
| `GET`    | `/receipts`             | List receipts (filter: `?needs_review=true`, `?merchant=walmart`) |
| `GET`    | `/receipts/{id}`        | Single receipt with line items                                    |
| `PATCH`  | `/receipts/{id}`        | Update any field (merchant, date, total, items, needs_review)     |
| `DELETE` | `/receipts/{id}`        | Delete a receipt                                                  |
| `GET`    | `/analytics/summary`   | Aggregated spend by category, merchant, day (`?start=&end=`)      |
| `GET`    | `/images/{filename}`    | Serve uploaded receipt images                                     |

### Upload example

```bash
curl -X POST http://localhost:8000/receipts \
  -F "file=@receipt.jpg"
```

### Upload with your own API key

```bash
curl -X POST http://localhost:8000/receipts \
  -H "X-Api-Key: nvapi-your-key" \
  -F "file=@receipt.jpg"
```

---

## Categories

The vision model assigns each item to one of these categories:

`Food` · `Groceries` · `Restaurant` · `Alcohol` · `Household` · `Electronics` · `Health` · `Transportation` · `Entertainment` · `Other`

---

## Duplicate Detection

1. **Exact duplicate** (same image bytes) — SHA-256 hash match → upload rejected with HTTP 409
2. **Probable duplicate** (different image, same merchant + date + total ±$0.02) — receipt is saved but flagged `possible_duplicate: true`

---

## Tests

```bash
pytest -v
```

Test coverage:

| Area                     | What's tested                                                        |
| :----------------------- | :------------------------------------------------------------------- |
| Schema validation        | Required fields, invalid types, defaults, partial updates            |
| Merchant normalization   | Case, whitespace, known variants, unknown/accented names             |
| Arithmetic validation    | Exact match, ±$0.02 boundary, ±$0.05 item sum, zero, negatives      |
| JSON parsing             | Markdown fences, `<think>` tags, conversational wrapping             |
| SQLite CRUD              | Empty DB, 100-item receipts, partial updates, SQL injection safety   |
| FastAPI endpoints        | CORS, file type validation, CRUD lifecycle, filters, 404/409/422     |
| Duplicate detection      | Hash lookup, fingerprint tolerance, API reject/flag behavior         |
| PDF support              | First-page rendering, mime type detection                            |
| API key passthrough      | `X-Api-Key` header reaches the NIM client                           |

---

## Tech Stack

| Layer      | Technology                                             |
| :--------- | :----------------------------------------------------- |
| AI         | NVIDIA NIM Vision LLM (OpenAI-compatible API)          |
| Validation | Pydantic v2                                            |
| Backend    | FastAPI                                                |
| Database   | SQLite (single file)                                   |
| Dashboard  | Streamlit                                              |
| PDF        | PyMuPDF                                                |
| Testing    | pytest + FastAPI TestClient                            |

---

## What's explicitly not included (v1)

- No LangChain / LangSmith
- No OCR
- No multi-agent pipeline
- No Claude / OpenAI API
- No auth, S3, worker queues, or provider abstraction

These are intentional — the goal is to prove the pipeline works with a single vision LLM call before adding complexity.
