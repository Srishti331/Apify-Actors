"""
extract_contacts.py
Layer 3 — Deterministic regex-based extraction of contact fields from resume text.

Usage:
    python execution/extract_contacts.py <text_file_path>
    OR: import and call extract_contacts(text: str) -> dict

Output:
    {
        "name": "string | null",
        "email": "string | null",
        "phone": "string | null",
        "location": "string | null",
        "linkedin": "string | null"
    }
"""

import re
import sys
import json
from pathlib import Path
from typing import Optional


# ── Regex patterns ────────────────────────────────────────────────────────────

EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE
)

# Phone patterns — tried in order, first valid match wins:
#   1. International with country code:  +91 98989-22331  /  +1 (650) 555-0192
#   2. Bare 10-digit mobile (India etc): 98989-22331  /  9898922331
#   3. Generic 7-15 digit fallback
PHONE_PATTERNS = [
    # +CC then number (most reliable — match as much as possible)
    re.compile(r"\+[\d]{1,3}[\s\-.]?(?:\(?\d{2,5}\)?[\s\-.]){1,3}\d{3,6}(?:[\s\-.]?\d{1,5})?"),
    # Bare 10-digit mobile (no country code) — common in India/Asia
    re.compile(r"\b\d{5}[\s\-.]?\d{5}\b"),
    # Generic: (area) number with separators
    re.compile(r"(?:\(?\d{2,4}\)?[\s\-.]){1,3}\d{3,5}(?:\s?(?:x|ext)\.?\s?\d{1,5})?"),
]

LINKEDIN_RE = re.compile(
    r"(?:https?://)?(?:www\.)?linkedin\.com/in/[\w\-%.]+",
    re.IGNORECASE
)

# Location heuristic: "City, State" or "City, Country" patterns
# (stays on one line; Latin-1, Latin Extended and Vietnamese letters allowed)
LOCATION_RE = re.compile(
    r"\b([A-Z][a-zA-Z\u00C0-\u024F\u1E00-\u1EFF \t\-]{1,30}),[ \t]*([A-Z]{2}|[A-Z][a-z]{2,20})\b"
)

# Patterns that indicate a line is NOT a name
NOT_NAME_RE = re.compile(
    r"@|http|www\.|linkedin|github|\.com|resume|curriculum|vitae|profile|\d{4}|"
    r"objective|summary|skills|experience|education|references",
    re.IGNORECASE
)


# ── Extractors ────────────────────────────────────────────────────────────────

def extract_email(text: str) -> Optional[str]:
    match = EMAIL_RE.search(text)
    return match.group(0).lower() if match else None


def find_phones(text: str) -> list[str]:
    """
    All phone-like matches using tiered patterns:
      1. International (+CC ...) — most reliable
      2. Bare 10-digit mobile (India/Asia: 98989-22331)
      3. Generic local formats
    Filters out year ranges. Sorted by digit count, most digits first.
    """
    candidates = []
    for pattern in PHONE_PATTERNS:
        for m in pattern.finditer(text):
            raw = m.group(0).strip()
            digits = re.sub(r"\D", "", raw)
            if not 7 <= len(digits) <= 15:
                continue
            # Skip date ranges like "2018-2020" or "2019 2021"
            groups = re.findall(r"\d+", raw)
            if all(len(g) == 4 and 1950 <= int(g) <= 2100 for g in groups):
                continue
            candidates.append((len(digits), raw))
    candidates.sort(key=lambda x: -x[0])
    return [raw for _, raw in candidates]


def extract_phone(text: str) -> Optional[str]:
    """Best phone match (most digits — international numbers win over short local)."""
    phones = find_phones(text)
    return phones[0] if phones else None


def extract_linkedin(text: str) -> Optional[str]:
    match = LINKEDIN_RE.search(text)
    if not match:
        return None
    url = match.group(0)
    if not url.startswith("http"):
        url = "https://" + url
    return url


def extract_location(text: str) -> Optional[str]:
    """
    Heuristic: 'City, ST' or 'City, Country' on a contact-style line — a short line
    (<= 40 chars) or one that also holds an email/phone/separator. Matches inside
    long prose lines ("Analyst at Grace Labs, Pune") are ignored; better null than wrong.
    Prefers the top of the document.
    """
    for line in text.splitlines():
        match = LOCATION_RE.search(line)
        if not match:
            continue
        stripped = line.strip()
        if len(stripped) <= 40 or re.search(r"[@|·•]", stripped) or find_phones(stripped):
            return match.group(0).strip()
    return None


def extract_name(text: str, email: Optional[str] = None) -> Optional[str]:
    """
    Heuristic: The name is typically the first non-empty line that:
      - Is not an email, phone, URL, or section header
      - Contains at least 2 words
      - Is under 50 characters
      - Preserves Unicode (for non-English names like 韩晓明)
    """
    lines = text.strip().splitlines()
    for line in lines[:15]:  # Check only first 15 lines
        line = line.strip()
        if not line:
            continue
        if NOT_NAME_RE.search(line):
            continue
        # Must have at least 2 'word' tokens (supports CJK too)
        words = line.split()
        if len(words) < 2 and not _is_cjk(line):
            continue
        if len(line) > 60:
            continue
        # Names don't contain digits (rules out phone/date lines)
        if sum(c.isdigit() for c in line) >= 3:
            continue
        # Avoid lines that are purely uppercase acronyms (e.g., "MBA", "B.TECH")
        if line.isupper() and len(line) < 10:
            continue
        # Don't return the email as a name
        if email and line.lower() == email.lower():
            continue
        return line
    return None


def _is_cjk(text: str) -> bool:
    """Returns True if text contains CJK (Chinese/Japanese/Korean) characters."""
    return any('\u4e00' <= c <= '\u9fff' or
               '\u3040' <= c <= '\u309f' or
               '\uac00' <= c <= '\ud7af'
               for c in text)


# ── Main function ─────────────────────────────────────────────────────────────

def extract_contacts(text: str) -> dict:
    email = extract_email(text)
    phone = extract_phone(text)
    linkedin = extract_linkedin(text)
    location = extract_location(text)
    name = extract_name(text, email=email)

    return {
        "name": name,
        "email": email,
        "phone": phone,
        "location": location,
        "linkedin": linkedin,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: python extract_contacts.py <text_file>"}))
        sys.exit(1)

    text = Path(sys.argv[1]).read_text(encoding="utf-8")
    result = extract_contacts(text)
    print(json.dumps(result, indent=2, ensure_ascii=False))
