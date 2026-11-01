"""
actors/jd-match-scorer/main.py
Apify Actor entrypoint — JD ↔ Resume Match Scorer

Architecture:
  Layer 1 (Directive):    directives/match_resume_jd.md
  Layer 2 (Orchestrator): This file. Parses the JD once, parses every resume,
                           scores and ranks them, pushes one row per resume.
  Layer 3 (Execution):    execution/map_jd.py (LLM: JD → requirements),
                           execution/parse_pipeline.py (resume parse),
                           execution/score_match.py (deterministic scoring)
"""

import sys
import asyncio
from pathlib import Path

# Ensure execution/ is importable (this file lives at actors/<name>/main.py)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from apify import Actor

from execution.map_sections import make_client
from execution.map_jd import llm_extract_jd
from execution.parse_pipeline import parse_resume
from execution.score_match import score_candidate


async def main():
    async with Actor:
        actor_input = await Actor.get_input() or {}

        jd_text: str = (actor_input.get("job_description") or "").strip()
        urls: list[str] = actor_input.get("resume_urls", [])
        model: str = actor_input.get("llm_model", "gpt-4o-mini")
        max_concurrency: int = int(actor_input.get("max_concurrency", 5))

        if not jd_text or not urls:
            Actor.log.error("Both job_description and resume_urls are required.")
            return

        client, model = make_client(model, actor_input.get("llm_api_key"))
        if client is None:
            Actor.log.error("No LLM key: add your own in the 'llm_api_key' input, or the owner must set OPENROUTER_API_KEY / OPENAI_API_KEY.")
            return

        jd, jd_failed = await llm_extract_jd(jd_text, client, model)
        if jd_failed or not jd["required_skills"]:
            Actor.log.error("Could not extract requirements from the job description.")
            return
        Actor.log.info(f"JD requirements: {jd}")
        await Actor.set_value("JD_REQUIREMENTS", jd)

        semaphore = asyncio.Semaphore(max_concurrency)

        async def run_one(url: str) -> dict:
            async with semaphore:
                Actor.log.info(f"Scoring: {url}")
                resume = await parse_resume(url, client, model)
            row = {
                "source_url": url,
                "name": resume.get("name"),
                "email": resume.get("email"),
                "phone": resume.get("phone"),
                "job_title": jd["job_title"],
                **score_candidate(resume, jd, resume.get("_text", "")),
                "parse_confidence": resume.get("parse_confidence"),
                "error": resume.get("error"),
            }
            if resume.get("error"):
                row["match_score"] = 0
            return row

        results = await asyncio.gather(*(run_one(u) for u in urls), return_exceptions=True)
        rows = [
            r if not isinstance(r, Exception)
            else {"source_url": u, "match_score": 0, "error": str(r)}
            for u, r in zip(urls, results)
        ]
        rows.sort(key=lambda r: -r["match_score"])
        for rank, row in enumerate(rows, start=1):
            await Actor.push_data({"rank": rank, **row})

        Actor.log.info(f"Done. Ranked {len(rows)} resume(s).")


if __name__ == "__main__":
    asyncio.run(main())
