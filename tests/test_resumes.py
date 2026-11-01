"""
test_resumes.py
Field-level accuracy test on the 5 fixture resumes in tests/fixtures/
(2-column, fresher, non-English name, single-column US, DOCX with "Present").

    python tests/test_resumes.py

Always checks the deterministic fields (contacts) on the real files, and the
date math on the known experience entries. If OPENROUTER_API_KEY or OPENAI_API_KEY
is set (env or .env) it also runs
the LLM section mapper and checks skills / experience / education.
"""

import asyncio
import os
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from execution.extract_text import extract_text
from execution.extract_contacts import extract_contacts
from execution.calc_experience import normalize_experience, calc_total_years
from execution.validate_schema import validate_resume

FIXTURES = Path(__file__).parent / "fixtures"

EXPECTED = {
    "two_column.pdf": {
        "name": "Priya Ramanathan", "email": "priya.r@gmail.com", "phone": "+91 98450 12345",
        "location": "Bangalore, India", "linkedin": "https://linkedin.com/in/priyaram",
        "skills": ["Python", "SQL", "Apache Spark", "Airflow", "AWS"],
        "experience": [
            ("Software Engineer", "Infosys", "2016-08", "2018-06"),
            ("Data Engineer", "Swiggy", "2018-07", "2021-04"),
            ("Freelance Data Consultant", "Self-employed", "2020-01", "2020-12"),
            ("Senior Data Engineer", "Flipkart", "2021-03", None),
        ],
        "education": [("B.E. Computer Science", "RV College of Engineering", 2016)],
    },
    "fresher.pdf": {
        "name": "Rahul Verma", "email": "rahul.verma2024@outlook.com", "phone": "98989-22331",
        "location": "Pune, India", "linkedin": None,
        "skills": ["Java", "JavaScript", "React", "HTML", "CSS", "Git"],
        "experience": [],
        "education": [
            ("B.Tech Computer Science", "Vishwakarma Institute of Technology", 2024),
            ("Higher Secondary Certificate", "Fergusson College", 2020),
        ],
    },
    "non_english.pdf": {
        "name": "Nguyễn Thị Hương", "email": "huong.nguyen@fpt.com.vn", "phone": "+84 912 345 678",
        "location": "Hà Nội, Vietnam", "linkedin": "https://linkedin.com/in/nguyen-thi-huong",
        "skills": ["Product Strategy", "Jira", "SQL", "Agile", "Stakeholder Management"],
        "experience": [
            ("Business Analyst", "Viettel Group", "2017-06", "2020-01"),
            ("Product Manager", "FPT Software", "2020-02", None),
        ],
        "education": [("MBA", "National Economics University", 2017)],
    },
    "single_column.pdf": {
        "name": "Michael O'Connor", "email": "mike.oconnor@protonmail.com", "phone": "(512) 555-0148",
        "location": "Austin, TX", "linkedin": "https://www.linkedin.com/in/mikeoconnor",
        "skills": ["Go", "Python", "PostgreSQL", "Kubernetes", "Terraform"],
        "experience": [
            ("Software Engineer", "Dell Technologies", "2017-05", "2021-12"),
            ("Staff Software Engineer", "Stripe", "2022-01", None),
        ],
        "education": [("B.S. Computer Science", "University of Texas at Austin", 2017)],
    },
    "present.docx": {
        "name": "Sofia Martínez", "email": "sofia.martinez@example.es", "phone": "+34 612 345 678",
        "location": "Madrid, Spain", "linkedin": "https://linkedin.com/in/sofiamartinez",
        "skills": ["Figma", "User Research", "Prototyping", "Design Systems"],
        "experience": [
            ("Junior Designer", "Cabify", "2018-01", "2019-08"),
            ("UX Designer", "Telefónica", "2019-09", None),
        ],
        "education": [("BA Graphic Design", "Universidad Complutense de Madrid", 2017)],
    },
}

CONTACT_FIELDS = ["name", "email", "phone", "location", "linkedin"]
correct, total, failures = 0, 0, []


def check(label: str, ok: bool, detail: str = ""):
    global correct, total
    total += 1
    correct += ok
    if not ok:
        failures.append(f"{label}: {detail}")


