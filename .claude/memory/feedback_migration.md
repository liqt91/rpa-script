---
name: project-migration-preference
description: User prefers in-model migration over standalone migration files for this project
type: feedback
---

Do NOT create standalone database migration files (e.g. `src/repo/migrations/001_*.py`). This project handles schema changes directly inside `models.py` (`init_db()` with `ALTER TABLE` logic).

**Why:** User explicitly rejected a standalone migration file I created and instructed to keep migrations in models.py.

**How to apply:** When adding new columns to existing tables, add the column to the SQLAlchemy model class and include an inline `ALTER TABLE` guard inside `init_db()` (or the equivalent startup hook). Do not create Alembic-style or numbered migration scripts unless the user explicitly asks for them.
