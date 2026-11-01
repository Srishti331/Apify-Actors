"""
map_jd.py
Layer 3 — LLM step for the JD Match Scorer: maps a free-text job description to
structured requirements. Scoring itself is deterministic (score_match.py).

Usage:
    from execution.map_jd import llm_extract_jd
    jd, llm_failed = await llm_extract_jd(jd_text, client, model)
"""

import json
import logging
import textwrap

log = logging.getLogger(__name__)

EDUCATION_LEVELS = ["none", "high_school", "diploma", "bachelor", "master", "phd"]

JD_PROMPT = textwrap.dedent("""
You are a recruiting assistant. Extract the hiring requirements from this job description.
Return VALID JSON only — no explanation, no markdown fences.

Output format:
{
  "job_title": "string",
  "required_skills": ["skill1", "skill2"],
  "nice_to_have_skills": ["skill3"],
  "min_years_experience": 3,
  "education_level": "none|high_school|diploma|bachelor|master|phd"
}

Rules:
- required_skills: concrete skills/tools/technologies stated as required or must-have. Short names ("Python", "Kubernetes"), no sentences.
- nice_to_have_skills: skills marked preferred, a plus, bonus, or nice to have.
- A skill appears in only one list.
- min_years_experience: minimum years of experience as a number; 0 if not stated. For a range like "3-5 years" use 3.
- education_level: minimum degree required; "none" if not stated.
- Do NOT invent requirements that are not in the text.

Job description:
\"\"\"
{jd_text}
\"\"\"
""").strip()


async def llm_extract_jd(jd_text: str, client, model: str) -> tuple[dict, bool]:
    """Returns (jd_requirements, llm_failed)."""
    empty = {"job_title": None, "required_skills": [], "nice_to_have_skills": [],
             "min_years_experience": 0, "education_level": "none"}
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": JD_PROMPT.replace("{jd_text}", jd_text[:12000])}],
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=1000,
        )
        parsed = json.loads(response.choices[0].message.content)
    except Exception as e:
        log.warning(f"JD extraction failed: {e}")
        return empty, True

    # Coerce to a predictable shape
    def as_list(v):
        return [str(s).strip() for s in v if str(s).strip()] if isinstance(v, list) else []

    try:
        years = max(0.0, float(parsed.get("min_years_experience") or 0))
    except (TypeError, ValueError):
        years = 0.0
    level = str(parsed.get("education_level") or "none").lower()
    return {
        "job_title": parsed.get("job_title") or None,
        "required_skills": as_list(parsed.get("required_skills")),
        "nice_to_have_skills": as_list(parsed.get("nice_to_have_skills")),
        "min_years_experience": years,
        "education_level": level if level in EDUCATION_LEVELS else "none",
    }, False
