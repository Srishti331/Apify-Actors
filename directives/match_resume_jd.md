# Directive: JD ↔ Resume Match Scorer (Apify Actor)

**Goal:** Score and rank a batch of resumes against one job description so a recruiter can shortlist quickly, with a reason for every score (matched / missing skills, experience fit).

**Use Case:** Recruiters screening 20–500 applicants for one role.

---

## Inputs

| Field | Type | Required | Description |
|---|---|---|---|
| `job_description` | string | Yes | Full JD text |
| `resume_urls` | array[string] | Yes | PDF/DOCX resume URLs |
| `llm_model` | string | No | Default `gpt-4o-mini` |
| `llm_api_key` | string (secret) | No | User's own key; falls back to the owner's env key (see `parse_resume.md`) |
| `max_concurrency` | integer | No | Default 5 |

## Output (one row per resume, sorted by `rank`)

```json
{
  "rank": 1,
  "source_url": "string",
  "name": "string | null", "email": "string | null", "phone": "string | null",
  "job_title": "string | null",
  "match_score": "integer 0–100",
  "required_skills_matched": ["string"],
  "required_skills_missing": ["string"],
  "nice_to_have_matched": ["string"],
  "total_experience_years": "float",
  "required_years": "float",
  "experience_met": "bool",
  "education_met": "bool | null (null = JD states no degree requirement)",
  "parse_confidence": "float",
  "error": "string | null"
}
```

The extracted JD requirements are also saved to the run's key-value store as `JD_REQUIREMENTS`.

---

## Execution Pipeline

1. **`execution/map_jd.py`** (LLM, once per run) — JD text → `{job_title, required_skills, nice_to_have_skills, min_years_experience, education_level}`. Abort the run if it fails or finds no required skills.
2. **`execution/parse_pipeline.py`** — full resume parse per URL (same as the Resume Parser; see `parse_resume.md`).
3. **`execution/score_match.py`** (deterministic) — scoring below.

## Scoring (deterministic)

```
match_score = 100 × (0.6 × required coverage + 0.3 × experience fit + 0.1 × nice-to-have coverage)
  experience fit = min(1, candidate_years / required_years), 1.0 if none required
  no nice-to-have skills in JD → 0.7 × required coverage + 0.3 × experience fit
  resume failed to parse → 0
```

Education is a flag (`education_met`), not part of the score — recruiters decide how strict to be.

## Edge Cases & Rules

- **Skill spellings:** normalize case/punctuation and an alias table (`k8s`→`kubernetes`, `Node.js`→`node`, `Apache Spark`→`spark`, …). A required skill also matches if all its tokens appear inside one candidate skill ("Spark" ⊂ "Apache Spark Streaming").
- **Skills missing from the LLM's list:** also search the raw resume text (word-boundary). Skipped for 1–2 letter skills (`Go`, `R`, `C`) — they appear as ordinary words; those only match via the skills list.
- **Degree levels:** regex on degree strings → high school 1, diploma 2, bachelor 3, master 4 (incl. MBA/MCA), PhD 5.
- **Freshers:** years 0 → experience fit 0 unless the JD requires 0 years.
- **Overlapping jobs:** handled by `calc_experience.py` (merged intervals), so moonlighting doesn't inflate years.

## Learnings

- TF-IDF cosine similarity on raw text (the old archived `text_matcher.py`) isn't useful for recruiters: it rewards keyword stuffing and can't say *which* requirement is missing. Explicit requirement coverage is explainable.

## Tests

`python tests/test_matcher_anonymizer.py` — scoring on the 5 fixture resumes against a data-engineer JD (ranking, alias/containment matching, text fallback, short-skill guard, degree levels, weight variants).
