#!/usr/bin/env python3
"""
Nightly tier evaluation — run via cron or systemd timer.

Usage:
    python run_tier_evaluation.py            # evaluate
    python run_tier_evaluation.py --apply    # evaluate + apply pending changes
    python run_tier_evaluation.py --dry-run  # simulate
"""
import argparse
import sys
from datetime import datetime

from app import create_app, db


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="Also apply downgrades/terminations after evaluating")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show what would happen without changing anything")
    args = ap.parse_args()

    app = create_app()
    with app.app_context():
        from app.tiers import evaluate_all, apply_downgrade, apply_termination
        from app.models import WholesaleAccount

        print(f"=== Tier evaluation @ {datetime.utcnow().isoformat()} ===")

        results = evaluate_all(dry_run=args.dry_run)
        changed = 0
        skipped = 0

        for r in results:
            if r.get("skipped"):
                skipped += 1
                continue
            if r.get("state_before") != r.get("state_after"):
                changed += 1
                acct = r["account"]
                print(f"  {acct.company_name}: {r['state_before']} → {r['state_after']} "
                      f"(rev ${r['actual_revenue']:.2f} / target ${r['requirement']['amount']:.0f})")

        print(f"Evaluated: {len(results)} · state changes: {changed} · skipped: {skipped}")

        if args.apply:
            print("\n=== Applying pending tier changes ===")
            applied = 0
            for acct in WholesaleAccount.query.filter_by(status="approved", tier_state="terminate").all():
                r = apply_termination(acct)
                if r:
                    print(f"  {acct.company_name}: {r['from']} → {r['to']}")
                    applied += 1
            for acct in WholesaleAccount.query.filter_by(status="approved", tier_state="downgrade").all():
                r = apply_downgrade(acct)
                if r:
                    print(f"  {acct.company_name}: {r['from']} → {r['to']}")
                    applied += 1
            print(f"Applied: {applied}")

        if args.dry_run:
            print("\n(DRY RUN — nothing was written)")


if __name__ == "__main__":
    main()
