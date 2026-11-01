# Resume Parser API

Parse PDF and DOCX resumes from URLs into structured JSON. Handles 2-column layouts, scanned PDFs (OCR), non-English names, overlapping jobs and "Present" end dates.

**Pricing:** pay per result — one dataset item per resume ($0.005 suggested; set it in Apify Console → Publication → Monetization).

## Input

```json
{
  "urls": ["https://example.com/resume1.pdf", "https://example.com/resume2.docx"],
  "llm_model": "gpt-4o-mini",
  "max_concurrency": 5
}
```

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `urls` | string[] | yes | — | Direct download URLs to PDF/DOCX files (file type is detected from content, so URLs without an extension work) |
| `llm_model` | string | no | `gpt-4o-mini` | OpenAI model used to map skills/experience/education sections |
| `max_concurrency` | integer | no | 5 | Resumes processed in parallel (1–20) |
| `llm_api_key` | string (secret) | no | — | Your own OpenRouter (`sk-or-…`) or OpenAI key. Leave empty to use the actor's built-in key |

**LLM key:** if you supply `llm_api_key`, your key is used and billed by your provider. Otherwise the actor uses the owner's key (set by the owner as a secret env var `OPENROUTER_API_KEY` or `OPENAI_API_KEY`). Cost is roughly $0.0003 per resume on gpt-4o-mini.

## Output

One dataset item per resume:

```json
{
  "source_url": "https://example.com/priya.pdf",
  "name": "Priya Ramanathan",
  "email": "priya.r@gmail.com",
  "phone": "+91 98450 12345",
  "location": "Bangalore, India",
  "linkedin": "https://linkedin.com/in/priyaram",
  "skills": ["Python", "SQL", "Apache Spark", "Airflow", "AWS"],
  "experience": [
    {"title": "Software Engineer", "company": "Infosys", "start": "2016-08", "end": "2018-06", "duration_months": 22},
    {"title": "Data Engineer", "company": "Swiggy", "start": "2018-07", "end": "2021-04", "duration_months": 33},
    {"title": "Freelance Data Consultant", "company": "Self-employed", "start": "2020-01", "end": "2020-12", "duration_months": 11},
    {"title": "Senior Data Engineer", "company": "Flipkart", "start": "2021-03", "end": null, "duration_months": 68}
  ],
  "education": [
    {"degree": "B.E. Computer Science", "institution": "RV College of Engineering", "year": 2016}
  ],
  "total_experience_years": 10.2,
  "parse_confidence": 1.0,
  "error": null
}
```

- `end: null` means the role is current ("Present"); its duration runs to today.
- `total_experience_years` merges overlapping jobs (the freelance role above isn't double-counted).
- Missing fields are `null` / `[]`, never omitted. `error` is set if the file couldn't be downloaded or read.
- `parse_confidence` (0–1) starts at 1.0 and drops 0.05 per missing name/email/phone/location, 0.10 for OCR, 0.15 if the LLM step failed, 0.10 if no experience *and* no education, 0.05 if no education.

## How it works

Only one step uses an LLM; everything else is deterministic code.

```
URL → extract_text.py → extract_contacts.py → map_sections.py → calc_experience.py → validate_schema.py → JSON
      pdfplumber/docx/OCR   regex                LLM: skills,       date parsing,          pydantic,
                                                 experience,        overlap merge          confidence
                                                 education
```

The SOP and edge-case rules are in `directives/parse_resume.md`.

## Development

See the repo root `README.md` for tests and deployment.
