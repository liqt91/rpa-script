"""
Lightweight SQLite migrations with versioning.

How to add a new migration:
1. Bump _SCHEMA_VERSION to N+1
2. Add function _migrate_N() with the ALTER / CREATE / REBUILD logic
3. Restart server — missing migrations run automatically

For changes that SQLite ALTER TABLE cannot do (drop column, change type,
add AUTOINCREMENT, add FK to existing table), use _rebuild_table().
"""

from sqlalchemy import inspect, text
from .models import engine, Base

_SCHEMA_VERSION = 3  # Bump this when you add a new _migrate_N()


def _ensure_schema_version_table():
    """Create schema_migrations tracking table if it doesn't exist."""
    inspector = inspect(engine)
    if "schema_migrations" not in inspector.get_table_names():
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.commit()


def _current_version() -> int:
    """Return the highest applied migration version, or 0."""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT MAX(version) FROM schema_migrations"))
            row = result.fetchone()
            return row[0] or 0
    except Exception:
        return 0


def _mark_applied(version: int):
    with engine.connect() as conn:
        conn.execute(
            text("INSERT OR REPLACE INTO schema_migrations (version) VALUES (:v)"),
            {"v": version},
        )
        conn.commit()


def _rebuild_table(
    table_name: str,
    new_ddl: str,
    copy_columns: list[str],
    post_sql: list[str] | None = None,
):
    """
    SQLite-safe table rebuild.
    1. Rename old table to _old
    2. Create new table with new_ddl
    3. INSERT INTO new SELECT copy_columns FROM old
    4. Drop old table
    5. Run optional post_sql (indexes, FKs, etc.)
    """
    with engine.connect() as conn:
        conn.execute(text(f"ALTER TABLE {table_name} RENAME TO {table_name}_old"))
        conn.execute(text(new_ddl))
        cols_str = ", ".join(copy_columns)
        conn.execute(text(f"INSERT INTO {table_name} ({cols_str}) SELECT {cols_str} FROM {table_name}_old"))
        conn.execute(text(f"DROP TABLE {table_name}_old"))
        for sql in post_sql or []:
            conn.execute(text(sql))
        conn.commit()


# ── Migration 001: baseline columns added during early development ──────────

def _migrate_001():
    inspector = inspect(engine)
    cols = {c["name"] for c in inspector.get_columns("workflow_commands")}
    with engine.connect() as conn:
        needs_disable = False
        for col, ddl in [
            ("reviewed_at", "ALTER TABLE workflow_commands ADD COLUMN reviewed_at DATETIME"),
            ("handler", "ALTER TABLE workflow_commands ADD COLUMN handler VARCHAR(32)"),
            ("local", "ALTER TABLE workflow_commands ADD COLUMN local INTEGER DEFAULT 0"),
            ("description", "ALTER TABLE workflow_commands ADD COLUMN description TEXT DEFAULT ''"),
            ("category_order", "ALTER TABLE workflow_commands ADD COLUMN category_order INTEGER DEFAULT 0"),
            ("command_order", "ALTER TABLE workflow_commands ADD COLUMN command_order INTEGER DEFAULT 0"),
        ]:
            if col not in cols:
                conn.execute(text(ddl))
                needs_disable = True
        if needs_disable:
            conn.execute(text("UPDATE workflow_commands SET enabled = 0"))
        conn.commit()

    cols_nodes = {c["name"] for c in inspector.get_columns("workflow_nodes")}
    with engine.connect() as conn:
        if "enabled" not in cols_nodes:
            conn.execute(text("ALTER TABLE workflow_nodes ADD COLUMN enabled INTEGER DEFAULT 1"))
            conn.commit()

    table_names = {t for t in inspector.get_table_names()}
    if "data_tables" not in table_names:
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE data_tables (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workflow_id INTEGER NOT NULL,
                    name VARCHAR(128) NOT NULL,
                    columns TEXT DEFAULT '[]',
                    rows TEXT DEFAULT '[]',
                    created_at DATETIME,
                    updated_at DATETIME,
                    FOREIGN KEY (workflow_id) REFERENCES workflows(id)
                )
            """))
            conn.execute(text("CREATE INDEX idx_data_tables_wf ON data_tables(workflow_id)"))
            conn.commit()


# ── Migration 002: rebuild workflows with AUTOINCREMENT ─────────────────────

def _migrate_002():
    """
    SQLite cannot add AUTOINCREMENT to an existing table.
    Rebuild workflows so new IDs are never reused after deletion.
    """
    inspector = inspect(engine)
    if "workflows" not in inspector.get_table_names():
        return  # Table doesn't exist yet; init_db will create it correctly

    # Check if workflows already has AUTOINCREMENT
    # SQLite PRAGMA table_info does not expose AUTOINCREMENT directly.
    # We check sqlite_master DDL instead.
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='workflows'"
        ))
        row = result.fetchone()
        ddl = row[0] if row else ""
        if "AUTOINCREMENT" in ddl.upper():
            return  # Already correct

    _rebuild_table(
        table_name="workflows",
        new_ddl="""
            CREATE TABLE workflows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid VARCHAR(32) NOT NULL UNIQUE,
                name VARCHAR(128) NOT NULL,
                description TEXT DEFAULT '',
                url TEXT DEFAULT '',
                framework VARCHAR(32) DEFAULT 'DrissionPage',
                target_browser VARCHAR(16) DEFAULT '',
                created_at DATETIME,
                updated_at DATETIME
            )
        """,
        copy_columns=[
            "id", "uuid", "name", "description", "url",
            "framework", "target_browser", "created_at", "updated_at",
        ],
        post_sql=[
            "CREATE INDEX idx_workflows_uuid ON workflows(uuid)",
        ],
    )


# ── Migration 003: add closes_with for container commands ───────────────────

def _migrate_003():
    inspector = inspect(engine)
    cols = {c["name"] for c in inspector.get_columns("workflow_commands")}
    with engine.connect() as conn:
        if "closes_with" not in cols:
            conn.execute(text("ALTER TABLE workflow_commands ADD COLUMN closes_with VARCHAR(32)"))
            conn.commit()


# ── Runner ──────────────────────────────────────────────────────────────────

_MIGRATIONS = {
    1: _migrate_001,
    2: _migrate_002,
    3: _migrate_003,
}


def run_migrations():
    _ensure_schema_version_table()
    current = _current_version()
    if current >= _SCHEMA_VERSION:
        return

    for v in range(current + 1, _SCHEMA_VERSION + 1):
        fn = _MIGRATIONS.get(v)
        if not fn:
            raise RuntimeError(f"Migration {v} is defined in _SCHEMA_VERSION but has no function")
        fn()
        _mark_applied(v)
