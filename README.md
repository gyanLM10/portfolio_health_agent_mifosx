# Portfolio Health Agent — Mifos X AI Agentic Framework

An autonomous AI agent that monitors Mifos X loan portfolios, identifies at-risk accounts using a **5-factor weighted risk model**, executes pre-approved actions, and escalates complex cases to human loan officers with transparent, explainable reasoning.

Built with **LangChain ReAct** pattern + **Rust MCP Server** for high-performance Fineract integration.

---

## Architecture

```
Angular Dashboard ◄── REST API ──► FastAPI Backend
  (localhost:4200)                   (localhost:8000)
                                          │
                                          │ LangChain ReAct Agent
                                          │ + 5-Factor Risk Engine
                                          │ + Decision Logger
                                          │
                                          ▼ MCP Protocol (stdio)
                                   Rust MCP Server
                                   (mcp-rust-mifosx)
                                          │
                                          ▼ REST API
                                   Apache Fineract
                                   (Core Banking)
```

---

## Features

### ✅ Autonomous Portfolio Monitoring
The LangChain ReAct agent autonomously fetches client data, identifies overdue loans, and analyzes risk — without human intervention.

### ✅ 5-Factor Weighted Risk Model
Every loan is scored using a transparent, calibrated model:

| Factor | Weight | Description |
|---|---|---|
| Arrears Severity | **50%** | Days overdue relative to loan term |
| Repayment History | **25%** | Ratio of on-time vs total payments |
| Account Age | **10%** | Maturity of the banking relationship |
| Loan-to-Balance Ratio | **10%** | Outstanding vs original principal |
| Missed Payments | **5%** | Consecutive missed installments |

### ✅ Risk Classification
| Score Range | Level | Action |
|---|---|---|
| 0–24 | LOW | MONITOR |
| 25–49 | MEDIUM | SEND_REMINDER |
| 50–74 | HIGH | SCHEDULE_FOLLOWUP |
| 75–100 | CRITICAL | ESCALATE_TO_OFFICER |

### ✅ Pre-Approved Action Execution
The agent autonomously executes actions based on risk level:
- **MONITOR** — No action, continue tracking
- **SEND_REMINDER** — Automated payment reminder via Fineract
- **SCHEDULE_FOLLOWUP** — Officer visit scheduled with reason
- **ESCALATE_TO_OFFICER** — Flagged for immediate human review

### ✅ Explainable AI Decisions
Every decision includes a human-readable explanation with the exact factor breakdown:
```
Loan #101 for Alice Smith scored 67.3/100 (HIGH).
Primary drivers: 45 days overdue (arrears score 25/100),
2/12 on-time payments (repayment score 83/100),
$8,000 of $10,000 still outstanding (ratio score 80/100).
Recommended action: SCHEDULE_FOLLOWUP.
```

### ✅ Human-in-the-Loop Approval Workflow
Loan officers can review, approve, or dismiss agent escalations via the Angular dashboard using the `PATCH /escalations/{id}` endpoint.

### ✅ Decision Logging & Audit Trail
Every agent decision is persisted to SQLite with:
- Timestamp, scan ID, loan/client identifiers
- Full input snapshot (loan profile data)
- 5-factor breakdown scores
- Agent reasoning chain
- Action taken and result

### ✅ Test Suite (6/6 Passing)
```
test_risk_classification_boundaries     PASSED
test_action_recommendation_mapping      PASSED
test_high_risk_profile_scores_correctly PASSED
test_low_risk_profile_scores_correctly  PASSED
test_individual_factor_scores           PASSED
test_assessment_output_structure        PASSED
```

---

## REST API Reference (9 Endpoints)

| # | Method | Endpoint | Description |
|---|---|---|---|
| 1 | `POST` | `/scan` | Trigger autonomous portfolio scan |
| 2 | `GET` | `/scan/status` | Poll scan progress |
| 3 | `GET` | `/escalations` | Pending escalations (dashboard) |
| 4 | `GET` | `/escalations/all` | All escalations (any status) |
| 5 | `PATCH` | `/escalations/{id}` | Approve or dismiss escalation |
| 6 | `GET` | `/decisions` | Audit trail (decision log) |
| 7 | `GET` | `/stats` | Portfolio aggregate statistics |
| 8 | `POST` | `/assess` | Ad-hoc risk assessment for a loan |
| 9 | `GET` | `/health` | Service health check |

### Example: Ad-hoc Risk Assessment
```bash
curl -X POST http://localhost:8000/assess \
  -H "Content-Type: application/json" \
  -d '{
    "loan_id": 101,
    "client_name": "Alice Smith",
    "days_overdue": 45,
    "outstanding_balance": 8000,
    "original_principal": 10000,
    "total_installments": 12,
    "installments_on_time": 2,
    "consecutive_missed": 3
  }'
```

---

## Project Structure

```
portfolio-health-agent/
├── backend/
│   ├── api_server.py          # FastAPI gateway (9 endpoints)
│   ├── graph.py               # LangChain ReAct agent + MCP integration
│   ├── risk_engine.py         # 5-factor weighted risk assessment
│   ├── mifos_client.py        # Mifos X API client (integration layer)
│   ├── decision_logger.py     # Audit trail persistence
│   ├── test_agent.py          # 6 unit tests
│   ├── requirements.txt       # Python dependencies
│   └── .env                   # Configuration (API keys, binary paths)
└── frontend/
    └── src/app/
        ├── dashboard/         # Angular dashboard component
        │   ├── dashboard.ts
        │   ├── dashboard.html
        │   └── dashboard.css
        ├── api.ts             # Angular API service
        ├── app.ts             # Root component
        └── app.config.ts      # Angular configuration
```

---

## Quick Start

### Prerequisites
- Python 3.10+
- Node.js 18+ (for Angular)
- Rust MCP binary (`cargo build --release` in `mcp-mifosx/rust/`)
- OpenAI API key

### 1. Backend
```bash
cd portfolio-health-agent/backend
source .venv/bin/activate
# Edit .env with your OPENAI_API_KEY and RUST_MCP_BINARY_PATH
python api_server.py
```

### 2. Frontend
```bash
cd portfolio-health-agent/frontend
npm start
```

### 3. Run Tests
```bash
cd portfolio-health-agent/backend
source .venv/bin/activate
python -m pytest test_agent.py -v
```

---

## Extensibility

### Adding a New Risk Factor
1. Add a new `_score_*()` function in `risk_engine.py`
2. Add a new weight constant (ensure all weights sum to 1.0)
3. Include it in the `assess_risk()` composite calculation
4. Update the `factor_breakdown` dict
5. Add a unit test in `test_agent.py`

### Adding a New Pre-Approved Action
1. Add the method to `mifos_client.py`
2. Add the action mapping in `risk_engine.py::recommend_action()`
3. Add the execution branch in `graph.py::_execute_action()`

### Adding a New API Endpoint
1. Add the route in `api_server.py`
2. Add the corresponding method in `frontend/src/app/api.ts`
3. Update the dashboard component if UI changes are needed

---

## License

Mozilla Public License 2.0 — Mifos Initiative
