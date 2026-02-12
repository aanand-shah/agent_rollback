#!/usr/bin/env python3
"""
Launcher script for AI Sales Agent Demo.

Usage:
    python run_demo.py [--interactive]
"""

import sys
import os
import asyncio

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def interactive_demo():
    """Run an interactive demo session."""
    from demo.sales_agent import AISalesAgent

    print("""
╔══════════════════════════════════════════════════════════════╗
║        Interactive AI Sales Agent Demo with Rollback         ║
╚══════════════════════════════════════════════════════════════╝

Commands:
  import      - Import sample leads
  qualify     - Qualify all new leads
  convert     - Convert qualified leads to opportunities
  advance     - Advance opportunities to next stage
  close       - Close deals
  checkpoint  - Create a checkpoint
  error       - Simulate an error (corrupts data)
  rollback    - Rollback to last checkpoint
  status      - Show CRM status
  snapshots   - List available snapshots
  quit        - Exit demo

""")

    agent = AISalesAgent(db_path="interactive_demo.db")
    checkpoints = []

    try:
        await agent.start()

        while True:
            try:
                cmd = input("\n[demo]> ").strip().lower()

                if cmd == "quit" or cmd == "exit":
                    break

                elif cmd == "import":
                    leads = [
                        {"id": f"L{i:03d}", "company": f"Company {i}",
                         "contact_name": f"Contact {i}", "email": f"contact{i}@example.com",
                         "phone": f"555-{i:04d}", "industry": ["technology", "finance", "healthcare", "retail"][i % 4],
                         "company_size": (i + 1) * 100, "estimated_value": (i + 1) * 25000}
                        for i in range(1, 6)
                    ]
                    await agent.import_leads(leads)

                elif cmd == "qualify":
                    for lead_id in list(agent.crm.leads.keys()):
                        lead = agent.crm.leads[lead_id]
                        if lead.status == "new":
                            await agent.qualify_lead(lead_id)

                elif cmd == "convert":
                    for lead_id in list(agent.crm.leads.keys()):
                        lead = agent.crm.leads[lead_id]
                        if lead.status == "qualified":
                            await agent.create_opportunity(lead_id)

                elif cmd == "advance":
                    for opp_id in list(agent.crm.opportunities.keys()):
                        opp = agent.crm.opportunities[opp_id]
                        if opp.stage != "closed_won" and opp.stage != "closed_lost":
                            await agent.advance_opportunity(opp_id)

                elif cmd == "close":
                    for opp_id in list(agent.crm.opportunities.keys()):
                        opp = agent.crm.opportunities[opp_id]
                        if opp.stage == "negotiation":
                            await agent.close_deal(opp_id, won=True)

                elif cmd == "checkpoint":
                    name = input("Checkpoint name (or press Enter): ").strip() or "manual"
                    checkpoint_id = await agent.checkpoint(name)
                    checkpoints.append(checkpoint_id)
                    print(f"Checkpoint saved. Total checkpoints: {len(checkpoints)}")

                elif cmd == "error":
                    print("Choose error type:")
                    print("  1. Data corruption (clears all data)")
                    print("  2. Bad bulk update (corrupts leads)")
                    choice = input("Choice [1/2]: ").strip()
                    if choice == "1":
                        await agent.simulate_error()
                    elif choice == "2":
                        await agent.bad_bulk_update()

                elif cmd == "rollback":
                    snapshots = await agent.client.list_snapshots()
                    checkpoint_snaps = [s for s in snapshots if s.snapshot_type.value == "checkpoint"]

                    if not checkpoint_snaps:
                        print("No checkpoints available!")
                        continue

                    print("\nAvailable checkpoints:")
                    for i, snap in enumerate(checkpoint_snaps):
                        name = snap.state_data.get("checkpoint_name", "unnamed") if snap.state_data else "unnamed"
                        print(f"  {i + 1}. {snap.id[:8]}... - {name} ({snap.created_at})")

                    choice = input("Select checkpoint number: ").strip()
                    try:
                        idx = int(choice) - 1
                        if 0 <= idx < len(checkpoint_snaps):
                            await agent.rollback_to(checkpoint_snaps[idx].id)
                        else:
                            print("Invalid selection")
                    except ValueError:
                        print("Invalid input")

                elif cmd == "status":
                    agent.print_status()

                    print("Leads:")
                    for lead in agent.crm.leads.values():
                        print(f"  {lead.id}: {lead.company} - {lead.status} (score: {lead.score})")

                    print("\nOpportunities:")
                    for opp in agent.crm.opportunities.values():
                        print(f"  {opp.id}: {opp.company} - {opp.stage} (${opp.value:,.0f})")

                    print("\nDeals:")
                    for deal in agent.crm.deals.values():
                        print(f"  {deal.id}: {deal.company} - ${deal.value:,.0f}")

                elif cmd == "snapshots":
                    snapshots = await agent.client.list_snapshots()
                    print(f"\nTotal snapshots: {len(snapshots)}")
                    for snap in snapshots[-10:]:  # Show last 10
                        name = ""
                        if snap.state_data and "checkpoint_name" in snap.state_data:
                            name = f" ({snap.state_data['checkpoint_name']})"
                        print(f"  {snap.id[:8]}... - {snap.snapshot_type.value}{name}")

                elif cmd == "help":
                    print("""
Commands:
  import      - Import sample leads
  qualify     - Qualify all new leads
  convert     - Convert qualified leads to opportunities
  advance     - Advance opportunities to next stage
  close       - Close deals
  checkpoint  - Create a checkpoint
  error       - Simulate an error
  rollback    - Rollback to checkpoint
  status      - Show CRM status
  snapshots   - List snapshots
  quit        - Exit
""")

                else:
                    print(f"Unknown command: {cmd}. Type 'help' for available commands.")

            except KeyboardInterrupt:
                print("\nUse 'quit' to exit.")

    finally:
        await agent.stop()
        print("\nDemo ended. Goodbye!")


async def automated_demo():
    """Run the automated demo scenario."""
    from demo.sales_agent import demo_scenario
    await demo_scenario()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run AI Sales Agent Demo")
    parser.add_argument("--interactive", "-i", action="store_true",
                        help="Run in interactive mode")

    args = parser.parse_args()

    if args.interactive:
        asyncio.run(interactive_demo())
    else:
        asyncio.run(automated_demo())
