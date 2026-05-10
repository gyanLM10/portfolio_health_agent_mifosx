"""
Portfolio Health Agent — Decision Logger (Audit Trail)
Every agent decision is logged with timestamp, snapshot, risk assessment, action taken, and reasoning chain.
Logs are persisted to SQLite for compliance and review.
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional


DB_PATH = Path(__file__).parent / "agent_memory.db"


def init_decision_log_table():
    """Create the decision_log table if it doesn't exist."""
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS decision_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            scan_id TEXT,
            loan_id INTEGER,
            client_id INTEGER,
            client_name TEXT,
            risk_score REAL,
            risk_level TEXT,
            action_taken TEXT,
            action_result TEXT,
            input_snapshot TEXT,
            factor_breakdown TEXT,
            agent_reasoning TEXT,
            approved_by TEXT DEFAULT NULL,
            approved_at TEXT DEFAULT NULL
        )
    ''')
    conn.commit()
    conn.close()


def log_decision(
    scan_id: str,
    loan_id: int,
    client_id: int,
    client_name: str,
    risk_score: float,
    risk_level: str,
    action_taken: str,
    action_result: Optional[dict] = None,
    input_snapshot: Optional[dict] = None,
    factor_breakdown: Optional[dict] = None,
    agent_reasoning: Optional[str] = None,
):
    """
    Log a single agent decision to the audit trail.
    Called after every risk assessment + action execution.
    """
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute('''
        INSERT INTO decision_log
        (timestamp, scan_id, loan_id, client_id, client_name, risk_score,
         risk_level, action_taken, action_result, input_snapshot,
         factor_breakdown, agent_reasoning)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        datetime.utcnow().isoformat(),
        scan_id,
        loan_id,
        client_id,
        client_name,
        risk_score,
        risk_level,
        action_taken,
        json.dumps(action_result) if action_result else None,
        json.dumps(input_snapshot) if input_snapshot else None,
        json.dumps(factor_breakdown) if factor_breakdown else None,
        agent_reasoning,
    ))
    conn.commit()
    conn.close()


def get_decision_log(limit: int = 100) -> list:
    """Retrieve recent decisions from the audit trail."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM decision_log ORDER BY id DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_decisions_for_scan(scan_id: str) -> list:
    """Retrieve all decisions from a specific scan."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM decision_log WHERE scan_id = ? ORDER BY id", (scan_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_portfolio_stats() -> dict:
    """Aggregate statistics for the portfolio dashboard."""
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()

    # Total decisions logged
    c.execute("SELECT COUNT(*) FROM decision_log")
    total = c.fetchone()[0]

    # Breakdown by risk level
    c.execute("""
        SELECT risk_level, COUNT(*) as count
        FROM decision_log
        GROUP BY risk_level
    """)
    by_level = {row[0]: row[1] for row in c.fetchall()}

    # Breakdown by action
    c.execute("""
        SELECT action_taken, COUNT(*) as count
        FROM decision_log
        GROUP BY action_taken
    """)
    by_action = {row[0]: row[1] for row in c.fetchall()}

    # Average risk score
    c.execute("SELECT AVG(risk_score) FROM decision_log")
    avg_score = c.fetchone()[0] or 0

    # Escalation approval rate
    c.execute("SELECT COUNT(*) FROM escalations WHERE status = 'APPROVED'")
    approved = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM escalations WHERE status IN ('APPROVED', 'DISMISSED')")
    resolved = c.fetchone()[0]

    conn.close()

    return {
        "total_decisions": total,
        "by_risk_level": by_level,
        "by_action": by_action,
        "average_risk_score": round(avg_score, 1),
        "escalation_approval_rate": f"{(approved / resolved * 100):.0f}%" if resolved > 0 else "N/A",
    }
