# Portfolio Health Agent — Test Suite
# 6 unit tests covering risk engine calibration, classification, and action mapping.
#
# Run with:  python -m pytest test_agent.py -v

import pytest
from risk_engine import (
    LoanProfile, RiskAssessment, assess_risk,
    classify_risk, recommend_action,
    _score_arrears, _score_repayment_history,
    _score_account_age, _score_loan_ratio, _score_missed_payments,
)


# ─── Test 1: Risk Classification Boundaries ────────────────────────────────────
def test_risk_classification_boundaries():
    """Verify that classify_risk maps score ranges to correct levels."""
    assert classify_risk(0) == "LOW"
    assert classify_risk(10) == "LOW"
    assert classify_risk(24) == "LOW"
    assert classify_risk(25) == "MEDIUM"
    assert classify_risk(49) == "MEDIUM"
    assert classify_risk(50) == "HIGH"
    assert classify_risk(74) == "HIGH"
    assert classify_risk(75) == "CRITICAL"
    assert classify_risk(100) == "CRITICAL"


# ─── Test 2: Action Recommendation Mapping ─────────────────────────────────────
def test_action_recommendation_mapping():
    """Verify that each risk level maps to the correct pre-approved action."""
    assert recommend_action("LOW") == "MONITOR"
    assert recommend_action("MEDIUM") == "SEND_REMINDER"
    assert recommend_action("HIGH") == "SCHEDULE_FOLLOWUP"
    assert recommend_action("CRITICAL") == "ESCALATE_TO_OFFICER"
    # Unknown level falls back to MONITOR
    assert recommend_action("UNKNOWN") == "MONITOR"


# ─── Test 3: High-Risk Profile Calibration ─────────────────────────────────────
def test_high_risk_profile_scores_correctly():
    """
    A severely overdue loan with poor repayment should score HIGH or CRITICAL.
    Profile: 60 days overdue, 0/12 on-time payments, $8000/$10000 outstanding.
    """
    profile = LoanProfile(
        loan_id=101,
        client_id=1,
        client_name="High Risk Client",
        days_overdue=60,
        outstanding_balance=8000.0,
        original_principal=10000.0,
        total_installments=12,
        installments_paid=2,
        installments_on_time=0,
        consecutive_missed=3,
        loan_term_days=365,
    )
    result = assess_risk(profile)

    assert result.composite_score >= 50, f"Expected HIGH+, got {result.composite_score}"
    assert result.risk_level in ("HIGH", "CRITICAL")
    assert result.recommended_action in ("SCHEDULE_FOLLOWUP", "ESCALATE_TO_OFFICER")
    assert "60 days overdue" in result.explanation
    assert result.factor_breakdown["arrears_severity"]["score"] > 0


# ─── Test 4: Low-Risk Profile Calibration ──────────────────────────────────────
def test_low_risk_profile_scores_correctly():
    """
    A healthy loan with on-time payments should score LOW.
    Profile: 0 days overdue, 10/10 on-time payments, $1000/$10000 outstanding.
    """
    profile = LoanProfile(
        loan_id=202,
        client_id=2,
        client_name="Good Client",
        days_overdue=0,
        outstanding_balance=1000.0,
        original_principal=10000.0,
        total_installments=10,
        installments_paid=10,
        installments_on_time=10,
        consecutive_missed=0,
        account_open_date="2022-01-15",
        loan_term_days=365,
    )
    result = assess_risk(profile)

    assert result.composite_score < 25, f"Expected LOW, got {result.composite_score}"
    assert result.risk_level == "LOW"
    assert result.recommended_action == "MONITOR"


# ─── Test 5: Individual Factor Scoring ──────────────────────────────────────────
def test_individual_factor_scores():
    """Verify each factor scorer returns values in the 0-100 range."""
    # Arrears: 0 days → 0, 90 days on 365 term → ~49
    assert _score_arrears(0, 365) == 0.0
    assert 40 < _score_arrears(90, 365) < 60

    # Repayment: 10/10 on-time → 0, 0/10 → 100
    assert _score_repayment_history(10, 10) == 0.0
    assert _score_repayment_history(0, 10) == 100.0

    # Account age: recent → high, old → low
    assert _score_account_age("2026-04-01") > 30  # ~1 month old
    assert _score_account_age("2020-01-01") < 25  # 6+ years old

    # Loan ratio: 0/10000 → 0, 10000/10000 → 100
    assert _score_loan_ratio(0, 10000) == 0.0
    assert _score_loan_ratio(10000, 10000) == 100.0

    # Missed payments: 0 → 0, 3 → 90
    assert _score_missed_payments(0) == 0.0
    assert _score_missed_payments(3) == 90.0


# ─── Test 6: Assessment Output Structure ───────────────────────────────────────
def test_assessment_output_structure():
    """Verify the RiskAssessment output has all required fields for the API."""
    profile = LoanProfile(
        loan_id=303,
        client_id=3,
        client_name="Structure Test",
        days_overdue=30,
        outstanding_balance=5000.0,
        original_principal=10000.0,
        total_installments=12,
        installments_paid=6,
        installments_on_time=4,
        consecutive_missed=1,
        loan_term_days=365,
    )
    result = assess_risk(profile)
    d = result.to_dict()

    # Required fields
    assert "loan_id" in d
    assert "client_id" in d
    assert "client_name" in d
    assert "composite_score" in d
    assert "risk_level" in d
    assert "recommended_action" in d
    assert "explanation" in d
    assert "factor_breakdown" in d

    # Factor breakdown has all 5 factors
    fb = d["factor_breakdown"]
    assert "arrears_severity" in fb
    assert "repayment_history" in fb
    assert "account_age" in fb
    assert "loan_ratio" in fb
    assert "missed_payments" in fb

    # Each factor has score, weight, detail
    for factor_name, factor in fb.items():
        assert "score" in factor, f"{factor_name} missing 'score'"
        assert "weight" in factor, f"{factor_name} missing 'weight'"
        assert "detail" in factor, f"{factor_name} missing 'detail'"


# ─── Run directly ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
