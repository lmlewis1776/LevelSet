"""Offline Phase 1B schema/migration regression tests.

Uses a temporary SQLite database seeded with the pre-Phase-1B LevelSet schema.
No live Stripe activity or production data operations occur.
"""

import json
import os
import sqlite3
import sys
import tempfile
import types
import unittest

# Keep imports offline when the Stripe SDK is absent in the local test environment.
try:
    import stripe  # noqa: F401
except ModuleNotFoundError:
    stripe = types.ModuleType('stripe')

    class OfflineCheckoutSession:
        @staticmethod
        def create(*args, **kwargs):
            raise AssertionError('Stripe must be mocked in offline tests')

        @staticmethod
        def retrieve(*args, **kwargs):
            raise AssertionError('Stripe must be mocked in offline tests')

    class OfflineSubscription:
        @staticmethod
        def retrieve(*args, **kwargs):
            raise AssertionError('Stripe must be mocked in offline tests')

        @staticmethod
        def cancel(*args, **kwargs):
            raise AssertionError('Stripe must be mocked in offline tests')

    stripe.checkout = types.SimpleNamespace(Session=OfflineCheckoutSession)
    stripe.Subscription = OfflineSubscription
    sys.modules['stripe'] = stripe

import app as levelset
from organization_data import (
    create_organization,
    create_user_organization,
    get_organization_context_for_user,
    upsert_organization_profile,
)


def create_legacy_database(path):
    conn = sqlite3.connect(path)
    conn.execute(
        '''CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT NOT NULL,
            organization TEXT DEFAULT '',
            role TEXT DEFAULT 'user',
            plan TEXT DEFAULT 'free',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )'''
    )
    conn.execute(
        '''CREATE TABLE reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            report_type TEXT NOT NULL,
            title TEXT NOT NULL,
            data TEXT DEFAULT '{}',
            score REAL DEFAULT 0,
            max_score REAL DEFAULT 0,
            paid INTEGER DEFAULT 0,
            payment_id TEXT DEFAULT '',
            org_type TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )'''
    )
    conn.execute(
        '''CREATE TABLE payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            report_id INTEGER,
            amount REAL NOT NULL,
            payment_id TEXT NOT NULL,
            status TEXT DEFAULT 'completed',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (report_id) REFERENCES reports(id)
        )'''
    )
    conn.execute(
        '''CREATE TABLE contact_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            subject TEXT,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )'''
    )
    conn.execute(
        "INSERT INTO users (id, email, password_hash, name, organization, role, plan) "
        "VALUES (1, 'owner@example.test', 'unused', 'Owner', 'Legacy Organization', 'user', 'subscription')"
    )
    conn.execute(
        "INSERT INTO users (id, email, password_hash, name, organization, role, plan) "
        "VALUES (2, 'other@example.test', 'unused', 'Other User', '', 'user', 'free')"
    )
    conn.execute(
        "INSERT INTO reports (id, user_id, report_type, title, data, score, max_score, paid, payment_id, org_type) "
        "VALUES (1, 1, 'tech_assessment', 'Legacy Report', ?, 16, 32, 1, 'cs_legacy', '')",
        (json.dumps({'overall_pct': 50}),),
    )
    conn.execute(
        "INSERT INTO payments (id, user_id, report_id, amount, payment_id, status) "
        "VALUES (1, 1, 1, 49.0, 'cs_legacy', 'completed')"
    )
    conn.commit()
    conn.close()


class OrganizationProfileMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, 'legacy-levelset.db')
        self.previous_db_path = levelset.DB_PATH
        create_legacy_database(self.db_path)
        levelset.DB_PATH = self.db_path
        levelset.init_db()
        self.client = levelset.app.test_client()

    def tearDown(self):
        levelset.DB_PATH = self.previous_db_path
        self.tmpdir.cleanup()

    def _conn(self):
        return levelset.get_db()

    def _login_as(self, user_id):
        with self.client.session_transaction() as flask_session:
            flask_session['_user_id'] = str(user_id)
            flask_session['_fresh'] = True

    def test_legacy_users_reports_and_payments_survive_schema_migration(self):
        conn = self._conn()
        user = conn.execute('SELECT email, organization, role, plan FROM users WHERE id = 1').fetchone()
        report = conn.execute(
            'SELECT user_id, data, score, max_score, paid, payment_id, organization_id, respondent_context_json '
            'FROM reports WHERE id = 1'
        ).fetchone()
        payment = conn.execute(
            'SELECT user_id, report_id, amount, payment_id, status FROM payments WHERE id = 1'
        ).fetchone()
        versions = conn.execute('SELECT version, name FROM schema_migrations').fetchall()
        conn.close()

        self.assertEqual(tuple(user), ('owner@example.test', 'Legacy Organization', 'user', 'subscription'))
        self.assertEqual(report['user_id'], 1)
        self.assertEqual(json.loads(report['data'])['overall_pct'], 50)
        self.assertEqual((report['score'], report['max_score'], report['paid'], report['payment_id']), (16, 32, 1, 'cs_legacy'))
        self.assertIsNone(report['organization_id'])
        self.assertIsNone(report['respondent_context_json'])
        self.assertEqual(tuple(payment), (1, 1, 49.0, 'cs_legacy', 'completed'))
        self.assertEqual([(row['version'], row['name']) for row in versions], [(1, 'phase1b_organization_profile')])

    def test_migration_is_idempotent_and_does_not_backfill_legacy_organization_text(self):
        levelset.init_db()
        conn = self._conn()
        organization_count = conn.execute('SELECT COUNT(*) AS count FROM organizations').fetchone()['count']
        migration_count = conn.execute('SELECT COUNT(*) AS count FROM schema_migrations').fetchone()['count']
        report = conn.execute('SELECT organization_id FROM reports WHERE id = 1').fetchone()
        conn.close()

        self.assertEqual(organization_count, 0)
        self.assertEqual(migration_count, 1)
        self.assertIsNone(report['organization_id'])

    def test_organization_profile_and_multiple_relationships_are_retrievable_server_side(self):
        conn = self._conn()
        first_org = create_organization(conn, 'Example Organization')
        second_org = create_organization(conn, 'Second Client Organization')
        create_user_organization(
            conn,
            1,
            first_org,
            relationship_type='external_consultant_advisor',
            respondent_role='Principal Advisor',
            organizational_familiarity='high',
            is_primary=True,
        )
        create_user_organization(
            conn,
            1,
            second_org,
            relationship_type='external_consultant_advisor',
            respondent_role='Principal Advisor',
            organizational_familiarity='medium',
            is_primary=False,
        )
        upsert_organization_profile(
            conn,
            first_org,
            organization_type='nonprofit',
            organization_size_band='11_50',
            workforce_composition='substantial_employee_contractor_mix',
            decision_making_structures=['board_governed', 'executive_led'],
            people_workforce_structures=['distributed_team'],
            technology_structures=['cloud_saas'],
            voice_participation_structures=['staff_feedback', 'community_advisory_group'],
        )
        conn.commit()

        context = get_organization_context_for_user(conn, 1, first_org)
        relationship_count = conn.execute(
            'SELECT COUNT(*) AS count FROM user_organizations WHERE user_id = 1'
        ).fetchone()['count']
        conn.close()

        self.assertEqual(context['organization_name'], 'Example Organization')
        self.assertEqual(context['relationship_type'], 'external_consultant_advisor')
        self.assertEqual(context['respondent_role'], 'Principal Advisor')
        self.assertEqual(context['organizational_familiarity'], 'high')
        self.assertEqual(context['is_primary'], 1)
        self.assertEqual(context['organization_type'], 'nonprofit')
        self.assertEqual(context['organization_size_band'], '11_50')
        self.assertEqual(context['workforce_composition'], 'substantial_employee_contractor_mix')
        self.assertEqual(json.loads(context['decision_making_structures']), ['board_governed', 'executive_led'])
        self.assertEqual(json.loads(context['voice_participation_structures']), ['staff_feedback', 'community_advisory_group'])
        self.assertEqual(relationship_count, 2)

    def test_organization_membership_does_not_change_existing_report_ownership(self):
        conn = self._conn()
        org_id = create_organization(conn, 'Shared Organization Context')
        create_user_organization(conn, 1, org_id, relationship_type='internal_member', is_primary=True)
        create_user_organization(conn, 2, org_id, relationship_type='external_consultant_advisor')
        conn.commit()
        conn.close()

        self._login_as(1)
        owner_response = self.client.get('/report/1')
        self.assertEqual(owner_response.status_code, 200)

        self._login_as(2)
        other_response = self.client.get('/report/1')
        self.assertEqual(other_response.status_code, 303)
        self.assertIn('/dashboard', other_response.headers['Location'])


if __name__ == '__main__':
    unittest.main()
