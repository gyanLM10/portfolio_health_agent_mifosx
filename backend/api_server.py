"""
Portfolio Health Agent — FastAPI Gateway (9 REST Endpoints)
Serves the Angular frontend and dispatches scans to the LangGraph agent.
"""
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
import sqlite3
from pathlib import Path

from decision_logger import (
    init_decision_log_table,
    get_decision_log,
    get_portfolio_stats,
)
from risk_engine import LoanProfile, assess_risk

app = FastAPI(
    title="Portfolio Health Agent API",
    description="REST gateway for the Mifos X Portfolio Health Agent. "
                "9 endpoints for loan officer oversight, agent triggering, "
                "audit trail access, and ad-hoc risk assessment.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = Path(__file__).parent / "agent_memory.db"



def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS escalations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id TEXT,
            client_name TEXT,
            risk_score REAL,
            explanation TEXT,
            status TEXT DEFAULT 'PENDING',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS scan_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            status TEXT DEFAULT 'RUNNING',
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()
    # Also init the decision log table
    init_decision_log_table()


@app.on_event("startup")
def startup_event():
    init_db()



def _run_scan_with_logging():
    """Wrapper that logs scan start/end to the database, then runs the agent."""
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("INSERT INTO scan_log (status) VALUES ('RUNNING')")
    scan_id = c.lastrowid
    conn.commit()
    conn.close()

    try:
        from graph import run_portfolio_scan
        run_portfolio_scan()
        status = "COMPLETED"
    except Exception as e:
        print(f"❌ Scan failed: {e}", flush=True)
        status = f"FAILED: {str(e)[:200]}"

    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute(
        "UPDATE scan_log SET status = ?, completed_at = ? WHERE id = ?",
        (status, datetime.utcnow().isoformat(), scan_id),
    )
    conn.commit()
    conn.close()


@app.post("/scan")
async def trigger_scan(background_tasks: BackgroundTasks):
    """
    Triggers an autonomous portfolio health scan.
    The scan connects to the Rust MCP Server, fetches overdue loans via
    Fineract, runs the 5-factor risk engine, executes pre-approved actions,
    and logs all decisions to the audit trail.
    """
    background_tasks.add_task(_run_scan_with_logging)
    return {
        "status": "scan_initiated",
        "message": "Portfolio scan dispatched to the LangChain agent. "
                   "The agent is connecting to the Rust MCP server. "
                   "Poll /scan/status to track progress.",
    }



@app.get("/scan/status")
async def get_scan_status():
    """Returns the status of the most recent scan."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM scan_log ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    if row:
        return dict(row)
    return {"status": "NO_SCANS_YET"}



@app.get("/escalations")
async def get_escalations():
    """Returns all pending escalations for the dashboard, sorted by risk score."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM escalations WHERE status = 'PENDING' ORDER BY risk_score DESC")
    rows = c.fetchall()
    conn.close()
    return {"escalations": [dict(r) for r in rows]}



@app.get("/escalations/all")
async def get_all_escalations():
    """Returns all escalations regardless of status."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM escalations ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return {"escalations": [dict(r) for r in rows]}



class EscalationAction(BaseModel):
    action: str  # "APPROVE" or "DISMISS"


@app.patch("/escalations/{escalation_id}")
async def resolve_escalation(escalation_id: int, body: EscalationAction):
    """
    Human-in-the-loop endpoint. Allows a loan officer to approve or
    dismiss an agent-generated escalation from the Angular dashboard.
    """
    if body.action not in ("APPROVE", "DISMISS"):
        raise HTTPException(status_code=400, detail="Action must be APPROVE or DISMISS")

    new_status = "APPROVED" if body.action == "APPROVE" else "DISMISSED"
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute(
        "UPDATE escalations SET status = ? WHERE id = ?",
        (new_status, escalation_id),
    )
    if c.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Escalation not found")
    conn.commit()
    conn.close()
    return {"id": escalation_id, "status": new_status}



@app.get("/decisions")
async def get_decisions(limit: int = 100):
    """
    Returns the decision audit log. Every agent decision (risk assessment,
    action taken, reasoning chain) is logged here for compliance review.
    """
    decisions = get_decision_log(limit=limit)
    return {"decisions": decisions, "count": len(decisions)}



@app.get("/stats")
async def get_stats():
    """
    Returns aggregate portfolio health statistics:
    total decisions, risk level breakdown, action breakdown,
    average risk score, and escalation approval rate.
    """
    return get_portfolio_stats()



class AssessRequest(BaseModel):
    loan_id: int
    client_id: int = 0
    client_name: str = "Unknown"
    days_overdue: int = 0
    outstanding_balance: float = 0.0
    original_principal: float = Field(default=1.0, gt=0)
    total_installments: int = Field(default=1, ge=1)
    installments_paid: int = 0
    installments_on_time: int = 0
    consecutive_missed: int = 0
    account_open_date: Optional[str] = None
    loan_term_days: int = 365


@app.post("/assess")
async def assess_loan_risk(body: AssessRequest):
    """
    Ad-hoc risk assessment. Submit a loan profile and receive the
    5-factor weighted risk score, classification, recommended action,
    and transparent factor breakdown — without triggering a full scan.
    """
    profile = LoanProfile(
        loan_id=body.loan_id,
        client_id=body.client_id,
        client_name=body.client_name,
        days_overdue=body.days_overdue,
        outstanding_balance=body.outstanding_balance,
        original_principal=body.original_principal,
        total_installments=body.total_installments,
        installments_paid=body.installments_paid,
        installments_on_time=body.installments_on_time,
        consecutive_missed=body.consecutive_missed,
        account_open_date=body.account_open_date,
        loan_term_days=body.loan_term_days,
    )
    assessment = assess_risk(profile)
    return assessment.to_dict()



@app.get("/health")
async def health():
    """Health check for Kubernetes liveness/readiness probes."""
    return {"status": "ok", "service": "portfolio-health-agent", "version": "1.0.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
