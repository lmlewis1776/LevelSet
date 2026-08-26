"""Phase 1B: additive organization/profile data layer.

This migration is intentionally schema-only. It does not create organizations from
legacy users.organization values and does not associate historical reports with an
organization.
"""

VERSION = 1
NAME = "phase1b_organization_profile"


def _column_exists(conn, table_name, column_name):
    columns = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(column[1] == column_name for column in columns)


def apply(conn):
    conn.execute(
        '''CREATE TABLE IF NOT EXISTS organizations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )'''
    )

    conn.execute(
        '''CREATE TABLE IF NOT EXISTS user_organizations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            organization_id INTEGER NOT NULL,
            relationship_type TEXT,
            respondent_role TEXT,
            organizational_familiarity TEXT,
            is_primary INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, organization_id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (organization_id) REFERENCES organizations(id)
        )'''
    )

    conn.execute(
        '''CREATE TABLE IF NOT EXISTS organization_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER NOT NULL UNIQUE,
            organization_type TEXT,
            organization_size_band TEXT,
            workforce_composition TEXT,
            decision_making_structures TEXT NOT NULL DEFAULT '[]',
            people_workforce_structures TEXT NOT NULL DEFAULT '[]',
            technology_structures TEXT NOT NULL DEFAULT '[]',
            voice_participation_structures TEXT NOT NULL DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (organization_id) REFERENCES organizations(id)
        )'''
    )

    if not _column_exists(conn, 'reports', 'organization_id'):
        conn.execute('ALTER TABLE reports ADD COLUMN organization_id INTEGER REFERENCES organizations(id)')
    if not _column_exists(conn, 'reports', 'respondent_context_json'):
        conn.execute('ALTER TABLE reports ADD COLUMN respondent_context_json TEXT')

    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_user_organizations_user_id ON user_organizations(user_id)'
    )
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_user_organizations_organization_id ON user_organizations(organization_id)'
    )
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_reports_organization_id ON reports(organization_id)'
    )
