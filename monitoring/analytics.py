from datetime import timedelta
import math

from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from logs.models import APILog
from monitoring.models import APIMonitor


VALID_PERIODS = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


def _period_window(period, now=None):
    """Return a validated period and its inclusive time window."""
    now = now or timezone.now()
    if period not in VALID_PERIODS:
        period = "7d"
    return period, now - VALID_PERIODS[period], now


def _logs_for_period(monitor, start_time, end_time):
    """Checks belonging to one monitor and the requested time window."""
    return APILog.objects.filter(
        api_monitor=monitor,
        checked_at__gte=start_time,
        checked_at__lte=end_time,
    )


def _valid_response_times(logs):
    """Return finite, non-negative response times in milliseconds."""
    values = logs.exclude(response_time_ms__isnull=True).values_list(
        "response_time_ms", flat=True
    )
    result = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            continue
        if math.isfinite(number) and number >= 0:
            result.append(number)
    return result


def _percentile_nearest_rank(values, percentile):
    """
    Calculate a percentile using the nearest-rank method.
    percentile is a fraction from 0 to 1, for example 0.95 for P95.
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def _analytics_counts(logs):
    """Calculate counts and uptime from the same filtered check set."""
    total_checks = logs.count()
    up_checks = logs.filter(status="UP").count()
    down_checks = logs.filter(status="DOWN").count()

    # Uptime is the percentage of recorded checks marked UP in this period.
    # It is not a time-weighted availability calculation.
    uptime_percentage = (
        (up_checks / total_checks) * 100 if total_checks else 0.0
    )

    return {
        "total_checks": total_checks,
        "up_checks": up_checks,
        "down_checks": down_checks,
        "uptime_percentage": round(uptime_percentage, 2),
    }


def _response_time_metrics(logs):
    response_times = _valid_response_times(logs)
    average = (
        sum(response_times) / len(response_times) if response_times else 0.0
    )
    p95 = _percentile_nearest_rank(response_times, 0.95)

    return {
        "response_times": response_times,
        "avg_response_time": round(average, 2),
        "p95_latency": round(p95, 2),
    }


class MonitorAnalyticsView(APIView):
    """
    Return analytics for one monitor.

    Supported periods:
      24h = last 24 hours
      7d  = last 7 days
      30d = last 30 days

    Response-time values are milliseconds. Uptime is based on recorded checks,
    not on elapsed wall-clock time.
    """

    def get(self, request, monitor_id):
        try:
            monitor = APIMonitor.objects.get(pk=monitor_id)
        except APIMonitor.DoesNotExist:
            return Response(
                {"error": "Monitor not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        period, start_time, end_time = _period_window(
            request.query_params.get("period", "7d")
        )

        logs = _logs_for_period(monitor, start_time, end_time)
        counts = _analytics_counts(logs)
        response_metrics = _response_time_metrics(logs)

        response_time_history = []
        for log in logs.only(
            "checked_at", "response_time_ms", "status"
        ).iterator():
            if log.response_time_ms is None:
                continue
            try:
                response_time = float(log.response_time_ms)
            except (TypeError, ValueError, OverflowError):
                continue
            if not math.isfinite(response_time) or response_time < 0:
                continue

            response_time_history.append(
                {
                    "checked_at": log.checked_at,
                    "response_time_ms": response_time,
                    "status": log.status,
                }
            )

        recent_history = list(
            logs.order_by("-checked_at")[:10].values(
                "status",
                "checked_at",
                "response_time_ms",
            )
        )

        return Response(
            {
                "monitor_id": monitor.id,
                "name": monitor.name,
                "url": monitor.url,
                "status": monitor.status,
                "period": period,
                "start_time": start_time,
                "end_time": end_time,
                **counts,
                **response_metrics,
                "response_time_history": response_time_history,
                "recent_history": recent_history,
            }
        )


class GlobalMonitoringAnalytics(APIView):
    """Return all-monitor analytics using one shared time window."""

    def get(self, request):
        result = []
        monitors = APIMonitor.objects.all().order_by("id")

        for monitor in monitors:
            # Preserve the existing global endpoint's all-time behavior.
            logs = APILog.objects.filter(api_monitor=monitor)
            counts = _analytics_counts(logs)
            response_metrics = _response_time_metrics(logs)

            result.append(
                {
                    "monitor_id": monitor.id,
                    "name": monitor.name,
                    "url": monitor.url,
                    "status": monitor.status,
                    **counts,
                    "avg_response_time": response_metrics["avg_response_time"],
                    "p95_latency": response_metrics["p95_latency"],
                }
            )

        return Response(result)


class PublicStatusPage(APIView):
    """
    Public status page. Authentication is disabled intentionally.
    """

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        monitors = APIMonitor.objects.filter(is_active=True).order_by("id")
        result = []

        for monitor in monitors:
            logs = APILog.objects.filter(api_monitor=monitor)
            counts = _analytics_counts(logs)
            last_log = logs.order_by("-checked_at").first()

            result.append(
                {
                    "name": monitor.name,
                    "url": monitor.url,
                    "status": monitor.status,
                    "uptime_percentage": counts["uptime_percentage"],
                    "last_checked": last_log.checked_at if last_log else None,
                }
            )

        overall_status = "OPERATIONAL"
        if any(service["status"] == "DOWN" for service in result):
            overall_status = "DEGRADED"

        return Response(
            {
                "overall_status": overall_status,
                "services": result,
            }
        )
