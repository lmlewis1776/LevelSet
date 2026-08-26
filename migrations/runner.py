"""Small forward-only migration runner for LevelSet's SQLite database."""

from .phase1b_organization_profile import NAME as PHASE1B_NAME
from .phase1b_organization_profile import VERSION as PHASE1B_VERSION
from .phase1b_organization_profile import apply as apply_phase1b


MIGRATIONS = (
    (PHASE1B_VERSION, PHASE1B_NAME, apply_phase1b),
)


def run_migrations(conn):
    conn.execute(
        '''CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )'''
    )
    applied_versions = {
        row[0] for row in conn.execute('SELECT version FROM schema_migrations').fetchall()
    }
    for version, name, apply_migration in MIGRATIONS:
        if version in applied_versions:
            continue
        apply_migration(conn)
        conn.execute(
            'INSERT INTO schema_migrations (version, name) VALUES (?, ?)',
            (version, name),
        )
