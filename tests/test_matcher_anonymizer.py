"""
test_matcher_anonymizer.py
Tests for the JD Match Scorer (deterministic scoring) and Resume Anonymizer.

    python tests/test_matcher_anonymizer.py

Uses the 5 fixture resumes and their known parsed fields from test_resumes.py.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from execution.extract_text import extract_text
from execution.extract_contacts import extract_contacts
from execution.calc_experience import normalize_experience, calc_total_years
from execution.redact_pii import redact_resume_text
from execution.score_match import score_candidate, normalize_skill, degree_level
from test_resumes import EXPECTED, FIXTURES, as_llm_entries

passed, failures = 0, []


def check(label: str, ok: bool, detail: str = ""):
    global passed
    if ok:
        passed += 1
    else:
        failures.append(f"{label}: {detail}")


def parsed(fname: str) -> tuple[dict, str]:
    """Fixture resume as the parser would return it, plus its raw text."""
    exp = EXPECTED[fname]
    norm = normalize_experience(as_llm_entries(exp["experience"]))
    resume = {
        "skills": exp["skills"],
        "experience": norm,
        "education": [{"degree": d, "institution": i, "year": y} for d, i, y in exp["education"]],
        "total_experience_years": calc_total_years(norm),
    }
    return resume, extract_text(str(FIXTURES / fname))["text"]


# ── Match scorer ──────────────────────────────────────────────────────────────

DATA_ENG_JD = {
    "job_title": "Senior Data Engineer",
    "required_skills": ["Python", "Spark", "SQL", "Airflow"],
    "nice_to_have_skills": ["Kafka", "Kubernetes"],
    "min_years_experience": 5,
    "education_level": "bachelor",
}

scores = {f: score_candidate(*parsed(f)[:1], DATA_ENG_JD, parsed(f)[1]) for f in EXPECTED}

priya = scores["two_column.pdf"]
check("Priya: all required skills matched (Spark ← 'Apache Spark')",
      priya["required_skills_missing"] == [], f"missing={priya['required_skills_missing']}")
check("Priya: Kafka found in resume text (not in skills list)",
      "Kafka" in priya["nice_to_have_matched"], f"nice={priya['nice_to_have_matched']}")
check("Priya: experience and education met",
      priya["experience_met"] and priya["education_met"] is True, str(priya))
check("Priya: score 95 (0.6 + 0.3 + 0.1×½)", priya["match_score"] == 95, f"got={priya['match_score']}")

rahul = scores["fresher.pdf"]
check("Fresher: missing Python/Spark/SQL/Airflow",
      set(rahul["required_skills_missing"]) == {"Python", "Spark", "SQL", "Airflow"},
      f"missing={rahul['required_skills_missing']}")
check("Fresher: experience not met, score 0", not rahul["experience_met"] and rahul["match_score"] == 0,
      str(rahul))

ranked = sorted(scores, key=lambda f: -scores[f]["match_score"])
check("Data-eng JD ranks the data engineer first", ranked[0] == "two_column.pdf", f"ranking={ranked}")

mike = scores["single_column.pdf"]
check("'Go' not text-matched from prose; only Python matched for Michael",
      mike["required_skills_matched"] == ["Python"], f"matched={mike['required_skills_matched']}")

check("Aliases: k8s → kubernetes, Node.js → node",
      normalize_skill("K8s") == "kubernetes" and normalize_skill("Node.js") == "node")
check("Degree levels: MBA=master, B.E.=bachelor, PhD=phd",
      (degree_level("MBA"), degree_level("B.E. Computer Science"), degree_level("PhD Physics")) == (4, 3, 5))

no_req = score_candidate(parsed("present.docx")[0],
                         {"required_skills": ["Figma"], "min_years_experience": 0}, "")
check("No nice-to-have + no years required → 100 for full required match",
      no_req["match_score"] == 100 and no_req["education_met"] is None, str(no_req))


# ── Anonymizer ────────────────────────────────────────────────────────────────

for fname, exp in EXPECTED.items():
    text = extract_text(str(FIXTURES / fname))["text"]
    redacted, counts = redact_resume_text(text, extract_contacts(text))
    leaks = [v for v in (exp["email"], exp["linkedin"]) if v and v.split("//")[-1] in redacted]
    leaks += [t for t in exp["name"].split() if len(t) > 2 and re.search(rf"(?<!\w){re.escape(t)}(?!\w)", redacted)]
    if exp["phone"] in redacted:
        leaks.append(exp["phone"])
    if exp["location"].split(",")[0] in redacted:
        leaks.append(exp["location"])
    check(f"{fname}: no PII left", not leaks, f"leaked={leaks}")
    kept = [s for s in exp["skills"] if s not in redacted]
    check(f"{fname}: skills text kept", not kept, f"lost={kept}")

sample = """ANJALI GUPTA
anjali.g@yahoo.in | +91 99887 66554
DOB: 12/03/1998 | Gender: Female | Marital Status: Single
Nationality - Indian
Father's Name: Ramesh Gupta
Experience
Analyst at Grace Hopper Labs, Pune, India (2021 - 2023)"""
red, counts = redact_resume_text(sample)
check("Personal details redacted (DOB/gender/marital/nationality/father)",
      counts.get("personal_details") == 5 and "1998" not in red and "Female" not in red and "Ramesh" not in red,
      red)
check("ALL-CAPS name and surname inside other text redacted", "ANJALI" not in red and "Gupta" not in red, red)
check("Job line and dates survive", "Grace Hopper Labs" in red and "2021 - 2023" in red, red)


total = passed + len(failures)
print(f"Matcher + anonymizer: {passed}/{total} passed")
for f in failures:
    print(f"  ❌ {f}")
sys.exit(1 if failures else 0)
