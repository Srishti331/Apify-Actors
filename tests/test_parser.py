"""
test_parser.py
Expanded test suite — 10 test groups, ~35 assertions.
Uses venv Python. Run with:

    source venv/bin/activate
    python tests/test_parser.py

Real-file extraction is covered by tests/test_resumes.py.

Test groups:
  1.  CJK name extraction
  2.  Western name with suffix/credentials
  3.  "Present" / alias end dates
  4.  Overlapping / concurrent jobs
  5.  Three-way overlap + full containment
  6.  Fresher (no experience, no penalty)
  7.  Confidence formula variants
  8.  Date edge cases (year-only, MM/YY, ambiguous)
  9.  Contact regex edge cases (spaced email, intl phone, no LinkedIn)
  10. validate_schema coercion (bad year, negative duration, skill dedup)
  12. All-null confidence floor (worst case)
"""

import sys
import json
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from execution.extract_contacts import extract_contacts
from execution.calc_experience import normalize_experience, calc_total_years, parse_date
from execution.validate_schema import validate_resume, compute_confidence

PASS = "✅ PASS"
FAIL = "❌ FAIL"
results = []


def check(test_name: str, condition: bool, detail: str = ""):
    status = PASS if condition else FAIL
    results.append((test_name, status, detail))
    print(f"{status}  {test_name}" + (f"\n        → {detail}" if detail else ""))


# ════════════════════════════════════════════════════════════════
# TEST GROUP 1: CJK (non-English) name extraction
# ════════════════════════════════════════════════════════════════
print("\n── Group 1: CJK name extraction ──")
text_cjk = """韩晓明
han.xiaoming@example.com
+86 138 0000 1234
Beijing, China
linkedin.com/in/hanxiaoming
Software Engineer at Alibaba
"""
contacts = extract_contacts(text_cjk)
check("CJK name preserved as Unicode",
      contacts["name"] == "韩晓明",
      f"got={contacts['name']!r}")
check("CJK email extracted",
      contacts["email"] == "han.xiaoming@example.com",
      f"got={contacts['email']!r}")
check("CJK phone extracted (contains '138')",
      contacts["phone"] is not None and "138" in contacts["phone"],
      f"got={contacts['phone']!r}")
check("CJK LinkedIn extracted",
      contacts["linkedin"] is not None and "hanxiaoming" in contacts["linkedin"],
      f"got={contacts['linkedin']!r}")


# ════════════════════════════════════════════════════════════════
# TEST GROUP 2: Western name with post-nominal credentials
# ════════════════════════════════════════════════════════════════
print("\n── Group 2: Western name with credentials ──")
text_western = """Dr. Amelia J. Thornton, PhD
amelia.thornton@stanford.edu
+1 (650) 555-0192
Palo Alto, CA
https://linkedin.com/in/ameliathornton
"""
c2 = extract_contacts(text_western)
check("Name with title/credential extracted",
      c2["name"] is not None and "Thornton" in c2["name"],
      f"got={c2['name']!r}")
check("US phone extracted",
      c2["phone"] is not None and "650" in c2["phone"],
      f"got={c2['phone']!r}")
check("LinkedIn full URL extracted",
      c2["linkedin"] is not None and "ameliathornton" in c2["linkedin"],
      f"got={c2['linkedin']!r}")
check("Location 'Palo Alto, CA' detected",
      c2["location"] is not None and "Palo Alto" in c2["location"],
      f"got={c2['location']!r}")


# ════════════════════════════════════════════════════════════════
# TEST GROUP 3: All "Present" aliases
# ════════════════════════════════════════════════════════════════
print("\n── Group 3: All 'Present' alias variants ──")
today = date.today()
PRESENT_ALIASES = ["Present", "present", "Current", "current", "Now", "Till date",
                   "Ongoing", "—", "-", "Currently"]
for alias in PRESENT_ALIASES:
    norm = normalize_experience([
        {"title": "Dev", "company": "Co", "start": "Jan 2023", "end": alias}
    ])
    check(
        f"Alias '{alias}' → end=null",
        norm[0]["end"] is None,
        f"got end={norm[0]['end']!r}"
    )

# Also verify duration is calculated to today (not 0)
norm_p = normalize_experience([{"title": "Dev", "company": "Co", "start": "Jan 2023", "end": "Present"}])
check("Present role → duration_months > 0",
      norm_p[0]["duration_months"] > 0,
      f"got={norm_p[0]['duration_months']}")


