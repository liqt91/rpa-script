# -*- coding: utf-8 -*-
"""Pretty-print a workflow run.log (SSE JSONL) in step order.

(copied from .claude/skills/command-test/scripts/read_run.py — keep in sync)

Usage:
    python skills/scripts/read_run.py <logDir>
"""
import argparse
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("logdir", help="logDir from the run response (contains run.log)")
    args = ap.parse_args()

    path = os.path.join(args.logdir, "run.log")
    if not os.path.isfile(path):
        sys.exit(f"run.log not found: {path}")

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                print("raw:", line[:200])
                continue
            t = e.get("type")
            if t == "stepStart":
                print(f"> {e.get('stepId')} {e.get('cmdType')} | {(e.get('_summary') or '')[:80]}")
            elif t == "stepComplete":
                r = json.dumps(e.get("result"), ensure_ascii=False, default=str)[:160]
                print(f"< {e.get('stepId')} OK {r}")
            elif t == "stepError":
                print(f"< {e.get('stepId')} ERROR {e.get('error')}")
            elif t == "stepWarning":
                print(f"! {e.get('stepId')} WARN {e.get('warning')}")
            elif t == "done":
                print(f"~ done success={e.get('success')} "
                      f"completed={e.get('completedSteps')}/{e.get('totalSteps')}")
            else:
                print(f"~ {t} {json.dumps(e, ensure_ascii=False, default=str)[:140]}")


if __name__ == "__main__":
    main()
