from django.test import TestCase
from django.utils import timezone
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
