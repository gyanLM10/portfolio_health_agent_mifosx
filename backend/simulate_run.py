import json
from risk_engine import LoanProfile, assess_risk
from decision_logger import init_decision_log_table, log_decision, get_decision_log, get_portfolio_stats
from api_server import init_db
init_db()

print("==================================================")
print("  Portfolio Health Agent — Feature Demonstration  ")
print("==================================================\n")

print("--- 1. Initializing Decision Logger ---")
init_decision_log_table()
print("Decision log table initialized.\n")

print("--- 2. Assessing HIGH RISK Profile ---")
high_risk_profile = LoanProfile(
    loan_id=101, client_id=1, client_name="Alice Smith", days_overdue=45,
    outstanding_balance=8000, original_principal=10000,
    total_installments=12, installments_on_time=2, consecutive_missed=3
)
high_risk_assessment = assess_risk(high_risk_profile)
print(f"Profile: {high_risk_profile.client_name}, {high_risk_profile.days_overdue} days overdue")
print(f"Risk Score: {high_risk_assessment.composite_score}/100")
print(f"Risk Level: {high_risk_assessment.risk_level}")
print(f"Recommended Action: {high_risk_assessment.recommended_action}")
print(f"Explanation:\n  {high_risk_assessment.explanation}")
print("Factor Breakdown:")
print(json.dumps(high_risk_assessment.factor_breakdown, indent=2))
print()

print("--- 3. Assessing LOW RISK Profile ---")
low_risk_profile = LoanProfile(
    loan_id=202, client_id=2, client_name="Bob Jones", days_overdue=0,
    outstanding_balance=1000, original_principal=10000,
    total_installments=10, installments_on_time=10, consecutive_missed=0
)
low_risk_assessment = assess_risk(low_risk_profile)
print(f"Profile: {low_risk_profile.client_name}, {low_risk_profile.days_overdue} days overdue")
print(f"Risk Score: {low_risk_assessment.composite_score}/100")
print(f"Risk Level: {low_risk_assessment.risk_level}")
print(f"Recommended Action: {low_risk_assessment.recommended_action}")
print(f"Explanation:\n  {low_risk_assessment.explanation}")
print()

print("--- 4. Logging Decisions ---")
log_decision(
    scan_id="scan-demo", loan_id=high_risk_assessment.loan_id, client_id=high_risk_assessment.client_id,
    client_name=high_risk_assessment.client_name, risk_score=high_risk_assessment.composite_score,
    risk_level=high_risk_assessment.risk_level, action_taken=high_risk_assessment.recommended_action,
    factor_breakdown=high_risk_assessment.factor_breakdown, agent_reasoning=high_risk_assessment.explanation
)
log_decision(
    scan_id="scan-demo", loan_id=low_risk_assessment.loan_id, client_id=low_risk_assessment.client_id,
    client_name=low_risk_assessment.client_name, risk_score=low_risk_assessment.composite_score,
    risk_level=low_risk_assessment.risk_level, action_taken=low_risk_assessment.recommended_action,
    factor_breakdown=low_risk_assessment.factor_breakdown, agent_reasoning=low_risk_assessment.explanation
)
print("Decisions logged successfully.\n")

print("--- 5. Retrieving Audit Trail ---")
logs = get_decision_log(limit=2)
for log in logs:
    print(f"[{log['timestamp']}] Loan {log['loan_id']} ({log['client_name']}): {log['risk_level']} -> {log['action_taken']}")
print()

print("--- 6. Retrieving Portfolio Stats ---")
stats = get_portfolio_stats()
print(json.dumps(stats, indent=2))
print()
