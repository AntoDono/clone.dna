"""
Database initialization — SQLite setup via Peewee.

Enables WAL journal mode and foreign key enforcement on every connection.
Runs _migrate_candidate_columns() on startup to add DNA-status columns that were
introduced after the initial schema (Peewee's safe=True only creates missing tables,
not missing columns).
"""

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
        ("dna_cloned",             "INTEGER NOT NULL DEFAULT 0"),
        ("dna_path",               "TEXT"),
        ("dna_cloned_at",          "TEXT"),
        ("system_prompt",          "TEXT"),
        ("personality_profile",    "TEXT"),
        ("architectural_patterns", "TEXT"),
        ("code_quality_signals",   "TEXT"),
        ("domain_expertise",       "TEXT"),
    ]
    for col, definition in migrations:
        if col not in existing:
            db.execute_sql(f"ALTER TABLE candidate ADD COLUMN {col} {definition}")


def _migrate_team_columns() -> None:
    """Add discord_pair_code and user_id columns to team table if they don't exist yet."""
    cursor = db.execute_sql("PRAGMA table_info(team)")
    existing = {row[1] for row in cursor.fetchall()}
    if "discord_pair_code" not in existing:
        db.execute_sql("ALTER TABLE team ADD COLUMN discord_pair_code TEXT")
    if "user_id" not in existing:
        db.execute_sql("ALTER TABLE team ADD COLUMN user_id INTEGER REFERENCES user(id)")


def init_db() -> None:
    from models import User, Team, RoleSlot, Candidate, ChatMessage, DiscordPairing, GithubProfileCache, HeadhuntCache  # noqa: F401

    with db:
        db.create_tables([User, Team, RoleSlot, Candidate, ChatMessage, DiscordPairing, GithubProfileCache, HeadhuntCache], safe=True)
        _migrate_candidate_columns()
        _migrate_team_columns()
