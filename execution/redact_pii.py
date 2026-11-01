"""
redact_pii.py
Layer 3 — Deterministic PII redaction of resume text for blind screening.

Usage:
    python execution/redact_pii.py <file_path_or_url>
    OR: from execution.redact_pii import redact_resume_text
        redacted, counts = redact_resume_text(text)

Redacts: name, email, phone, URLs (LinkedIn/GitHub/portfolio), location, and
labelled personal details (DOB, gender, marital status, nationality, religion,
age, parents' names, photo).
"""

import re
import sys
import json
from typing import Optional

from execution.extract_contacts import extract_contacts, find_phones, EMAIL_RE

URL_RE = re.compile(r"(?:https?://|www\.)\S+|\b(?:linkedin\.com|github\.com)/\S+", re.IGNORECASE)

# "DOB: 01/02/1995", "Gender - Male", "Marital Status: Single" (also mid-line, e.g. "Age: 27 | Gender: F")
PERSONAL_LABELS = (
    r"date of birth|d\.?o\.?b\.?|birth ?date|gender|sex|marital status|nationality|religion|"
    r"caste|age|father'?s name|mother'?s name|spouse'?s? name|passport(?: no\.?| number)?|photo"
)
PERSONAL_RE = re.compile(
    r"\b(" + PERSONAL_LABELS + r")\s*[:\-–]\s*([^|\n·•;]*[^|\n·•;\s])",
    re.IGNORECASE,
)

TITLES = {"dr", "mr", "mrs", "ms", "miss", "prof", "phd", "md", "jr", "sr", "ii", "iii"}


def _sub(pattern, repl: str, text: str, counts: dict, key: str) -> str:
    text, n = pattern.subn(repl, text)
    counts[key] = counts.get(key, 0) + n
    return text


def _literal(value: str, flags=0):
    """Match a literal value without gluing onto neighbouring word characters."""
    return re.compile(r"(?<!\w)" + re.escape(value) + r"(?!\w)", flags)


def _name_tokens(name: str) -> list[str]:
    tokens = [t.strip(".,") for t in name.split()]
    return [t for t in tokens if len(t) >= 2 and t.lower().strip(".") not in TITLES]


def redact_resume_text(text: str, contacts: Optional[dict] = None) -> tuple[str, dict]:
    contacts = contacts or extract_contacts(text)
    counts: dict = {}

    text = _sub(PERSONAL_RE, lambda m: f"{m.group(1)}: [REDACTED]", text, counts, "personal_details")
    text = _sub(EMAIL_RE, "[EMAIL]", text, counts, "email")
    text = _sub(URL_RE, "[URL]", text, counts, "url")

    for phone in sorted(set(find_phones(text)), key=len, reverse=True):
        text = _sub(_literal(phone), "[PHONE]", text, counts, "phone")

    name = contacts.get("name")
    if name:
        text = _sub(_literal(name, re.IGNORECASE), "[NAME]", text, counts, "name")
        # Leftover first/last names, matched case-sensitively (as written or ALL CAPS)
        # so ordinary words that happen to be names ("Grace", "Hope") survive in prose
        for token in _name_tokens(name):
            for form in {token, token.upper()}:
                text = _sub(_literal(form), "[NAME]", text, counts, "name")

    location = contacts.get("location")
    if location:
        text = _sub(_literal(location, re.IGNORECASE), "[LOCATION]", text, counts, "location")
        city = location.split(",")[0].strip()
        if len(city) >= 3:
            text = _sub(_literal(city), "[LOCATION]", text, counts, "location")

    return text, {k: v for k, v in counts.items() if v}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: python execution/redact_pii.py <file_path_or_url>"}))
        sys.exit(1)

    from execution.extract_text import extract_text
    extraction = extract_text(sys.argv[1])
    redacted, counts = redact_resume_text(extraction["text"])
    print(json.dumps({"redacted_text": redacted, "redactions": counts}, indent=2, ensure_ascii=False))