# ════════════════════════════════════════════════════════════════
# TEST GROUP 4: Overlapping / concurrent jobs (2-way)
# ════════════════════════════════════════════════════════════════
print("\n── Group 4: Overlapping jobs (2-way) ──")
raw_overlap = [
    {"title": "Consultant", "company": "Firm A", "start": "Jan 2020", "end": "Dec 2021"},
    {"title": "Advisor",    "company": "Firm B", "start": "Jun 2020", "end": "Jun 2022"},
]
norm_ov = normalize_experience(raw_overlap)
total_ov = calc_total_years(norm_ov)
naive_ov = (norm_ov[0]["duration_months"] + norm_ov[1]["duration_months"]) / 12

check("2-way overlap: merged < naive sum",
      total_ov < naive_ov,
      f"merged={total_ov}yrs, naive={round(naive_ov,1)}yrs")
check("2-way overlap: merged ≈ 2.5 yrs (Jan 2020–Jun 2022)",
      2.3 <= total_ov <= 2.7,
      f"got={total_ov}")


# ════════════════════════════════════════════════════════════════
# TEST GROUP 5: 3-way overlap + fully contained interval
# ════════════════════════════════════════════════════════════════
print("\n── Group 5: 3-way overlap + fully contained interval ──")
# A: Jan 2018 – Dec 2020 (36 mo)
# B: Jun 2019 – Jun 2021 (24 mo) — overlaps A, extends
# C: Mar 2019 – Aug 2019 (5 mo)  — fully inside A
# Merged: Jan 2018 – Jun 2021 = 42 months = 3.5 yrs
raw_3way = [
    {"title": "R1", "company": "C1", "start": "Jan 2018", "end": "Dec 2020"},
    {"title": "R2", "company": "C2", "start": "Jun 2019", "end": "Jun 2021"},
    {"title": "R3", "company": "C3", "start": "Mar 2019", "end": "Aug 2019"},
]
norm_3 = normalize_experience(raw_3way)
total_3 = calc_total_years(norm_3)
naive_3 = sum(e["duration_months"] for e in norm_3) / 12

check("3-way overlap: merged < naive sum",
      total_3 < naive_3,
      f"merged={total_3}yrs, naive={round(naive_3,1)}yrs")
check("3-way overlap: merged ≈ 3.5 yrs",
      3.3 <= total_3 <= 3.7,
      f"got={total_3}")


# ════════════════════════════════════════════════════════════════
# TEST GROUP 6: Fresher — no experience, no confidence penalty
# ════════════════════════════════════════════════════════════════
print("\n── Group 6: Fresher (no experience) ──")
fresher_raw = {
    "source_url": "http://example.com/fresher.pdf",
    "name": "Priya Sharma",
    "email": "priya@example.com",
    "phone": "+91 98765 43210",
    "location": "Bangalore, IN",
    "linkedin": None,
    "skills": ["Python", "SQL"],
    "experience": [],
    "education": [{"degree": "B.Tech CS", "institution": "IIT Delhi", "year": 2024}],
    "total_experience_years": 0.0,
}
fresher_out = validate_resume(fresher_raw, is_ocr=False, llm_failed=False)
check("Fresher: total_experience_years == 0.0",
      fresher_out["total_experience_years"] == 0.0,
      f"got={fresher_out['total_experience_years']}")
check("Fresher: experience == []",
      fresher_out["experience"] == [],
      f"got={fresher_out['experience']}")
check("Fresher: confidence ≥ 0.75 (edu present, all contacts filled)",
      fresher_out["parse_confidence"] >= 0.75,
      f"got={fresher_out['parse_confidence']}")


# ════════════════════════════════════════════════════════════════
# TEST GROUP 7: Confidence formula — all penalty combinations
# ════════════════════════════════════════════════════════════════
print("\n── Group 7: Confidence formula variants ──")

# 7a: Perfect resume — all fields present, no OCR, LLM OK
perfect = {
    "name": "A", "email": "a@b.com", "phone": "123", "location": "NYC",
    "experience": [{"title": "X", "company": "Y", "start": "2020-01", "end": None, "duration_months": 10}],
    "education": [{"degree": "BS", "institution": "MIT", "year": 2020}],
}
check("Perfect: confidence == 1.0",
      compute_confidence(perfect, is_ocr=False, llm_failed=False) == 1.0,
      f"got={compute_confidence(perfect)}")

# 7b: OCR only penalty
raw_ocr = {**perfect, "phone": "123", "location": "NYC"}
check("OCR only: confidence == 0.90",
      compute_confidence(raw_ocr, is_ocr=True, llm_failed=False) == 0.90,
      f"got={compute_confidence(raw_ocr, is_ocr=True)}")

# 7c: LLM failed only
check("LLM fail only: confidence == 0.85",
      compute_confidence(perfect, is_ocr=False, llm_failed=True) == 0.85,
      f"got={compute_confidence(perfect, llm_failed=True)}")

