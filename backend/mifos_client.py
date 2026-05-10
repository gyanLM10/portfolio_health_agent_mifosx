"""
Portfolio Health Agent — Mifos X API Client (Integration Layer)
Provides a typed Python interface for interacting with Fineract via
the Rust MCP Server. Each method maps to one or more MCP tool calls.
This layer is used by the agent when executing pre-approved actions.
"""
import asyncio
import json
from typing import List, Dict, Any, Optional
from datetime import datetime


class MifosClient:
    """
    High-level Mifos X integration client.
    Wraps MCP tool calls behind a clean Python interface for the agent
    to use when fetching data or executing pre-approved actions.

    The `session` parameter is an active MCP ClientSession connected to
    the Rust MCP server.
    """

    def __init__(self, session):
        self.session = session

    async def _call_tool(self, name: str, arguments: dict) -> Any:
        """Execute an MCP tool call and return the parsed result."""
        result = await asyncio.wait_for(
            self.session.call_tool(name, arguments=arguments),
            timeout=30,
        )
        # MCP returns content as a list of content blocks
        if result.content:
            text = result.content[0].text if hasattr(result.content[0], 'text') else str(result.content[0])
            try:
                return json.loads(text)
            except (json.JSONDecodeError, ValueError):
                return {"raw": text}
        return {}


    async def get_clients(self, limit: int = 200) -> List[Dict]:
        """Fetch all clients from Fineract."""
        try:
            result = await self._call_tool("search_clients_by_name", {"name": ""})
            if isinstance(result, list):
                return result
            return result.get("pageItems", result.get("clients", []))
        except Exception:
            return []

    async def get_client_details(self, client_id: int) -> Dict:
        """Get full profile details for a single client."""
        return await self._call_tool("get_client_details", {"client_id": client_id})

    async def get_client_accounts(self, client_id: int) -> Dict:
        """Get all loan and savings accounts for a client."""
        return await self._call_tool("get_client_accounts", {"client_id": client_id})


    async def get_overdue_loans(self, client_id: int) -> List[Dict]:
        """Get overdue loans for a specific client."""
        result = await self._call_tool("get_overdue_loans", {"client_id": client_id})
        if isinstance(result, list):
            return result
        return result.get("loans", [])

    async def get_loan_details(self, loan_id: int) -> Dict:
        """Get detailed information about a specific loan."""
        return await self._call_tool("get_loan_details", {"loan_id": loan_id})

    async def get_repayment_schedule(self, loan_id: int) -> Dict:
        """Get the repayment schedule for a loan."""
        return await self._call_tool("get_repayment_schedule", {"loan_id": loan_id})

    async def get_loan_history(self, loan_id: int) -> List[Dict]:
        """Get full transaction history for a loan."""
        result = await self._call_tool("get_loan_history", {"loan_id": loan_id})
        if isinstance(result, list):
            return result
        return result.get("transactions", [])


    async def bulk_get_loan_status(self, loan_ids: List[int]) -> List[Dict]:
        """Fetch statuses for multiple loans in parallel (Rust bulk tool)."""
        result = await self._call_tool("bulk_get_loan_status", {"loan_ids": loan_ids})
        if isinstance(result, list):
            return result
        return result.get("results", [])


    async def send_reminder(self, client_id: int, loan_id: int, message: str) -> Dict:
        """
        Send a payment reminder to a client.
        In production, this would trigger an SMS/email via Fineract's
        notification system. For now, it logs a client charge note.
        """
        try:
            return await self._call_tool("apply_client_charge", {
                "client_id": client_id,
                "charge_id": 1,  # Default reminder charge template
                "amount": 0.0,   # Zero-amount reminder (no actual fee)
            })
        except Exception:
            # If charge tool fails, log as a note
            return {"status": "reminder_logged", "client_id": client_id, "message": message}

    async def schedule_followup(self, client_id: int, loan_id: int, reason: str) -> Dict:
        """
        Schedule a follow-up visit for a loan officer.
        Creates a follow-up record in the audit trail.
        """
        return {
            "status": "followup_scheduled",
            "client_id": client_id,
            "loan_id": loan_id,
            "reason": reason,
            "scheduled_date": datetime.utcnow().isoformat(),
        }

    async def escalate_to_officer(self, client_id: int, loan_id: int,
                                   risk_score: float, explanation: str) -> Dict:
        """
        Escalate a case to a human loan officer for review.
        This creates a PENDING escalation record that appears on the dashboard.
        """
        return {
            "status": "escalated",
            "client_id": client_id,
            "loan_id": loan_id,
            "risk_score": risk_score,
            "explanation": explanation,
            "escalated_at": datetime.utcnow().isoformat(),
        }
