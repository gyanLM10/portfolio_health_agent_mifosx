"""
Portfolio Health Agent — Core LangGraph Engine
Connects a LangChain ReAct agent to the Rust MCP Server over stdio.
"""
import asyncio
import json
import os
import sqlite3
import uuid
from pathlib import Path
from contextlib import AsyncExitStack
from datetime import datetime
from dataclasses import asdict

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langchain_mcp_adapters.tools import convert_mcp_tool_to_langchain_tool
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from dotenv import load_dotenv

from risk_engine import LoanProfile, RiskAssessment, assess_risk, classify_risk, recommend_action
from mifos_client import MifosClient
from decision_logger import log_decision, init_decision_log_table

load_dotenv(dotenv_path=Path(__file__).parent / ".env")


MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-4o")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
RUST_MCP_BINARY = os.getenv("RUST_MCP_BINARY_PATH", "../../rust/target/release/mcp-rust-mifosx")
RUST_MCP_TRANSPORT = os.getenv("RUST_MCP_TRANSPORT", "binary")
RUST_MCP_DOCKER_CONTAINER = os.getenv("RUST_MCP_DOCKER_CONTAINER", "mcp-rust-mifosx")

# Persistent memory database
MEMORY_DB_PATH = Path(__file__).parent / "agent_memory.db"

# SQLite DB path for escalations (shared with api_server.py)
ESCALATION_DB_PATH = Path(__file__).parent / "agent_memory.db"


llm = ChatOpenAI(
    model=MODEL_NAME,
    temperature=0,
    max_tokens=2048,
    api_key=OPENAI_API_KEY,
    model_kwargs={"tool_choice": "auto"},
)


SYSTEM_PROMPT = """
╔══════════════════════════════════════════════════════════════════╗
║         PORTFOLIO HEALTH AGENT — AUTONOMOUS MONITOR             ║
║                  MIFOS X BANKING SYSTEM                         ║
╠══════════════════════════════════════════════════════════════════╣
║  You are an autonomous Portfolio Health Agent for Mifos X.       ║
║  Your mission is to proactively monitor loan portfolios,        ║
║  identify at-risk accounts, and report findings with clear,     ║
║  human-readable explanations.                                    ║
╚══════════════════════════════════════════════════════════════════╝

You have access to a live Rust MCP Server connected to Apache Fineract.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MISSION: PORTFOLIO HEALTH SCAN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

When asked to perform a portfolio scan, execute the following steps:

1. 📋 FETCH ALL CLIENTS: Use `list_clients` or `search_clients_by_name` to
   get the current client roster.

2. 🔍 IDENTIFY OVERDUE LOANS: For each client, use `get_overdue_loans` to
   find any loans that are past due. If bulk tools are available, prefer
   `bulk_get_loan_status` for efficiency.

3. 📊 ANALYZE RISK: For each overdue loan, use `get_loan_details` and
   `get_repayment_schedule` to assess:
   - Days past due
   - Outstanding balance
   - Number of missed installments
   - Repayment history pattern

4. 🏷️ CLASSIFY RISK using the 5-Factor Weighted Model:
   - Arrears Severity (50%): Days overdue relative to loan term
   - Repayment History (25%): Ratio of on-time vs total payments
   - Account Age (10%): Maturity of the banking relationship
   - Loan-to-Balance Ratio (10%): Outstanding vs original principal
   - Missed Payments (5%): Consecutive missed installments

5. 📝 EXPLAIN: For EVERY at-risk account, provide a clear, human-readable
   explanation of WHY it was flagged. Include specific numbers and the
   factor breakdown.

6. 🎯 RECOMMEND ACTION based on risk level:
   - LOW (0-24):      MONITOR — No immediate action needed
   - MEDIUM (25-49):  SEND_REMINDER — Automated payment reminder
   - HIGH (50-74):    SCHEDULE_FOLLOWUP — Officer visit scheduled
   - CRITICAL (75+):  ESCALATE_TO_OFFICER — Immediate human review

7. 📋 REPORT: Return your findings as a structured JSON array with this
   exact schema for each account:
   ```json
   {
     "account_id": "<loan_id>",
     "client_id": "<client_id>",
     "client_name": "<full_name>",
     "risk_score": <0-100>,
     "risk_level": "LOW|MEDIUM|HIGH|CRITICAL",
     "days_overdue": <number>,
     "outstanding_balance": <amount>,
     "original_principal": <amount>,
     "installments_paid": <number>,
     "total_installments": <number>,
     "consecutive_missed": <number>,
     "explanation": "<human-readable explanation with factor breakdown>",
     "recommended_action": "MONITOR|SEND_REMINDER|SCHEDULE_FOLLOWUP|ESCALATE_TO_OFFICER"
   }
   ```

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRITICAL RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. FACTS ONLY: Only report data explicitly returned by MCP tools.
   NEVER invent client names, IDs, amounts, or dates.
2. NO HALLUCINATED IDs: If you don't have an ID, search for it first.
3. COMPLETE REPORTING: Report EVERY overdue account found. Never truncate.
4. AUTONOMOUS EXECUTION: Do NOT ask for confirmation between steps.
   Execute the full scan pipeline autonomously.
5. ALWAYS include the structured JSON report at the end of your response.
6. INCLUDE ALL FIELDS needed for the 5-factor model in your JSON output.
"""



