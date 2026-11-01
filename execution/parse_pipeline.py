"""
parse_pipeline.py
Layer 3 — Full resume parse for one file/URL, shared by the Resume Parser and
JD Match Scorer actors.

Usage:
    from execution.parse_pipeline import parse_resume
    record = await parse_resume(url, client, model)   # validated output dict

The returned dict also carries the raw text under "_text" for callers that need
it (e.g. skill matching); actors strip it before pushing.
"""

import asyncio

from execution.extract_text import extract_text
from execution.extract_contacts import extract_contacts
from execution.calc_experience import normalize_experience, calc_total_years
from execution.validate_schema import validate_resume
from execution.map_sections import llm_extract_sections


async def parse_resume(source: str, client, model: str) -> dict:
    # Step 1: Extract text (deterministic)
    extraction = await asyncio.to_thread(extract_text, source)
    raw_text = extraction.get("text", "")
    is_ocr = extraction.get("method") == "ocr"

    if not raw_text:
        out = validate_resume(
            {"source_url": source, "error": extraction.get("error") or "Empty text extracted"},
            is_ocr=is_ocr,
            llm_failed=False,
        )
        out["_text"] = ""
        return out

    # Step 2: Contact extraction (deterministic regex)
    contacts = extract_contacts(raw_text)

    # Step 3: LLM section mapping (only for skills/experience/education)
    llm_data, llm_failed = await llm_extract_sections(raw_text, client, model)

    # Step 4: Normalize experience dates + calculate durations (deterministic)
    normalized_exp = normalize_experience(llm_data.get("experience") or [])

    # Step 5: Validate schema + compute confidence (deterministic)
    out = validate_resume({
        "source_url": source,
        **contacts,
        "skills": llm_data.get("skills") or [],
        "experience": normalized_exp,
        "education": llm_data.get("education") or [],
        "total_experience_years": calc_total_years(normalized_exp),
    }, is_ocr=is_ocr, llm_failed=llm_failed)
    out["_text"] = raw_text
    return out
