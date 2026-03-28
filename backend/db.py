import os
from peewee import SqliteDatabase
from dotenv import load_dotenv

load_dotenv()

db = SqliteDatabase(
    os.getenv("DB_PATH", "clone_dna.db"),
    pragmas={"journal_mode": "wal", "foreign_keys": 1},
)


def _migrate_candidate_columns() -> None:
    """Add dna_* columns to candidate table if they don't exist yet."""
    cursor = db.execute_sql("PRAGMA table_info(candidate)")
    existing = {row[1] for row in cursor.fetchall()}
    migrations = [
        ("dna_cloned",    "INTEGER NOT NULL DEFAULT 0"),
        ("dna_path",      "TEXT"),
        ("dna_cloned_at", "TEXT"),
    ]
    for col, definition in migrations:
        if col not in existing:
            db.execute_sql(f"ALTER TABLE candidate ADD COLUMN {col} {definition}")


def init_db() -> None:
    from models import Team, RoleSlot, Candidate, ChatMessage  # noqa: F401

    with db:
        db.create_tables([Team, RoleSlot, Candidate, ChatMessage], safe=True)
        # Add new columns to existing Candidate rows (safe=True only creates missing tables,
        # not missing columns — so we migrate manually for the dna_* fields)
        _migrate_candidate_columns()
