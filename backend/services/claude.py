import json
import logging

from anthropic import Anthropic

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a computational biology research assistant. You are generating a drug "
    "repurposing report for researchers. Be scientifically precise but write in clear "
    "language. For each drug candidate, explain the biological mechanism connecting the "
    "drug to the cancer target. Reference specific pathways and protein functions. End "
    "with a clear recommendation of which candidates are most promising and why. Include "
    "appropriate caveats that this is computational prediction requiring experimental "
    "validation."
)

MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 4000


def _build_user_prompt(disease: str, target: dict, results: list[dict]) -> str:
    drugs_section = ""
    for i, r in enumerate(results, 1):
        name = r.get("drug_name") or "Unknown"
        score = r.get("confidence_score", "N/A")
        mech = r.get("mechanism") or "Unknown mechanism"
        phase = r.get("max_phase")
        phase_str = f"Phase {phase}" if phase else "Unknown phase"
        drugs_section += (
            f"{i}. **{name}** (SMILES: {r['smiles'][:60]}...)\n"
            f"   - Confidence score: {score}\n"
            f"   - Mechanism: {mech}\n"
            f"   - Clinical stage: {phase_str}\n\n"
        )

    return (
        f"Generate a drug repurposing report for **{disease}**.\n\n"
        f"## Target Protein\n"
        f"- Symbol: {target['symbol']}\n"
        f"- Name: {target['name']}\n\n"
        f"## Docking Results (ranked by binding confidence)\n\n"
        f"{drugs_section}"
        f"For the top candidates (up to 5), provide:\n"
        f"1. A 2-3 sentence mechanistic explanation of why this drug might work\n"
        f"2. What the binding confidence score means in practical terms\n"
        f"3. Any known research or clinical trials related to this repurposing\n"
        f"4. A risk/benefit summary\n\n"
        f"End with a prioritized recommendation ranking.\n\n"
        f"IMPORTANT: After the markdown report, output a JSON block on its own line "
        f"starting with ```json and ending with ``` containing an array of objects "
        f"with keys: drug_name, explanation, risk_benefit, priority_rank (integer, "
        f"1 = most promising). Only include the top candidates you analyzed."
    )


def generate_report(
    api_key: str,
    disease: str,
    target: dict,
    results: list[dict],
) -> dict:
    """Generate an explainability report using Claude.

    Returns {"report_text": str, "candidates": [{"drug_name", "explanation", "risk_benefit", "priority_rank"}]}
    """
    client = Anthropic(api_key=api_key)

    message = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": _build_user_prompt(disease, target, results)},
        ],
    )

    full_text = message.content[0].text

    # Parse structured candidates from JSON block
    candidates = []
    if "```json" in full_text:
        try:
            json_str = full_text.split("```json")[1].split("```")[0].strip()
            candidates = json.loads(json_str)
        except (IndexError, json.JSONDecodeError) as e:
            logger.warning("Failed to parse candidates JSON: %s", e)
            # Retry: strip trailing commas and fix common JSON issues
            try:
                import re
                cleaned = re.sub(r',\s*([}\]])', r'\1', json_str)  # trailing commas
                cleaned = re.sub(r'[\x00-\x1f]', ' ', cleaned)     # control chars
                candidates = json.loads(cleaned)
            except Exception:
                logger.warning("Retry parse also failed, returning empty candidates")

    # Extract report text (everything before the JSON block)
    report_text = full_text.split("```json")[0].strip() if "```json" in full_text else full_text

    return {
        "report_text": report_text,
        "candidates": candidates,
    }
