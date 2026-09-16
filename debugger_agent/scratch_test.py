import sys
import asyncio
from pathlib import Path
import auditor
import healer

async def test():
    print("Finding latest svodny...")
    svodny = auditor.find_latest_svodny(Path("/app/data/outputs"))
    print(f"Svodny: {svodny}")
    uploads = Path("/app/data/uploads")
    print("Auditing...")
    report = auditor.audit_svodny_price(svodny, uploads)
    print(f"Discrepancies found: {len(report.discrepancies)}")
    for d in report.discrepancies:
        print(f"[{d.distributor_label}] {d.issue_type}: {d.description}")
        print(f"Sample data: {d.raw_sample_data}")
        fix = await healer.diagnose_and_propose_fix(d)
        print(f"Proposed fix: id={fix.fix_id}, cause={fix.root_cause}, rule={fix.proposed_rule}, expl={fix.explanation}")

if __name__ == "__main__":
    asyncio.run(test())
