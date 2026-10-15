from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.http import JsonResponse
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

import redis

from .models import APIMonitor, Incident
from logs.models import APILog


class AdminSystemOverviewView(APIView):
    """Return system-wide monitoring statistics for administrators only."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        if getattr(request.user, "role", None) != "ADMIN":
            return JsonResponse(
                {"detail": "Admin access required."},
                status=403,
            )

        User = get_user_model()

        monitors = APIMonitor.objects.all()
        logs = APILog.objects.all()
        incidents = Incident.objects.all()

        active_monitors = monitors.filter(is_active=True)
        paused_monitors = monitors.filter(is_active=False)
        down_monitors = monitors.filter(status="DOWN")

        # Match the existing Dashboard's status logic:
        # UP + response time above the monitor threshold = SLOW
        slow_monitors = []

        for monitor in active_monitors.filter(status="UP"):
            if (
                monitor.response_time is not None
                and monitor.response_time > monitor.response_time_threshold_ms
            ):
                slow_monitors.append(monitor.id)

        slow_count = len(slow_monitors)

        # Healthy means UP and NOT slow.
        healthy_count = (
            active_monitors.filter(status="UP").count()
            - slow_count
        )

        ongoing_incidents = incidents.filter(status="ONGOING")

        checks_up = logs.filter(status="UP").count()
        checks_down = logs.exclude(status="UP").count()

        # System dependency health
        checks = {
            "database": "ok",
            "redis": "ok",
        }

        healthy = True

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception:
            checks["database"] = "error"
            healthy = False

        try:
            client = redis.Redis.from_url(
                settings.CELERY_BROKER_URL,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            client.ping()
        except Exception:
            checks["redis"] = "error"
            healthy = False

        recent_incidents = list(
            incidents
            .select_related("monitor")
            .order_by("-created_at")[:10]
            .values(
                "id",
                "monitor_id",
                "monitor__name",
                "status",
                "reason",
                "started_at",
                "resolved_at",
                "created_at",
            )
        )

        return JsonResponse(
            {
                "status": "ok" if healthy else "degraded",
                "generated_at": timezone.now(),
                "system": {
                    "users": User.objects.count(),
                    "monitors": monitors.count(),
                    "active_monitors": active_monitors.count(),
                    "paused_monitors": paused_monitors.count(),
                    "healthy_monitors": healthy_count,
                    "slow_monitors": slow_count,
                    "down_monitors": down_monitors.count(),
                    "total_checks": logs.count(),
                    "successful_checks": checks_up,
                    "failed_checks": checks_down,
                    "total_incidents": incidents.count(),
                    "ongoing_incidents": ongoing_incidents.count(),
                },
                "checks": checks,
                "recent_incidents": recent_incidents,
            },
            status=200 if healthy else 503,
        )