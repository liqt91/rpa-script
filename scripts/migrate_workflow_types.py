"""
Migrate workflow_nodes.type from old names to new handler names.

Usage: python scripts/migrate_workflow_types.py
"""

import os
import sqlite3

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "data.db"
)

# Old type name → new handler name (mirrors LEGACY_MAP in extension_emitter.py)
TYPE_MAP = {
    "click": "elementAction",
    "input": "elementAction",
    "clearInput": "elementAction",
    "doubleClick": "elementAction",
    "rightClick": "elementAction",
    "hover": "elementAction",
    "unhover": "elementAction",
    "selectOption": "elementAction",
    "getAttr": "elementAction",
    "getHtml": "elementAction",
    "getText": "elementAction",
    "getValue": "elementAction",
    "scrollToBottom": "elementAction",
    "scrollToTop": "elementAction",
    "scrollBy": "elementAction",
    "scrollOneScreen": "elementAction",
    "inputAndPressEnter": "elementAction",
    "clickCurrentLoopItem": "elementAction",
    "pressKey": "pressKey",
    "keyCombo": "keyCombo",
    "getPageTitle": "getPageTitle",
    "getElementCount": "getElementCount",
    "takeScreenshot": "takeScreenshot",
    "executeJs": "executeJs",
    "waitForElement": "wait",
    "waitForText": "wait",
    "waitForUrl": "wait",
    "waitForLoad": "wait",
    "waitForElementHide": "wait",
}


def main():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}, nothing to migrate")
        return

    conn = sqlite3.connect(DB_PATH)
    try:
        # Show before state
        cur = conn.cursor()
        cur.execute("SELECT type, COUNT(*) FROM workflow_nodes GROUP BY type ORDER BY type")
        before = {row[0]: row[1] for row in cur.fetchall()}

        changed = 0
        for old_type, new_type in TYPE_MAP.items():
            cur.execute(
                "UPDATE workflow_nodes SET type = ? WHERE type = ?",
                (new_type, old_type),
            )
            if cur.rowcount > 0:
                print(f"  {old_type!r} → {new_type!r}: {cur.rowcount} row(s) updated")
                changed += cur.rowcount

        conn.commit()

        if changed == 0:
            print("No old type names found, nothing to migrate.")
        else:
            print(f"\nTotal: {changed} row(s) updated.")

            # Show after state
            cur.execute("SELECT type, COUNT(*) FROM workflow_nodes GROUP BY type ORDER BY type")
            after = {row[0]: row[1] for row in cur.fetchall()}
            for t, cnt in sorted(after.items()):
                before_cnt = before.get(t, 0)
                if before_cnt != cnt:
                    print(f"  {t}: {before_cnt} → {cnt}")
                else:
                    print(f"  {t}: {cnt}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
