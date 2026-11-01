# Directive: Resume Parser API (Apify Actor)

**Goal:** Parse resume files (PDF or DOCX) from URLs and extract structured JSON data for downstream ATS/HR tooling.

**Use Case:** HR teams, ATS systems, or job boards that need structured candidate data from raw resume files at scale.

---

## Inputs

| Field       | Type          | Required | Description                              |
|-------------|---------------|----------|------------------------------------------|
| `urls`      | array[string] | Yes      | One or more direct download URLs to PDF/DOCX resumes |
| `llm_model` | string        | No       | LLM model to use for section mapping (default: `gpt-4o-mini`) |
| `llm_api_key` | string (secret) | No   | User's own OpenRouter/OpenAI key; falls back to the owner's env key |

---

## Output Schema (per resume)

```json
{
  "source_url": "string",
  "name": "string | null",
  "email": "string | null",
  "phone": "string | null",
  "location": "string | null",
  "linkedin": "string | null",
  "skills": ["string"],
  "experience": [
    {
      "title": "string",
      "company": "string",
      "start": "YYYY-MM",
      "end": "YYYY-MM | null",
      "duration_months": "integer"
    }
  ],
  "education": [
    {
      "degree": "string",
      "institution": "string",
      "year": "integer | null"
    }
  ],
  "total_experience_years": "float",
  "parse_confidence": "float (0.0–1.0)",
  "error": "string | null"
}
```

---

## Execution Pipeline (DOE Layer 3)

Run scripts in this order:

1. **`execution/extract_text.py`** — Download file from URL, extract raw text (pdfplumber for PDF, python-docx for DOCX). Falls back to OCR (pytesseract) for scanned PDFs with <30 words.
2. **`execution/extract_contacts.py`** — Regex-based extraction of email, phone, LinkedIn URL, and name (first N lines heuristic).
3. **`execution/map_sections.py`** (LLM section mapper, called from `execution/parse_pipeline.py`, orchestrated by `actors/resume-parser/main.py`) — Send raw text to LLM with structured prompt; LLM outputs JSON for skills, experience, education sections only.
4. **`execution/calc_experience.py`** — Merge overlapping date ranges, resolve "Present" → current date, calculate `duration_months` per role and `total_experience_years`.
5. **`execution/validate_schema.py`** — Pydantic validation, clamp confidence score, coerce types.

---

## Edge Cases & Rules

### Scanned PDFs
- **Detect:** `pdfplumber` extracts text; if word count < 30, classify as scanned. (100 was too high — short digital fresher resumes have 40–90 words.)
- **Fix:** Run `pytesseract` OCR on each page image.
- **Confidence penalty:** −0.10 from base confidence for OCR-parsed resumes.

### "Present" / "Current" End Dates
- Normalize to `null` in the output `end` field.
- Use `datetime.now()` as the effective end date when calculating `duration_months`.
- Accepted strings: `Present`, `Current`, `Now`, `Till date`, `Ongoing`, `—`, `-` (trailing).

### Overlapping / Concurrent Jobs
- Sort all experience entries by `start` date ascending.
- Merge overlapping intervals using interval-union logic (same as calendar deduplication).
- Total experience = sum of merged intervals, NOT sum of individual role durations.
- Keep individual role `duration_months` accurate (not merged) for display purposes.

### Missing Fields
- Set to `null` (string/scalar) or `[]` (arrays). Never omit keys.
- Each missing required field (name, email, phone, location) subtracts 0.05 from confidence.
- If no experience extracted: `total_experience_years = 0.0`.

### Non-English Names
- Do NOT attempt transliteration. Preserve original Unicode characters.
- Name extraction: first non-empty line of resume that is not an email/phone/URL.

### 2-Column PDF Layouts
- Detect a real gutter: an empty vertical band ≥12pt wide in the middle half of the page that no body word touches. Splitting at the page midpoint is wrong — it chops every long line of a normal single-column resume in half.
- Output order: header (anything above where both columns start, e.g. the name) → left column → right column.
- No gutter found → plain line-by-line extraction.

### Freshers (No Experience)
- `experience = []`, `total_experience_years = 0.0`.
- Confidence not penalized for missing experience if resume contains education.

### Date Normalization
- Accept: `Jan 2020`, `January 2020`, `01/2020`, `2020-01`, `2020`.
- Year-only dates: default to `YYYY-01` (January of that year).
- Ambiguous month/year (e.g., `03/20`): try `MM/YY`, interpret as `20YY-MM`.

