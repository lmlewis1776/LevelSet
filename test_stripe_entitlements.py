"""Offline tests for Stripe Checkout entitlement verification.

All Stripe provider calls are mocked. These tests use a temporary SQLite database and
never create charges, subscriptions, refunds, or cancellations with Stripe.
"""
import os
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

# Keep the suite offline and runnable in a minimal environment. Production still
# installs the real Stripe SDK from requirements.txt; these placeholders are only
# used when that SDK is absent locally.
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


class StripeCheckoutEntitlementTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.previous_db_path = levelset.DB_PATH
        levelset.DB_PATH = os.path.join(self.tmpdir.name, 'levelset-test.db')
        levelset.app.config.update(TESTING=True, SECRET_KEY='test-secret-key')
        levelset.app.secret_key = 'test-secret-key'
        levelset.serializer = levelset.URLSafeTimedSerializer(levelset.app.secret_key)
        levelset.init_db()

        conn = levelset.get_db()
        conn.execute(
            "INSERT INTO users (id, email, password_hash, name, organization, role, plan) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (1, 'owner@example.test', 'unused', 'Report Owner', 'Example Org', 'user', 'free')
        )
        conn.execute(
            "INSERT INTO users (id, email, password_hash, name, organization, role, plan) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (2, 'other@example.test', 'unused', 'Other User', 'Other Org', 'user', 'free')
        )
        conn.execute(
            "INSERT INTO reports (id, user_id, report_type, title, data, score, max_score, paid) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (1, 1, 'tech_assessment', 'Owner report', '{"overall_pct": 50}', 1, 1, 0)
        )
        conn.commit()
        conn.close()

        self.client = levelset.app.test_client()
        with self.client.session_transaction() as flask_session:
            flask_session['_user_id'] = '1'
            flask_session['_fresh'] = True

    def tearDown(self):
        levelset.DB_PATH = self.previous_db_path
        self.tmpdir.cleanup()

    def _report_paid(self):
        conn = levelset.get_db()
        row = conn.execute('SELECT paid FROM reports WHERE id = 1').fetchone()
        conn.close()
        return row['paid']

    def _plan(self):
        conn = levelset.get_db()
        row = conn.execute('SELECT plan FROM users WHERE id = 1').fetchone()
        conn.close()
        return row['plan']

    def _subscription_record(self, user_id=1):
        conn = levelset.get_db()
        row = conn.execute(
            '''SELECT id, payment_id, status FROM payments
               WHERE user_id = ? AND report_id IS NULL
               ORDER BY id DESC LIMIT 1''',
            (user_id,)
        ).fetchone()
        conn.close()
        return row

    def _payment_count(self, user_id=1):
        conn = levelset.get_db()
        count = conn.execute('SELECT COUNT(*) AS count FROM payments WHERE user_id = ?', (user_id,)).fetchone()['count']
        conn.close()
        return count

    def _report_contains_premium_analysis(self):
        response = self.client.get('/report/1')
        self.assertEqual(response.status_code, 200)
        return 'Based on our exhaustive system diagnostics' in response.get_data(as_text=True)

    def _start_checkout(self, checkout_type):
        with patch.object(
            levelset.stripe.checkout.Session,
            'create',
            return_value=types.SimpleNamespace(url='https://checkout.example.test/session')
        ) as create:
            suffix = '?report_id=1' if checkout_type == 'ppr' else ''
            response = self.client.get(f'/create-checkout-session/{checkout_type}{suffix}')
        self.assertEqual(response.status_code, 303)
        return create.call_args.kwargs

    @staticmethod
    def _provider_session(checkout_args, **overrides):
        session = {
            'id': 'cs_offline_verified',
            'client_reference_id': checkout_args['client_reference_id'],
            'metadata': dict(checkout_args['metadata']),
            'mode': checkout_args['mode'],
            'status': 'complete',
            'currency': 'usd',
            'amount_total': 4900,
            'payment_status': 'paid',
        }
        session.update(overrides)
        return session

    def test_admin_role_grants_premium_product_access_without_billing_records(self):
        conn = levelset.get_db()
        conn.execute("UPDATE users SET role = 'admin', plan = 'free' WHERE id = 1")
        conn.commit()
        conn.close()

        self.assertTrue(self._report_contains_premium_analysis())
        self.assertEqual(self._plan(), 'free')
        self.assertEqual(self._payment_count(), 0)

    def test_free_user_does_not_receive_premium_product_access(self):
        self.assertFalse(self._report_contains_premium_analysis())
        self.assertEqual(self._payment_count(), 0)

    def test_active_subscriber_retains_premium_product_access(self):
        conn = levelset.get_db()
        conn.execute("UPDATE users SET plan = 'subscription' WHERE id = 1")
        conn.commit()
        conn.close()

        self.assertTrue(self._report_contains_premium_analysis())
        self.assertEqual(self._payment_count(), 0)

    def test_admin_access_survives_subscription_state_changes(self):
        conn = levelset.get_db()
        conn.execute("UPDATE users SET role = 'admin', plan = 'subscription' WHERE id = 1")
        conn.commit()
        conn.close()

        # Simulate a later billing-state change without altering the Admin role.
        conn = levelset.get_db()
        conn.execute("UPDATE users SET plan = 'free' WHERE id = 1")
        conn.commit()
        conn.close()

        self.assertTrue(self._report_contains_premium_analysis())
        self.assertEqual(self._payment_count(), 0)

    def test_report_checkout_binds_signed_user_report_and_price_metadata(self):
        checkout_args = self._start_checkout('ppr')

        self.assertEqual(checkout_args['mode'], 'payment')
        self.assertIn('session_id={CHECKOUT_SESSION_ID}', checkout_args['success_url'])
        self.assertEqual(checkout_args['metadata'], {
            'levelset_product': levelset.STRIPE_PRODUCT_REPORT,
            'levelset_purchase_type': 'report',
            'levelset_user_id': '1',
            'levelset_report_id': '1',
            'levelset_amount_cents': '4900',
            'levelset_currency': 'usd',
        })
        self.assertEqual(
            checkout_args['line_items'][0]['price_data']['product_data']['metadata'],
            {'levelset_product': levelset.STRIPE_PRODUCT_REPORT}
        )
        payload = levelset._load_checkout_token(checkout_args['client_reference_id'])
        self.assertEqual(payload['user_id'], '1')
        self.assertEqual(payload['report_id'], '1')
        self.assertEqual(payload['purchase_type'], 'report')

    def test_verified_paid_report_session_unlocks_only_bound_report(self):
        checkout_args = self._start_checkout('ppr')
        provider_session = self._provider_session(checkout_args)

        with patch.object(levelset.stripe.checkout.Session, 'retrieve', return_value=provider_session):
            response = self.client.get('/stripe-success/ppr_1?session_id=cs_offline_verified')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._report_paid(), 1)

    def test_missing_unpaid_wrong_mode_or_wrong_product_session_does_not_unlock_report(self):
        with patch.object(levelset.stripe.checkout.Session, 'retrieve') as retrieve:
            missing = self.client.get('/stripe-success/ppr_1')
        self.assertEqual(missing.status_code, 302)
        retrieve.assert_not_called()
        self.assertEqual(self._report_paid(), 0)

        checkout_args = self._start_checkout('ppr')
        invalid_sessions = [
            self._provider_session(checkout_args, payment_status='unpaid'),
            self._provider_session(checkout_args, mode='subscription'),
            self._provider_session(
                checkout_args,
                metadata={**checkout_args['metadata'], 'levelset_product': 'different_product'}
            ),
        ]
        for index, provider_session in enumerate(invalid_sessions):
            with self.subTest(case=index), patch.object(
                levelset.stripe.checkout.Session, 'retrieve', return_value=provider_session
            ):
                response = self.client.get('/stripe-success/ppr_1?session_id=cs_invalid')
            self.assertEqual(response.status_code, 302)
            self.assertEqual(self._report_paid(), 0)

    def test_session_bound_to_another_user_cannot_unlock_current_users_report(self):
        checkout_args = self._start_checkout('ppr')
        provider_session = self._provider_session(checkout_args)
        other_payload = levelset._load_checkout_token(checkout_args['client_reference_id'])
        other_payload['user_id'] = '2'
        provider_session['client_reference_id'] = levelset._checkout_token(other_payload)

        with patch.object(levelset.stripe.checkout.Session, 'retrieve', return_value=provider_session):
            response = self.client.get('/stripe-success/ppr_1?session_id=cs_other_user')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._report_paid(), 0)

    def test_active_subscription_session_sets_plan_after_provider_verification(self):
        checkout_args = self._start_checkout('subscription')
        provider_session = self._provider_session(checkout_args, subscription='sub_offline_active')

        with patch.object(levelset.stripe.checkout.Session, 'retrieve', return_value=provider_session), patch.object(
            levelset.stripe.Subscription, 'retrieve', return_value={'id': 'sub_offline_active', 'status': 'active'}
        ):
            response = self.client.get('/stripe-success/subscription?session_id=cs_subscription')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._plan(), 'subscription')
        record = self._subscription_record()
        self.assertEqual(record['payment_id'], 'sub_offline_active')
        self.assertEqual(record['status'], 'subscription_active')

    def test_inactive_subscription_never_sets_plan(self):
        checkout_args = self._start_checkout('subscription')
        provider_session = self._provider_session(checkout_args, subscription='sub_offline_incomplete')

        with patch.object(levelset.stripe.checkout.Session, 'retrieve', return_value=provider_session), patch.object(
            levelset.stripe.Subscription, 'retrieve', return_value={'id': 'sub_offline_incomplete', 'status': 'incomplete'}
        ):
            response = self.client.get('/stripe-success/subscription?session_id=cs_subscription')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._plan(), 'free')

    def test_cancelled_provider_subscription_downgrades_only_after_confirmation(self):
        conn = levelset.get_db()
        conn.execute("UPDATE users SET plan = 'subscription' WHERE id = 1")
        conn.execute(
            "INSERT INTO payments (user_id, amount, payment_id, status) VALUES (?, ?, ?, ?)",
            (1, 49.00, 'sub_offline_active', 'subscription_active')
        )
        conn.commit()
        conn.close()

        with patch.object(
            levelset.stripe.Subscription,
            'cancel',
            return_value={'id': 'sub_offline_active', 'status': 'canceled'}
        ) as cancel:
            response = self.client.post('/cancel-subscription')

        self.assertEqual(response.status_code, 303)
        cancel.assert_called_once_with('sub_offline_active')
        self.assertEqual(self._plan(), 'free')
        self.assertEqual(self._subscription_record()['status'], 'subscription_cancelled')

    def test_cancel_stripe_failure_does_not_downgrade_access(self):
        conn = levelset.get_db()
        conn.execute("UPDATE users SET plan = 'subscription' WHERE id = 1")
        conn.execute(
            "INSERT INTO payments (user_id, amount, payment_id, status) VALUES (?, ?, ?, ?)",
            (1, 49.00, 'sub_offline_failure', 'subscription_active')
        )
        conn.commit()
        conn.close()

        with patch.object(levelset.stripe.Subscription, 'cancel', side_effect=RuntimeError('offline failure')):
            response = self.client.post('/cancel-subscription')

        self.assertEqual(response.status_code, 303)
        self.assertEqual(self._plan(), 'subscription')
        self.assertEqual(self._subscription_record()['status'], 'subscription_active')

    def test_cancel_does_not_downgrade_without_a_stored_stripe_provider_identifier(self):
        conn = levelset.get_db()
        conn.execute("UPDATE users SET plan = 'subscription' WHERE id = 1")
        conn.commit()
        conn.close()

        response = self.client.post('/cancel-subscription')

        self.assertEqual(response.status_code, 303)
        self.assertEqual(self._plan(), 'subscription')

    def test_user_cannot_cancel_another_users_stored_subscription(self):
        conn = levelset.get_db()
        conn.execute("UPDATE users SET plan = 'subscription' WHERE id = 1")
        conn.execute(
            "INSERT INTO payments (user_id, amount, payment_id, status) VALUES (?, ?, ?, ?)",
            (2, 49.00, 'sub_other_user', 'subscription_active')
        )
        conn.commit()
        conn.close()

        with patch.object(levelset.stripe.Subscription, 'cancel') as cancel:
            response = self.client.post('/cancel-subscription')

        self.assertEqual(response.status_code, 303)
        cancel.assert_not_called()
        self.assertEqual(self._plan(), 'subscription')
        self.assertEqual(self._subscription_record(user_id=2)['status'], 'subscription_active')


if __name__ == '__main__':
    unittest.main()
