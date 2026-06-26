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

_SCHEMA_VERSION = 6  # Bump this when you add a new _migrate_N()


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


# ── Migration 004: route built-in element commands through elementAction ─────

def _migrate_004():
    """Migrate existing built-in element commands to the unified elementAction handler.

    - Updates handler to "elementAction".
    - Injects a hidden `action` default field into each command's fields JSON so
      old workflow nodes pick up the action without code changes.
    - Enables rightClick and inserts doubleClick as a new built-in command.
    """
    import json
    from sqlalchemy import text
    from .models import engine

    element_actions = {
        "click": "click",
        "rightClick": "rightClick",
        "input": "input",
        "inputAndPressEnter": "inputAndPressEnter",
        "clearInput": "clearInput",
        "getText": "extract",
        "getAttr": "extract",
        "getHtml": "extract",
        "getValue": "extract",
        "scrollToBottom": "scroll",
        "scrollToTop": "scroll",
        "scrollOneScreen": "scroll",
        "scrollBy": "scroll",
        "hover": "hover",
        "unhover": "unhover",
        "selectOption": "selectOption",
    }

    with engine.connect() as conn:
        for cmd_type, action in element_actions.items():
            result = conn.execute(
                text("SELECT id, fields FROM workflow_commands WHERE type = :type"),
                {"type": cmd_type},
            )
            row = result.fetchone()
            if not row:
                continue
            fields = json.loads(row[1] or "[]")
            if not any(f.get("name") == "action" for f in fields):
                action_field = {
                    "name": "action",
                    "label": "扩展动作",
                    "type": "hidden",
                    "default": action,
                }
                # Place action after common element locators so hidden defaults are grouped
                insert_idx = 0
                for i, f in enumerate(fields):
                    if f.get("name") in ("windowVar", "element_name", "scope"):
                        insert_idx = i + 1
                fields.insert(insert_idx, action_field)
            conn.execute(
                text("""
                    UPDATE workflow_commands
                    SET handler = 'elementAction', local = 0, fields = :fields, enabled = 1
                    WHERE id = :id
                """),
                {"id": row[0], "fields": json.dumps(fields, ensure_ascii=False)},
            )

        # Insert doubleClick if missing
        existing = conn.execute(
            text("SELECT 1 FROM workflow_commands WHERE type = 'doubleClick'")
        ).fetchone()
        if not existing:
            conn.execute(
                text("""
                    INSERT INTO workflow_commands
                    (type, label, category, icon, icon_color, bg_color,
                     is_container, is_branch, is_structural, closes_with,
                     fields, description, is_builtin, enabled, handler, local,
                     category_order, command_order)
                    VALUES
                    (:type, :label, :category, :icon, :icon_color, :bg_color,
                     0, 0, 0, NULL,
                     :fields, :description, 1, 1, 'elementAction', 0,
                     :category_order, :command_order)
                """),
                {
                    "type": "doubleClick",
                    "label": "双击元素",
                    "category": "元素点击",
                    "icon": "fa-computer-mouse",
                    "icon_color": "text-blue-500",
                    "bg_color": "bg-blue-50",
                    "fields": json.dumps([
                        {"name": "windowVar", "label": "窗口变量", "type": "varName", "required": False, "default": "browser1", "placeholder": "如 browser1", "group": "input"},
                        {"name": "element_name", "label": "元素", "type": "elementName", "required": True, "isPrimaryElement": True},
                        {"name": "scope", "label": "匹配范围", "type": "select", "options": [{"label": "在当前外层元素内查找", "value": "local"}, {"label": "全页面匹配", "value": "global"}], "default": "global", "group": "advanced", "description": "在当前外层元素内查找=仅在当前 forEachElement 循环到的元素内部搜索该选择器；全页面匹配=在整个页面搜索，不依赖循环上下文。"},
                        {"name": "action", "label": "扩展动作", "type": "hidden", "default": "doubleClick"},
                    ], ensure_ascii=False),
                    "description": "在元素上触发双击事件",
                    "category_order": 20,
                    "command_order": 50,
                },
            )

        conn.commit()


# ── Migration 005: openBrowser becomes backend/local execution ───────────────

def _migrate_005():
    """openBrowser is now a backend-only command that launches the browser.

    Updates existing openBrowser rows to local=True and handler='openBrowser'
    so the extension runner routes it through LOCAL_HANDLERS instead of sending
    it to content.js.
    """
    with engine.connect() as conn:
        conn.execute(
            text("UPDATE workflow_commands SET local = 1, handler = 'openBrowser' WHERE type = 'openBrowser'")
        )
        conn.commit()


# ── Migration 006: repair openBrowser rows that have local but no handler ─────

def _migrate_006():
    """Earlier Migration 005 set local=1 without handler for some rows.

    Ensure openBrowser always has handler='openBrowser' when it is local.
    """
    with engine.connect() as conn:
        conn.execute(
            text("UPDATE workflow_commands SET handler = 'openBrowser' WHERE type = 'openBrowser' AND (handler IS NULL OR handler = '')")
        )
        conn.commit()


# ── Runner ──────────────────────────────────────────────────────────────────

_MIGRATIONS = {
    1: _migrate_001,
    2: _migrate_002,
    3: _migrate_003,
    4: _migrate_004,
    5: _migrate_005,
    6: _migrate_006,
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