def _get_server_params() -> StdioServerParameters:
    """Build the StdioServerParameters to connect to the Rust MCP binary."""
    if RUST_MCP_TRANSPORT == "docker":
        # Route into Docker container — same pattern as rust/agent.py
        return StdioServerParameters(
            command="docker",
            args=["exec", "-i", RUST_MCP_DOCKER_CONTAINER, "mcp-rust-mifosx"],
        )
    else:
        # Local binary — resolve path relative to this file
        binary_path = Path(__file__).parent / RUST_MCP_BINARY
        resolved = binary_path.resolve()
        if not resolved.exists():
            raise FileNotFoundError(
                f"Rust MCP binary not found at: {resolved}\n"
                f"Build it with: cd rust && cargo build --release"
            )
        return StdioServerParameters(
            command=str(resolved),
            args=[],
        )


async def _connect_and_load_tools(exit_stack: AsyncExitStack):
    """
    Opens a stdio connection to the Rust MCP server, initializes the MCP
    session, and converts all discovered tools into LangChain-compatible
    tool objects. Returns (session, tools).

    This follows the exact same paginated loading pattern as rust/agent.py.
    """
    server_params = _get_server_params()

    print("🔌 Connecting to Rust MCP Server (stdio)...", flush=True)
    read, write = await exit_stack.enter_async_context(stdio_client(server_params))

    print("🤝 Initializing MCP session...", flush=True)
    session = await exit_stack.enter_async_context(ClientSession(read, write))
    await session.initialize()

    # Paginated tool loader — ensures ALL tools are fetched (same as rust/agent.py)
    print("📚 Syncing tools from Rust Server...", flush=True)
    all_mcp_tools = []
    cursor = None
    while True:
        try:
            result = await asyncio.wait_for(session.list_tools(cursor=cursor), timeout=10)
            all_mcp_tools.extend(result.tools)
            cursor = result.nextCursor
            if not cursor:
                break
        except Exception as e:
            print(f"⚠️  Tool fetch error (continuing): {e}", flush=True)
            break

    print(f"⚙️  Converting {len(all_mcp_tools)} tools to LangChain format...", flush=True)
    tools = [
        convert_mcp_tool_to_langchain_tool(session, t)
        for t in all_mcp_tools
    ]

    print(f"✅ Toolkit ready ({len(tools)} tools from Rust server).", flush=True)
    return session, tools



def _build_loan_profile(finding: dict) -> LoanProfile:
    """Convert an agent JSON finding into a LoanProfile for the risk engine."""
    return LoanProfile(
        loan_id=int(finding.get("account_id", finding.get("loan_id", 0))),
        client_id=int(finding.get("client_id", 0)),
        client_name=finding.get("client_name", "Unknown"),
        days_overdue=int(finding.get("days_overdue", 0)),
        outstanding_balance=float(finding.get("outstanding_balance", 0)),
        original_principal=float(finding.get("original_principal", finding.get("outstanding_balance", 1))),
        total_installments=int(finding.get("total_installments", 1)),
        installments_paid=int(finding.get("installments_paid", 0)),
        installments_on_time=int(finding.get("installments_on_time", finding.get("installments_paid", 0))),
        consecutive_missed=int(finding.get("consecutive_missed", 0)),
        account_open_date=finding.get("account_open_date"),
        loan_term_days=int(finding.get("loan_term_days", 365)),
    )


