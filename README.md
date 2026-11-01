# HR Recruiter Actors (Apify)

Three Apify actors for recruiters that share one deterministic resume engine (`execution/`).

| Actor | What it does | LLM | Suggested price |
|---|---|---|---|
| [Resume Parser API](actors/resume-parser/README.md) | PDF/DOCX resume → structured JSON (contacts, skills, experience, education) | yes | $0.005 / resume |
| [JD ↔ Resume Match Scorer](actors/jd-match-scorer/README.md) | Rank resumes against a JD with a 0–100 score, matched and missing skills | yes | $0.01 / resume |
| [Resume Anonymizer](actors/resume-anonymizer/README.md) | Strip PII and personal details for blind screening | no | $0.002 / resume |

## Layout

```
directives/          SOPs: parse_resume.md, match_resume_jd.md, anonymize_resume.md
execution/           shared deterministic scripts (+ the two LLM mappers)
actors/<name>/       main.py, Dockerfile, README.md, .actor/{actor.json,input_schema.json}
tests/               fixtures + tests
requirements.txt     shared by all actors
```

## LLM key

The Parser and Match Scorer need an LLM for one step: mapping messy resume and JD sections to fields. The key is chosen in this order:

1. The user's own key in the `llm_api_key` input (a secret field). Their provider bills them.
2. Your `OPENROUTER_API_KEY` env var on the actor (Console → actor → Source → Environment variables → Secret).
3. Your `OPENAI_API_KEY` env var.

If you set no key, users must bring their own. If you set one, users don't need any setup, and pay-per-result covers your LLM cost (≈$0.0003 per resume on gpt-4o-mini). The Anonymizer needs no key.

## Tests

```bash
venv/bin/python tests/test_parser.py               # unit: dates, overlaps, confidence, regex
venv/bin/python tests/test_resumes.py              # field accuracy on 5 fixture resumes (+ LLM fields if a key is in .env)
venv/bin/python tests/test_matcher_anonymizer.py   # scoring + redaction on the same fixtures
```

Fixtures (2-column, fresher, non-English name, single-column, DOCX with "Present") are regenerated with `venv/bin/python tests/make_fixtures.py` (needs `reportlab`).

## Deploy

Each actor builds with the repo root as its Docker context (`dockerContextDir` in its `actor.json`), so they all share `execution/`. Easiest route: push this repo to GitHub, then in Apify Console create one actor per folder with **Source → Git repository**, URL `https://github.com/<you>/<repo>#main:actors/<name>`.

The actors need Python 3.11+ (the Docker image). The local venv is Python 3.9, which runs `execution/` and the tests but can't import the Apify SDK.