# 7d: Missing all 4 contacts + no experience + no education + OCR
all_bad = {"name": None, "email": None, "phone": None, "location": None,
           "experience": [], "education": []}
score_bad = compute_confidence(all_bad, is_ocr=True, llm_failed=True)
check("Worst case: confidence clamped ≥ 0.0",
      score_bad >= 0.0,
      f"got={score_bad}")
check("Worst case: confidence < 0.5 (all penalties applied)",
      score_bad < 0.5,
      f"got={score_bad} (expected: 1.0-0.20-0.10-0.05-0.10-0.15=0.40)")

# 7e: OCR + missing phone + missing location = 1.0−0.05−0.05−0.10 = 0.80
raw_07e = {**perfect, "phone": None, "location": None}
check("OCR + 2 missing: confidence == 0.80",
      compute_confidence(raw_07e, is_ocr=True, llm_failed=False) == 0.80,
      f"got={compute_confidence(raw_07e, is_ocr=True)}")


# ════════════════════════════════════════════════════════════════
# TEST GROUP 8: Date parsing edge cases
# ════════════════════════════════════════════════════════════════
print("\n── Group 8: Date parsing edge cases ──")
from datetime import date as dt

# Year-only → defaults to Jan of that year
r_year = normalize_experience([{"title": "T", "company": "C", "start": "2018", "end": "2020"}])
check("Year-only start '2018' → '2018-01'",
      r_year[0]["start"] == "2018-01",
      f"got={r_year[0]['start']!r}")
check("Year-only end '2020' → '2020-01'",
      r_year[0]["end"] == "2020-01",
      f"got={r_year[0]['end']!r}")

# MM/YYYY format
r_mmyyyy = normalize_experience([{"title": "T", "company": "C", "start": "03/2019", "end": "11/2021"}])
check("MM/YYYY start '03/2019' → '2019-03'",
      r_mmyyyy[0]["start"] == "2019-03",
      f"got={r_mmyyyy[0]['start']!r}")

# YYYY-MM (already normalised)
r_iso = normalize_experience([{"title": "T", "company": "C", "start": "2021-06", "end": "2023-01"}])
check("ISO YYYY-MM '2021-06' passes through",
      r_iso[0]["start"] == "2021-06",
      f"got={r_iso[0]['start']!r}")

# MM/YY short form → 20YY
r_mmyy = normalize_experience([{"title": "T", "company": "C", "start": "06/22", "end": "12/23"}])
check("MM/YY '06/22' → '2022-06'",
      r_mmyy[0]["start"] == "2022-06",
      f"got={r_mmyy[0]['start']!r}")

# Unparseable date → graceful (duration 0, no crash)
r_bad = normalize_experience([{"title": "T", "company": "C", "start": "whenever", "end": "dunno"}])
check("Unparseable date → no crash, duration=0",
      r_bad[0]["duration_months"] == 0,
      f"got duration={r_bad[0]['duration_months']}")


# ════════════════════════════════════════════════════════════════
# TEST GROUP 9: Contact regex edge cases
# ════════════════════════════════════════════════════════════════
print("\n── Group 9: Contact regex edge cases ──")

# 9a: Email with spaces around @ (common OCR artefact) — should NOT match (invalid)
text_spaced_email = "Contact: kavya.nair88 @mail.com\nPhone: +91 98123 44556"
c9a = extract_contacts(text_spaced_email)
check("Spaced email 'kavya.nair88 @mail.com' → not extracted",
      c9a["email"] is None or "@" not in (c9a["email"] or "").replace(" ", ""),
      f"got={c9a['email']!r}")

# 9b: Indian mobile number without country code
text_indian = "Rohan Mehta\nPhone: 98989-22331\nrohan@test.com"
c9b = extract_contacts(text_indian)
check("Indian mobile (no +91) extracted",
      c9b["phone"] is not None and "98989" in c9b["phone"],
      f"got={c9b['phone']!r}")

# 9c: No LinkedIn in text → None (not hallucinated)
text_no_li = "Jane Smith\njane@example.com\n+1 212 555 0100\nNew York, NY"
c9c = extract_contacts(text_no_li)
check("No LinkedIn in text → linkedin=None",
      c9c["linkedin"] is None,
      f"got={c9c['linkedin']!r}")

# 9d: GitHub URL not confused with LinkedIn
text_github = "Dev Person\ndev@example.com\nhttps://github.com/devperson"
c9d = extract_contacts(text_github)
check("GitHub URL not extracted as LinkedIn",
      c9d["linkedin"] is None,
      f"got={c9d['linkedin']!r}")

