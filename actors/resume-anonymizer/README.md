# Resume Anonymizer (Blind Screening)

Strip names, contact details, links, location and personal details (date of birth, gender, marital status, nationality, religion, age, parents' names) from PDF/DOCX resumes, so reviewers screen on skills and experience only.

No LLM and no API key: fast, cheap, and the same input always gives the same output.

**Pricing:** pay per result — one row per resume ($0.002 suggested; set in Apify Console → Publication → Monetization).

## Input

```json
{
  "urls": ["https://example.com/anjali.pdf", "https://example.com/rahul.docx"]
}
```

## Output

One dataset row per resume:

```json
{
  "candidate_id": "4b70f86470c8",
  "redacted_text": "[NAME]\n[EMAIL] | [PHONE]\nDOB: [REDACTED] | Gender: [REDACTED] | Marital Status: [REDACTED]\nExperience\nData Analyst, Flipkart, Jul 2021 - Present\n...",
  "redactions": {"personal_details": 3, "email": 1, "phone": 1, "name": 1},
  "error": null
}
```

**Re-identifying a shortlisted candidate:** the `candidate_id → name / email / phone / source URL` map is saved in the run's key-value store as `CANDIDATE_MAP`, kept out of the dataset. Share the dataset with reviewers and keep the map yourself.

## What gets redacted

| Placeholder | What |
|---|---|
| `[NAME]` | Full name, plus first/last name wherever else they appear |
| `[EMAIL]` | Every email address |
| `[PHONE]` | Every phone number (international and local formats) |
| `[URL]` | LinkedIn, GitHub, portfolio and other links |
| `[LOCATION]` | Candidate's city/region |
| `Label: [REDACTED]` | DOB, gender, marital status, nationality, religion, caste, age, father's/mother's/spouse's name, passport, photo |

Job titles, companies, dates, education and skills are kept. Photos embedded in PDFs aren't included because the output is text.
