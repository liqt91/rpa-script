#!/usr/bin/env python3
"""
Validate command registry consistency (CLI runner).

Invokes the validation logic living in src/runtime/workflow/validation.py
so that the router can call it directly without subprocess.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from runtime.workflow.validation import validate  # noqa: E402


def main() -> int:
    print("Validating COMMAND_REGISTRY...")
    passed, messages = validate()

    if not passed:
        print(f"\nCOMMAND VALIDATION FAILED ({len(messages)} errors)")
        for e in messages:
            print(f"  - {e}")
        return 1
    else:
        print("\nCOMMAND VALIDATION PASSED")
        return 0


if __name__ == "__main__":
    sys.exit(main())
