import json
from typing import Dict, Any, List, Tuple

REDIRECT_THRESHOLD = 1
NOVELTY_DAYS = 7
NAME_FLOOR = 0.5
COVERAGE_FLOOR = 50
AUTO_APPROVAL_LIMIT_PAISE = 1000000

def compute_risk_score(risk_signals: Dict[str, Any], contradiction_results: List[Dict[str, Any]]) -> float:
    """
    Task 10: Deterministic weighted risk score (0-100).
    """
    total = 0.0

    # Name mismatch (max 10 points)
    name_score = risk_signals.get("name_similarity_score")
    if name_score is not None:
        total += 10.0 * (1.0 - float(name_score))

    # Redirect velocity (max 20 points)
    redirect_count = risk_signals.get("redirect_count_30d")
    if redirect_count is not None and redirect_count > REDIRECT_THRESHOLD:
        total += 20.0

    # Destination novelty (max 15 points)
    age_days = risk_signals.get("destination_age_days")
    if age_days is not None and age_days < NOVELTY_DAYS:
        total += 15.0

    # Contradictions (cap 80 points)
    contradiction_total = 0.0
    for check in contradiction_results:
        if check.get("status") == "CONTRADICTED":
            sev = check.get("severity", "LOW").upper()
            if sev == "HIGH":
                contradiction_total += 40.0
            elif sev == "MEDIUM":
                contradiction_total += 20.0
            else:
                contradiction_total += 10.0
    
    total += min(80.0, contradiction_total)

    # LLM Flags (max 30 points)
    flags = risk_signals.get("message_risk_flags", {})
    if isinstance(flags, str):
        try:
            flags = json.loads(flags)
        except json.JSONDecodeError:
            flags = {}

    if flags:
        llm_total = 0.0
        # Check actual schema keys or shorthand from instructions
        if flags.get("urgency_language") or flags.get("urgency"):
            llm_total += 15.0
        if flags.get("third_party_destination") or flags.get("third_party"):
            llm_total += 15.0
            
        total += min(30.0, llm_total)

    return float(min(100.0, max(0.0, total)))

def evaluate_policy(
    risk_score: float,
    evidence_coverage: float,
    contradiction_results: List[Dict[str, Any]],
    message_risk_flags: Dict[str, Any],
    amount_paise: int,
    known_destination: bool,
    amount_matches_original: bool,
    risk_signals: Dict[str, Any]
) -> Tuple[str, List[str]]:
    """
    Task 10: Deterministic policy engine.
    """
    reasons = []

    if isinstance(message_risk_flags, str):
        try:
            message_risk_flags = json.loads(message_risk_flags)
        except json.JSONDecodeError:
            message_risk_flags = {}

    name_score = risk_signals.get("name_similarity_score")
    redirect_count = risk_signals.get("redirect_count_30d")
    ownership = risk_signals.get("ownership_signal")
    age_days = risk_signals.get("destination_age_days")
    prior_uses = risk_signals.get("destination_prior_uses")

    # 1. Collect Reasons
    if ownership == "UNAVAILABLE":
        reasons.append("OWNERSHIP_UNAVAILABLE")
    elif ownership == "MISMATCH_SYNTHETIC":
        reasons.append("OWNERSHIP_MISMATCH")

    is_novel = False
    if age_days is not None and age_days < NOVELTY_DAYS:
        reasons.append("NEW_DESTINATION")
        is_novel = True

    if prior_uses == 0 or not known_destination:
        reasons.append("ZERO_PRIOR_USAGE")
    elif known_destination:
        reasons.append("KNOWN_DESTINATION")

    if any(c.get("status") == "CONTRADICTED" for c in contradiction_results):
        reasons.append("CLAIM_CONTRADICTED")

    if evidence_coverage < COVERAGE_FLOOR:
        reasons.append("INSUFFICIENT_EVIDENCE")
    else:
        reasons.append("EVIDENCE_SUFFICIENT")

    if not amount_matches_original:
        reasons.append("AMOUNT_MISMATCH")
    else:
        reasons.append("AMOUNT_MATCH")

    if redirect_count is not None and redirect_count > REDIRECT_THRESHOLD:
        reasons.append("REDIRECT_VELOCITY_HIGH")

    # Non-empty message_risk_flags means any True value
    has_flags = any(val is True for val in message_risk_flags.values())
    if has_flags:
        reasons.append("LLM_MESSAGE_RISK")

    if amount_paise > AUTO_APPROVAL_LIMIT_PAISE:
        reasons.append("OVER_AUTO_APPROVAL_LIMIT")

    if name_score is not None and name_score < NAME_FLOOR:
        reasons.append("NAME_MISMATCH_BELOW_FLOOR")

    # 2. TIER 1 - REJECT
    is_reject = (
        risk_score >= 71 or
        (name_score is not None and name_score < NAME_FLOOR) or
        (redirect_count is not None and redirect_count > REDIRECT_THRESHOLD)
    )
    if is_reject:
        return "REJECT", reasons

    # 3. TIER 2 - REVIEW
    is_review = (
        amount_paise > AUTO_APPROVAL_LIMIT_PAISE or
        evidence_coverage < COVERAGE_FLOOR or
        has_flags or
        is_novel or
        amount_matches_original is False or
        risk_score >= 31
    )
    if is_review:
        return "REVIEW", reasons

    # 4. TIER 3 - APPROVE
    can_approve = (
        risk_score <= 30 and
        known_destination is True and
        amount_matches_original is True and
        amount_paise <= AUTO_APPROVAL_LIMIT_PAISE and
        evidence_coverage >= COVERAGE_FLOOR and
        not has_flags and
        not is_reject
    )
    
    if can_approve:
        return "APPROVE", reasons
    
    # Safe fallback
    return "REVIEW", reasons