async def _execute_action(mifos: MifosClient, assessment: RiskAssessment) -> dict:
    """Execute the pre-approved action recommended by the risk engine."""
    action = assessment.recommended_action

    if action == "SEND_REMINDER":
        return await mifos.send_reminder(
            client_id=assessment.client_id,
            loan_id=assessment.loan_id,
            message=f"Payment reminder: Your loan #{assessment.loan_id} is overdue. "
                    f"Risk level: {assessment.risk_level}.",
        )
    elif action == "SCHEDULE_FOLLOWUP":
        return await mifos.schedule_followup(
            client_id=assessment.client_id,
            loan_id=assessment.loan_id,
            reason=assessment.explanation,
        )
    elif action == "ESCALATE_TO_OFFICER":
        return await mifos.escalate_to_officer(
            client_id=assessment.client_id,
            loan_id=assessment.loan_id,
            risk_score=assessment.composite_score,
            explanation=assessment.explanation,
        )
    else:
        # MONITOR — no action needed
        return {"status": "monitoring", "loan_id": assessment.loan_id}


def _process_findings_with_risk_engine(findings: list, scan_id: str) -> list:
    """
    Take raw agent findings, run each through the 5-factor risk engine,
    and log every decision to the audit trail.
    Returns enriched findings with proper risk scores.
    """
    enriched = []
    for finding in findings:
        profile = _build_loan_profile(finding)
        assessment = assess_risk(profile)

        # Log the decision to the audit trail
        log_decision(
            scan_id=scan_id,
            loan_id=assessment.loan_id,
            client_id=assessment.client_id,
            client_name=assessment.client_name,
            risk_score=assessment.composite_score,
            risk_level=assessment.risk_level,
            action_taken=assessment.recommended_action,
            input_snapshot=asdict(profile),
            factor_breakdown=assessment.factor_breakdown,
            agent_reasoning=assessment.explanation,
        )

        enriched.append({
            "account_id": str(assessment.loan_id),
            "client_id": assessment.client_id,
            "client_name": assessment.client_name,
            "risk_score": assessment.composite_score,
            "risk_level": assessment.risk_level,
            "recommended_action": assessment.recommended_action,
            "explanation": assessment.explanation,
            "factor_breakdown": assessment.factor_breakdown,
        })

    return enriched



def _save_escalations(findings: list):
    """Persist findings to the shared SQLite database."""
    conn = sqlite3.connect(str(ESCALATION_DB_PATH))
    c = conn.cursor()
    for finding in findings:
        c.execute('''
            INSERT INTO escalations (account_id, client_name, risk_score, explanation, status)
            VALUES (?, ?, ?, ?, 'PENDING')
        ''', (
            str(finding.get("account_id", "")),
            finding.get("client_name", "Unknown"),
            finding.get("risk_score", 0),
            finding.get("explanation", "No explanation provided."),
        ))
    conn.commit()
    conn.close()
    print(f"💾 Saved {len(findings)} escalations to database.", flush=True)



def _parse_findings_from_response(response_text: str) -> list:
    """
    Extract JSON findings array from the agent's final response.
    The agent is instructed to return a JSON array; we parse it out.
    """
    import re
    findings = []
    # Try to find a JSON array in the response
    try:
        start = response_text.find("[")
        end = response_text.rfind("]")
        if start != -1 and end != -1 and end > start:
            json_str = response_text[start:end + 1]
            findings = json.loads(json_str)
            if isinstance(findings, list):
                return findings
    except (json.JSONDecodeError, ValueError):
        pass

    # Fallback: try to find individual {...} objects
    json_blocks = re.findall(r'\{[^{}]+\}', response_text)
    for block in json_blocks:
        try:
            obj = json.loads(block)
            if "account_id" in obj or "risk_score" in obj:
                findings.append(obj)
        except (json.JSONDecodeError, ValueError):
            continue

    return findings



