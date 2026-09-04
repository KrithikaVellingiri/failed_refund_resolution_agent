from typing import List, Dict, Any

def check_claims(extracted_claims: 'ExtractedClaims', evidence_bundle: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Deterministic contradiction checker (Task 8).
    Takes LLM output claims and deterministic evidence bundle,
    and returns a list of claim_evidence_checks dicts.
    
    Output item schema:
    {
        "claim": str,
        "evidence": str,
        "status": "CONSISTENT" | "CONTRADICTED" | "UNVERIFIABLE",
        "severity": "LOW" | "MEDIUM" | "HIGH",
        "source": str
    }
    """
    checks = []

    for claim in extracted_claims.claims:
        check = {
            "claim": claim.claim_text,
            "evidence": "No relevant evidence available",
            "status": "UNVERIFIABLE",
            "severity": "LOW",  # Defaulting severity to low when unverifiable
            "source": "UNKNOWN"
        }

        if claim.claim_type == "account_closed":
            account_status = evidence_bundle.get("account_status")
            if account_status is None:
                check["status"] = "UNVERIFIABLE"
                check["evidence"] = "Account status evidence is missing"
                check["source"] = "UNKNOWN"
                check["severity"] = "HIGH"
            elif account_status.upper() == "CLOSED":
                check["status"] = "CONSISTENT"
                check["evidence"] = f"account_status = {account_status.upper()}"
                check["source"] = "payments"
                check["severity"] = "HIGH"
            elif account_status.upper() == "ACTIVE":
                check["status"] = "CONTRADICTED"
                check["evidence"] = f"account_status = {account_status.upper()}"
                check["source"] = "payments"
                check["severity"] = "HIGH"
            else:
                check["status"] = "UNVERIFIABLE"
                check["evidence"] = f"account_status = {account_status.upper()}"
                check["source"] = "payments"
                check["severity"] = "HIGH"

        elif claim.claim_type == "prior_usage":
            prior_uses = evidence_bundle.get("destination_prior_uses")
            if prior_uses is None:
                check["status"] = "UNVERIFIABLE"
                check["evidence"] = "Usage evidence is missing"
                check["source"] = "UNKNOWN"
                check["severity"] = "HIGH"
            elif prior_uses > 0:
                check["status"] = "CONSISTENT"
                check["evidence"] = f"destination usage count = {prior_uses}"
                check["source"] = "alternate_destinations"
                check["severity"] = "HIGH"
            elif prior_uses == 0:
                check["status"] = "CONTRADICTED"
                check["evidence"] = f"destination usage count = {prior_uses}"
                check["source"] = "alternate_destinations"
                check["severity"] = "HIGH"

        elif claim.claim_type == "third_party":
            # Can't reliably verify third party ownership merely from destination_prior_uses
            # We would need ownership_signal, but ownership_signal verified/mismatch doesn't 
            # strictly prove it's a third party without knowing exactly who the third party is.
            # We treat third_party claims as UNVERIFIABLE for now.
            check["status"] = "UNVERIFIABLE"
            check["evidence"] = "Third party identity cannot be deterministically verified"
            check["source"] = "llm"
            check["severity"] = "MEDIUM"

        elif claim.claim_type == "urgency":
            # Urgency is a subjective claim, generally UNVERIFIABLE
            check["status"] = "UNVERIFIABLE"
            check["evidence"] = "Urgency is a subjective intent flag"
            check["source"] = "llm"
            check["severity"] = "LOW"

        else:
            # "other" or unsupported claims
            check["status"] = "UNVERIFIABLE"
            check["evidence"] = f"Claim type '{claim.claim_type}' is not supported for verification"
            check["source"] = "llm"
            check["severity"] = "LOW"

        checks.append(check)

    return checks
