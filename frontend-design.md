# frontend-design.md — UI Specification

> Companion to `PRD.md`, `task.md`, `architecture.md`, `backend-schema.md`, `implementation.md`. Terminology, states, and field names below are identical to `backend-schema.md`'s tables — `case_state`, `decision_type` (`APPROVE`/`REVIEW`/`REJECT`), `decision_reasons`, `ground_truth_label` (`LEGITIMATE`/`AMBIGUOUS`/`ADVERSARIAL`), `ownership_signal` (`VERIFIED_SYNTHETIC`/`MISMATCH_SYNTHETIC`/`UNAVAILABLE`). This is a financial-operations/risk console, not a chatbot — every screen should read as something a payments-risk team would actually use, and a judge should understand the whole product within 30 seconds of the Queue screen.

## 0. Design language (applies to every screen)

- **Palette:** neutral dark-on-light operations UI (slate/gray base), with color reserved strictly for status semantics — never decorative. Risk and decision colors are the only saturated colors on screen.
- **Status colors (used consistently everywhere a badge appears):**
  - `APPROVE` / `APPROVED` → green
  - `REVIEW` → amber
  - `REJECT` / `REJECTED` → red
  - `PAYOUT_SUCCESS` / `RESOLVED` → slate-green (muted, "closed" not "active")
  - `DUPLICATE_GUARD_TRIGGERED` → violet — deliberately a distinct color from red/amber, because this is a *safety system working correctly*, not a risk finding, and should read differently on sight.
  - `PAYOUT_FAILED` / `CASE_EXPIRED` → gray-red, muted
- **Synthetic-data labeling (non-negotiable on every screen that shows it):** any value sourced from `DemoVerificationProvider` or the synthetic dataset renders with a small, consistently-styled **`SYNTHETIC`** tag — a distinct badge shape/color (dashed border, muted violet) from every real risk/decision badge, so it can never be mistaken for a live result at a glance. Never render a bare "VERIFIED" — always "VERIFIED — SYNTHETIC DEMO DATA" or the shortened `SYNTHETIC` tag next to the value.
- **Typography:** one serif or distinctive display face for numbers/headers (risk scores, amounts) so they read as a financial product, not a generic SaaS dashboard template; monospace for IDs, keys, and hashes (`case_id`, `idempotency_key`).
- **Evidence tiers**, used on the Case Investigation screen and echoed as color coding elsewhere: **Strong** (solid fill) / **Moderate** (light fill) / **Weak** (outline only, always paired with a "weak signal" microcopy label) — this directly reflects the strong/moderate/weak signal classification from the project's own research and must never be flattened into one undifferentiated list.

## 1. Failed Refund Queue

**Purpose:** the entry point — every open case, scannable in under a minute, risk-color-coded so a reviewer knows what to open first.

**Layout:** full-width table, sortable columns, filter bar above.

**Columns:**
| Column | Source | Notes |
|---|---|---|
| Case ID | `refund_cases.case_id` | truncated monospace, click to open Case Investigation |
| Amount | `refund_cases` → `refunds.amount` | formatted ₹, right-aligned |
| Failure Type | `refund_cases.failure_type` | badge: `TYPE_1_TECHNICAL` (gray, muted — these should visually recede) / `TYPE_2_DESTINATION_UNAVAILABLE` (the active workflow) |
| Risk | `refund_cases.risk_score` | numeric + colored dot (green <31, amber 31–70, red 71+) |
| Evidence Coverage | `refund_cases.evidence_coverage` | separate colored dot from Risk — **this is the single most important visual distinction on the page**: a case can be low-risk and low-coverage simultaneously, and the queue must make that visible as two dots, not one blended score |
| Decision | `refund_cases.decision` | badge, `—` if not yet decided |
| Status | `refund_cases.state` | badge, full `case_state` vocabulary |
| Age | `created_at` | relative time |

