import asyncio
import json
import logging

from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 200


def _build_prompt(drug_name: str, disease: str) -> str:
    return (
        f'Is the drug "{drug_name}" currently approved or in clinical trials '
        f"specifically for {disease}?\n"
        f'Reply with ONLY a JSON object: {{"status": "approved"|"in_trials"|"novel", '
        f'"detail": "one sentence explanation"}}\n'
        f'- "approved" = FDA/EMA approved for this disease\n'
        f'- "in_trials" = active or recent clinical trials for this disease\n'
        f'- "novel" = not known to be used or trialed for this disease'
    )


async def _check_single(
    client: AsyncAnthropic, drug_name: str, disease: str
) -> dict:
    try:
        message = await client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": _build_prompt(drug_name, disease)}],
        )
        text = message.content[0].text.strip()
        # Extract JSON from response (handle markdown code blocks)
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        result = json.loads(text)
        status = result.get("status", "unknown")
        if status not in ("approved", "in_trials", "novel"):
            status = "unknown"
        return {
            "novelty_status": status,
            "novelty_detail": result.get("detail", ""),
        }
    except Exception as e:
        logger.warning("Novelty check failed for %s: %s", drug_name, e)
        return {"novelty_status": "unknown", "novelty_detail": ""}


async def check_novelty_batch(
    api_key: str, disease: str, candidates: list[dict]
) -> list[dict]:
    """Check novelty for a batch of drug candidates concurrently.

    Args:
        api_key: Anthropic API key
        disease: Disease name
        candidates: List of {"drug_name": ..., "mechanism": ...}

    Returns:
        List of {"novelty_status": ..., "novelty_detail": ...}
    """
    client = AsyncAnthropic(api_key=api_key)
    tasks = [
        _check_single(client, c.get("drug_name") or "Unknown", disease)
        for c in candidates
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return [
        r if isinstance(r, dict) else {"novelty_status": "unknown", "novelty_detail": ""}
        for r in results
    ]
