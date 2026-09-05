from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class CaseListItem(BaseModel):
    case_id: str
    amount: int
    failure_type: str
    risk_score: Optional[float]
    evidence_coverage: Optional[float]
    decision: Optional[str]
    state: str
    created_at: datetime

    class Config:
        from_attributes = True

class ClaimCheck(BaseModel):
    claim_text: str
    claim_type: str
    status: str
    severity: str
    source: str

class RefundInfo(BaseModel):
    refund_id: str
    payment_id: str
    failure_reason: str

class CustomerInfo(BaseModel):
    name: str
    created_at: datetime

class ProposedDestination(BaseModel):
    type: str
    identifier: str
    holder_name: str
    first_seen_at: datetime
    times_used: int

class MessageRiskFlags(BaseModel):
    urgency_language: bool
    third_party_destination: bool
    avoid_verified_channel: bool
    instruction_manipulation: bool

class RiskSignals(BaseModel):
    amount_matches_original: Optional[bool]
    destination_age_days: Optional[int]
    destination_prior_uses: Optional[int]
    redirect_count_30d: Optional[int]
    message_risk_flags: Optional[MessageRiskFlags]
    name_similarity_score: Optional[float]
    ownership_signal: str

class AuditEvent(BaseModel):
    actor_type: str
    action: str
    reason: str
    created_at: datetime

class CaseDetail(BaseModel):
    case_id: str
    amount: int
    failure_type: str
    state: str
    decision: Optional[str]
    created_at: datetime
    refund: RefundInfo
    customer: CustomerInfo
    proposed_destination: Optional[ProposedDestination]
    extracted_claims: List[ClaimCheck]
    risk_signals: RiskSignals
    evidence_coverage: Optional[float]
    decision_reasons: Optional[List[str]]
    audit_events: List[AuditEvent]

    class Config:
        from_attributes = True
