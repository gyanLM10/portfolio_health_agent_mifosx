"""
Portfolio Health Agent — 5-Factor Weighted Risk Assessment Engine
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional



@dataclass
class LoanProfile:
    """Raw data extracted from Fineract via MCP tools."""
    loan_id: int
    client_id: int
    client_name: str
    days_overdue: int = 0
    outstanding_balance: float = 0.0
    original_principal: float = 1.0
    total_installments: int = 1
    installments_paid: int = 0
    installments_on_time: int = 0
    consecutive_missed: int = 0
    account_open_date: Optional[str] = None   # ISO date string
    loan_term_days: int = 365


@dataclass
class RiskAssessment:
    """Output of the 5-factor risk engine."""
    loan_id: int
    client_id: int
    client_name: str
    composite_score: float
    risk_level: str                          # LOW / MEDIUM / HIGH / CRITICAL
    recommended_action: str                  # MONITOR / SEND_REMINDER / SCHEDULE_FOLLOWUP / ESCALATE_TO_OFFICER
    explanation: str                         # Human-readable reasoning
    factor_breakdown: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)



WEIGHT_ARREARS          = 0.50
WEIGHT_REPAYMENT        = 0.25
WEIGHT_ACCOUNT_AGE      = 0.10
WEIGHT_LOAN_RATIO       = 0.10
WEIGHT_MISSED_PAYMENTS  = 0.05

assert abs((WEIGHT_ARREARS + WEIGHT_REPAYMENT + WEIGHT_ACCOUNT_AGE +
            WEIGHT_LOAN_RATIO + WEIGHT_MISSED_PAYMENTS) - 1.0) < 1e-9, \
    "Weights must sum to 1.0"



def _score_arrears(days_overdue: int, loan_term_days: int) -> float:
    """
    Factor 1 (50%): Arrears severity.
    Measures days overdue as a proportion of the loan term, capped at 100.
    - 0 days overdue  → 0
    - 90+ days        → 90–100 (depending on term)
    """
    if days_overdue <= 0:
        return 0.0
    # Normalize: 90 days overdue on a 365-day loan is severe
    raw = (days_overdue / max(loan_term_days, 1)) * 200
    return min(raw, 100.0)


def _score_repayment_history(installments_on_time: int, total_installments: int) -> float:
    """
    Factor 2 (25%): Repayment consistency.
    High score = poor repayment history.
    - 100% on-time → score 0
    - 0% on-time   → score 100
    """
    if total_installments <= 0:
        return 50.0  # No data → neutral
    on_time_ratio = installments_on_time / total_installments
    return (1.0 - on_time_ratio) * 100.0


def _score_account_age(account_open_date: Optional[str]) -> float:
    """
    Factor 3 (10%): Account maturity.
    Newer accounts are riskier (less relationship history).
    - < 3 months  → score 80
    - 3-12 months → score 40
    - 1-3 years   → score 20
    - 3+ years    → score 5
    """
    if not account_open_date:
        return 50.0  # No data → neutral
    try:
        opened = datetime.fromisoformat(account_open_date.replace("Z", "+00:00"))
        age_days = (datetime.now(opened.tzinfo) - opened).days
    except (ValueError, TypeError):
        return 50.0

    if age_days < 90:
        return 80.0
    elif age_days < 365:
        return 40.0
    elif age_days < 1095:
        return 20.0
    else:
        return 5.0


def _score_loan_ratio(outstanding_balance: float, original_principal: float) -> float:
    """
    Factor 4 (10%): Loan-to-balance ratio.
    High remaining balance relative to principal = higher risk.
    - Fully repaid (0%) → score 0
    - 100% outstanding  → score 100
    """
    if original_principal <= 0:
        return 50.0
    ratio = outstanding_balance / original_principal
    return min(ratio * 100.0, 100.0)


def _score_missed_payments(consecutive_missed: int) -> float:
    """
    Factor 5 (5%): Consecutive missed payments.
    - 0 missed → 0
    - 1 missed → 30
    - 2 missed → 60
    - 3+ missed → 90-100
    """
    if consecutive_missed <= 0:
        return 0.0
    return min(consecutive_missed * 30.0, 100.0)



def classify_risk(score: float) -> str:
    """Map a composite score to a human-readable risk level."""
    if score >= 75:
        return "CRITICAL"
    elif score >= 50:
        return "HIGH"
    elif score >= 25:
        return "MEDIUM"
    else:
        return "LOW"


def recommend_action(risk_level: str) -> str:
    """Map a risk level to a pre-approved action."""
    actions = {
        "LOW": "MONITOR",
        "MEDIUM": "SEND_REMINDER",
        "HIGH": "SCHEDULE_FOLLOWUP",
        "CRITICAL": "ESCALATE_TO_OFFICER",
    }
    return actions.get(risk_level, "MONITOR")


def assess_risk(profile: LoanProfile) -> RiskAssessment:
    """
    Run the full 5-factor weighted risk assessment on a loan profile.
    Returns a RiskAssessment with composite score, classification,
    recommended action, and a transparent explanation of each factor.
    """
    # Score each factor
    f1 = _score_arrears(profile.days_overdue, profile.loan_term_days)
    f2 = _score_repayment_history(profile.installments_on_time, profile.total_installments)
    f3 = _score_account_age(profile.account_open_date)
    f4 = _score_loan_ratio(profile.outstanding_balance, profile.original_principal)
    f5 = _score_missed_payments(profile.consecutive_missed)

    # Weighted composite
    composite = (
        f1 * WEIGHT_ARREARS +
        f2 * WEIGHT_REPAYMENT +
        f3 * WEIGHT_ACCOUNT_AGE +
        f4 * WEIGHT_LOAN_RATIO +
        f5 * WEIGHT_MISSED_PAYMENTS
    )
    composite = round(min(composite, 100.0), 1)

    risk_level = classify_risk(composite)
    action = recommend_action(risk_level)

    # Build transparent explanation
    factor_breakdown = {
        "arrears_severity":   {"score": round(f1, 1), "weight": "50%", "detail": f"{profile.days_overdue} days overdue on {profile.loan_term_days}-day term"},
        "repayment_history":  {"score": round(f2, 1), "weight": "25%", "detail": f"{profile.installments_on_time}/{profile.total_installments} installments paid on time"},
        "account_age":        {"score": round(f3, 1), "weight": "10%", "detail": f"Account opened {profile.account_open_date or 'unknown'}"},
        "loan_ratio":         {"score": round(f4, 1), "weight": "10%", "detail": f"${profile.outstanding_balance:,.2f} outstanding of ${profile.original_principal:,.2f} principal"},
        "missed_payments":    {"score": round(f5, 1), "weight": "5%",  "detail": f"{profile.consecutive_missed} consecutive missed installments"},
    }

    explanation = (
        f"Loan #{profile.loan_id} for {profile.client_name} scored {composite}/100 ({risk_level}). "
        f"Primary drivers: {profile.days_overdue} days overdue (arrears score {f1:.0f}/100), "
        f"{profile.installments_on_time}/{profile.total_installments} on-time payments "
        f"(repayment score {f2:.0f}/100), "
        f"${profile.outstanding_balance:,.2f} of ${profile.original_principal:,.2f} still outstanding "
        f"(ratio score {f4:.0f}/100). "
        f"Recommended action: {action}."
    )

    return RiskAssessment(
        loan_id=profile.loan_id,
        client_id=profile.client_id,
        client_name=profile.client_name,
        composite_score=composite,
        risk_level=risk_level,
        recommended_action=action,
        explanation=explanation,
        factor_breakdown=factor_breakdown,
    )
