"""
actors/resume-parser/main.py
Apify Actor entrypoint — Resume Parser API

Architecture:
  Layer 1 (Directive):    directives/parse_resume.md
  Layer 2 (Orchestrator): This file. Reads input, runs the pipeline, pushes output.
  Layer 3 (Execution):    execution/parse_pipeline.py → extract_text, extract_contacts,
                           map_sections (the only LLM call), calc_experience, validate_schema
"""

import sys
import asyncio
from pathlib import Path

# Ensure execution/ is importable (this file lives at actors/<name>/main.py)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from apify import Actor

from execution.parse_pipeline import parse_resume
from execution.validate_schema import validate_resume
from execution.map_sections import make_client


async def main():
    async with Actor:
        actor_input = await Actor.get_input() or {}

        urls: list[str] = actor_input.get("urls", [])
        model: str = actor_input.get("llm_model", "gpt-4o-mini")
        max_concurrency: int = int(actor_input.get("max_concurrency", 5))

        if not urls:
            Actor.log.error("No URLs provided in input.")
            return

        client, model = make_client(model, actor_input.get("llm_api_key"))
        if client is None:
            Actor.log.error("No LLM key: add your own in the 'llm_api_key' input, or the owner must set OPENROUTER_API_KEY / OPENAI_API_KEY.")
            return

        Actor.log.info(f"Parsing {len(urls)} resume(s) with model={model}")
        semaphore = asyncio.Semaphore(max_concurrency)

        async def run_one(url: str) -> dict:
            async with semaphore:
                Actor.log.info(f"Processing: {url}")
                return await parse_resume(url, client, model)

        results = await asyncio.gather(*(run_one(u) for u in urls), return_exceptions=True)

        for url, result in zip(urls, results):
            if isinstance(result, Exception):
                result = validate_resume({"source_url": url, "error": str(result)})
            result.pop("_text", None)
            await Actor.push_data(result)

        Actor.log.info(f"Done. Pushed {len(results)} result(s).")


if __name__ == "__main__":
    asyncio.run(main())
