"""
map_sections.py
Layer 3 — The only LLM step: maps messy skills / experience / education sections
to JSON. Contacts, dates, durations and confidence are handled deterministically
elsewhere.

Usage:
    from execution.map_sections import make_client, llm_extract_sections
    client, model = make_client("gpt-4o-mini")  # or make_client(model, user_api_key)
    data, llm_failed = await llm_extract_sections(text, client, model)
"""

import json
import logging
import os
import textwrap
from typing import Optional

from openai import AsyncOpenAI

log = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def make_client(model: str, api_key: Optional[str] = None) -> tuple[Optional[AsyncOpenAI], str]:
    """
    Build the LLM client. A key passed in (the user's own, from actor input) wins;
    otherwise fall back to the owner's env vars, OPENROUTER_API_KEY before OPENAI_API_KEY.
    OpenRouter keys start with "sk-or-"; OpenRouter model ids are vendor-prefixed,
    so "gpt-4o-mini" → "openai/gpt-4o-mini".
    Returns (None, model) if no key is available.
    """
    key = (api_key or "").strip()
    if not key:
        key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""
    if not key:
        return None, model
    if key.startswith("sk-or-"):
        client = AsyncOpenAI(api_key=key, base_url=OPENROUTER_BASE_URL)
        return client, model if "/" in model else f"openai/{model}"
    return AsyncOpenAI(api_key=key), model


# ── LLM section mapper ────────────────────────────────────────────────────────

LLM_PROMPT = textwrap.dedent("""
You are a resume parser. Given raw resume text, extract ONLY the following three sections.
Return VALID JSON only — no explanation, no markdown fences.

Output format:
{
  "skills": ["skill1", "skill2"],
  "experience": [
    {"title": "Job Title", "company": "Company Name", "start": "Mon YYYY", "end": "Mon YYYY or Present"}
  ],
  "education": [
    {"degree": "Degree Name", "institution": "Institution Name", "year": 2020}
  ]
}

Rules:
- skills: flat list of technical and soft skills only. No duplicates.
- experience: include ALL roles in chronological order. Use "Present" if still employed.
- education: include ALL degrees. Set year to graduation year (integer) or null if unknown.
- If a section is absent, return an empty array [].
- Do NOT invent data. If unsure, omit.
- Preserve non-English names/company names as-is (Unicode OK).

Resume text:
\"\"\"
{resume_text}
\"\"\"
""").strip()


async def llm_extract_sections(
    text: str,
    client: AsyncOpenAI,
    model: str,
) -> tuple[dict, bool]:
    """
    Call LLM to extract skills, experience, education blocks.
    Returns (parsed_dict, llm_failed: bool).
    """
    # Truncate to ~12k tokens worth of text to stay within context limits
    truncated = text[:12000]

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": LLM_PROMPT.replace("{resume_text}", truncated)}],
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=2000,
        )
        raw_json = response.choices[0].message.content
        parsed = json.loads(raw_json)
        return parsed, False
    except Exception as e:
        log.warning(f"LLM extraction failed: {e}")
        return {"skills": [], "experience": [], "education": []}, True
