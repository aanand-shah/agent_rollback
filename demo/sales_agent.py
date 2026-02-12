"""
AI Sales Agent Demo Application.

This demo simulates an AI-driven sales agent that:
1. Qualifies leads based on criteria
2. Moves prospects through a sales pipeline
3. Updates CRM records
4. Can make mistakes that need to be rolled back

All actions are tracked via AgentRollback for recovery.
"""

import asyncio
import random
from datetime import datetime, timedelta
from typing import Any, Optional
from dataclasses import dataclass, field, asdict

from agent_rollback.sdk import AgentRollbackClient
from agent_rollback.models import SessionStatus


@dataclass
class Lead:
    """A sales lead."""
    id: str
    company: str
    contact_name: str
    email: str
    phone: str
    industry: str
    company_size: int
    estimated_value: float
    status: str = "new"
    score: int = 0
    notes: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    last_activity: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class Opportunity:
    """A sales opportunity."""
    id: str
    lead_id: str
    company: str
    contact_name: str
    value: float
    stage: str = "qualification"
    probability: int = 10
    close_date: Optional[str] = None
    notes: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class Deal:
    """A closed deal."""
    id: str
    opportunity_id: str
    company: str
    value: float
    status: str = "won"
    closed_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class CRMDatabase:
    """Simulated CRM database."""

    def __init__(self):
        self.leads: dict[str, Lead] = {}
        self.opportunities: dict[str, Opportunity] = {}
        self.deals: dict[str, Deal] = {}
        self.revenue: float = 0
        self.version: int = 0

    def get_state(self) -> dict[str, Any]:
        """Get current database state."""
        return {
            "leads": {k: asdict(v) for k, v in self.leads.items()},
            "opportunities": {k: asdict(v) for k, v in self.opportunities.items()},
            "deals": {k: asdict(v) for k, v in self.deals.items()},
            "revenue": self.revenue,
            "version": self.version,
        }

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore database state."""
        self.leads = {k: Lead(**v) for k, v in state.get("leads", {}).items()}
        self.opportunities = {k: Opportunity(**v) for k, v in state.get("opportunities", {}).items()}
        self.deals = {k: Deal(**v) for k, v in state.get("deals", {}).items()}
        self.revenue = state.get("revenue", 0)
        self.version = state.get("version", 0)


class AISalesAgent:
    """AI-powered sales agent with rollback support."""

    def __init__(
        self,
        agent_id: str = "ai-sales-agent",
        db_path: str = "sales_agent.db",
    ):
        self.agent_id = agent_id
        self.client = AgentRollbackClient(local=True, db_path=db_path)
        self.crm = CRMDatabase()
        self.session_id: Optional[str] = None

    async def start(self) -> str:
        """Start the agent and tracking session."""
        await self.client.connect()
        session = await self.client.start_session(
            agent_id=self.agent_id,
            metadata={
                "type": "sales_agent",
                "started_at": datetime.utcnow().isoformat(),
            }
        )
        self.session_id = session.id
        print(f"[Agent] Started session: {session.id}")
        return session.id

    async def stop(self, status: SessionStatus = SessionStatus.COMPLETED) -> None:
        """Stop the agent and end session."""
        await self.client.end_session(status=status)
        await self.client.close()
        print(f"[Agent] Session ended with status: {status.value}")

    async def _record_action(
        self,
        action_type: str,
        action_data: dict[str, Any],
        before_state: Optional[dict[str, Any]] = None,
        after_state: Optional[dict[str, Any]] = None,
    ) -> None:
        """Record an action with state tracking."""
        await self.client.record_action(
            action_type=action_type,
            action_data=action_data,
            before_state=before_state or self.crm.get_state(),
            after_state=after_state or self.crm.get_state(),
            connector_type="crm",
        )
        self.crm.version += 1

    async def checkpoint(self, name: str = "manual") -> str:
        """Create a checkpoint of current state."""
        snapshot = await self.client.create_checkpoint(
            state_data={
                "checkpoint_name": name,
                **self.crm.get_state()
            },
            connector_type="crm",
        )
        print(f"[Agent] Checkpoint created: {snapshot.id[:8]}... ({name})")
        return snapshot.id

    # CRM Operations

    async def import_leads(self, leads: list[dict[str, Any]]) -> int:
        """Import leads into the CRM."""
        before = self.crm.get_state()

        imported = 0
        for lead_data in leads:
            lead = Lead(**lead_data)
            self.crm.leads[lead.id] = lead
            imported += 1

        await self._record_action(
            action_type="import_leads",
            action_data={"count": imported, "leads": [l["id"] for l in leads]},
            before_state=before,
        )
        print(f"[Agent] Imported {imported} leads")
        return imported

    async def qualify_lead(self, lead_id: str) -> Optional[str]:
        """AI qualifies a lead based on scoring criteria."""
        if lead_id not in self.crm.leads:
            print(f"[Agent] Lead not found: {lead_id}")
            return None

        before = self.crm.get_state()
        lead = self.crm.leads[lead_id]

        # AI scoring logic
        score = 0
        if lead.company_size > 100:
            score += 20
        if lead.company_size > 500:
            score += 15
        if lead.estimated_value > 50000:
            score += 25
        if lead.estimated_value > 100000:
            score += 20
        if lead.industry in ["technology", "finance", "healthcare"]:
            score += 15

        # Add some randomness (simulating AI uncertainty)
        score += random.randint(-10, 10)
        lead.score = max(0, min(100, score))

        if lead.score >= 50:
            lead.status = "qualified"
            lead.notes.append(f"AI qualified with score {lead.score}")
            print(f"[Agent] Lead {lead_id} qualified (score: {lead.score})")
        else:
            lead.status = "disqualified"
            lead.notes.append(f"AI disqualified with score {lead.score}")
            print(f"[Agent] Lead {lead_id} disqualified (score: {lead.score})")

        lead.last_activity = datetime.utcnow().isoformat()

        await self._record_action(
            action_type="qualify_lead",
            action_data={
                "lead_id": lead_id,
                "score": lead.score,
                "result": lead.status,
            },
            before_state=before,
        )

        return lead.status

    async def create_opportunity(self, lead_id: str) -> Optional[str]:
        """Convert a qualified lead to an opportunity."""
        if lead_id not in self.crm.leads:
            print(f"[Agent] Lead not found: {lead_id}")
            return None

        lead = self.crm.leads[lead_id]
        if lead.status != "qualified":
            print(f"[Agent] Lead {lead_id} is not qualified")
            return None

        before = self.crm.get_state()

        opp_id = f"OPP-{len(self.crm.opportunities) + 1:04d}"
        opportunity = Opportunity(
            id=opp_id,
            lead_id=lead_id,
            company=lead.company,
            contact_name=lead.contact_name,
            value=lead.estimated_value,
            stage="qualification",
            probability=25,
            close_date=(datetime.utcnow() + timedelta(days=90)).isoformat(),
        )
        self.crm.opportunities[opp_id] = opportunity
        lead.status = "converted"
        lead.notes.append(f"Converted to opportunity {opp_id}")

        await self._record_action(
            action_type="create_opportunity",
            action_data={
                "lead_id": lead_id,
                "opportunity_id": opp_id,
                "value": opportunity.value,
            },
            before_state=before,
        )

        print(f"[Agent] Created opportunity {opp_id} from lead {lead_id}")
        return opp_id

    async def advance_opportunity(self, opp_id: str) -> Optional[str]:
        """Move opportunity to next stage."""
        if opp_id not in self.crm.opportunities:
            print(f"[Agent] Opportunity not found: {opp_id}")
            return None

        before = self.crm.get_state()
        opp = self.crm.opportunities[opp_id]

        stages = ["qualification", "needs_analysis", "proposal", "negotiation", "closed_won"]
        stage_probabilities = [25, 40, 60, 80, 100]

        current_idx = stages.index(opp.stage) if opp.stage in stages else 0
        if current_idx < len(stages) - 1:
            opp.stage = stages[current_idx + 1]
            opp.probability = stage_probabilities[current_idx + 1]
            opp.notes.append(f"Advanced to {opp.stage}")

            await self._record_action(
                action_type="advance_opportunity",
                action_data={
                    "opportunity_id": opp_id,
                    "new_stage": opp.stage,
                    "probability": opp.probability,
                },
                before_state=before,
            )

            print(f"[Agent] Advanced {opp_id} to {opp.stage} ({opp.probability}%)")
            return opp.stage
        return opp.stage

    async def close_deal(self, opp_id: str, won: bool = True) -> Optional[str]:
        """Close an opportunity as won or lost."""
        if opp_id not in self.crm.opportunities:
            print(f"[Agent] Opportunity not found: {opp_id}")
            return None

        before = self.crm.get_state()
        opp = self.crm.opportunities[opp_id]

        if won:
            deal_id = f"DEAL-{len(self.crm.deals) + 1:04d}"
            deal = Deal(
                id=deal_id,
                opportunity_id=opp_id,
                company=opp.company,
                value=opp.value,
                status="won",
            )
            self.crm.deals[deal_id] = deal
            self.crm.revenue += opp.value
            opp.stage = "closed_won"
            opp.probability = 100

            await self._record_action(
                action_type="close_deal_won",
                action_data={
                    "opportunity_id": opp_id,
                    "deal_id": deal_id,
                    "value": opp.value,
                },
                before_state=before,
            )

            print(f"[Agent] Closed deal {deal_id}: ${opp.value:,.2f}")
            return deal_id
        else:
            opp.stage = "closed_lost"
            opp.probability = 0
            opp.notes.append("Deal lost")

            await self._record_action(
                action_type="close_deal_lost",
                action_data={
                    "opportunity_id": opp_id,
                },
                before_state=before,
            )

            print(f"[Agent] Lost deal {opp_id}")
            return None

    # Error simulation

    async def simulate_error(self) -> None:
        """Simulate an AI mistake - corrupt data."""
        before = self.crm.get_state()

        # Corrupt the data
        print("[Agent] ERROR: Simulating catastrophic AI failure...")
        self.crm.leads.clear()
        self.crm.opportunities.clear()
        self.crm.deals.clear()
        self.crm.revenue = -99999

        await self._record_action(
            action_type="error_data_corruption",
            action_data={"error": "Catastrophic failure - all data lost"},
            before_state=before,
        )

        print("[Agent] All CRM data has been corrupted!")

    async def bad_bulk_update(self) -> None:
        """Simulate a bad bulk update that needs rollback."""
        before = self.crm.get_state()

        print("[Agent] ERROR: Running bad bulk update...")
        for lead in self.crm.leads.values():
            lead.status = "invalid"
            lead.score = -100
            lead.notes.append("CORRUPTED BY BAD UPDATE")

        await self._record_action(
            action_type="error_bad_bulk_update",
            action_data={"error": "Bad bulk update corrupted all leads"},
            before_state=before,
        )

        print("[Agent] All leads corrupted by bad update!")

    # Recovery

    async def rollback_to(self, snapshot_id: str) -> bool:
        """Rollback to a specific snapshot."""
        print(f"[Agent] Rolling back to snapshot {snapshot_id[:8]}...")

        # Get the snapshot first
        snapshot = await self.client.get_snapshot(snapshot_id)
        if not snapshot or not snapshot.state_data:
            print("[Agent] Rollback failed: Snapshot not found or empty")
            return False

        # Execute the rollback (marks actions as rolled back)
        result = await self.client.rollback(
            target_snapshot_id=snapshot_id,
            dry_run=False,
        )

        # Restore CRM state from snapshot regardless of connector status
        # (In a real system, the connector would handle this)
        state = {k: v for k, v in snapshot.state_data.items() if k != "checkpoint_name"}

        # Debug: show what we're restoring
        print(f"[Agent] Restoring state with {len(state.get('leads', {}))} leads, "
              f"{len(state.get('opportunities', {}))} opportunities, "
              f"{len(state.get('deals', {}))} deals, "
              f"revenue=${state.get('revenue', 0):,.2f}")

        self.crm.set_state(state)

        print(f"[Agent] Rollback successful! Reverted {result.actions_reverted} actions")
        print(f"[Agent] CRM state restored from snapshot")
        return True

    # Reporting

    def print_status(self) -> None:
        """Print current CRM status."""
        print("\n" + "=" * 50)
        print("CRM STATUS")
        print("=" * 50)
        print(f"Leads:         {len(self.crm.leads)}")
        print(f"Opportunities: {len(self.crm.opportunities)}")
        print(f"Deals:         {len(self.crm.deals)}")
        print(f"Revenue:       ${self.crm.revenue:,.2f}")
        print("=" * 50 + "\n")


async def demo_scenario():
    """Run a complete demo scenario."""
    agent = AISalesAgent(db_path="demo_sales.db")

    try:
        # Start the agent
        await agent.start()

        # Import some leads
        leads = [
            {"id": "L001", "company": "Acme Corp", "contact_name": "John Smith",
             "email": "john@acme.com", "phone": "555-0101", "industry": "technology",
             "company_size": 500, "estimated_value": 75000},
            {"id": "L002", "company": "TechStart Inc", "contact_name": "Jane Doe",
             "email": "jane@techstart.io", "phone": "555-0102", "industry": "technology",
             "company_size": 50, "estimated_value": 25000},
            {"id": "L003", "company": "Global Finance", "contact_name": "Bob Wilson",
             "email": "bob@globalfin.com", "phone": "555-0103", "industry": "finance",
             "company_size": 1000, "estimated_value": 150000},
            {"id": "L004", "company": "Local Shop", "contact_name": "Alice Brown",
             "email": "alice@localshop.com", "phone": "555-0104", "industry": "retail",
             "company_size": 10, "estimated_value": 5000},
        ]
        await agent.import_leads(leads)
        agent.print_status()

        # Qualify leads
        for lead_id in ["L001", "L002", "L003", "L004"]:
            await agent.qualify_lead(lead_id)

        # Create checkpoint after qualification
        checkpoint1 = await agent.checkpoint("after_qualification")

        # Create opportunities from qualified leads
        for lead in agent.crm.leads.values():
            if lead.status == "qualified":
                await agent.create_opportunity(lead.id)

        agent.print_status()

        # Advance opportunities
        for opp_id in list(agent.crm.opportunities.keys()):
            await agent.advance_opportunity(opp_id)
            await agent.advance_opportunity(opp_id)

        # Create checkpoint before closing deals
        checkpoint2 = await agent.checkpoint("before_closing")

        # Close some deals
        for opp_id in list(agent.crm.opportunities.keys())[:2]:
            await agent.close_deal(opp_id, won=True)

        agent.print_status()

        # Simulate an error
        print("\n⚠️  Simulating AI error...")
        await agent.simulate_error()
        agent.print_status()

        # Rollback to last good state
        print("\n🔄 Rolling back to checkpoint...")
        await agent.rollback_to(checkpoint2)
        agent.print_status()

        print("\n✅ Demo completed successfully!")
        print(f"Total revenue recovered: ${agent.crm.revenue:,.2f}")

    finally:
        await agent.stop()


if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════════╗
║             AI Sales Agent Demo with Rollback                ║
╚══════════════════════════════════════════════════════════════╝
""")
    asyncio.run(demo_scenario())
