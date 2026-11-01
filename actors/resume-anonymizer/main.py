"""
actors/resume-anonymizer/main.py
Apify Actor entrypoint — Resume Anonymizer (blind screening). No LLM.

Architecture:
  Layer 1 (Directive):    directives/anonymize_resume.md
  Layer 2 (Orchestrator): This file. Extracts text, redacts PII, pushes one row per
                           resume, and stores the candidate_id → identity map privately.
  Layer 3 (Execution):    execution/extract_text.py, execution/redact_pii.py
"""

import sys
import asyncio
import hashlib
from pathlib import Path

# Ensure execution/ is importable (this file lives at actors/<name>/main.py)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from apify import Actor

from execution.extract_text import extract_text
from execution.extract_contacts import extract_contacts
from execution.redact_pii import redact_resume_text


def anonymize(url: str) -> tuple[dict, dict]:
    """Returns (dataset row, identity record for the private map)."""
    extraction = extract_text(url)
    text = extraction.get("text", "")
    contacts = extract_contacts(text) if text else {}
    candidate_id = hashlib.sha256((contacts.get("email") or url).encode()).hexdigest()[:12]

    if not text:
        row = {"candidate_id": candidate_id, "redacted_text": "", "redactions": {},
               "error": extraction.get("error") or "Empty text extracted"}
    else:
        redacted, counts = redact_resume_text(text, contacts)
        row = {"candidate_id": candidate_id, "redacted_text": redacted, "redactions": counts,
               "error": None}
    identity = {"source_url": url, "name": contacts.get("name"), "email": contacts.get("email"),
                "phone": contacts.get("phone")}
    return row, identity


async def main():
    async with Actor:
        actor_input = await Actor.get_input() or {}
        urls: list[str] = actor_input.get("urls", [])
        if not urls:
            Actor.log.error("No URLs provided in input.")
            return

        results = await asyncio.gather(*(asyncio.to_thread(anonymize, u) for u in urls),
                                       return_exceptions=True)
        identity_map = {}
        for url, result in zip(urls, results):
            if isinstance(result, Exception):
                row = {"candidate_id": hashlib.sha256(url.encode()).hexdigest()[:12],
                       "redacted_text": "", "redactions": {}, "error": str(result)}
                identity = {"source_url": url}
            else:
                row, identity = result
            identity_map[row["candidate_id"]] = identity
            await Actor.push_data(row)

        # Kept out of the dataset so reviewers only see anonymized rows
        await Actor.set_value("CANDIDATE_MAP", identity_map)
        Actor.log.info(f"Done. Anonymized {len(urls)} resume(s); identity map in key-value store CANDIDATE_MAP.")


if __name__ == "__main__":
    asyncio.run(main())
