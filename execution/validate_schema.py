"""
validate_schema.py
Layer 3 — Pydantic schema validation and confidence scoring for parsed resume output.

Usage:
    from execution.validate_schema import validate_resume, ResumeOutput

Input: raw dict assembled by the orchestrator (execution/parse_pipeline.py).
Output: validated ResumeOutput dict with parse_confidence clamped to [0.0, 1.0].
"""

from __future__ import annotations


import sys
import json
from typing import Optional
from pydantic import BaseModel, field_validator, model_validator


# ── Pydantic Models ───────────────────────────────────────────────────────────

class ExperienceEntry(BaseModel):
    title: Optional[str] = None
    company: Optional[str] = None
    start: Optional[str] = None       # YYYY-MM format
    end: Optional[str] = None         # YYYY-MM or null
    duration_months: int = 0

    @field_validator("duration_months", mode="before")
    @classmethod
    def coerce_duration(cls, v):
        try:
            return max(0, int(v))
        except (TypeError, ValueError):
            return 0


class EducationEntry(BaseModel):
    degree: Optional[str] = None
    institution: Optional[str] = None
    year: Optional[int] = None

    @field_validator("year", mode="before")
    @classmethod
    def coerce_year(cls, v):
        if v is None:
            return None
        try:
            y = int(str(v)[:4])
            return y if 1900 <= y <= 2100 else None
        except (TypeError, ValueError):
            return None


class ResumeOutput(BaseModel):
    source_url: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    linkedin: Optional[str] = None
    skills: list[str] = []
    experience: list[ExperienceEntry] = []
    education: list[EducationEntry] = []
    total_experience_years: float = 0.0
    parse_confidence: float = 1.0
    error: Optional[str] = None

    @field_validator("skills", mode="before")
    @classmethod
    def coerce_skills(cls, v):
        if not isinstance(v, list):
            return []
        return [str(s).strip() for s in v if s and str(s).strip()]

    @field_validator("total_experience_years", mode="before")
    @classmethod
    def coerce_years(cls, v):
        try:
            return max(0.0, round(float(v), 1))
        except (TypeError, ValueError):
            return 0.0

    @field_validator("parse_confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, v):
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return 0.5

    @model_validator(mode="after")
    def strip_strings(self):
        for field in ("name", "email", "phone", "location", "linkedin", "source_url"):
            val = getattr(self, field)
            if val is not None:
                setattr(self, field, val.strip() or None)
        return self


# ── Confidence scoring ────────────────────────────────────────────────────────

def compute_confidence(
    raw: dict,
    is_ocr: bool = False,
    llm_failed: bool = False,
) -> float:
    """
    Deterministic confidence formula (from directive):
        base 1.0
        − 0.05 × missing required contact fields (name, email, phone, location)
        − 0.10  if OCR was used
        − 0.15  if LLM JSON parsing failed
        − 0.10  if no experience found (skipped for freshers who have education)
        − 0.05  if no education found
        clamped to [0.0, 1.0]
    """
    score = 1.0

    # Missing required contact fields
    required_contact = ["name", "email", "phone", "location"]
    for field in required_contact:
        if not raw.get(field):
            score -= 0.05

    # OCR penalty
    if is_ocr:
        score -= 0.10

    # LLM failure penalty
    if llm_failed:
        score -= 0.15

    # Missing sections
    if not raw.get("experience") and not raw.get("education"):
        score -= 0.10
    if not raw.get("education"):
        score -= 0.05

    return max(0.0, min(1.0, round(score, 2)))


# ── Main validator ────────────────────────────────────────────────────────────

def validate_resume(
    raw: dict,
    is_ocr: bool = False,
    llm_failed: bool = False,
) -> dict:
    """
    Validate and clean a raw resume dict.
    Returns a fully-typed, serializable dict matching the output schema.
    """
    # Compute confidence before validation modifies values
    confidence = compute_confidence(raw, is_ocr=is_ocr, llm_failed=llm_failed)
    raw["parse_confidence"] = confidence

    try:
        model = ResumeOutput(**raw)
        return model.model_dump()
    except Exception as e:
        # Last-resort fallback: return minimal valid output
        return ResumeOutput(
            source_url=raw.get("source_url"),
            error=f"Schema validation failed: {e}",
            parse_confidence=0.0,
        ).model_dump()


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    """
    Expects JSON on stdin or as a file path argument.
    Flags: --ocr (if OCR was used), --llm-failed (if LLM parsing failed)
    """
    import argparse
    import pathlib

    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?", help="JSON file path (or stdin)")
    ap.add_argument("--ocr", action="store_true")
    ap.add_argument("--llm-failed", action="store_true")
    args = ap.parse_args()

    if args.file:
        raw = json.loads(pathlib.Path(args.file).read_text())
    else:
        raw = json.loads(sys.stdin.read())

    result = validate_resume(raw, is_ocr=args.ocr, llm_failed=args.llm_failed)
    print(json.dumps(result, indent=2, ensure_ascii=False))
