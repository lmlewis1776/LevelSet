"""Server-side data helpers for the additive Phase 1B organization layer.

These helpers do not alter report authorization, user plans, payments, or Stripe state.
"""

import json


PROFILE_JSON_FIELDS = (
    'decision_making_structures',
    'people_workforce_structures',
    'technology_structures',
    'voice_participation_structures',
)


def create_organization(conn, name=None):
    cursor = conn.execute('INSERT INTO organizations (name) VALUES (?)', (name,))
    return cursor.lastrowid


def create_user_organization(
    conn,
    user_id,
    organization_id,
    relationship_type=None,
    respondent_role=None,
    organizational_familiarity=None,
    is_primary=False,
):
    cursor = conn.execute(
        '''INSERT INTO user_organizations (
            user_id, organization_id, relationship_type, respondent_role,
            organizational_familiarity, is_primary
        ) VALUES (?, ?, ?, ?, ?, ?)''',
        (
            user_id,
            organization_id,
            relationship_type,
            respondent_role,
            organizational_familiarity,
            1 if is_primary else 0,
        ),
    )
    return cursor.lastrowid


def upsert_organization_profile(conn, organization_id, **profile):
    values = {
        'organization_type': profile.get('organization_type'),
        'organization_size_band': profile.get('organization_size_band'),
        'workforce_composition': profile.get('workforce_composition'),
    }
    for field in PROFILE_JSON_FIELDS:
        values[field] = json.dumps(profile.get(field, []))

    conn.execute(
        '''INSERT INTO organization_profiles (
            organization_id, organization_type, organization_size_band,
            workforce_composition, decision_making_structures,
            people_workforce_structures, technology_structures,
            voice_participation_structures
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(organization_id) DO UPDATE SET
            organization_type = excluded.organization_type,
            organization_size_band = excluded.organization_size_band,
            workforce_composition = excluded.workforce_composition,
            decision_making_structures = excluded.decision_making_structures,
            people_workforce_structures = excluded.people_workforce_structures,
            technology_structures = excluded.technology_structures,
            voice_participation_structures = excluded.voice_participation_structures,
            updated_at = CURRENT_TIMESTAMP''',
        (
            organization_id,
            values['organization_type'],
            values['organization_size_band'],
            values['workforce_composition'],
            values['decision_making_structures'],
            values['people_workforce_structures'],
            values['technology_structures'],
            values['voice_participation_structures'],
        ),
    )


def get_organization_context_for_user(conn, user_id, organization_id):
    """Retrieve membership, organization, and profile context for future authorized views."""
    return conn.execute(
        '''SELECT
            o.id AS organization_id,
            o.name AS organization_name,
            uo.relationship_type,
            uo.respondent_role,
            uo.organizational_familiarity,
            uo.is_primary,
            op.organization_type,
            op.organization_size_band,
            op.workforce_composition,
            op.decision_making_structures,
            op.people_workforce_structures,
            op.technology_structures,
            op.voice_participation_structures
        FROM user_organizations uo
        JOIN organizations o ON o.id = uo.organization_id
        LEFT JOIN organization_profiles op ON op.organization_id = o.id
        WHERE uo.user_id = ? AND uo.organization_id = ?''',
        (user_id, organization_id),
    ).fetchone()