def norm(v):
    """Loose string compare: case/punctuation/whitespace-insensitive."""
    return re.sub(r"[\W_]+", "", str(v)).lower() if v is not None else None


def expected_years(entries) -> float:
    """Independent check: count distinct covered months (same [start, end) convention)."""
    today = date.today()
    months = set()
    for _, _, start, end in entries:
        sy, sm = map(int, start.split("-"))
        ey, em = (today.year, today.month) if end is None else map(int, end.split("-"))
        months.update(range(sy * 12 + sm, ey * 12 + em))
    return round(len(months) / 12, 1)


def as_llm_entries(entries):
    return [{"title": t, "company": c, "start": s, "end": e or "Present"} for t, c, s, e in entries]


async def run_llm(texts: dict) -> dict:
    from execution.map_sections import make_client, llm_extract_sections
    client, model = make_client("gpt-4o-mini")
    results = await asyncio.gather(*(llm_extract_sections(t, client, model) for t in texts.values()))
    return dict(zip(texts.keys(), results))


def load_dotenv():
    """Pick up API keys from the project's .env (gitignored) if not already set."""
    env = Path(__file__).parent.parent / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() and not key.strip().startswith("#"):
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def main():
    load_dotenv()
    texts = {}
    for fname, exp in EXPECTED.items():
        extraction = extract_text(str(FIXTURES / fname))
        check(f"{fname} text extracted", bool(extraction["text"]) and not extraction["error"],
              str(extraction["error"]))
        texts[fname] = extraction["text"]
        contacts = extract_contacts(extraction["text"])

        for field in CONTACT_FIELDS:
            got, want = contacts[field], exp[field]
            if field == "phone":
                ok = re.sub(r"\D", "", got or "") == re.sub(r"\D", "", want)
            else:
                ok = norm(got) == norm(want)
            check(f"{fname} {field}", ok, f"got={got!r} want={want!r}")

        # Date math on the known entries (what the LLM is expected to hand over)
        normalized = normalize_experience(as_llm_entries(exp["experience"]))
        years = calc_total_years(normalized)
        check(f"{fname} total_experience_years", years == expected_years(exp["experience"]),
              f"got={years} want={expected_years(exp['experience'])}")
        if exp["experience"]:
            check(f"{fname} 'Present' end -> null", normalized[-1]["end"] is None,
                  f"got={normalized[-1]['end']!r}")

        out = validate_resume({**contacts, "experience": normalized, "skills": exp["skills"],
                               "education": [dict(zip(("degree", "institution", "year"), e))
                                             for e in exp["education"]],
                               "total_experience_years": years})
        check(f"{fname} schema valid", out.get("error") is None, str(out.get("error")))

    if os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY"):
        print("LLM key set — checking LLM section mapping too")
        for fname, (data, failed) in asyncio.run(run_llm(texts)).items():
            exp = EXPECTED[fname]
            check(f"{fname} LLM ok", not failed)
            got_skills = {norm(s) for s in data.get("skills", [])}
            for s in exp["skills"]:
                check(f"{fname} skill {s}", norm(s) in got_skills, f"got={sorted(got_skills)}")
            got_exp = normalize_experience(data.get("experience", []))
            got_keys = {(norm(e["company"]), e["start"], e["end"]) for e in got_exp}
            for t, c, s, e in exp["experience"]:
                check(f"{fname} job {c}", (norm(c), s, e) in got_keys, f"got={got_keys}")
            check(f"{fname} no extra jobs", len(got_exp) == len(exp["experience"]),
                  f"got {len(got_exp)} jobs")
            got_edu = {(norm(e.get("institution")), e.get("year")) for e in data.get("education", [])}
            for d, inst, y in exp["education"]:
                check(f"{fname} edu {inst}", (norm(inst), y) in got_edu, f"got={got_edu}")
    else:
        print("No OPENROUTER_API_KEY / OPENAI_API_KEY — skipping LLM section checks (skills/experience/education)")

    pct = round(100 * correct / total, 1)
    print(f"\nField accuracy: {correct}/{total} = {pct}%")
    for f in failures:
        print(f"  ❌ {f}")
    if pct < 95:
        sys.exit(1)
    print("✅ >95% target met")


if __name__ == "__main__":
    main()
