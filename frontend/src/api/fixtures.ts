// Development fixtures for when the backend is not fully implemented
import { CaseDetail, CaseListItem } from './types';

export const queueFixture: CaseListItem[] = [
  {
    case_id: 'a1b2c3d4-e5f6-7890-1234-567890abcdef',
    amount: 500000,
    failure_type: 'TYPE_2_DESTINATION_UNAVAILABLE',
    risk_score: 65,
    evidence_coverage: 100,
    decision: 'REVIEW',
    state: 'REVIEW',
    created_at: new Date(Date.now() - 3600000).toISOString(),
  },
  {
    case_id: 'b2c3d4e5-f6a7-8901-2345-67890abcdef1',
    amount: 1500000,
    failure_type: 'TYPE_1_TECHNICAL',
    risk_score: 15,
    evidence_coverage: 40,
    decision: 'APPROVE',
    state: 'APPROVED',
    created_at: new Date(Date.now() - 7200000).toISOString(),
  }
];

export const caseDetailFixture: CaseDetail = {
  case_id: 'a1b2c3d4-e5f6-7890-1234-567890abcdef',
  amount: 500000,
  failure_type: 'TYPE_2_DESTINATION_UNAVAILABLE',
  state: 'REVIEW',
  decision: 'REVIEW',
  created_at: new Date(Date.now() - 3600000).toISOString(),
  refund: {
    refund_id: 'rfnd_123abc',
    payment_id: 'pay_123abc',
    failure_reason: 'Account Closed or Transferred',
  },
  customer: {
    name: 'Jane Doe',
    created_at: '2023-01-15T00:00:00Z',
  },
  proposed_destination: {
    type: 'UPI',
    identifier: 'jane.doe@okicici',
    holder_name: 'Jane Doe',
    first_seen_at: '2023-05-20T00:00:00Z',
    times_used: 3,
  },
  extracted_claims: [
    {
      claim_text: "My old bank account was closed.",
      claim_type: "account_closed",
      status: "CONSISTENT",
      severity: "LOW",
      source: "payments",
    },
    {
      claim_text: "I want this sent to my other account.",
      claim_type: "third_party",
      status: "UNVERIFIABLE",
      severity: "MEDIUM",
      source: "llm",
    }
  ],
  risk_signals: {
    amount_matches_original: true,
    destination_age_days: 120,
    destination_prior_uses: 3,
    redirect_count_30d: 0,
    message_risk_flags: {
      urgency_language: false,
      third_party_destination: true,
      avoid_verified_channel: false,
      instruction_manipulation: false,
    },
    name_similarity_score: 0.95,
    ownership_signal: 'VERIFIED_SYNTHETIC',
  },
  evidence_coverage: 100,
  decision_reasons: [
    "Ownership verified",
    "New destination"
  ],
  audit_events: [
    {
      actor_type: 'SYSTEM',
      action: 'STATE_TRANSITION',
      reason: 'Refund failure received',
      created_at: new Date(Date.now() - 3600000).toISOString(),
    },
    {
      actor_type: 'LLM',
      action: 'CLAIMS_EXTRACTED',
      reason: 'Extracted 2 claims',
      created_at: new Date(Date.now() - 3500000).toISOString(),
    }
  ]
};
