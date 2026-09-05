import sys
import os
import unittest

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from scripts.simulate_thresholds import simulate_decision

class TestThresholdSimulator(unittest.TestCase):
    
    def test_baseline_equivalence(self):
        # Should exactly mirror policy.py tier boundaries
        
        # Test 1: APPROVE below REVIEW threshold with no deterministic flags
        self.assertEqual(simulate_decision(30.0, [], 31, 71), "APPROVE")
        
        # Test 2: REVIEW at or above REVIEW threshold but below REJECT
        self.assertEqual(simulate_decision(31.0, [], 31, 71), "REVIEW")
        self.assertEqual(simulate_decision(70.0, [], 31, 71), "REVIEW")
        
        # Test 3: REJECT at or above REJECT threshold
        self.assertEqual(simulate_decision(71.0, [], 31, 71), "REJECT")
        self.assertEqual(simulate_decision(100.0, [], 31, 71), "REJECT")
        
    def test_deterministic_safety_gates(self):
        # Even with low risk score, safety flags should force REVIEW or REJECT
        
        # REVIEW gates
        self.assertEqual(simulate_decision(10.0, ["OVER_AUTO_APPROVAL_LIMIT"], 31, 71), "REVIEW")
        self.assertEqual(simulate_decision(10.0, ["INSUFFICIENT_EVIDENCE"], 31, 71), "REVIEW")
        self.assertEqual(simulate_decision(10.0, ["LLM_MESSAGE_RISK"], 31, 71), "REVIEW")
        self.assertEqual(simulate_decision(10.0, ["NEW_DESTINATION"], 31, 71), "REVIEW")
        self.assertEqual(simulate_decision(10.0, ["AMOUNT_MISMATCH"], 31, 71), "REVIEW")
        
        # REJECT gates (override everything including REVIEW gates)
        self.assertEqual(simulate_decision(10.0, ["NAME_MISMATCH_BELOW_FLOOR"], 31, 71), "REJECT")
        self.assertEqual(simulate_decision(10.0, ["REDIRECT_VELOCITY_HIGH"], 31, 71), "REJECT")
        
        self.assertEqual(simulate_decision(10.0, ["NEW_DESTINATION", "NAME_MISMATCH_BELOW_FLOOR"], 31, 71), "REJECT")
        
    def test_threshold_sweeps(self):
        # Test an ultra conservative config
        self.assertEqual(simulate_decision(10.0, [], 10, 50), "REVIEW")
        self.assertEqual(simulate_decision(9.9, [], 10, 50), "APPROVE")
        self.assertEqual(simulate_decision(50.0, [], 10, 50), "REJECT")
        
        # Test an aggressive config
        self.assertEqual(simulate_decision(45.0, [], 50, 80), "APPROVE")
        self.assertEqual(simulate_decision(60.0, [], 50, 80), "REVIEW")
        
if __name__ == "__main__":
    unittest.main()
