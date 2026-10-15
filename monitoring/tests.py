from django.test import TestCase
from django.utils import timezone
from unittest.mock import patch
from users.models import Team, TeamMember, TeamMonitor, User
from monitoring.models import (
    APIMonitor,
    Incident,
    MonitorAlertSettings,
    NotificationLog,
)
from logs.models import APILog


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


class MonitoringTaskSafetyTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email="task-owner@example.com",
            password="TestPassword123!",
        )
        self.monitor = APIMonitor.objects.create(
            name="Task Test API",
            url="https://example.com",
            method="GET",
            expected_status=200,
            owner=self.user,
        )

    def successful_response(self):
        response = type("Response", (), {})()
        response.status_code = 200
        response.text = "ok"
        return response, 25, None

    @patch("monitoring.tasks.cache")
    @patch("monitoring.tasks._attempt_request")
    def test_active_forced_check_executes_and_releases_lock(
        self,
        mock_request,
        mock_cache,
    ):
        mock_cache.add.return_value = True
        mock_cache.get.return_value = None
        mock_request.return_value = self.successful_response()

        from monitoring.tasks import check_api_health

        check_api_health.run(
            monitor_id=self.monitor.id,
            force=True,
        )

        self.assertEqual(mock_request.call_count, 1)
        self.assertEqual(
            APILog.objects.filter(api_monitor=self.monitor).count(),
            1,
        )
        mock_cache.delete.assert_called_once_with(
            f"api_monitor:check_lock:{self.monitor.id}"
        )

    @patch("monitoring.tasks.cache")
    @patch("monitoring.tasks._attempt_request")
    def test_inactive_monitor_does_not_execute_or_change_state(
        self,
        mock_request,
        mock_cache,
    ):
        self.monitor.status = "DOWN"
        self.monitor.failure_count = 3
        self.monitor.last_error = "Existing error"
        self.monitor.is_active = False
        self.monitor.save(
            update_fields=[
                "status",
                "failure_count",
                "last_error",
                "is_active",
            ]
        )

        mock_cache.add.return_value = True

        from monitoring.tasks import check_api_health

        check_api_health.run(
            monitor_id=self.monitor.id,
            force=True,
        )

        mock_request.assert_not_called()
        self.assertEqual(
            APILog.objects.filter(api_monitor=self.monitor).count(),
            0,
        )
        self.assertFalse(
            Incident.objects.filter(monitor=self.monitor).exists()
        )
        self.assertFalse(
            NotificationLog.objects.filter(monitor=self.monitor).exists()
        )
        self.monitor.refresh_from_db()
        self.assertEqual(self.monitor.status, "DOWN")
        self.assertEqual(self.monitor.failure_count, 3)
        self.assertEqual(self.monitor.last_error, "Existing error")
        mock_cache.delete.assert_called_once_with(
            f"api_monitor:check_lock:{self.monitor.id}"
        )

    @patch("monitoring.tasks.cache")
    @patch("monitoring.tasks._attempt_request")
    @patch("monitoring.tasks.APILog.objects.create")
    def test_exception_releases_lock_and_subsequent_check_runs(
        self,
        mock_log_create,
        mock_request,
        mock_cache,
    ):
        mock_cache.add.return_value = True
        mock_cache.get.return_value = None
        mock_request.return_value = self.successful_response()
        mock_log_create.side_effect = RuntimeError("database unavailable")

        from monitoring.tasks import check_api_health

        with self.assertRaises(RuntimeError):
            check_api_health.run(
                monitor_id=self.monitor.id,
                force=True,
            )

        lock_key = f"api_monitor:check_lock:{self.monitor.id}"
        mock_cache.delete.assert_called_once_with(lock_key)

        mock_cache.delete.reset_mock()
        mock_log_create.side_effect = None
        mock_log_create.return_value = APILog(
            api_monitor=self.monitor,
            status="UP",
            status_code=200,
            response_time_ms=25,
        )

        check_api_health.run(
            monitor_id=self.monitor.id,
            force=True,
        )

        self.assertEqual(mock_request.call_count, 2)
        mock_cache.delete.assert_called_once_with(lock_key)

    @patch("monitoring.tasks.cache")
    @patch("monitoring.tasks._attempt_request")
    def test_lock_contention_does_not_delete_existing_lock(
        self,
        mock_request,
        mock_cache,
    ):
        mock_cache.add.return_value = False

        from monitoring.tasks import check_api_health

        check_api_health.run(
            monitor_id=self.monitor.id,
            force=True,
        )

        mock_request.assert_not_called()
        mock_cache.delete.assert_not_called()


class SmsAlertTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            password="TestPassword123!",
            mobile_number="+15551234567",
            sms_alerts_enabled=True,
        )

        self.monitor = APIMonitor.objects.create(
            name="Test API",
            url="https://example.com",
            method="GET",
            expected_status=200,
            owner=self.user,
        )

    # --- _collect_alert_phones ---

    def test_collect_phones_with_mobile(self):
        from monitoring.tasks import _collect_alert_phones

        phones = _collect_alert_phones(self.monitor)

        self.assertEqual(phones, ["+15551234567"])

    def test_collect_phones_no_sms_enabled(self):
        self.user.sms_alerts_enabled = False
        self.user.save(update_fields=["sms_alerts_enabled"])

        from monitoring.tasks import _collect_alert_phones

        self.assertEqual(_collect_alert_phones(self.monitor), [])

    def test_collect_phones_no_mobile(self):
        self.user.mobile_number = ""
        self.user.save(update_fields=["mobile_number"])

        from monitoring.tasks import _collect_alert_phones

        self.assertEqual(_collect_alert_phones(self.monitor), [])

    # --- _sms_enabled ---

    def test_sms_enabled_when_phone_enabled(self):
        MonitorAlertSettings.objects.create(
            monitor=self.monitor,
            phone_enabled=True,
        )

        from monitoring.tasks import _sms_enabled

        self.assertTrue(_sms_enabled(self.monitor))

    def test_sms_disabled_when_phone_disabled(self):
        MonitorAlertSettings.objects.create(
            monitor=self.monitor,
            phone_enabled=False,
        )

        from monitoring.tasks import _sms_enabled

        self.assertFalse(_sms_enabled(self.monitor))

    # --- _send_sms ---

    @patch("monitoring.sms_utils.send_sms_alert", return_value=True)
    def test_send_sms_creates_notification_log(self, mock_send):
        MonitorAlertSettings.objects.create(
            monitor=self.monitor,
            phone_enabled=True,
        )

        from monitoring.tasks import _send_sms

        result = _send_sms(
            self.monitor,
            "Subject",
            "Body",
            "DOWN",
            use_cooldown=False,
        )

        self.assertTrue(result)
        self.assertTrue(mock_send.called)

        log = NotificationLog.objects.latest("id")
        self.assertEqual(log.recipient_email, "+15551234567")
        self.assertEqual(log.status, "SENT")
        self.assertTrue(log.subject.startswith("[SMS]"))

    @patch("monitoring.sms_utils.send_sms_alert", return_value=False)
    def test_send_sms_logs_failure(self, mock_send):
        MonitorAlertSettings.objects.create(
            monitor=self.monitor,
            phone_enabled=True,
        )

        from monitoring.tasks import _send_sms

        result = _send_sms(
            self.monitor,
            "Subject",
            "Body",
            "DOWN",
            use_cooldown=False,
        )

        self.assertFalse(result)

        log = NotificationLog.objects.latest("id")
        self.assertEqual(log.status, "FAILED")
        self.assertEqual(
            log.error_message,
            "Twilio SMS delivery failed",
        )

    def test_send_sms_skips_when_phone_disabled(self):
        MonitorAlertSettings.objects.create(
            monitor=self.monitor,
            phone_enabled=False,
        )

        from monitoring.tasks import _send_sms

        result = _send_sms(
            self.monitor,
            "Subject",
            "Body",
            "DOWN",
            use_cooldown=False,
        )

        self.assertFalse(result)
        self.assertFalse(NotificationLog.objects.exists())

    def test_send_sms_skips_without_mobile(self):
        self.user.mobile_number = ""
        self.user.save(update_fields=["mobile_number"])

        MonitorAlertSettings.objects.create(
            monitor=self.monitor,
            phone_enabled=True,
        )

        from monitoring.tasks import _send_sms

        result = _send_sms(
            self.monitor,
            "Subject",
            "Body",
            "DOWN",
            use_cooldown=False,
        )

        self.assertFalse(result)
        self.assertFalse(NotificationLog.objects.exists())

    # --- Integration: _send_down_alert sends both channels ---

    @patch("monitoring.sms_utils.send_sms_alert", return_value=True)
    @patch("monitoring.tasks._send_email", return_value=True)
    def test_down_alert_sends_sms(self, mock_email, mock_sms):
        MonitorAlertSettings.objects.create(
            monitor=self.monitor,
            phone_enabled=True,
        )

        from monitoring.tasks import _send_down_alert

        _send_down_alert(self.monitor, "Connection refused")

        mock_sms.assert_called_once()

        sms_log = NotificationLog.objects.filter(
            subject__startswith="[SMS]"
        ).first()

        self.assertIsNotNone(sms_log)
        self.assertEqual(sms_log.status, "SENT")


