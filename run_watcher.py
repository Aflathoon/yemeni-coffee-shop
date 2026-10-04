#!/usr/bin/env python3
"""
Background health watcher.

Runs the health check battery, persists alerts, optionally AI-summarises,
optionally sends Telegram notifications.

Usage:
    python run_watcher.py                    # silent unless something's wrong
    python run_watcher.py --verbose          # print every check
    python run_watcher.py --no-ai            # skip the AI summary (saves tokens)
    python run_watcher.py --no-notify        # don't send Telegram
"""
import argparse
import sys
from datetime import datetime

from app import create_app


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true", help="Print every check")
    ap.add_argument("--no-ai", action="store_true", help="Skip the AI summary")
    ap.add_argument("--no-notify", action="store_true", help="Skip Telegram alerts")
    args = ap.parse_args()

    app = create_app()
    with app.app_context():
        from app.health import run_all_checks, summarize, persist_alerts
        from app.ai import is_configured as ai_ok, explain_health
        from app.models import AiWatcherRun, Setting
        from app import db

        # Read watcher config
        enabled = (Setting.get("AI_WATCHER_ENABLED") or "0") == "1"

        started = datetime.utcnow()
        run = AiWatcherRun(started_at=started)

        try:
            results = run_all_checks()
            s = summarize(results)

            # AI summary only when there's something to explain
            ai_summary = None
            has_problems = s["warn"] + s["fail"] > 0
            if has_problems and not args.no_ai and ai_ok():
                try:
                    ai_r = explain_health(results)
                    if ai_r.get("ok"):
                        ai_summary = ai_r["summary"]
                except Exception as e:
                    print(f"[watcher] AI summary failed: {e}", file=sys.stderr)

            # Persist + notify
            counts = persist_alerts(results, ai_summary=ai_summary, notify=not args.no_notify)

            run.finished_at = datetime.utcnow()
            run.ok_count = s["ok"]
            run.warn_count = s["warn"]
            run.fail_count = s["fail"]
            run.new_alerts = counts["created"]
            run.telegram_sent = counts["telegram_sent"]

            db.session.add(run)
            db.session.commit()

            # Output
            if args.verbose or counts["created"] > 0 or s["fail"] > 0:
                print(f"[{started.isoformat(timespec='seconds')}] "
                      f"ok={s['ok']} warn={s['warn']} fail={s['fail']} "
                      f"new={counts['created']} resolved={counts['resolved_auto']} "
                      f"telegram={counts['telegram_sent']}")
                for r in results:
                    if args.verbose or r["status"] != "ok":
                        icon = {"ok":"✅","warn":"⚠️","fail":"❌"}[r["status"]]
                        print(f"   {icon} {r['name']}: {r['message']}")
                if ai_summary:
                    print(f"   🤖 {ai_summary}")
            else:
                print(f"[{started.isoformat(timespec='seconds')}] all ok")

            sys.exit(0)

        except Exception as e:
            run.finished_at = datetime.utcnow()
            run.error = str(e)[:1000]
            db.session.add(run)
            db.session.commit()
            print(f"[watcher] FATAL: {e}", file=sys.stderr)
            sys.exit(2)


if __name__ == "__main__":
    main()