### DOCX Files
- Use `python-docx` to read paragraphs and table cells **in document order** (walk the body XML), so an experience table stays under its "Experience" heading.
- Table cells often contain tabular experience/education — flatten to `key: value` text before LLM call.

### LLM Prompt Rules
- LLM is ONLY used for: section boundary detection, skills list extraction, experience/education block parsing.
- LLM is NOT used for: contact info (always regex), date calculation (always code), confidence scoring (always code).
- If LLM returns malformed JSON: catch exception, set affected arrays to `[]`, subtract 0.15 confidence.

---

## Confidence Scoring Formula

```
base = 1.0
− 0.05 × (count of null required fields: name, email, phone, location)
− 0.10  if OCR was used
− 0.15  if LLM JSON parse failed
− 0.10  if experience section missing entirely
− 0.05  if education section missing entirely
= parse_confidence  (clamped to [0.0, 1.0])
```

---

## Known API Constraints & Learnings

- `pdfplumber` works well on digital PDFs. Fails silently on fully scanned (image-only) pages — always check word count.
- `pytesseract` requires `tesseract` binary installed. Dockerfile must `apt-get install tesseract-ocr`.
- **LLM key:** `OPENROUTER_API_KEY` (preferred if set; base URL `https://openrouter.ai/api/v1`, model ids vendor-prefixed — `make_client()` adds `openai/`) or `OPENAI_API_KEY`. Resolution order: the user's own key from the `llm_api_key` input (secret field) → owner's `OPENROUTER_API_KEY` → owner's `OPENAI_API_KEY`. Keys starting `sk-or-` are routed to OpenRouter.
- OpenAI `gpt-4o-mini` is cheapest model with reliable JSON mode. Use `response_format={"type": "json_object"}`.
- Apify actor input is read via `Actor.get_input()`. Output pushed via `Actor.push_data()`.
- Large resume batches: process concurrently with `asyncio.gather` + semaphore (max 5 concurrent LLM calls).
- Apify pricing: set `price_per_dataset_item` in `actor.json` (e.g., $0.005 per resume parsed).
- **Python 3.9 compatibility:** The venv runs Python 3.9. Do NOT use `str | None` union syntax in function signatures — use `Optional[str]` from `typing` instead, or add `from __future__ import annotations` at the top of the file. `list[str]` in Pydantic models requires `from __future__ import annotations` in 3.9.
- **Phone regex — tiered patterns required:** A single generic regex fails on bare 10-digit Indian mobiles (e.g. `98989-22331`). Use 3-tier approach: (1) international `+CC ...`, (2) bare `\d{5}[\s\-.]?\d{5}` 10-digit, (3) generic local. Pick the match with the most digits.
- **Prompt template has literal JSON braces** — never use `str.format()` on it (raises KeyError, every LLM call silently fails). Use `.replace("{resume_text}", text)`.
- **`Actor.log` is a plain `logging.Logger`** in apify SDK 2.x — don't `await` its methods.
- **apify SDK does not import on Python 3.9** (crawlee/pydantic incompatibility). The local venv can run `execution/` and tests, but `actors/*/main.py` only run in the Docker image (Python 3.11).
- **Location regex must not match across newlines** (`[ \t]` not `\s`) and needs `\u1E00-\u1EFF` for Vietnamese.
- **Phone regex must skip year ranges** like `2018-2020`.
- **Confidence worst-case floor is 0.40**, not 0.0: 4 missing contacts (−0.20) + no exp (−0.10) + no edu (−0.05) + OCR (−0.10) + LLM fail (−0.15) = 0.40. Score cannot reach 0.0 under current formula.

---

## Test Cases

Fixtures live in `tests/fixtures/` (regenerate with `python tests/make_fixtures.py`). Run `python tests/test_resumes.py`; with an LLM key in env or `.env` it also checks the LLM-mapped sections.

| # | File | Special Condition | Target Fields to Verify |
|---|------|-------------------|-------------------------|
| 1 | `two_column.pdf` | 2-column layout + overlapping/contained jobs | reading order, contacts, merged `total_experience_years` |
| 2 | `fresher.pdf` | Fresher (no experience), short digital PDF | `experience=[]`, not misclassified as scanned |
| 3 | `non_english.pdf` | Non-English name/city (Nguyễn Thị Hương, Hà Nội) | Unicode preserved in `name` and `location` |
| 4 | `present.docx` | DOCX, experience in a table, "Present" end date | `end=null`, table stays in its section |
| 5 | `single_column.pdf` | Long lines spanning the page midpoint | not misdetected as 2-column |

**Target accuracy:** >95% field-level accuracy across all 5 test cases.
