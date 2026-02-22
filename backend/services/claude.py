import json
import logging

from anthropic import Anthropic

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a computational biology research assistant. You are generating a drug "
    "repurposing report for researchers. Be scientifically precise but write in clear "
    "language. For each drug candidate, explain the biological mechanism connecting the "
    "drug to the target. Reference specific pathways and protein functions.\n\n"
    "IMPORTANT: You are given molecular docking scores (binding confidence, 0-1), "
    "ADMET safety profiles (absorption, distribution, metabolism, excretion, toxicity, "
    "drug-likeness), and when available, GNN-predicted binding affinity (pKd and Kd in nM).\n\n"
    "- Prioritize compounds with high binding confidence, strong predicted affinity, "
    "AND good safety profiles.\n"
    "- When binding affinity is available, discuss it: lower Kd (nM) means tighter binding. "
    "pKd > 7 is strong, 5-7 moderate, < 5 weak.\n"
    "- For compounds that bind well but have safety concerns, explicitly call this out, e.g.: "
    "\"Compound X shows strong binding (0.87) and tight affinity (Kd=45 nM) but is flagged "
    "for toxicity concern — monitor for adverse effects if repurposed.\"\n"
    "- For compounds that are very safe but bind weakly, note this too, e.g.: "
    "\"Compound Y has an excellent safety profile but low binding confidence (0.34) — "
    "unlikely to be effective.\"\n"
    "- The final ranking should weight binding, affinity, AND safety together.\n\n"
    "Include appropriate caveats that this is computational prediction requiring "
    "experimental validation."
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
        admet = r.get("admet") or {}
        admet_overall = admet.get("overall_score", "N/A")
        admet_pf = admet.get("pass_fail", "N/A")
        admet_flags = ", ".join(admet.get("flags", [])) or "None"
        combined = r.get("combined_score", "N/A")
        pkd = r.get("predicted_pkd")
        kd_nm = r.get("predicted_kd_nm")
        affinity_score = r.get("affinity_score")

        affinity_line = ""
        if pkd is not None:
            affinity_line = f"   - GNN predicted affinity: pKd={pkd}, Kd={kd_nm} nM (score={affinity_score})\n"

        has_affinity = affinity_score is not None
        score_formula = "binding 35% + affinity 30% + safety 35%" if has_affinity else "binding 60% + safety 40%"

        drugs_section += (
            f"{i}. **{name}** (SMILES: {r['smiles'][:60]}...)\n"
            f"   - Binding confidence: {score}\n"
            f"{affinity_line}"
            f"   - Mechanism: {mech}\n"
            f"   - Clinical stage: {phase_str}\n"
            f"   - ADMET overall: {admet_overall} ({admet_pf})\n"
            f"   - ADMET flags: {admet_flags}\n"
            f"   - Absorption: {admet.get('absorption', 'N/A')}, "
            f"Distribution: {admet.get('distribution', 'N/A')}, "
            f"Metabolism: {admet.get('metabolism', 'N/A')}, "
            f"Excretion: {admet.get('excretion', 'N/A')}, "
            f"Toxicity: {admet.get('toxicity', 'N/A')}, "
            f"Drug-likeness: {admet.get('drug_likeness', 'N/A')}\n"
            f"   - Combined score ({score_formula}): {combined}\n\n"
        )

    return (
        f"Generate a drug repurposing report for **{disease}**.\n\n"
        f"## Target Protein\n"
        f"- Symbol: {target['symbol']}\n"
        f"- Name: {target['name']}\n\n"
        f"## Candidates (ranked by combined binding + affinity + safety score)\n\n"
        f"{drugs_section}"
        f"For each candidate (up to 5), provide:\n"
        f"1. A 2-3 sentence mechanistic explanation of why this drug might work\n"
        f"2. Assessment of binding confidence, predicted affinity (if available), AND safety profile\n"
        f"3. Any known research or clinical trials related to this repurposing\n"
        f"4. A risk/benefit summary that accounts for ADMET flags\n\n"
        f"Specifically:\n"
        f"- If a compound binds well but has safety flags, call it out explicitly\n"
        f"- If a compound is safe but binds weakly, note it is unlikely to be effective\n"
        f"- Your final ranking should reflect the combined score weighting\n\n"
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
