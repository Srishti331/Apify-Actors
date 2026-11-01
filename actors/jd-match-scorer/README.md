# JD ↔ Resume Match Scorer

Paste a job description, give it a batch of PDF/DOCX resumes, get them back **ranked** with a 0–100 match score and the reason behind it: which required skills each candidate has, which are missing, and whether they meet the experience and degree bar.

**Pricing:** pay per result — one row per resume scored ($0.01 suggested; set in Apify Console → Publication → Monetization).

## Input

```json
{
  "job_description": "Senior Data Engineer... Must have: Python, Spark, SQL, Airflow. 5+ years. Nice to have: Kafka, Kubernetes. Bachelor's in CS or related.",
  "resume_urls": ["https://example.com/priya.pdf", "https://example.com/rahul.pdf"],
  "llm_model": "gpt-4o-mini"
}
```

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `job_description` | string | yes | — | Full JD text |
| `resume_urls` | string[] | yes | — | Direct download URLs to PDF/DOCX resumes |
| `llm_model` | string | no | `gpt-4o-mini` | Model for JD and resume section extraction |
| `llm_api_key` | string (secret) | no | — | Your own OpenRouter (`sk-or-…`) or OpenAI key. Leave empty to use the actor's built-in key |
| `max_concurrency` | integer | no | 5 | Resumes processed in parallel (1–20) |

## Output

One dataset row per resume, best match first:

```json
{
  "rank": 1,
  "source_url": "https://example.com/priya.pdf",
  "name": "Priya Ramanathan",
  "email": "priya.r@gmail.com",
  "phone": "+91 98450 12345",
  "job_title": "Senior Data Engineer",
  "match_score": 95,
  "required_skills_matched": ["Python", "Spark", "SQL", "Airflow"],
  "required_skills_missing": [],
  "nice_to_have_matched": ["Kafka"],
  "total_experience_years": 10.2,
  "required_years": 5.0,
  "experience_met": true,
  "education_met": true,
  "parse_confidence": 1.0,
  "error": null
}
```

The requirements extracted from the JD are saved in the run's key-value store as `JD_REQUIREMENTS`, so you can check what the candidates were scored against.

## How the score works

```
match_score = 100 × (0.6 × required skills covered
                   + 0.3 × experience fit        (candidate years ÷ required years, capped at 1)
                   + 0.1 × nice-to-have covered)
```

- If the JD lists no nice-to-have skills, required skills count for 0.7.
- Skills match across common spellings (`k8s` = Kubernetes, `Node.js` = Node, "Spark" matches "Apache Spark"), and a skill mentioned anywhere in the resume counts even if it isn't in the skills section.
- Experience uses merged dates, so overlapping jobs aren't double-counted.
- Education is shown as `education_met` but doesn't change the score.

The LLM only reads the JD and maps resume sections; the score itself is plain arithmetic, so the same inputs always give the same ranking.
