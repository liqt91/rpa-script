# -*- coding: utf-8 -*-
"""Trigger a workflow run via POST /api/workflows/{id}/run/extension.

Mints a local JWT from .env SECRET_KEY (HS256, sub=1) and blocks until the run
finishes. Prints a compact per-step summary. Designed for the command-test skill.

Usage (from repo root):
    python .claude/skills/command-test/scripts/run_workflow.py <wf_id> [--timeout 480]
"""
import argparse
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _secret_key() -> str:
    env_path = os.path.join(os.getcwd(), ".env")
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("SECRET_KEY"):
                return line.split("=", 1)[1].strip()
    sys.exit("SECRET_KEY not found in .env (run from repo root)")


def _token(secret: str) -> str:
    from jose import jwt
    payload = {"sub": "1", "username": "admin",
               "exp": datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=1)}
    return jwt.encode(payload, secret, algorithm="HS256")


def _brief(item: dict) -> str:
    r = item.get("result") if isinstance(item.get("result"), dict) else item
    if isinstance(r, dict) and "setVar" in r:
        return f"setVar {r['setVar']} = {json.dumps(r.get('value'), ensure_ascii=False)}"
    if isinstance(r, dict) and "log" in r:
        return f"log[{r.get('level')}]: {r['log']}"
    sid = item.get("stepId", "?")
    status = item.get("status", "?")
    body = json.dumps(r, ensure_ascii=False, default=str)[:120] if r else item.get("error", "")
    return f"{sid} {status}: {body}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("wf_id", type=int)
    ap.add_argument("--timeout", type=int, default=480)
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()

    url = f"http://127.0.0.1:{args.port}/api/workflows/{args.wf_id}/run/extension"
    req = urllib.request.Request(
        url, data=b"{}",
        headers={"Authorization": "Bearer " + _token(_secret_key()),
                 "Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:1000]}")
    elapsed = time.time() - t0

    failed = body.get("failedSteps") or []
    print(f"HTTP 200  {elapsed:.1f}s  success={body.get('success')} "
          f"completed={body.get('completedSteps')}/{body.get('totalSteps')} "
          f"failed={len(failed)}")
    for f in failed:
        instr = f.get("instruction") or {}
        print(f"  FAILED {f.get('stepId')} ({instr.get('cmdType')}): {f.get('error')}")
    print("--- results ---")
    for item in body.get("results") or []:
        print(" ", _brief(item))
    print(f"logDir: {body.get('logDir')}")


if __name__ == "__main__":
    main()
