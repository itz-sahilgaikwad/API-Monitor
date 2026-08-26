from datetime import timedelta

from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from logs.models import APILog
from monitoring.models import APIMonitor


class MonitorAnalyticsView(APIView):
    """
    Return analytics for one monitor.

    Supported periods:
        24h = last 24 hours
        7d  = last 7 days
        30d = last 30 days
    """

    def get(self, request, monitor_id):
        try:
            monitor = APIMonitor.objects.get(pk=monitor_id)
        except APIMonitor.DoesNotExist:
            return Response(
                {"error": "Monitor not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # ---------------------------------------------------------
        # PERIOD
        # ---------------------------------------------------------
        period = request.query_params.get("period", "7d")

        now = timezone.now()

        if period == "24h":
            start_time = now - timedelta(hours=24)

        elif period == "30d":
            start_time = now - timedelta(days=30)

        else:
            period = "7d"
            start_time = now - timedelta(days=7)

        # ---------------------------------------------------------
        # LOGS FOR SELECTED MONITOR + SELECTED PERIOD
        # ---------------------------------------------------------
        logs = APILog.objects.filter(
            api_monitor=monitor,
            checked_at__gte=start_time,
            checked_at__lte=now,
        ).order_by("checked_at")

        # ---------------------------------------------------------
        # CHECK COUNTS
        # ---------------------------------------------------------
        total_checks = logs.count()

        up_checks = logs.filter(status="UP").count()

        down_checks = logs.filter(status="DOWN").count()

        uptime_percentage = (
            (up_checks / total_checks) * 100
            if total_checks
            else 0
        )

        # ---------------------------------------------------------
        # RESPONSE TIMES
        # ---------------------------------------------------------
        response_times = list(
            logs.exclude(
                response_time_ms=None
            ).values_list(
                "response_time_ms",
                flat=True,
            )
        )

        # Remove invalid/negative values just in case
        response_times = [
            float(value)
            for value in response_times
            if value is not None and float(value) >= 0
        ]

        # Average response time
        avg_response_time = (
            sum(response_times) / len(response_times)
            if response_times
            else 0
        )

        # ---------------------------------------------------------
        # P95 LATENCY
        # ---------------------------------------------------------
        p95_latency = 0

        if response_times:
            sorted_times = sorted(response_times)

            index = int(
                0.95 * (len(sorted_times) - 1)
            )

            p95_latency = sorted_times[index]

        # ---------------------------------------------------------
        # RESPONSE TIME HISTORY
        #
        # Used by analytics.html for the response-time graph.
        # ---------------------------------------------------------
        response_time_history = []

        for log in logs:
            if log.response_time_ms is not None:
                response_time_history.append(
                    {
                        "checked_at": log.checked_at,
                        "response_time_ms": float(
                            log.response_time_ms
                        ),
                        "status": log.status,
                    }
                )

        # ---------------------------------------------------------
        # RECENT CHECK HISTORY
        # ---------------------------------------------------------
        recent_history = list(
            logs.order_by("-checked_at")[:10].values(
                "status",
                "checked_at",
                "response_time_ms",
            )
        )

        # ---------------------------------------------------------
        # CURRENT STATUS
        # ---------------------------------------------------------
        current_status = monitor.status

        # ---------------------------------------------------------
        # RESPONSE
        # ---------------------------------------------------------
        return Response(
            {
                "monitor_id": monitor.id,
                "name": monitor.name,
                "url": monitor.url,
                "status": current_status,

                "period": period,

                "start_time": start_time,
                "end_time": now,

                "total_checks": total_checks,
                "up_checks": up_checks,
                "down_checks": down_checks,

                "uptime_percentage": round(
                    uptime_percentage,
                    2,
                ),

                "avg_response_time": round(
                    avg_response_time,
                    2,
                ),

                "p95_latency": round(
                    p95_latency,
                    2,
                ),

                "response_times": response_times,

                "response_time_history": response_time_history,

                "recent_history": recent_history,
            }
        )


class GlobalMonitoringAnalytics(APIView):
    """
    Return analytics for all monitors.
    """

    def get(self, request):
        monitors = APIMonitor.objects.all()

        result = []

        for monitor in monitors:
            logs = APILog.objects.filter(
                api_monitor=monitor
            )

            total_checks = logs.count()

            up_checks = logs.filter(
                status="UP"
            ).count()

            down_checks = logs.filter(
                status="DOWN"
            ).count()

            uptime_percentage = (
                (up_checks / total_checks) * 100
                if total_checks
                else 0
            )

            # Response times
            response_times = list(
                logs.exclude(
                    response_time_ms=None
                ).values_list(
                    "response_time_ms",
                    flat=True,
                )
            )

            response_times = [
                float(value)
                for value in response_times
                if value is not None and float(value) >= 0
            ]

            avg_response_time = (
                sum(response_times) / len(response_times)
                if response_times
                else 0
            )

            # P95
            p95_latency = 0

            if response_times:
                sorted_times = sorted(response_times)

                index = int(
                    0.95 * (len(sorted_times) - 1)
                )

                p95_latency = sorted_times[index]

            result.append(
                {
                    "monitor_id": monitor.id,
                    "name": monitor.name,
                    "url": monitor.url,
                    "status": monitor.status,

                    "total_checks": total_checks,
                    "up_checks": up_checks,
                    "down_checks": down_checks,

                    "uptime_percentage": round(
                        uptime_percentage,
                        2,
                    ),

                    "avg_response_time": round(
                        avg_response_time,
                        2,
                    ),

                    "p95_latency": round(
                        p95_latency,
                        2,
                    ),
                }
            )

        return Response(result)


class PublicStatusPage(APIView):
    """
    Public status page.

    Authentication is disabled intentionally.
    """

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        monitors = APIMonitor.objects.filter(
            is_active=True
        )

        result = []

        for monitor in monitors:
            logs = APILog.objects.filter(
                api_monitor=monitor
            )

            total_checks = logs.count()

            up_checks = logs.filter(
                status="UP"
            ).count()

            uptime = (
                (up_checks / total_checks) * 100
                if total_checks
                else 0
            )

            last_log = (
                logs.order_by("-checked_at").first()
            )

            result.append(
                {
                    "name": monitor.name,
                    "url": monitor.url,
                    "status": monitor.status,

                    "uptime_percentage": round(
                        uptime,
                        2,
                    ),

                    "last_checked": (
                        last_log.checked_at
                        if last_log
                        else None
                    ),
                }
            )

        # ---------------------------------------------------------
        # OVERALL STATUS
        # ---------------------------------------------------------
        overall_status = "OPERATIONAL"

        for service in result:
            if service["status"] == "DOWN":
                overall_status = "DEGRADED"
                break

        return Response(
            {
                "overall_status": overall_status,
                "services": result,
            }
        )