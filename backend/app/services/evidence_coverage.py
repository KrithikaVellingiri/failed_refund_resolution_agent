from typing import Dict, Any, List

def calculate_evidence_coverage(evidence_bundle: Dict[str, Any], claim_checks: List[Dict[str, Any]]) -> float:
    """
    Task 9: Evidence-coverage assessment.
    Calculates explicit case-level evidence coverage ratio (0-100).
    
    This evaluates the completeness of the required evidence inputs,
    completely separated from the contradiction/support status of individual claims.
    """
    coverage_signals = [
        evidence_bundle.get("ownership_signal") != "UNAVAILABLE",
        evidence_bundle.get("destination_prior_uses") is not None,
        evidence_bundle.get("destination_age_days") is not None,
        len(claim_checks) > 0
    ]
    
    true_count = sum(1 for signal in coverage_signals if signal is True)
    coverage = 100.0 * (true_count / 4.0)
    
    return coverage
