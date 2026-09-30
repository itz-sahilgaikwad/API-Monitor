from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from unittest.mock import patch
from logs.models import APILog
from users.models import User
from monitoring.models import (
    APIMonitor,
    Incident,
    MonitorAlertSettings,
    NotificationLog,
)


class MonitoringModelTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            password="TestPassword123!"
        )

        self.monitor = APIMonitor.objects.create(
            name="Test API",
            url="https://example.com",
            method="GET",
            expected_status=200,
            owner=self.user,
        )

    def test_api_monitor_creation(self):
        self.assertEqual(self.monitor.name, "Test API")
        self.assertEqual(self.monitor.url, "https://example.com")
        self.assertEqual(self.monitor.method, "GET")
        self.assertEqual(self.monitor.expected_status, 200)
        self.assertEqual(self.monitor.owner, self.user)
        self.assertTrue(self.monitor.is_active)

    def test_api_monitor_defaults(self):
        self.assertEqual(self.monitor.status, "UP")
        self.assertEqual(self.monitor.failure_count, 0)
        self.assertEqual(self.monitor.check_interval, 60)
        self.assertEqual(
            self.monitor.response_time_threshold_ms,
            1000,
        )

    def test_incident_duration_when_resolved(self):
        started = timezone.now()
        resolved = started + timezone.timedelta(seconds=120)

        incident = Incident.objects.create(
            monitor=self.monitor,
            started_at=started,
            resolved_at=resolved,
            status="RESOLVED",
            reason="Test outage",
        )

        self.assertEqual(incident.duration_seconds(), 120)

    def test_ongoing_incident_has_no_duration(self):
        incident = Incident.objects.create(
            monitor=self.monitor,
            started_at=timezone.now(),
            status="ONGOING",
            reason="Test outage",
        )

        self.assertIsNone(incident.duration_seconds())

    def test_alert_settings_creation(self):
        settings = MonitorAlertSettings.objects.create(
            monitor=self.monitor,
        )

        self.assertTrue(settings.alerts_enabled)
        self.assertTrue(settings.down_alert_enabled)
        self.assertTrue(settings.slow_alert_enabled)
        self.assertTrue(settings.recovery_alert_enabled)
        self.assertTrue(settings.email_enabled)
        self.assertFalse(settings.phone_enabled)
        self.assertEqual(settings.cooldown_minutes, 30)

    def test_notification_log_creation(self):
        notification = NotificationLog.objects.create(
            monitor=self.monitor,
            alert_type="DOWN",
            recipient_email="test@example.com",
            subject="API Down",
            status="SENT",
        )

        self.assertEqual(notification.monitor, self.monitor)
        self.assertEqual(notification.alert_type, "DOWN")
        self.assertEqual(notification.status, "SENT")
        self.assertEqual(
            notification.recipient_email,
            "test@example.com",
        )


class MonitoringStateCorrectnessTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email="state-test@example.com",
            password="TestPassword123!",
        )
        self.monitor = APIMonitor.objects.create(
            name="State Test API",
            url="https://example.com",
            owner=self.user,
        )

    @patch("monitoring.tasks._send_down_alert", return_value=True)
    @patch("monitoring.tasks.time.sleep")
    @patch("monitoring.tasks._attempt_request")
    @patch("monitoring.tasks._monitor_check_lock")
    def test_down_requires_three_separate_failed_checks(
        self,
        mock_lock_factory,
        mock_attempt,
        _mock_sleep,
        _mock_down_alert,
    ):
        from monitoring.tasks import check_api_health

        lock = mock_lock_factory.return_value
        lock.acquire.return_value = True
        failed_response = type("Response", (), {"status_code": 503})()
        mock_attempt.return_value = (
            failed_response,
            12.0,
            None,
        )

        for expected_status, expected_failures in (
            ("UP", 1),
            ("UP", 2),
            ("DOWN", 3),
        ):
            check_api_health.run(
                monitor_id=self.monitor.id,
                force=True,
            )
            self.monitor.refresh_from_db()
            self.assertEqual(self.monitor.status, expected_status)
            self.assertEqual(
                self.monitor.failure_count,
                expected_failures,
            )

        self.assertEqual(APILog.objects.filter(api_monitor=self.monitor).count(), 3)
        self.assertEqual(
            Incident.objects.filter(
                monitor=self.monitor,
                status="ONGOING",
            ).count(),
            1,
        )
        self.assertEqual(_mock_down_alert.call_count, 1)
        self.assertEqual(lock.acquire.call_count, 3)
        self.assertEqual(lock.release.call_count, 3)

    @patch("monitoring.tasks._attempt_request")
    @patch("monitoring.tasks._monitor_check_lock")
    def test_busy_lock_skips_duplicate_check(
        self,
        mock_lock_factory,
        mock_attempt,
    ):
        from monitoring.tasks import check_api_health

        mock_lock_factory.return_value.acquire.return_value = False

        result = check_api_health.run(
            monitor_id=self.monitor.id,
            force=True,
        )

        self.assertIn("already running", result)
        mock_attempt.assert_not_called()
        self.assertEqual(APILog.objects.filter(api_monitor=self.monitor).count(), 0)

    @patch("monitoring.tasks.queue_monitor_check")
    def test_periodic_task_fans_out_per_active_monitor(self, mock_queue):
        from monitoring.tasks import check_api_health

        another_monitor = APIMonitor.objects.create(
            name="Second API",
            url="https://example.org",
            owner=self.user,
        )
        paused_monitor = APIMonitor.objects.create(
            name="Paused API",
            url="https://paused.example",
            owner=self.user,
            is_active=False,
        )

        queued_count = check_api_health.run()

        self.assertEqual(queued_count, 2)
        self.assertCountEqual(
            [
                call.args[0]
                for call in mock_queue.call_args_list
            ],
            [self.monitor.id, another_monitor.id],
        )
        self.assertNotIn(
            paused_monitor.id,
            [call.args[0] for call in mock_queue.call_args_list],
        )

    @patch("monitoring.tasks.queue_monitor_check")
    def test_check_now_queues_only_selected_monitor(self, mock_queue):
        mock_queue.return_value = type("QueuedTask", (), {"id": "task-123"})()
        client = APIClient()
        client.force_authenticate(self.user)

        response = client.post(
            f"/api/monitoring/{self.monitor.id}/check-now/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(mock_queue.call_count, 1)
        self.assertEqual(
            mock_queue.call_args,
            ((self.monitor.id,), {}),
        )