# =============================================================================
# TEAM MONITOR SHARING - ACCESS CONTROL
# =============================================================================

class TeamMonitorAccessTests(TestCase):

    def setUp(self):
        from rest_framework.test import APIClient

        self.client = APIClient()

        self.owner = User.objects.create_user(
            email="owner@example.com",
            password="TestPassword123!",
        )

        self.member = User.objects.create_user(
            email="member@example.com",
            password="TestPassword123!",
        )

        self.stranger = User.objects.create_user(
            email="stranger@example.com",
            password="TestPassword123!",
        )

        self.monitor = APIMonitor.objects.create(
            name="Shared API",
            url="https://shared.example.com",
            method="GET",
            expected_status=200,
            owner=self.owner,
        )

        self.team = Team.objects.create(
            name="Dev Team",
            owner=self.owner,
        )

        TeamMember.objects.create(
            team=self.team,
            user=self.member,
            role="VIEWER",
        )

        TeamMonitor.objects.create(
            team=self.team,
            monitor=self.monitor,
        )

        self.shared_id = self.monitor.id
        self.team_id = self.team.id

    # ---------------------------------------------------------
    # Queryset access - who can SEE the shared monitor
    # ---------------------------------------------------------

    def test_owner_sees_own_monitor(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.get(
            "/api/monitoring/"
        )

        self.assertEqual(response.status_code, 200)

        ids = {
            item["id"] for item in response.data
        }

        self.assertIn(self.shared_id, ids)

    def test_member_sees_shared_monitor(self):
        self.client.force_authenticate(user=self.member)

        response = self.client.get(
            "/api/monitoring/"
        )

        self.assertEqual(response.status_code, 200)

        ids = {
            item["id"] for item in response.data
        }

        self.assertIn(self.shared_id, ids)

    def test_stranger_does_not_see_monitor(self):
        self.client.force_authenticate(user=self.stranger)

        response = self.client.get(
            "/api/monitoring/"
        )

        self.assertEqual(response.status_code, 200)

        ids = {
            item["id"] for item in response.data
        }

        self.assertNotIn(self.shared_id, ids)

    def test_member_sees_shared_monitor_detail(self):
        self.client.force_authenticate(user=self.member)

        response = self.client.get(
            f"/api/monitoring/{self.shared_id}/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["id"],
            self.shared_id,
        )

    def test_stranger_cannot_read_monitor_detail(self):
        self.client.force_authenticate(user=self.stranger)

        response = self.client.get(
            f"/api/monitoring/{self.shared_id}/"
        )

        self.assertEqual(response.status_code, 404)

    # ---------------------------------------------------------
    # Read-only for members: no update / delete / toggle
    # ---------------------------------------------------------

    def test_member_cannot_update_monitor(self):
        self.client.force_authenticate(user=self.member)

        response = self.client.patch(
            f"/api/monitoring/{self.shared_id}/",
            {"name": "Hacked"},
        )

        self.assertEqual(response.status_code, 403)

        self.monitor.refresh_from_db()
        self.assertEqual(self.monitor.name, "Shared API")

    def test_member_cannot_delete_monitor(self):
        self.client.force_authenticate(user=self.member)

        response = self.client.delete(
            f"/api/monitoring/{self.shared_id}/"
        )

        self.assertEqual(response.status_code, 403)

        self.assertTrue(
            APIMonitor.objects.filter(
                id=self.shared_id
            ).exists()
        )

    def test_member_cannot_toggle_monitor(self):
        self.client.force_authenticate(user=self.member)

        response = self.client.patch(
            f"/api/monitoring/{self.shared_id}/toggle/"
        )

        self.assertEqual(response.status_code, 403)

        self.monitor.refresh_from_db()
        self.assertTrue(self.monitor.is_active)

    def test_owner_can_toggle_monitor(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.patch(
            f"/api/monitoring/{self.shared_id}/toggle/"
        )

        self.assertEqual(response.status_code, 200)

        self.monitor.refresh_from_db()
        self.assertFalse(self.monitor.is_active)

    # ---------------------------------------------------------
    # Read-only for members: no alert-settings changes
    # ---------------------------------------------------------

    def test_member_cannot_change_alert_settings(self):
        MonitorAlertSettings.objects.create(
            monitor=self.monitor,
            email_enabled=True,
        )

        self.client.force_authenticate(user=self.member)

        response = self.client.patch(
            f"/api/monitoring/{self.shared_id}/alert-settings/",
            {"email_enabled": False},
        )

        self.assertEqual(response.status_code, 403)

        settings_obj = MonitorAlertSettings.objects.get(
            monitor_id=self.shared_id,
        )

        self.assertTrue(settings_obj.email_enabled)

    def test_member_can_read_alert_settings(self):
        self.client.force_authenticate(user=self.member)

        response = self.client.get(
            f"/api/monitoring/{self.shared_id}/alert-settings/"
        )

        self.assertEqual(response.status_code, 200)

    # ---------------------------------------------------------
    # Members CAN check-now and read logs / incidents
    # ---------------------------------------------------------

    def test_member_can_queue_check_now(self):
        from unittest.mock import patch as mock_patch

        self.client.force_authenticate(user=self.member)

        with mock_patch(
            "monitoring.tasks.check_api_health"
        ) as mock_task:
            mock_task.delay.return_value = (
                type("FakeTask", (), {"id": "abc123"})()
            )

            response = self.client.post(
                f"/api/monitoring/{self.shared_id}/check-now/"
            )

        self.assertEqual(response.status_code, 202)
        mock_task.delay.assert_called_once_with(
            monitor_id=self.shared_id,
            force=True,
        )

    def test_member_can_read_logs(self):
        self.client.force_authenticate(user=self.member)

        response = self.client.get(
            f"/api/monitoring/{self.shared_id}/logs/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["monitor_id"], self.shared_id)

    def test_member_sees_incident_dashboard(self):
        self.client.force_authenticate(user=self.member)

        response = self.client.get(
            f"/api/monitoring/incidents/{self.shared_id}/"
        )

        self.assertEqual(response.status_code, 200)

    def test_stranger_cannot_check_now(self):
        self.client.force_authenticate(user=self.stranger)

        response = self.client.post(
            f"/api/monitoring/{self.shared_id}/check-now/"
        )

        self.assertEqual(response.status_code, 404)

    # ---------------------------------------------------------
    # Share / unshare endpoints (owner only)
    # ---------------------------------------------------------

    def test_owner_can_share_monitor(self):
        self.client.force_authenticate(user=self.owner)

        other = APIMonitor.objects.create(
            name="Second API",
            url="https://second.example.com",
            method="GET",
            expected_status=200,
            owner=self.owner,
        )

        response = self.client.post(
            f"/api/users/teams/{self.team_id}/monitors/",
            {"monitor_id": other.id},
        )

        self.assertEqual(response.status_code, 201)

        self.assertTrue(
            TeamMonitor.objects.filter(
                team_id=self.team_id,
                monitor_id=other.id,
            ).exists()
        )

    def test_owner_can_unshare_monitor(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.delete(
            f"/api/users/teams/{self.team_id}/monitors/{self.shared_id}/"
        )

        self.assertEqual(response.status_code, 200)

        self.assertFalse(
            TeamMonitor.objects.filter(
                team_id=self.team_id,
                monitor_id=self.shared_id,
            ).exists()
        )

    def test_member_cannot_share_monitor(self):
        self.client.force_authenticate(user=self.member)

        response = self.client.post(
            f"/api/users/teams/{self.team_id}/monitors/",
            {"monitor_id": self.shared_id},
        )

        self.assertEqual(response.status_code, 404)

    def test_member_cannot_unshare_monitor(self):
        self.client.force_authenticate(user=self.member)

        response = self.client.delete(
            f"/api/users/teams/{self.team_id}/monitors/{self.shared_id}/"
        )

        self.assertEqual(response.status_code, 404)

    def test_owner_can_list_shared_monitors(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.get(
            f"/api/users/teams/{self.team_id}/monitors/"
        )

        self.assertEqual(response.status_code, 200)

        ids = {
            item["id"] for item in response.data
        }

        self.assertIn(self.shared_id, ids)


# =============================================================================
# NOTIFICATION HISTORY - PERIOD FILTERING
# =============================================================================

class NotificationHistoryPeriodTests(TestCase):

    def setUp(self):
        from rest_framework.test import APIClient

        self.client = APIClient()

        self.user = User.objects.create_user(
            email="notif-owner@example.com",
            password="TestPassword123!",
        )

        self.monitor = APIMonitor.objects.create(
            name="Notif API",
            url="https://notif.example.com",
            method="GET",
            expected_status=200,
            owner=self.user,
        )

        self.client.force_authenticate(user=self.user)

        # Create four notification logs at explicit ages so the
        # period filter can be tested deterministically.
        # sent_at is auto_now_add, so backdate with .update().
        self.ages_hours = [
            2,      # within 24h  / 7d / 30d
            24 * 2, # outside 24h, within 7d / 30d
            24 * 10, # outside 7d, within 30d
            24 * 40, # outside all periods
        ]

        for index, age_hours in enumerate(self.ages_hours):
            log = NotificationLog.objects.create(
                monitor=self.monitor,
                alert_type="DOWN",
                recipient_email=f"user{index}@example.com",
                subject=f"Alert {index}",
                status="SENT",
            )

            NotificationLog.objects.filter(id=log.id).update(
                sent_at=(
                    timezone.now()
                    - timezone.timedelta(hours=age_hours)
                )
            )

    def _count(self, period=None):
        url = "/api/monitoring/notifications/"

        if period:
            url += f"?period={period}"

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

        return response.data["count"]

    def test_no_period_returns_all(self):
        self.assertEqual(self._count(), 4)

    def test_period_24h_filters(self):
        self.assertEqual(self._count("24h"), 1)

    def test_period_7d_filters(self):
        self.assertEqual(self._count("7d"), 2)

    def test_period_30d_filters(self):
        self.assertEqual(self._count("30d"), 3)

    def test_invalid_period_returns_400(self):
        response = self.client.get(
            "/api/monitoring/notifications/?period=1y"
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data["detail"],
            "Invalid period.",
        )

    def test_response_format_preserved(self):
        response = self.client.get(
            "/api/monitoring/notifications/?period=7d"
        )

        self.assertEqual(response.status_code, 200)

        body = response.data

        self.assertIn("count", body)
        self.assertIn("results", body)
        self.assertEqual(len(body["results"]), 2)

        expected_keys = {
            "id",
            "monitor_id",
            "monitor_name",
            "alert_type",
            "recipient_email",
            "subject",
            "status",
            "error_message",
            "sent_at",
        }

        self.assertTrue(
            expected_keys.issubset(body["results"][0].keys())
        )



class LatencyAnomalyTests(TestCase):
    """Test the existing latency anomaly helper."""

    def setUp(self):
        from monitoring.views import _build_latency_anomaly
        self.detect = _build_latency_anomaly

    def test_normal_latency(self):
        history = [
            {"latency": 2000},
            {"latency": 2000},
            {"latency": 2500},
        ]
        result = self.detect(history, [], 0)

        self.assertEqual(result["severity"], "normal")
        self.assertEqual(result["current_ms"], 2500.0)
        self.assertEqual(result["baseline_ms"], 2000.0)

    def test_warning_latency(self):
        history = [
            {"latency": 2000},
            {"latency": 2000},
            {"latency": 3000},
        ]
        result = self.detect(history, [], 0)

        self.assertEqual(result["severity"], "warning")
        self.assertEqual(result["kind"], "latency_spike")

    def test_critical_latency(self):
        history = [
            {"latency": 2000},
            {"latency": 2000},
            {"latency": 4000},
        ]
        result = self.detect(history, [], 0)

        self.assertEqual(result["severity"], "critical")
        self.assertEqual(result["kind"], "latency_spike")

    def test_missing_measurements(self):
        result = self.detect([], [], 0)

        self.assertEqual(result["severity"], "normal")
        self.assertIsNone(result["current_ms"])
        self.assertIsNone(result["baseline_ms"])
        self.assertEqual(result["affected_checks"], 0)
