from enum import Enum
from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)

class FailureType(str, Enum):
    TYPE_1_TECHNICAL = "TYPE_1_TECHNICAL"
    TYPE_2_DESTINATION_UNAVAILABLE = "TYPE_2_DESTINATION_UNAVAILABLE"

class ClassificationSource(str, Enum):
    MATCHED_RULE = "MATCHED_RULE"
    UNRECOGNIZED_DEFAULTED = "UNRECOGNIZED_DEFAULTED"

TYPE_1_REASONS = {
    "bank_processing_error",
    "technical_issue",
    "npci_timeout",
    "gateway_error",
    "account_temporarily_frozen",
    "account_details_malformed",
    "vpa_malformed"
}

TYPE_2_REASONS = {
    "account_closed",
    "account_permanently_deactivated",
    "account_details_nonexistent",
    "vpa_permanently_deactivated"
}

def classify_refund_failure(error_reason: Optional[str], error_description: Optional[str]) -> Tuple[FailureType, ClassificationSource]:
    """
    Deterministically classifies a refund failure as Type 1 (Technical) or Type 2 (Destination Unavailable).
    
    Rules:
    - Type 1: Technical/retryable issues. MUST NEVER enter the AI pipeline.
    - Type 2: Original destination is unreachable. Transitions to AWAITING_ALTERNATE.
    - Unknown/unmapped: Safely falls back to Type 1 to prevent unknown failures from entering AI processing.
    """
    reason = (error_reason or "").lower()
    description = (error_description or "").lower()
    
    # 1. Exact match on known Type 2 reasons
    if reason in TYPE_2_REASONS:
        return FailureType.TYPE_2_DESTINATION_UNAVAILABLE, ClassificationSource.MATCHED_RULE
        
    # 2. Exact match on known Type 1 reasons
    if reason in TYPE_1_REASONS:
        return FailureType.TYPE_1_TECHNICAL, ClassificationSource.MATCHED_RULE
        
    # 3. Deterministic description-based matching if reason is missing/ambiguous
    type_2_keywords = ["closed", "permanently deactivated", "nonexistent"]
    if any(keyword in description for keyword in type_2_keywords):
        return FailureType.TYPE_2_DESTINATION_UNAVAILABLE, ClassificationSource.MATCHED_RULE
        
    type_1_keywords = ["bank processing error", "technical issue", "timeout", "gateway error", "temporarily frozen", "malformed"]
    if any(keyword in description for keyword in type_1_keywords):
        return FailureType.TYPE_1_TECHNICAL, ClassificationSource.MATCHED_RULE
        
    # 4. Safe fallback for unknown/unmapped reasons
    logger.warning(f"Unknown refund failure reason '{error_reason}'. Safely falling back to TYPE_1_TECHNICAL.")
    return FailureType.TYPE_1_TECHNICAL, ClassificationSource.UNRECOGNIZED_DEFAULTED
