"""
calc_experience.py
Layer 3 — Deterministic date parsing, interval merging, and experience calculation.

Usage:
    import and call:
        normalize_experience(raw_list: list[dict]) -> list[dict]
        calc_total_years(experience: list[dict]) -> float

Input (raw_list): list of dicts from LLM with keys:
    { "title", "company", "start": "Jan 2020", "end": "Present" }

Output per entry:
    { "title", "company", "start": "2020-01", "end": null, "duration_months": int }

total_experience_years: float (merged intervals, no double-counting)
"""

import re
import sys
import json
from datetime import datetime, date
from typing import Optional
from dateutil import parser as dateutil_parser


# ── Constants ─────────────────────────────────────────────────────────────────

PRESENT_ALIASES = {
    "present", "current", "now", "till date", "to date",
    "ongoing", "today", "—", "-", "–", "currently"
}


# ── Date normalization ────────────────────────────────────────────────────────

def parse_date(raw: Optional[str]) -> Optional[date]:
    """
    Parse a messy date string into a date object.
    Handles: "Jan 2020", "2020", "01/2020", "2020-01", "03/20" (MM/YY), None.
    Returns the 1st of the parsed month.
    """
    if raw is None:
        return None

    raw = str(raw).strip()

    # Check for "present" aliases
    if raw.lower() in PRESENT_ALIASES or raw == "":
        return None  # caller treats None end as "present"

    # Try: MM/YY short form → 20YY-MM
    match_mmyy = re.fullmatch(r"(\d{1,2})/(\d{2})", raw)
    if match_mmyy:
        month, year_short = match_mmyy.groups()
        year = int(year_short) + 2000
        return date(year, int(month), 1)

    # Try: YYYY-MM or YYYY/MM
    match_ym = re.fullmatch(r"(\d{4})[-/](\d{1,2})", raw)
    if match_ym:
        year, month = match_ym.groups()
        return date(int(year), int(month), 1)

    # Try: MM/YYYY
    match_my = re.fullmatch(r"(\d{1,2})/(\d{4})", raw)
    if match_my:
        month, year = match_my.groups()
        return date(int(year), int(month), 1)

    # Year only → default to January
    match_year = re.fullmatch(r"(\d{4})", raw)
    if match_year:
        return date(int(raw), 1, 1)

    # Use dateutil for natural language: "Jan 2020", "January 2020", "2020 Jan"
    try:
        parsed = dateutil_parser.parse(raw, default=datetime(2000, 1, 1))
        return date(parsed.year, parsed.month, 1)
    except Exception:
        return None


def date_to_str(d: Optional[date]) -> Optional[str]:
    """Convert date to YYYY-MM string, or None."""
    if d is None:
        return None
    return d.strftime("%Y-%m")


def months_between(start: date, end: date) -> int:
    """Number of full months between two dates (inclusive of start month)."""
    return max(0, (end.year - start.year) * 12 + (end.month - start.month))


# ── Interval merging ──────────────────────────────────────────────────────────

def merge_intervals(intervals: list[tuple[date, date]]) -> list[tuple[date, date]]:
    """
    Classic interval union merge. Input: list of (start, end) date tuples.
    Returns sorted, non-overlapping merged intervals.
    """
    if not intervals:
        return []

    sorted_intervals = sorted(intervals, key=lambda x: x[0])
    merged = [sorted_intervals[0]]

    for current_start, current_end in sorted_intervals[1:]:
        last_start, last_end = merged[-1]
        if current_start <= last_end:
            # Overlapping or adjacent — extend the last interval
            merged[-1] = (last_start, max(last_end, current_end))
        else:
            merged.append((current_start, current_end))

    return merged


# ── Main functions ────────────────────────────────────────────────────────────

def normalize_experience(raw_list: list[dict]) -> list[dict]:
    """
    Normalizes raw LLM experience output:
    - Parses messy date strings
    - Resolves "Present" → None (in output) / today (for calculations)
    - Calculates duration_months per role
    - Sorts by start date ascending
    """
    today = date.today()
    normalized = []

    for entry in raw_list:
        title = (entry.get("title") or "").strip() or None
        company = (entry.get("company") or "").strip() or None
        raw_start = str(entry.get("start") or "")
        raw_end = str(entry.get("end") or "")

        start_date = parse_date(raw_start)
        is_present = raw_end.strip().lower() in PRESENT_ALIASES or raw_end.strip() == ""
        end_date = None if is_present else parse_date(raw_end)

        # Effective end for duration calculation
        effective_end = today if end_date is None else end_date

        if start_date is None:
            # Can't compute duration without a start date — include with 0 months
            duration = 0
        else:
            duration = months_between(start_date, effective_end)

        normalized.append({
            "title": title,
            "company": company,
            "start": date_to_str(start_date),
            "end": date_to_str(end_date),  # null if "Present"
            "duration_months": duration,
        })

    # Sort by start ascending (None starts go to the end)
    normalized.sort(key=lambda x: x["start"] or "9999-99")
    return normalized


def calc_total_years(experience: list[dict]) -> float:
    """
    Calculate total experience years using MERGED date intervals.
    This avoids double-counting overlapping or concurrent jobs.

    Input: list of normalized experience entries (with 'start', 'end' as YYYY-MM or null).
    """
    today = date.today()
    intervals = []

    for entry in experience:
        start_str = entry.get("start")
        end_str = entry.get("end")

        if not start_str:
            continue

        try:
            start = datetime.strptime(start_str, "%Y-%m").date()
        except ValueError:
            continue

        if end_str:
            try:
                end = datetime.strptime(end_str, "%Y-%m").date()
            except ValueError:
                end = today
        else:
            end = today  # "Present"

        intervals.append((start, end))

    merged = merge_intervals(intervals)
    total_months = sum(months_between(s, e) for s, e in merged)
    return round(total_months / 12, 1)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    """
    Expects JSON array on stdin or as a file argument.
    Example:
        echo '[{"title":"SWE","company":"Google","start":"Jan 2019","end":"Present"}]' | \
          python execution/calc_experience.py
    """
    if len(sys.argv) > 1:
        import pathlib
        raw = json.loads(pathlib.Path(sys.argv[1]).read_text())
    else:
        raw = json.loads(sys.stdin.read())

    normalized = normalize_experience(raw)
    total = calc_total_years(normalized)
    print(json.dumps({
        "experience": normalized,
        "total_experience_years": total
    }, indent=2, ensure_ascii=False))