async def run_portfolio_scan_async():
    """
    The main scan workflow. Opens a real connection to the Rust MCP server,
    creates a LangChain ReAct agent with all 89 tools, and instructs it to
    perform an autonomous portfolio health scan. Raw findings are then
    processed through the 5-factor risk engine and logged to the audit trail.
    """
    # Ensure decision log table exists
    init_decision_log_table()

    scan_id = f"scan-{uuid.uuid4().hex[:8]}"

    print("\n" + "=" * 60, flush=True)
    print("🏥 Portfolio Health Agent — Starting Scan", flush=True)
    print(f"   Scan ID : {scan_id}", flush=True)
    print(f"   Model   : {MODEL_NAME}", flush=True)
    print(f"   Transport: {RUST_MCP_TRANSPORT}", flush=True)
    print("=" * 60 + "\n", flush=True)

    exit_stack = AsyncExitStack()

    try:
        async with exit_stack:
            # 1. Initialize persistent memory
            print("💾 Initializing persistent memory...", flush=True)
            memory = await exit_stack.enter_async_context(
                AsyncSqliteSaver.from_conn_string(str(MEMORY_DB_PATH))
            )

            # 2. Connect to Rust MCP Server and load all tools
            session, tools = await _connect_and_load_tools(exit_stack)

            # 3. Create MifosClient for action execution
            mifos = MifosClient(session)

            # 4. Create the ReAct agent (same pattern as rust/agent.py)
            agent = create_react_agent(
                llm,
                tools,
                checkpointer=memory,
                prompt=SYSTEM_PROMPT,
            )

            # 5. Run the autonomous scan
            thread_id = f"health-{scan_id}"
            config = {"configurable": {"thread_id": thread_id}}

            scan_prompt = (
                "Perform a complete Portfolio Health Scan now. "
                "Fetch all clients, check for overdue loans across the portfolio, "
                "analyze risk for each overdue account, and return a structured "
                "JSON report of all findings. For each loan, include: account_id, "
                "client_id, client_name, days_overdue, outstanding_balance, "
                "original_principal, installments_paid, total_installments, "
                "consecutive_missed. Execute autonomously — do not ask "
                "for confirmation."
            )

            print(f"🚀 Dispatching scan to LLM agent (thread: {thread_id})...\n", flush=True)

            final_response = ""
            async for chunk in agent.astream(
                {"messages": [("human", scan_prompt)]},
                config=config,
                stream_mode="values",
                recursion_limit=100,
            ):
                message = chunk["messages"][-1]

                # Log tool calls as they happen
                if message.type == "ai" and message.tool_calls:
                    for tc in message.tool_calls:
                        print(f"🛠️  Calling Tool: {tc['name']} with {tc['args']}", flush=True)

                # Capture the final AI response
                if message.type == "ai" and not message.tool_calls and message.content:
                    final_response = message.content
                    print(f"\n🤖 Agent Response:\n{message.content}\n", flush=True)

            # 6. Parse findings and run through the 5-factor risk engine
            if final_response:
                raw_findings = _parse_findings_from_response(final_response)
                if raw_findings:
                    print(f"\n📊 Running 5-factor risk assessment on {len(raw_findings)} accounts...", flush=True)
                    enriched = _process_findings_with_risk_engine(raw_findings, scan_id)

                    # 7. Execute pre-approved actions for each finding
                    print("🎯 Executing pre-approved actions...", flush=True)
                    for finding in enriched:
                        profile = _build_loan_profile(finding)
                        assessment = assess_risk(profile)
                        action_result = await _execute_action(mifos, assessment)
                        print(f"   → {assessment.recommended_action} for Loan #{assessment.loan_id}: {action_result.get('status', 'done')}", flush=True)

                    # 8. Save escalations to dashboard
                    _save_escalations(enriched)
                    print(f"\n✅ Scan {scan_id} complete. {len(enriched)} accounts processed.", flush=True)

                    # Summary
                    by_level = {}
                    for f in enriched:
                        level = f["risk_level"]
                        by_level[level] = by_level.get(level, 0) + 1
                    print(f"   Risk breakdown: {by_level}", flush=True)
                else:
                    print("\n✅ Scan complete. No at-risk accounts found.", flush=True)
            else:
                print("\n⚠️ Scan complete but agent returned no response.", flush=True)

    except FileNotFoundError as e:
        print(f"\n❌ Configuration Error: {e}", flush=True)
        raise
    except Exception as e:
        print(f"\n❌ Scan Error: {e}", flush=True)
        raise


def run_portfolio_scan():
    """Synchronous wrapper for the async scan — called by FastAPI's BackgroundTasks."""
    asyncio.run(run_portfolio_scan_async())



if __name__ == "__main__":
    print("\nRunning Portfolio Health Scan from CLI...\n")
    asyncio.run(run_portfolio_scan_async())
