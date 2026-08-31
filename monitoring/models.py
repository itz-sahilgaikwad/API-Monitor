from django.db import models

from django.conf import settings


class APIMonitor(models.Model):

    HTTP_METHODS = (
        ("GET", "GET"),
        ("POST", "POST"),
        ("PUT", "PUT"),
        ("PATCH", "PATCH"),
        ("DELETE", "DELETE"),
    )

    INTERVAL_CHOICES = (
        (30, "Every 30 seconds"),
        (60, "Every 1 minute"),
        (300, "Every 5 minutes"),
        (600, "Every 10 minutes"),
    )

    AUTH_TYPES = (
        ("none", "No Authentication"),
        ("bearer", "Bearer API Key"),
        ("x_api_key", "X-API-Key"),
    )

    RESPONSE_VALIDATION_TYPES = (
        ("none", "No Response Validation"),
        ("contains", "Response Contains Text"),
        ("exact", "Exact Response Match"),
        ("json", "JSON Response Validation"),
    )

    # Basic API configuration

    name = models.CharField(
        max_length=100
    )

    url = models.URLField()

    method = models.CharField(
        max_length=10,
        choices=HTTP_METHODS,
        default="GET"
    )

    expected_status = models.IntegerField(
        default=200
    )

    is_active = models.BooleanField(
        default=True
    )

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )

    # Runtime state

    status = models.CharField(
        max_length=10,
        choices=[
            ("UP", "UP"),
            ("SLOW", "SLOW"),
            ("DOWN", "DOWN"),
        ],
        default="UP"
    )

    failure_count = models.IntegerField(
        default=0
    )

    response_time = models.FloatField(
        null=True,
        blank=True
    )  # milliseconds

    # Slow response threshold

    response_time_threshold_ms = models.FloatField(
        default=1000,
        help_text="Response time threshold in milliseconds"
    )

    # Contact / authentication

    phone_number = models.CharField(
        max_length=20,
        blank=True,
        null=True
    )

    auth_type = models.CharField(
        max_length=20,
        choices=AUTH_TYPES,
        default="none"
    )

    api_key = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    # Custom request headers

    request_headers = models.JSONField(
        default=dict,
        blank=True
    )

    # Request body for POST / PUT / PATCH requests

    request_body = models.TextField(
        default="",
        blank=True,
        help_text="Optional request body for POST, PUT, and PATCH requests."
    )

    # Response content validation

    response_validation_type = models.CharField(
        max_length=20,
        choices=RESPONSE_VALIDATION_TYPES,
        default="none",
        help_text="How the API response should be validated."
    )

    expected_response = models.TextField(
        blank=True,
        default="",
        help_text=(
            "Expected response value. For 'contains', enter text that "
            "must appear in the response. For 'exact', enter the exact "
            "response text. For 'json', enter valid JSON."
        )
    )

    # Downtime tracking

    downtime_started_at = models.DateTimeField(
        null=True,
        blank=True
    )

    last_downtime_duration = models.FloatField(
        null=True,
        blank=True
    )  # seconds

    # Monitoring interval

    check_interval = models.IntegerField(
        choices=INTERVAL_CHOICES,
        default=60
    )

    # Last health check

    last_checked_at = models.DateTimeField(
        null=True,
        blank=True
    )

    # Last error

    last_error = models.TextField(
        null=True,
        blank=True
    )

    # Cached uptime

    uptime_percentage = models.FloatField(
        null=True,
        blank=True
    )

    def __str__(self):
        return self.name


class Incident(models.Model):

    monitor = models.ForeignKey(
        APIMonitor,
        on_delete=models.CASCADE,
        related_name="incidents"
    )

    started_at = models.DateTimeField()

    resolved_at = models.DateTimeField(
        null=True,
        blank=True
    )

    status = models.CharField(
        max_length=20,
        choices=[
            ("ONGOING", "ONGOING"),
            ("RESOLVED", "RESOLVED"),
        ],
        default="ONGOING"
    )

    reason = models.TextField(
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def duration_seconds(self):
        if self.resolved_at:
            return (
                self.resolved_at - self.started_at
            ).total_seconds()

        return None

    def __str__(self):
        return f"{self.monitor.name} incident"
        # =============================================================================
# MONITOR ALERT SETTINGS
# =============================================================================

class MonitorAlertSettings(models.Model):

    monitor = models.OneToOneField(
        APIMonitor,
        on_delete=models.CASCADE,
        related_name="alert_settings"
    )

    # Master alert switch
    alerts_enabled = models.BooleanField(
        default=True
    )

    # Alert types
    down_alert_enabled = models.BooleanField(
        default=True
    )

    slow_alert_enabled = models.BooleanField(
        default=True
    )

    recovery_alert_enabled = models.BooleanField(
        default=True
    )

    # Notification channels
    email_enabled = models.BooleanField(
        default=True
    )

    phone_enabled = models.BooleanField(
        default=False
    )

    # Prevent repeated notifications
    cooldown_minutes = models.PositiveIntegerField(
        default=30
    )

    # Timestamps
    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return f"Alert settings - {self.monitor.name}"