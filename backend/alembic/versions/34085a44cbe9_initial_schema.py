"""initial_schema

Revision ID: 34085a44cbe9
Revises: 
Create Date: 2026-09-04 04:10:25.681446

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '34085a44cbe9'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.execute(r'''

CREATE TYPE case_state AS ENUM (
  'REFUND_FAILED', 'CLASSIFIED', 'AWAITING_ALTERNATE', 'ALTERNATE_SUBMITTED',
  'INVESTIGATING', 'RISK_SCORED', 'APPROVED', 'REVIEW', 'REJECTED',
  'NEEDS_INFORMATION', 'PAYOUT_PENDING', 'PAYOUT_SUCCESS', 'PAYOUT_FAILED',
  'DUPLICATE_GUARD_TRIGGERED', 'RESOLVED', 'CASE_EXPIRED'
);
-- No CASE_OPENED / REFUND_INITIATED here: a refund_cases row is only created
-- once a refund has already failed (architecture.md §4). Those earlier refund
-- lifecycle states live on refunds.status instead.

CREATE TYPE decision_type AS ENUM ('APPROVE', 'REVIEW', 'REJECT');

CREATE TYPE failure_type AS ENUM ('TYPE_1_TECHNICAL', 'TYPE_2_DESTINATION_UNAVAILABLE');

CREATE TYPE destination_type AS ENUM ('UPI', 'BANK');

CREATE TYPE evidence_status AS ENUM ('CONTRADICTED', 'CONSISTENT', 'UNVERIFIABLE');

CREATE TYPE evidence_severity AS ENUM ('LOW', 'MEDIUM', 'HIGH');

-- Always SYNTHETIC-labeled — see architecture.md §10, §17.
CREATE TYPE ownership_signal AS ENUM ('VERIFIED_SYNTHETIC', 'MISMATCH_SYNTHETIC', 'UNAVAILABLE');

CREATE TYPE actor_type AS ENUM ('SYSTEM', 'LLM', 'REVIEWER');

CREATE TYPE reviewer_action AS ENUM ('APPROVE', 'REJECT', 'REQUEST_MORE_INFO');

CREATE TYPE ground_truth_label AS ENUM ('LEGITIMATE', 'AMBIGUOUS', 'ADVERSARIAL');

CREATE TYPE eval_split AS ENUM ('TRAIN', 'DEV', 'HELD_OUT');


CREATE TABLE customers (
  customer_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name          TEXT NOT NULL,
  email         TEXT,
  phone         TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);


CREATE TABLE payments (
  payment_id    TEXT PRIMARY KEY,               -- Razorpay pay_<id> (real, test-mode)
  customer_id   UUID NOT NULL REFERENCES customers(customer_id),
  order_id      TEXT,
  amount        INT NOT NULL,                   -- paise
  currency      TEXT NOT NULL DEFAULT 'INR',
  method        TEXT,
  status        TEXT NOT NULL,                  -- captured/authorized/failed, mirrors Razorpay's own values
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_payments_customer ON payments(customer_id);


CREATE TABLE refunds (
  refund_id       TEXT PRIMARY KEY,              -- Razorpay rfnd_<id> (real, test-mode)
  payment_id      TEXT NOT NULL REFERENCES payments(payment_id),
  amount          INT NOT NULL,                  -- paise
  status          TEXT NOT NULL,                 -- pending / processed / failed (mirrors refund.entity.status)
  failure_reason  TEXT,                          -- error_reason / error_description from the webhook payload
  speed_requested TEXT,
  speed_processed TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_refunds_payment ON refunds(payment_id);


CREATE TABLE alternate_destinations (
  destination_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  customer_id     UUID NOT NULL REFERENCES customers(customer_id),
  type            destination_type NOT NULL,
  identifier      TEXT NOT NULL,                 -- VPA or masked account number
  holder_name     TEXT,
  submitted_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  times_used      INT NOT NULL DEFAULT 0
);
CREATE INDEX idx_alt_dest_customer ON alternate_destinations(customer_id);


CREATE TABLE refund_cases (
  case_id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  refund_id                TEXT NOT NULL UNIQUE REFERENCES refunds(refund_id),
  failure_type             failure_type NOT NULL,
  state                    case_state NOT NULL DEFAULT 'REFUND_FAILED',
  proposed_destination_id  UUID REFERENCES alternate_destinations(destination_id),
  customer_message         TEXT,
  risk_score                NUMERIC(5,2),
  evidence_coverage         NUMERIC(5,2),          -- 0-100; tracked separately from risk_score, architecture.md §7
  decision                 decision_type,
  decision_reasons         JSONB,                  -- short structured labels, architecture.md §9 — never free-text
  assigned_reviewer        TEXT,
  created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_refund_cases_state ON refund_cases(state);
CREATE INDEX idx_refund_cases_reviewer ON refund_cases(assigned_reviewer) WHERE assigned_reviewer IS NOT NULL;


CREATE TABLE extracted_claims (
  claim_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  case_id        UUID NOT NULL REFERENCES refund_cases(case_id),
  claim_text     TEXT NOT NULL,                  -- e.g. "My old bank account was closed last month."
  claim_type     TEXT NOT NULL,                  -- e.g. account_closed / prior_usage / urgency / third_party
  confidence     NUMERIC(4,3),                   -- LLM's own confidence, advisory only
  model_version  TEXT NOT NULL,
  extracted_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_extracted_claims_case ON extracted_claims(case_id);


CREATE TABLE claim_evidence_checks (
  check_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  case_id        UUID NOT NULL REFERENCES refund_cases(case_id),
  claim_id       UUID REFERENCES extracted_claims(claim_id),   -- NULL for purely deterministic checks (e.g. amount mismatch)
  claim_text     TEXT NOT NULL,
  evidence_text  TEXT NOT NULL,
  status         evidence_status NOT NULL,
  severity       evidence_severity NOT NULL,
  source         TEXT NOT NULL,                  -- e.g. 'payments' / 'refunds' / 'alternate_destinations' / 'llm'
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_claim_evidence_case ON claim_evidence_checks(case_id);


CREATE TABLE risk_signals (
  signal_id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  case_id                  UUID NOT NULL UNIQUE REFERENCES refund_cases(case_id),
  destination_age_days     INT,
  destination_prior_uses   INT,
  redirect_count_30d       INT,
  amount_matches_original  BOOLEAN,
  name_similarity_score    NUMERIC(4,3),          -- weak signal by design — must render labeled "weak" downstream, never as proof
  ownership_signal         ownership_signal NOT NULL DEFAULT 'UNAVAILABLE',  -- always SYNTHETIC-labeled in the UI
  message_risk_flags       JSONB,                 -- LLM-derived vector, e.g. {"urgency": true, "third_party": true}
  computed_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);


CREATE TABLE payouts (
  payout_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  case_id            UUID NOT NULL REFERENCES refund_cases(case_id),
  destination_id     UUID NOT NULL REFERENCES alternate_destinations(destination_id),
  amount             INT NOT NULL,                -- paise; must be <= AUTO_APPROVAL_LIMIT for an auto-approved case (enforced in application code, architecture.md §8)
  mode               TEXT NOT NULL,               -- UPI / NEFT / RTGS / IMPS (uppercase, per Razorpay's own API requirement)
  purpose            TEXT NOT NULL DEFAULT 'refund',  -- real built-in Razorpay purpose value — never invent a new one via the API
  status             TEXT NOT NULL,               -- queued/processing/processed/reversed/failed, mirrors RazorpayX payout lifecycle
  idempotency_key    TEXT NOT NULL UNIQUE,        -- value sent as X-Payout-Idempotency; 4-36 chars, derived deterministically from case_id
  razorpay_payout_id TEXT,                        -- pout_<id> once RazorpayX returns one
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX idx_payouts_case_success ON payouts(case_id) WHERE status IN ('processed');


CREATE TABLE audit_events (
  event_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  case_id            UUID NOT NULL REFERENCES refund_cases(case_id),
  actor_type         actor_type NOT NULL,
  actor_id           TEXT,                        -- e.g. 'policy_engine_v1', 'llm', 'reviewer:priya@merchant.com'
  action             TEXT NOT NULL,                -- e.g. 'STATE_TRANSITION', 'RISK_SIGNAL_UPDATED', 'PAYOUT_CREATED'
  reason             TEXT,
  model_version      TEXT,                         -- set only when actor_type = 'LLM'
  evidence_snapshot  JSONB,                         -- point-in-time evidence/signal state this event is based on
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_events_case ON audit_events(case_id, created_at);


CREATE TABLE reviewer_outcomes (
  outcome_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  case_id      UUID NOT NULL REFERENCES refund_cases(case_id),
  reviewer_id  TEXT NOT NULL,
  action       reviewer_action NOT NULL,
  reason       TEXT NOT NULL,                     -- mandatory, per task.md's human-review requirement
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_reviewer_outcomes_case ON reviewer_outcomes(case_id);


CREATE TABLE evaluation_cases (
  eval_case_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  dataset_version    TEXT NOT NULL,
  split              eval_split NOT NULL,
  case_payload       JSONB NOT NULL,               -- full synthetic snapshot: transaction, customer, destination, message
  ground_truth_label ground_truth_label NOT NULL,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_eval_cases_dataset_split ON evaluation_cases(dataset_version, split);


CREATE TABLE evaluation_runs (
  eval_run_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  dataset_version   TEXT NOT NULL,
  policy_version    TEXT NOT NULL,
  model_version     TEXT,
  prompt_version    TEXT,
  threshold_config  JSONB NOT NULL,                -- includes AUTO_APPROVAL_LIMIT and all policy thresholds in force for this run
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);


CREATE TABLE evaluation_results (
  result_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  eval_run_id        UUID NOT NULL REFERENCES evaluation_runs(eval_run_id),
  eval_case_id       UUID NOT NULL REFERENCES evaluation_cases(eval_case_id),
  predicted_decision decision_type NOT NULL,
  ground_truth_label ground_truth_label NOT NULL,   -- denormalized copy from evaluation_cases, avoids a join on every dashboard query
  is_correct         BOOLEAN NOT NULL,
  latency_ms         INT,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_eval_results_run ON evaluation_results(eval_run_id);
CREATE UNIQUE INDEX idx_eval_results_run_case ON evaluation_results(eval_run_id, eval_case_id);

    ''')



def downgrade() -> None:
    """Downgrade schema."""

    op.execute('DROP TABLE IF EXISTS evaluation_results CASCADE;')
    op.execute('DROP TABLE IF EXISTS evaluation_runs CASCADE;')
    op.execute('DROP TABLE IF EXISTS evaluation_cases CASCADE;')
    op.execute('DROP TABLE IF EXISTS reviewer_outcomes CASCADE;')
    op.execute('DROP TABLE IF EXISTS audit_events CASCADE;')
    op.execute('DROP TABLE IF EXISTS payouts CASCADE;')
    op.execute('DROP TABLE IF EXISTS risk_signals CASCADE;')
    op.execute('DROP TABLE IF EXISTS claim_evidence_checks CASCADE;')
    op.execute('DROP TABLE IF EXISTS extracted_claims CASCADE;')
    op.execute('DROP TABLE IF EXISTS refund_cases CASCADE;')
    op.execute('DROP TABLE IF EXISTS alternate_destinations CASCADE;')
    op.execute('DROP TABLE IF EXISTS refunds CASCADE;')
    op.execute('DROP TABLE IF EXISTS payments CASCADE;')
    op.execute('DROP TABLE IF EXISTS customers CASCADE;')

    op.execute('DROP TYPE IF EXISTS eval_split CASCADE;')
    op.execute('DROP TYPE IF EXISTS ground_truth_label CASCADE;')
    op.execute('DROP TYPE IF EXISTS reviewer_action CASCADE;')
    op.execute('DROP TYPE IF EXISTS actor_type CASCADE;')
    op.execute('DROP TYPE IF EXISTS ownership_signal CASCADE;')
    op.execute('DROP TYPE IF EXISTS evidence_severity CASCADE;')
    op.execute('DROP TYPE IF EXISTS evidence_status CASCADE;')
    op.execute('DROP TYPE IF EXISTS destination_type CASCADE;')
    op.execute('DROP TYPE IF EXISTS failure_type CASCADE;')
    op.execute('DROP TYPE IF EXISTS decision_type CASCADE;')
    op.execute('DROP TYPE IF EXISTS case_state CASCADE;')

