# Task 5 Dataset Notes

## 1. Required Task 5 Baseline
- 150 customers
- ~600 payments
- ~120 refunds
- ~35 failed refunds
- Alternate-destination distribution: 60% CLEAN / 25% AMBIGUOUS / 15% ADVERSARIAL

## 2. Actual Generated Dataset
- 150 customers
- 600 payments
- 120 refunds
- 35 failed refunds
- 20 Type 2 alternate-destination scenarios
  - 12 CLEAN
  - 5 AMBIGUOUS
  - 3 ADVERSARIAL

## 3. Held-out Split Decision
The dataset uses a deterministic stratified split for the 20 Type 2 scenarios rather than a random distribution:
- **CLEAN**: 9 TRAIN / 3 HELD_OUT
- **AMBIGUOUS**: 3 TRAIN / 2 HELD_OUT
- **ADVERSARIAL**: 2 TRAIN / 1 HELD_OUT

This was explicitly chosen to ensure the held-out evaluation cannot accidentally contain zero examples of any scenario class, preventing broken or uninformative evaluations.

## 4. Statistical Limitation
The required Task 5 dataset is intentionally small. The 3 adversarial cases provided (and the 1 held-out) are numerically insufficient to support a generalized "100% adversarial recall" claim by themselves. They are sufficient to demonstrate the required build artifact, but any future evaluation must present raw counts and intervals (e.g., 100% (3/3)) instead of bare percentages.

## 5. Stress Evaluation
A supplementary generator (`generate_stress_eval.py`) was intentionally deferred to the later Evaluation task on Day 3 and is excluded from the primary Task 5 commit to preserve the strict boundaries of the required scope.

## 6. Synthetic-Data Boundary
**CRITICAL**: All customers, payments, refunds, alternate-destination scenarios, verification outputs, and ground-truth labels in this dataset are entirely **SYNTHETIC**. They must never be represented or interpreted as real customer or payment intelligence.