**Filter bar:** state (multi-select), decision, failure type, risk band. Default filter: `state = REVIEW` (the reviewer's actual queue), with a toggle to "show all."

**Interaction:** row click → Case Investigation. No inline actions on this screen — approve/reject only happens on the Case Investigation / Human Review screen, to keep this screen a triage view, not an action surface.

**Empty state:** "No open cases — every failed refund is either resolved or on track automatically." (Distinguish explicitly from a loading failure — see below.)

**Loading state:** skeleton rows, not a spinner overlay — table shape should be visible immediately.

**Error state:** if the case list fails to load, show a retry action inline in the table area; never a blank page.

## 2. Case Investigation

**Purpose:** the single screen a judge or reviewer spends the most time on — every piece of evidence behind a decision, visibly separated by trust tier.

**Layout:** two-column. Left column (60%): evidence and claims. Right column (40%, sticky): decision summary + reviewer actions.

**Header:** Case ID, amount, failure type badge, current state badge, age.

**Section A — Original refund & customer**
- Original payment/refund IDs (`payments.payment_id`, `refunds.refund_id`), original destination info, `refunds.failure_reason` verbatim.
- Customer name, account tenure (from `customers.created_at`).

**Section B — Proposed alternate destination**
- `alternate_destinations` fields: type (UPI/BANK badge), masked identifier, holder name, `first_seen_at`, `times_used`.
- **`ownership_signal`** rendered as its own card, always with the `SYNTHETIC` tag from §0 — e.g. "Ownership signal: MISMATCH — SYNTHETIC DEMO DATA" in red, or "UNAVAILABLE — SYNTHETIC DEMO DATA" in neutral gray when the demo provider has no result. Never a bare green check.

**Section C — Extracted claims & contradiction results**
Table sourced from `extracted_claims` joined to `claim_evidence_checks`:
| Claim | Evidence | Status | Severity |
|---|---|---|---|
| customer's claim text | the matching database fact | `CONTRADICTED` (red) / `CONSISTENT` (green) / `UNVERIFIABLE` (gray) | LOW/MED/HIGH badge |

This table is the demo's centerpiece — render it prominently, not buried. A `CONTRADICTED` row should visually dominate the section (red left-border accent) since it's the strongest single fraud signal in the product.

**Section D — Risk signals (three visually separate tiers, not one flat list)**
- **Hard/deterministic signals:** `amount_matches_original`, `destination_age_days`, `destination_prior_uses`, `redirect_count_30d` — rendered as plain labeled values, no AI framing.
- **AI-flagged language:** `message_risk_flags` (e.g. `urgency`, `third_party_destination`) — rendered as chips, each visibly labeled "AI-flagged," in a distinct visual block from the hard signals above, so a reviewer can see at a glance the machine's math is separate from the model's judgment.
- **Weak/unverifiable signals:** `name_similarity_score` — rendered with a persistent "weak signal — not proof" microcopy caption every time it appears, never presented at the same visual weight as a strong signal.

**Section E — Evidence coverage**
A distinct callout (not folded into the risk score) stating whether the case was routed to `REVIEW` because of **risk** or because of **insufficient evidence** — these render with different icons and different explanatory text, per `architecture.md` §7. Example: "Routed to review: insufficient evidence (ownership unavailable, destination never used before)" vs. "Routed to review: elevated risk score (62/100)."

**Section F — Decision (right column, sticky)**
- Large decision badge (`APPROVE`/`REVIEW`/`REJECT`) with `risk_score` shown numerically beside it.
- **`decision_reasons`** rendered as a short bulleted list directly below the badge — exactly the labels from `architecture.md` §9 (e.g. "Ownership unverified · New destination · Insufficient evidence"). This list is never editable and never framed as AI-written — it is the deterministic policy engine's own summary.
- If `evidence_coverage` is low, a P1 **counterfactual** line if implemented: "Would flip to APPROVE if: ownership were verified." (Only shown if `implementation.md`'s counterfactual function is built — omit the section entirely otherwise, don't show a placeholder.)

**Section G — Audit timeline**
Chronological list from `audit_events`: actor icon (system/LLM/reviewer), action, reason, timestamp. This folds in the standalone audit-log screen the original brief considered and cut — no separate screen needed.

**Empty state:** if a case has no `extracted_claims` yet (still `INVESTIGATING`), show a progress indicator over Section C, not an empty table.

**Loading/error states:** section-level skeletons; a failed section (e.g. audit events didn't load) degrades independently rather than blocking the whole page.

## 3. Human Review

**Purpose:** the action surface for any case in `REVIEW`. Not a separate route — an action panel anchored to the bottom of Section F on Case Investigation, so a reviewer never loses the evidence context while deciding.

**Components:**
- Three buttons: **APPROVE**, **REJECT**, **REQUEST MORE INFORMATION** — map directly to `reviewer_action` enum.
- A required reason text field (`reviewer_outcomes.reason`) — the submit button is disabled until non-empty; this is not optional, per `task.md`'s human-review requirement.
- Confirmation step on APPROVE only, showing the payout amount and destination one more time before submission — the one place in the UI a human is asked to double-check before money moves.

**Interaction behavior:** submitting writes to `reviewer_outcomes`, transitions `refund_cases.state` accordingly, and immediately reflects the new state badge — no page reload. `REQUEST MORE INFORMATION` transitions to `NEEDS_INFORMATION` and shows a confirmation that the customer will be prompted to resubmit.

**Empty state:** N/A — this panel only renders when `state = REVIEW`.

**Error state:** if the submit call fails (e.g. a duplicate-guard trigger fired concurrently), show the specific reason inline ("This case was auto-resolved by the duplicate guard before your review was submitted") rather than a generic error — this is itself a demo-worthy moment, not just error handling.

## 4. Evaluation Dashboard

**Purpose:** answer "does this actually work" with numbers from a real run, not a claim — this is the screen that carries the most judging weight per `PRD.md` §10.

**Layout:** top strip of metric cards, confusion matrix below, threshold simulator (P1) at the bottom.

**Run selector:** dropdown at the top showing `evaluation_runs` by timestamp, each labeled with its `dataset_version`/`policy_version`/`model_version` — selecting a run reloads every metric below from that specific run's `evaluation_results`, never a blended "all-time" number. This is the direct UI expression of Evaluation Run Provenance (`architecture.md` §15) — a judge should be able to click into exactly which configuration produced a number.

**Metric cards:** precision, recall, false-approval rate (highlighted — largest card, red accent if non-zero, since this is the single most important safety metric), false-rejection rate, review rate, auto-resolution rate, average decision latency, duplicate-risk detection rate.

**Confusion matrix:** 3×3 grid, `ground_truth_label` (`LEGITIMATE`/`AMBIGUOUS`/`ADVERSARIAL`) rows against `predicted_decision` (`APPROVE`/`REVIEW`/`REJECT`) columns, cell values from the query in `backend-schema.md` §17. Diagonal cells shaded green; the `ADVERSARIAL`→`APPROVE` cell (a false approval) shaded red and visually the most prominent off-diagonal cell on the grid, regardless of its count.

**Exception list:** a scrollable panel listing held-out cases the system could not confidently resolve (per `task.md`'s Day 3 requirement) — case ID, ground truth, predicted decision, and a one-line reason, linked back to Case Investigation.

**Threshold simulator (P1):** an interactive slider or curve for the risk-score `REVIEW` threshold, live-updating three linked numbers as it moves: automation rate, false-approval rate, and expected cost under the assumed 20× false-approval-cost ratio (labeled inline as "assumed ratio, not a real Razorpay figure" — never presented without that caption). This is the strongest single interactive demo moment on the dashboard; render it as a real chart, not a static table.

**Empty state:** "No evaluation runs yet — run the evaluation harness to populate this dashboard," with the exact CLI/command reference from `implementation.md`.

## 5. Live Demo / Investigation Timeline (P2, only if ahead of schedule)

**Purpose:** during the live pitch, show evidence being assembled in real time rather than presenting a pre-computed result — the single best visual moment per `task.md`'s demo narrative.

**Layout:** a simplified, animated version of Case Investigation's Sections B–D, revealing each evidence block as the backend pipeline computes it (aggregation → LLM extraction → contradiction check → risk score), using the same real API calls as the standard flow — not a separate scripted animation.

**Only build this if Day 3's P0/P1 work is complete** — per `task.md`'s STOP/CUT rules, this is explicitly the first thing cut under time pressure, and Case Investigation alone is sufficient to carry the demo.

## 6. Cross-screen conventions

- **Amounts:** always ₹, always paise converted to rupees at render time, never raw paise integers shown to a user.
- **IDs:** always truncated with a copy-on-click affordance; full ID visible in a tooltip.
- **Every screen that renders `ownership_signal` or any other synthetic value repeats the `SYNTHETIC` tag locally** — it is never sufficient to label it once at the top of a page; a reviewer scanning one section in isolation must still see the label.
- **No screen ever shows LLM chain-of-thought or a free-text LLM explanation field** — per `architecture.md` §9, this field does not exist in the MVP; only `decision_reasons` (deterministic, short labels) and `extracted_claims`/`message_risk_flags` (structured, not prose) ever render.
