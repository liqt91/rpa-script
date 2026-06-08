"""
Lightweight SQLite migrations.
"""

from .models import engine


def run_migrations():
    """SQLite migration: add columns if missing; disable all commands once on first phase transition."""
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    cols = {c['name'] for c in inspector.get_columns('workflow_commands')}
    with engine.connect() as conn:
        needs_phase_transition = False
        if 'reviewed_at' not in cols:
            conn.execute(text("ALTER TABLE workflow_commands ADD COLUMN reviewed_at DATETIME"))
            needs_phase_transition = True
        if 'handler' not in cols:
            conn.execute(text("ALTER TABLE workflow_commands ADD COLUMN handler VARCHAR(32)"))
            needs_phase_transition = True
        if 'local' not in cols:
            conn.execute(text("ALTER TABLE workflow_commands ADD COLUMN local INTEGER DEFAULT 0"))
            needs_phase_transition = True
        if 'description' not in cols:
            conn.execute(text("ALTER TABLE workflow_commands ADD COLUMN description TEXT DEFAULT ''"))
            needs_phase_transition = True
        # Only disable all commands once — when the new columns are first added
        if needs_phase_transition:
            conn.execute(text("UPDATE workflow_commands SET enabled = 0"))
        conn.commit()

    # workflow_nodes migrations
    cols_nodes = {c['name'] for c in inspector.get_columns('workflow_nodes')}
    with engine.connect() as conn:
        if 'enabled' not in cols_nodes:
            conn.execute(text("ALTER TABLE workflow_nodes ADD COLUMN enabled INTEGER DEFAULT 1"))
            conn.commit()

    # data_tables migration
    table_names = {t for t in inspector.get_table_names()}
    if 'data_tables' not in table_names:
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
