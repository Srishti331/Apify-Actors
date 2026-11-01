"""
score_match.py
Layer 3 — Deterministic JD ↔ resume scoring.

Usage:
    from execution.score_match import score_candidate
    result = score_candidate(parsed_resume, jd_requirements, resume_text)

Score (0–100):
    0.6 × required-skill coverage
  + 0.3 × experience fit  (min(1, candidate_years / required_years); 1.0 if none required)
  + 0.1 × nice-to-have coverage
  (no nice-to-have skills in the JD → required skills weigh 0.7)

Education is reported as a flag (education_met) but not scored.
"""

import re
import sys
import json
from typing import Optional

# Common spellings → one canonical form
ALIASES = {
    "js": "javascript", "ts": "typescript", "k8s": "kubernetes", "postgres": "postgresql",
    "golang": "go", "nodejs": "node", "node.js": "node", "reactjs": "react", "react.js": "react",
    "vuejs": "vue", "vue.js": "vue", "nextjs": "next", "next.js": "next",
    "amazon web services": "aws", "google cloud": "gcp", "google cloud platform": "gcp",
    "ml": "machine learning", "dl": "deep learning", "ai": "artificial intelligence",
    "nlp": "natural language processing", "ci/cd": "cicd", "ci cd": "cicd",
    "ms excel": "excel", "microsoft excel": "excel", "apache spark": "spark", "pyspark": "spark",
    "scikit-learn": "sklearn", "scikit learn": "sklearn", "c sharp": "c#", "dotnet": ".net",
}

DEGREE_LEVELS = [
    (5, re.compile(r"\b(ph\.?\s?d|doctorate|doctor of)\b", re.I)),
    (4, re.compile(r"\b(m\.?\s?tech|m\.?\s?e\b|m\.?\s?sc|m\.?\s?s\b|m\.?\s?a\b|mba|mca|master)", re.I)),
    (3, re.compile(r"\b(b\.?\s?tech|b\.?\s?e\b|b\.?\s?sc|b\.?\s?s\b|b\.?\s?a\b|bba|bca|b\.?\s?com|bachelor)", re.I)),
    (2, re.compile(r"\b(diploma|associate)", re.I)),
    (1, re.compile(r"\b(high school|higher secondary|secondary school|12th|hsc|ssc)\b", re.I)),
]
JD_LEVEL = {"none": 0, "high_school": 1, "diploma": 2, "bachelor": 3, "master": 4, "phd": 5}


def normalize_skill(skill: str) -> str:
    s = re.sub(r"\s+", " ", str(skill).lower().strip())
    s = re.sub(r"[^\w+#./ -]", "", s).strip(" .-")
    return ALIASES.get(s, s)


def _in_text(skill: str, text_lower: str) -> bool:
    """Word-boundary search in the raw resume text. Skipped for 1–2 letter skills
    like "Go" or "R", which are ordinary words/letters in prose."""
    if len(skill) < 3 and not re.search(r"[+#]", skill):
        return False
    return re.search(r"(?<![\w+#])" + re.escape(skill) + r"(?![\w+#])", text_lower) is not None


def has_skill(required: str, candidate_skills: set, text_lower: str) -> bool:
    req = normalize_skill(required)
    if req in candidate_skills:
        return True
    # "Spark" vs candidate "Apache Spark Streaming": all required tokens inside one candidate skill
    req_tokens = set(req.split())
    if any(req_tokens <= set(c.split()) for c in candidate_skills):
        return True
    return _in_text(req, text_lower) or (req != required.lower() and _in_text(required.lower(), text_lower))


def degree_level(degree: Optional[str]) -> int:
    for level, pattern in DEGREE_LEVELS:
        if degree and pattern.search(degree):
            return level
    return 0


def score_candidate(resume: dict, jd: dict, resume_text: str = "") -> dict:
    candidate_skills = {normalize_skill(s) for s in resume.get("skills") or []}
    text_lower = (resume_text or "").lower()

    required = jd.get("required_skills") or []
    nice = jd.get("nice_to_have_skills") or []
    req_matched = [s for s in required if has_skill(s, candidate_skills, text_lower)]
    req_missing = [s for s in required if s not in req_matched]
    nice_matched = [s for s in nice if has_skill(s, candidate_skills, text_lower)]

    req_cov = len(req_matched) / len(required) if required else 1.0
    nice_cov = len(nice_matched) / len(nice) if nice else 0.0

    years = float(resume.get("total_experience_years") or 0.0)
    min_years = float(jd.get("min_years_experience") or 0.0)
    exp_fit = 1.0 if min_years <= 0 else min(1.0, years / min_years)

    if nice:
        score = 0.6 * req_cov + 0.3 * exp_fit + 0.1 * nice_cov
    else:
        score = 0.7 * req_cov + 0.3 * exp_fit

    jd_level = JD_LEVEL.get(jd.get("education_level") or "none", 0)
    cand_level = max((degree_level(e.get("degree")) for e in resume.get("education") or []), default=0)

    return {
        "match_score": round(100 * score),
        "required_skills_matched": req_matched,
        "required_skills_missing": req_missing,
        "nice_to_have_matched": nice_matched,
        "total_experience_years": years,
        "required_years": min_years,
        "experience_met": years >= min_years,
        "education_met": None if jd_level == 0 else cand_level >= jd_level,
    }


if __name__ == "__main__":
    """
    python execution/score_match.py <resume.json> <jd.json> [resume.txt]
    """
    from pathlib import Path
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Usage: score_match.py <resume.json> <jd.json> [resume.txt]"}))
        sys.exit(1)
    resume = json.loads(Path(sys.argv[1]).read_text())
    jd = json.loads(Path(sys.argv[2]).read_text())
    text = Path(sys.argv[3]).read_text() if len(sys.argv) > 3 else ""
    print(json.dumps(score_candidate(resume, jd, text), indent=2, ensure_ascii=False))
