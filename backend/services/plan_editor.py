"""Natural-language plan editing via LLM."""

from __future__ import annotations

import json
import logging
import re
import sys
import pathlib

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import OPENAI_API_KEY  # noqa: E402

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a fitness plan editor. Given a 7-day JSON plan and an edit command, "
    "return the modified plan as valid JSON only, same structure, no explanation."
)


def edit_plan(current_plan: list, command: str) -> list:
    """
    Apply a natural-language edit command to a 7-day plan via LLM.
    Returns the updated plan list, or the original on parse failure.
    """
    from openai import OpenAI

    client = OpenAI(api_key=OPENAI_API_KEY)
    plan_json = json.dumps(current_plan, ensure_ascii=False)

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": f"Plan:\n{plan_json}\n\nEdit command: {command}"},
            ],
            temperature=0.2,
        )
        content = response.choices[0].message.content.strip()

        # Strip markdown code fences if present
        content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.MULTILINE)
        content = re.sub(r"\s*```$", "", content, flags=re.MULTILINE).strip()

        return json.loads(content)
    except json.JSONDecodeError as exc:
        logger.error("LLM returned non-JSON for edit command %r: %s\nContent: %s", command, exc, content)
        return current_plan
    except Exception as exc:
        logger.error("LLM API call failed for edit command %r: %s", command, exc)
        return current_plan