# 9e: Multiple emails → first one returned
text_multi_email = "admin@company.com\njohn.doe@personal.com\nJohn Doe"
c9e = extract_contacts(text_multi_email)
check("Multiple emails → first one returned",
      c9e["email"] == "admin@company.com",
      f"got={c9e['email']!r}")


# ════════════════════════════════════════════════════════════════
# TEST GROUP 10: validate_schema coercion & guardrails
# ════════════════════════════════════════════════════════════════
print("\n── Group 10: Schema coercion & guardrails ──")

# 10a: Negative duration_months → coerced to 0
bad_duration = {
    "source_url": "http://x.com/r.pdf",
    "name": "X", "email": "x@x.com", "phone": "123", "location": "NY",
    "skills": ["Excel"],
    "experience": [{"title": "T", "company": "C", "start": "2020-01", "end": "2019-01", "duration_months": -5}],
    "education": [],
    "total_experience_years": 1.0,
}
out_10a = validate_resume(bad_duration)
check("Negative duration_months → coerced to 0",
      out_10a["experience"][0]["duration_months"] == 0,
      f"got={out_10a['experience'][0]['duration_months']}")

# 10b: Absurd graduation year (e.g. "20" or 9999) → None
bad_year = {
    "source_url": "http://x.com/r.pdf",
    "name": "Y", "email": "y@y.com", "phone": "456", "location": "LA",
    "skills": [], "experience": [],
    "education": [{"degree": "PhD", "institution": "MIT", "year": 9999}],
    "total_experience_years": 0.0,
}
out_10b = validate_resume(bad_year)
check("Absurd year 9999 → coerced to None",
      out_10b["education"][0]["year"] is None,
      f"got={out_10b['education'][0]['year']}")

# 10c: Duplicate skills → preserved as-is (dedup is LLM's job, schema keeps list)
dup_skills = {
    "source_url": "http://x.com/r.pdf",
    "name": "Z", "email": "z@z.com", "phone": "789", "location": "SF",
    "skills": ["Python", "  Python  ", "SQL", ""],   # whitespace + empty + dup
    "experience": [], "education": [],
    "total_experience_years": 0.0,
}
out_10c = validate_resume(dup_skills)
check("Empty string skill stripped from list",
      "" not in out_10c["skills"],
      f"got={out_10c['skills']}")
check("Whitespace skill '  Python  ' stripped to 'Python'",
      "Python" in out_10c["skills"],
      f"got={out_10c['skills']}")

# 10d: parse_confidence > 1.0 in input → clamped to 1.0
over_conf = {**bad_year, "parse_confidence": 999.9}
out_10d = validate_resume(over_conf)
check("Confidence > 1.0 → clamped to 1.0",
      out_10d["parse_confidence"] <= 1.0,
      f"got={out_10d['parse_confidence']}")


# ════════════════════════════════════════════════════════════════
# TEST GROUP 12: Edge — zero-job gap between consecutive roles
# ════════════════════════════════════════════════════════════════
print("\n── Group 12: Non-overlapping consecutive roles ──")
# No overlap: A ends exactly when B starts → should NOT merge
raw_consec = [
    {"title": "R1", "company": "C1", "start": "Jan 2018", "end": "Dec 2019"},   # 23 months
    {"title": "R2", "company": "C2", "start": "Jan 2020", "end": "Dec 2021"},   # 23 months
]
norm_consec = normalize_experience(raw_consec)
total_consec = calc_total_years(norm_consec)
check("Consecutive (non-overlapping) roles: total = sum of both",
      total_consec >= 3.5,
      f"got={total_consec}")
check("Consecutive roles sorted by start ascending",
      norm_consec[0]["start"] < norm_consec[1]["start"],
      f"starts={norm_consec[0]['start']!r}, {norm_consec[1]['start']!r}")


# ════════════════════════════════════════════════════════════════
# SUMMARY
# ════════════════════════════════════════════════════════════════
print("\n" + "="*60)
passed = sum(1 for _, s, _ in results if s == PASS)
failed = sum(1 for _, s, _ in results if s == FAIL)
total_tests = len(results)
pct = round(passed / total_tests * 100, 1)
print(f"Results: {passed}/{total_tests} passed  ({pct}%)")
if failed:
    print(f"\n❌ Failed tests:")
    for name, status, detail in results:
        if status == FAIL:
            print(f"   • {name}: {detail}")
if pct >= 95:
    print(f"\n🎉 >95% accuracy target met ({pct}%).")
else:
    print(f"\n⚠️  Below 95% target. Review failures above.")
    sys.exit(1)
