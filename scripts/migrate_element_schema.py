"""
Migrate element storage schema:
- locator_type -> selector_family (css|xpath|drission)
- method -> target_mode (single|list)
- drop css_selector

Usage: python scripts/migrate_element_schema.py
"""

import os
import sqlite3

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "data.db"
)


def infer_selector_family(locator: str, locator_type: str) -> str:
    if locator_type == "xpath":
        return "xpath"
    if locator_type in (
        "data-attr", "aria", "name", "tag_text", "text", "verse",
        "tag_attr", "tag_class", "multi_attr",
    ):
        return "drission"
    if locator:
        l = str(locator).strip()
        if l.startswith("xpath:") or l.startswith("//"):
            return "xpath"
        if l.startswith("@") or l.startswith("tag:") or l.startswith("verse:") or l.startswith("text=") or l.startswith("@@class:"):
            return "drission"
    return "css"


def infer_target_mode(method: str) -> str:
    if method in ("eles", "s_eles"):
        return "list"
    return "single"


def migrate_table(conn: sqlite3.Connection, table: str, drop_css_selector: bool = False):
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    cols = {row[1] for row in cur.fetchall()}

    if "selector_family" in cols and "target_mode" in cols:
        print(f"  [{table}] already migrated, skipping")
        return

    if "locator_type" not in cols and "method" not in cols:
        print(f"  [{table}] no old columns found, skipping")
        return

    # Add new columns
    cur.execute(f"ALTER TABLE {table} ADD COLUMN selector_family VARCHAR(16) DEFAULT 'css'")
    cur.execute(f"ALTER TABLE {table} ADD COLUMN target_mode VARCHAR(16) DEFAULT 'single'")

    # Update values
    cur.execute(f"SELECT id, locator, locator_type, method FROM {table}")
    for row in cur.fetchall():
        row_id, locator, locator_type, method = row
        sf = infer_selector_family(locator or "", locator_type or "")
        tm = infer_target_mode(method or "")
        cur.execute(
            f"UPDATE {table} SET selector_family = ?, target_mode = ? WHERE id = ?",
            (sf, tm, row_id),
        )

    # Drop old columns
    cur.execute(f"ALTER TABLE {table} DROP COLUMN locator_type")
    cur.execute(f"ALTER TABLE {table} DROP COLUMN method")
    if drop_css_selector and "css_selector" in cols:
        cur.execute(f"ALTER TABLE {table} DROP COLUMN css_selector")

    conn.commit()
    print(f"  [{table}] migrated successfully")


def main():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}, nothing to migrate")
        return

    conn = sqlite3.connect(DB_PATH)
    try:
        print("Migrating captured_elements...")
        migrate_table(conn, "captured_elements", drop_css_selector=True)
        print("Migrating workflow_nodes...")
        migrate_table(conn, "workflow_nodes")
        print("Done.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
