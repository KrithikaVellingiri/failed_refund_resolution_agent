export interface CaseListItem {
  case_id: string;
  amount: number;
  failure_type: string;
  risk_score: number | null;
  evidence_coverage: number | null;
  decision: string | null;
  state: string;
  created_at: string;
}

export interface ClaimCheck {
  claim_text: string;
  claim_type: string;
  status: 'CONTRADICTED' | 'CONSISTENT' | 'UNVERIFIABLE';
  severity: 'LOW' | 'MEDIUM' | 'HIGH';
  source: string;
}

export interface CaseDetail {
  case_id: string;
  amount: number;
  failure_type: string;
  state: string;
  decision: string | null;
  created_at: string;
  refund: {
    refund_id: string;
    payment_id: string;
    failure_reason: string;
  };
  customer: {
    name: string;
    created_at: string;
  };
  proposed_destination?: {
    type: string;
    identifier: string;
    holder_name: string;
    first_seen_at: string;
    times_used: number;
  };
  extracted_claims: ClaimCheck[];
  risk_signals: {
    amount_matches_original: boolean | null;
    destination_age_days: number | null;
    destination_prior_uses: number | null;
    redirect_count_30d: number | null;
    message_risk_flags: {
      urgency_language: boolean;
      third_party_destination: boolean;
      avoid_verified_channel: boolean;
      instruction_manipulation: boolean;
    } | null;
    name_similarity_score: number | null;
    ownership_signal: 'VERIFIED_SYNTHETIC' | 'MISMATCH_SYNTHETIC' | 'UNAVAILABLE';
  };
  evidence_coverage: number | null;
  decision_reasons: string[] | null;
  audit_events: {
    actor_type: string;
    action: string;
    reason: string;
    created_at: string;
  }[];
}
