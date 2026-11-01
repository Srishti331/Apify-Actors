# Directive: Resume Anonymizer (Apify Actor)

**Goal:** Remove identifying and bias-prone personal details from resumes so reviewers can screen on skills and experience only (blind hiring). Fully deterministic — no LLM, no API key.

**Use Case:** HR teams running blind screening, DEI programs, or sharing candidate profiles with hiring managers / clients before an introduction.

---

## Inputs

| Field | Type | Required | Description |
|---|---|---|---|
| `urls` | array[string] | Yes | PDF/DOCX resume URLs |

## Output (one row per resume)

```json
{
  "candidate_id": "12-char hash of email (or URL if no email)",
  "redacted_text": "string",
  "redactions": {"name": 2, "email": 1, "phone": 1, "url": 1, "location": 1, "personal_details": 3},
  "error": "string | null"
}
```

The `candidate_id → {source_url, name, email, phone}` map is saved to the run's key-value store as `CANDIDATE_MAP`, **not** to the dataset, so reviewers given the dataset only see anonymized rows; the recruiter uses the map to re-identify shortlisted candidates.

---

## Execution Pipeline

1. **`execution/extract_text.py`** — same extraction as the parser (2-column, DOCX tables, OCR).
2. **`execution/extract_contacts.py`** — find name, email, phone, location, LinkedIn.
3. **`execution/redact_pii.py`** — replace with placeholders, in this order:
   1. Labelled personal details: DOB, gender/sex, marital status, nationality, religion, caste, age, father's/mother's/spouse's name, passport, photo → `Label: [REDACTED]` (works mid-line, e.g. `Age: 27 | Gender: F`).
   2. All emails → `[EMAIL]`; all URLs (http, www, linkedin.com/…, github.com/…) → `[URL]`.
   3. All phone matches (`find_phones`) → `[PHONE]`.
   4. Full name (case-insensitive), then each name token ≥2 chars as written or ALL CAPS → `[NAME]`. Titles (Dr, Mr, PhD…) are left.
   5. Location string and its city → `[LOCATION]`.

## Edge Cases & Rules

- **Name tokens are matched case-sensitively** (as written or ALL CAPS), so ordinary words that are also names ("Grace", "Hope") survive in prose like "Grace Hopper Labs".
- **No location line:** `extract_location` only accepts a "City, Region" match on a contact-style line (≤40 chars, or containing `@ | · •` or a phone). Otherwise null — a wrong guess would redact a whole job line.
- **CJK / Vietnamese names** have no reliable token split — the full name string is redacted; tokens too when space-separated.
- **City inside an institution name** ("Universidad Complutense de Madrid") is redacted too — it's a location signal. Accepted.
- **Not handled (by design, keep minimal):** photos inside PDFs (text output only), gendered pronouns, graduation years as an age proxy.

## Tests

`python tests/test_matcher_anonymizer.py` — every fixture resume: no name/email/phone/LinkedIn/city left, all skills kept; plus a sample with DOB/gender/marital status/nationality/father's name.
