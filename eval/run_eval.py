import asyncio
import json
import os
import sys
from pathlib import Path

# Add project root to sys.path to resolve imports correctly
sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator import execute_agent
from agents.intake_agent import intake_agent
from agents.policy_agent import policy_agent


async def evaluate_case(case: dict) -> tuple[bool, dict]:
    """Runs a single test case through the real agents and validates the output."""
    desc = case["description"]
    expected = case["expected"]
    case_id = case["id"]

    print(f"\n--- Running: {case_id} ---")
    print(f"Input description: '{desc}'")

    # Step 1: Intake parsing
    try:
        intake_raw = await execute_agent(intake_agent, desc)
        expense_json = json.loads(intake_raw)
    except Exception as e:
        print(f"  [FAIL] Intake parsing failed: {e}")
        return False, {"error": f"Intake failed: {e}"}

    # Step 2: Policy checking
    try:
        policy_raw = await execute_agent(policy_agent, json.dumps(expense_json))
        result = json.loads(policy_raw)
    except Exception as e:
        print(f"  [FAIL] Policy check failed: {e}")
        return False, {"error": f"Policy failed: {e}"}

    print(f"Result returned: {json.dumps(result)}")

    # Validation
    violations = []
    
    # Check is_compliant (handle possible boolean conversions)
    actual_compliant = result.get("is_compliant")
    if actual_compliant is None:
        # Check alternative common keys just in case
        actual_compliant = result.get("compliant")
    
    if actual_compliant != expected.get("is_compliant"):
        violations.append(f"is_compliant mismatch: expected {expected.get('is_compliant')}, got {actual_compliant}")

    # Check needs_approval
    actual_approval = result.get("needs_approval")
    if actual_approval is None:
        actual_approval = result.get("manager_approval_required") or result.get("requires_manager_approval")
    
    if actual_approval != expected.get("needs_approval"):
        violations.append(f"needs_approval mismatch: expected {expected.get('needs_approval')}, got {actual_approval}")

    # Check usd_amount / range
    actual_usd = result.get("usd_amount")
    if actual_usd is None:
        actual_usd = result.get("amount_usd") or result.get("converted_amount_usd")

    if actual_usd is None:
        violations.append("usd_amount field missing in policy output")
    else:
        try:
            actual_usd = float(actual_usd)
            if "usd_amount" in expected:
                expected_usd = float(expected["usd_amount"])
                if abs(actual_usd - expected_usd) > 0.01:
                    violations.append(f"usd_amount mismatch: expected {expected_usd}, got {actual_usd}")
            elif "usd_amount_range" in expected:
                low, high = expected["usd_amount_range"]
                if not (low <= actual_usd <= high):
                    violations.append(f"usd_amount {actual_usd} out of expected range [{low}, {high}]")
        except ValueError:
            violations.append(f"usd_amount is not a valid float: {actual_usd}")

    if violations:
        print(f"  [FAIL] Validation failures:")
        for v in violations:
            print(f"    - {v}")
        return False, {"result": result, "violations": violations}
    else:
        print(f"  [PASS] All expected criteria met.")
        return True, {"result": result}


async def run_evaluation():
    eval_path = Path(__file__).parent / "eval_cases.json"
    if not eval_path.exists():
        print(f"Error: {eval_path} not found.")
        sys.exit(1)

    with open(eval_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    print("============================================================")
    print(f" Starting Expense Copilot Evaluation ({len(cases)} cases)")
    print("============================================================")

    passed_count = 0
    results = {}

    for case in cases:
        # Run sequentially with rate limiting delays built in
        success, details = await evaluate_case(case)
        if success:
            passed_count += 1
        results[case["id"]] = {
            "passed": success,
            "details": details
        }

    print("\n============================================================")
    print(" EVALUATION SCORECARD")
    print("============================================================")
    for case_id, status in results.items():
        outcome = "PASS" if status["passed"] else "FAIL"
        print(f"  - {case_id:<35}: {outcome}")
    
    score = (passed_count / len(cases)) * 100
    print(f"\nFinal Score: {passed_count}/{len(cases)} passed ({score:.1f}%)")
    
    if passed_count == len(cases):
        print("Success: All evaluation cases passed!")
        sys.exit(0)
    else:
        print("Failure: One or more evaluation cases failed.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_evaluation())
