import math
from datetime import timedelta

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, generics
from rest_framework.permissions import IsAuthenticated

from django.utils import timezone
from django.db.models import Avg, F, ExpressionWrapper, DurationField

from .models import APIMonitor, Incident, MonitorAlertSettings
from logs.models import APILog
from .serializers import APIMonitorSerializer, IncidentSerializer
from users.models import _log


# =============================================================================
# HELPERS
# =============================================================================

def _monitor_queryset_for_user(user):
    if user.role == "ADMIN":
        return APIMonitor.objects.all()

    return APIMonitor.objects.filter(owner=user)


# =============================================================================
# MONITORS
# =============================================================================

class APIMonitorListCreateView(generics.ListCreateAPIView):
    serializer_class = APIMonitorSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        if user.role == "ADMIN":
            return APIMonitor.objects.all().order_by("-id")

        return APIMonitor.objects.filter(
            owner=user
        ).order_by("-id")

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def create(self, request, *args, **kwargs):
        # ---------------------------------------------------------------------
        # Duplicate prevention
        # ---------------------------------------------------------------------
        url = (
            (request.data.get("url") or "")
            .strip()
            .rstrip("/")
        )

        method = (
            (request.data.get("method") or "GET")
            .upper()
        )

        owner = request.user

        qs = APIMonitor.objects.filter(
            owner=owner,
            method=method,
        )

        for monitor in qs:
            if monitor.url.rstrip("/") == url:
                return Response(
                    {
                        "url": [
                            f"A {method} monitor for this URL already exists."
                        ]
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # ---------------------------------------------------------------------
        # Interval minimum validation
        # ---------------------------------------------------------------------
        try:
            interval = int(
                request.data.get(
                    "check_interval",
                    60,
                )
            )
        except (TypeError, ValueError):
            interval = 60

        if interval < 10:
            return Response(
                {
                    "check_interval": [
                        "Interval must be at least 10 seconds."
                    ]
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        response = super().create(
            request,
            *args,
            **kwargs,
        )

        if response.status_code == status.HTTP_201_CREATED:
            name = request.data.get(
                "name",
                "",
            )

            _log(
                request.user,
                "MONITOR_CREATED",
                resource=name,
                request=request,
            )

        return response


class APIMonitorDetailView(
    generics.RetrieveUpdateDestroyAPIView
):
    serializer_class = APIMonitorSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return _monitor_queryset_for_user(
            self.request.user
        )

    def perform_destroy(self, instance):
        _log(
            self.request.user,
            "MONITOR_DELETED",
            resource=instance.name,
            request=self.request,
        )

        instance.delete()


# =============================================================================
# TOGGLE ENABLE / PAUSE
# =============================================================================

class MonitorToggleView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        try:
            monitor = _monitor_queryset_for_user(
                request.user
            ).get(pk=pk)

        except APIMonitor.DoesNotExist:
            return Response(
                {"error": "Not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        monitor.is_active = not monitor.is_active

        monitor.save(
            update_fields=["is_active"]
        )

        _log(
            request.user,
            "MONITOR_TOGGLED",
            resource=(
                f"{monitor.name} → "
                f"{'Active' if monitor.is_active else 'Paused'}"
            ),
            request=request,
        )

        return Response(
            {
                "id": monitor.id,
                "is_active": monitor.is_active,
                "message": (
                    "Monitor activated."
                    if monitor.is_active
                    else "Monitor paused."
                ),
            }
        )


# =============================================================================
# CHECK NOW
# =============================================================================

class MonitorCheckNowView(APIView):
    """
    Queue an immediate monitoring run.

    The existing Celery task is responsible for checking active monitors.
    This endpoint does not duplicate the monitoring logic.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            monitor = _monitor_queryset_for_user(
                request.user
            ).get(pk=pk)

        except APIMonitor.DoesNotExist:
            return Response(
                {"error": "Not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not monitor.is_active:
            return Response(
                {
                    "error": "Monitor is paused.",
                    "id": monitor.id,
                    "is_active": False,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            from .tasks import check_api_health

            task = check_api_health.delay()

        except Exception as exc:
            return Response(
                {
                    "error": "Unable to queue health check.",
                    "detail": str(exc),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        _log(
            request.user,
            "MONITOR_CHECK_NOW",
            resource=monitor.name,
            request=request,
        )

        return Response(
            {
                "id": monitor.id,
                "name": monitor.name,
                "message": (
                    "Health check queued successfully."
                ),
                "task_id": task.id,
            },
            status=status.HTTP_202_ACCEPTED,
        )


# =============================================================================
# LOGS
# =============================================================================

class MonitorLogsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            monitor = _monitor_queryset_for_user(
                request.user
            ).get(pk=pk)

        except APIMonitor.DoesNotExist:
            return Response(
                {"error": "Not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # ---------------------------------------------------------------------
        # Pagination
        # ---------------------------------------------------------------------
        try:
            page = max(
                1,
                int(
                    request.query_params.get(
                        "page",
                        1,
                    )
                ),
            )
        except (TypeError, ValueError):
            page = 1

        try:
            page_size = int(
                request.query_params.get(
                    "page_size",
                    30,
                )
            )
        except (TypeError, ValueError):
            page_size = 30

        page_size = min(
            max(page_size, 10),
            100,
        )

        # ---------------------------------------------------------------------
        # Query logs
        # ---------------------------------------------------------------------
        logs_qs = (
            APILog.objects
            .filter(api_monitor=monitor)
            .order_by("-checked_at")
        )

        total = logs_qs.count()

        total_pages = max(
            1,
            math.ceil(total / page_size),
        )

        page = min(
            page,
            total_pages,
        )

        start = (
            page - 1
        ) * page_size

        end = start + page_size

        logs = logs_qs[
            start:end
        ].values(
            "status",
            "status_code",
            "response_time_ms",
            "error_message",
            "checked_at",
        )

        return Response(
            {
                "monitor_id": monitor.id,
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages,
                "results": list(logs),
            }
        )


# =============================================================================
# ALL INCIDENTS
# =============================================================================

class AllIncidentsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role == "ADMIN":
            incidents = (
                Incident.objects
                .all()
                .select_related("monitor")
                .order_by("-started_at")
            )

        else:
            incidents = (
                Incident.objects
                .filter(
                    monitor__owner=request.user
                )
                .select_related("monitor")
                .order_by("-started_at")
            )

        serializer = IncidentSerializer(
            incidents[:100],
            many=True,
        )

        return Response(
            serializer.data
        )


# =============================================================================
# MONITOR-SPECIFIC INCIDENTS
# =============================================================================

class IncidentDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, monitor_id):
        # Security: only allow the user's monitors,
        # except for ADMIN users.
        try:
            monitor = _monitor_queryset_for_user(
                request.user
            ).get(pk=monitor_id)

        except APIMonitor.DoesNotExist:
            return Response(
                {"error": "Not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        incidents = (
            Incident.objects
            .filter(monitor=monitor)
            .order_by("-started_at")
        )

        total_incidents = incidents.count()

        unresolved = incidents.filter(
            status="ONGOING"
        ).count()

        resolved_incidents = (
            incidents
            .filter(status="RESOLVED")
            .annotate(
                duration=ExpressionWrapper(
                    F("resolved_at")
                    - F("started_at"),
                    output_field=DurationField(),
                )
            )
        )

        avg_duration = (
            resolved_incidents
            .aggregate(
                avg=Avg("duration")
            )["avg"]
        )

        avg_downtime = (
            avg_duration.total_seconds()
            if avg_duration
            else None
        )

        serializer = IncidentSerializer(
            incidents[:10],
            many=True,
        )

        return Response(
            {
                "monitor_id": monitor.id,
                "total_incidents": total_incidents,
                "ongoing_incidents": unresolved,
                "recent_incidents": serializer.data,
                "avg_downtime": avg_downtime,
            }
        )

# =============================================================================
# MONITOR ALERT SETTINGS
# =============================================================================

class MonitorAlertSettingsView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_monitor(self, request, monitor_id):
        try:
            return _monitor_queryset_for_user(
                request.user
            ).get(pk=monitor_id)
        except APIMonitor.DoesNotExist:
            return None

    def _get_settings(self, monitor):
        settings_obj, _ = MonitorAlertSettings.objects.get_or_create(
            monitor=monitor
        )
        return settings_obj

    def _serialize(self, settings_obj):
        return {
            "id": settings_obj.id,
            "monitor": settings_obj.monitor_id,
            "alerts_enabled": settings_obj.alerts_enabled,
            "down_alert_enabled": settings_obj.down_alert_enabled,
            "slow_alert_enabled": settings_obj.slow_alert_enabled,
            "recovery_alert_enabled": settings_obj.recovery_alert_enabled,
            "email_enabled": settings_obj.email_enabled,
            "phone_enabled": settings_obj.phone_enabled,
            "cooldown_minutes": settings_obj.cooldown_minutes,
            "created_at": settings_obj.created_at,
            "updated_at": settings_obj.updated_at,
        }

    def get(self, request, monitor_id):
        monitor = self._get_monitor(
            request,
            monitor_id
        )

        if monitor is None:
            return Response(
                {"error": "Not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        settings_obj = self._get_settings(
            monitor
        )

        return Response(
            self._serialize(settings_obj),
            status=status.HTTP_200_OK,
        )

    def patch(self, request, monitor_id):
        monitor = self._get_monitor(
            request,
            monitor_id
        )

        if monitor is None:
            return Response(
                {"error": "Not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        settings_obj = self._get_settings(
            monitor
        )

        boolean_fields = [
            "alerts_enabled",
            "down_alert_enabled",
            "slow_alert_enabled",
            "recovery_alert_enabled",
            "email_enabled",
            "phone_enabled",
        ]

        update_fields = []

        for field in boolean_fields:
            if field not in request.data:
                continue

            value = request.data.get(field)

            if isinstance(value, bool):
                parsed_value = value

            elif isinstance(value, str):
                normalized = value.strip().lower()

                if normalized in (
                    "true",
                    "1",
                    "yes",
                    "on",
                ):
                    parsed_value = True

                elif normalized in (
                    "false",
                    "0",
                    "no",
                    "off",
                ):
                    parsed_value = False

                else:
                    return Response(
                        {
                            field: [
                                "Value must be true or false."
                            ]
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            else:
                return Response(
                    {
                        field: [
                            "Value must be true or false."
                        ]
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            setattr(
                settings_obj,
                field,
                parsed_value
            )

            update_fields.append(
                field
            )

        if "cooldown_minutes" in request.data:
            try:
                cooldown = int(
                    request.data.get(
                        "cooldown_minutes"
                    )
                )
            except (
                TypeError,
                ValueError
            ):
                return Response(
                    {
                        "cooldown_minutes": [
                            "Cooldown must be a whole number."
                        ]
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if cooldown < 0:
                return Response(
                    {
                        "cooldown_minutes": [
                            "Cooldown cannot be negative."
                        ]
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            settings_obj.cooldown_minutes = cooldown

            update_fields.append(
                "cooldown_minutes"
            )

        if update_fields:
            settings_obj.save(
                update_fields=(
                    update_fields
                    + ["updated_at"]
                )
            )

        _log(
            request.user,
            "MONITOR_ALERT_SETTINGS_UPDATED",
            resource=monitor.name,
            request=request,
        )

        return Response(
            self._serialize(settings_obj),
            status=status.HTTP_200_OK,
        )



# =============================================================================
# MONITOR ANALYTICS
# =============================================================================

def _analytics_period(period):
    periods = {
        "24h": (24, 30 * 60),
        "7d": (24 * 7, 3 * 60 * 60),
        "30d": (24 * 30, 12 * 60 * 60),
    }
    return periods.get(period, periods["7d"])


def _build_analytics_history(logs, bucket_seconds):
    """Build chart-ready history from real monitoring logs."""
    buckets = {}

    for item in logs.values(
        "status",
        "response_time_ms",
        "checked_at",
    ):
        checked_at = item["checked_at"]
        if not checked_at:
            continue

        timestamp = int(checked_at.timestamp())
        bucket_timestamp = (
            timestamp // bucket_seconds
        ) * bucket_seconds

        bucket = buckets.setdefault(
            bucket_timestamp,
            {
                "latencies": [],
                "total": 0,
                "up": 0,
                "down": 0,
            },
        )

        bucket["total"] += 1

        if str(item["status"]).upper() == "UP":
            bucket["up"] += 1
        else:
            bucket["down"] += 1

        latency = item["response_time_ms"]

        if latency is not None:
            try:
                bucket["latencies"].append(float(latency))
            except (TypeError, ValueError):
                pass

    history = []

    for timestamp in sorted(buckets):
        bucket = buckets[timestamp]
        latencies = sorted(bucket["latencies"])

        average = (
            sum(latencies) / len(latencies)
            if latencies
            else None
        )

        p95 = None
        if latencies:
            rank = max(
                1,
                math.ceil(0.95 * len(latencies)),
            )
            p95 = latencies[rank - 1]

        uptime = (
            (bucket["up"] / bucket["total"]) * 100
            if bucket["total"]
            else None
        )

        history.append({
            "timestamp": timezone.datetime.fromtimestamp(
                timestamp,
                tz=timezone.get_current_timezone(),
            ).isoformat(),
            "latency": (
                round(average, 1)
                if average is not None
                else None
            ),
            "p95_latency": (
                round(p95, 1)
                if p95 is not None
                else None
            ),
            "uptime": (
                round(uptime, 2)
                if uptime is not None
                else None
            ),
            "checks": bucket["total"],
            "up_checks": bucket["up"],
            "down_checks": bucket["down"],
        })

    return history



def _build_analytics_insights(history, uptime, avg_response_time, p95_latency,
                               slow_percentage, total_checks):
    """Build simple, explainable analytics insights from real check history."""
    insights = []
    latency_trend = "stable"

    points = [
        item["latency"] for item in history
        if item.get("latency") is not None
    ]

    if len(points) >= 4:
        half = max(2, len(points) // 2)
        earlier = points[:half]
        recent = points[-half:]

        earlier_avg = sum(earlier) / len(earlier)
        recent_avg = sum(recent) / len(recent)

        if earlier_avg > 0:
            change = ((recent_avg - earlier_avg) / earlier_avg) * 100
            if change >= 10:
                latency_trend = "degrading"
                insights.append(
                    f"Latency increased about {round(change)}% recently."
                )
            elif change <= -10:
                latency_trend = "improving"
                insights.append(
                    f"Latency improved about {round(abs(change))}% recently."
                )

    if uptime is not None:
        if uptime >= 99.9:
            insights.append("Excellent availability.")
        elif uptime >= 99:
            insights.append("Availability is healthy.")
        elif uptime >= 95:
            insights.append("Availability needs attention.")
        else:
            insights.append("Frequent failures are affecting availability.")

    if slow_percentage >= 10:
        insights.append(
            f"{round(slow_percentage, 1)}% of measured checks exceeded the "
            "configured response-time threshold."
        )
    elif slow_percentage > 0:
        insights.append(
            f"{round(slow_percentage, 1)}% of measured checks were slower "
            "than the configured threshold."
        )

    if p95_latency is not None and avg_response_time is not None:
        if avg_response_time > 0 and p95_latency >= avg_response_time * 2:
            insights.append(
                "The p95 latency is much higher than the average, "
                "suggesting occasional slow spikes."
            )

    if total_checks == 0:
        insights.append("Not enough monitoring data yet.")

    # Keep the API response compact and deterministic.
    return {
        "latency_trend": latency_trend,
        "insights": insights[:5],
    }


class MonitorAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, monitor_id):
        try:
            monitor = _monitor_queryset_for_user(
                request.user
            ).get(pk=monitor_id)
        except APIMonitor.DoesNotExist:
            return Response(
                {"error": "Not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        period = request.query_params.get("period", "7d")
        hours, bucket_seconds = _analytics_period(period)

        start_time = (
            timezone.now()
            - timedelta(hours=hours)
        )

        logs = (
            APILog.objects
            .filter(
                api_monitor=monitor,
                checked_at__gte=start_time,
            )
            .order_by("-checked_at")
        )

        total = logs.count()
        up_count = logs.filter(status="UP").count()
        down_count = total - up_count

        uptime = (
            round((up_count / total) * 100, 2)
            if total
            else None
        )

        response_times = list(
            logs
            .exclude(response_time_ms=None)
            .values_list("response_time_ms", flat=True)
        )

        numeric_times = []
        for value in response_times:
            try:
                numeric_times.append(float(value))
            except (TypeError, ValueError):
                continue

        avg_response_time = (
            round(
                sum(numeric_times) / len(numeric_times),
                1,
            )
            if numeric_times
            else None
        )

        sorted_times = sorted(numeric_times)
        p95_latency = None

        if sorted_times:
            rank = max(
                1,
                math.ceil(0.95 * len(sorted_times)),
            )
            p95_latency = round(
                sorted_times[rank - 1],
                1,
            )

        slow_count = sum(
            1
            for value in numeric_times
            if value > monitor.response_time_threshold_ms
        )

        slow_percentage = (
            round(
                (slow_count / len(numeric_times)) * 100,
                2,
            )
            if numeric_times
            else 0
        )

        history = _build_analytics_history(
            logs,
            bucket_seconds,
        )

        analytics_insights = _build_analytics_insights(
            history=history,
            uptime=uptime,
            avg_response_time=avg_response_time,
            p95_latency=p95_latency,
            slow_percentage=slow_percentage,
            total_checks=total,
        )

        recent = list(
            logs[:20].values(
                "status",
                "status_code",
                "response_time_ms",
                "checked_at",
                "error_message",
            )
        )

        # ---------------------------------------------------------------------
        # PERFORMANCE SCORE
        # ---------------------------------------------------------------------
        # The score is calculated only from real monitoring data.
        # 60% uptime + 25% latency health + 15% slow-check health.
        performance_score = None
        performance_grade = None
        score_breakdown = {
            "uptime": None,
            "latency": None,
            "slow_checks": None,
        }

        if total > 0:
            uptime_score = float(uptime or 0)

            if avg_response_time is None:
                latency_score = 100.0
            else:
                threshold = float(
                    monitor.response_time_threshold_ms or 1000
                )
                if threshold <= 0:
                    threshold = 1000.0

                # At or below the configured threshold = 100.
                # At 2x threshold = 50, at 3x or more = 0.
                latency_score = max(
                    0.0,
                    min(
                        100.0,
                        100.0 - max(0.0, (
                            (avg_response_time / threshold) - 1.0
                        )) * 50.0,
                    ),
                )

            slow_check_score = max(
                0.0,
                100.0 - float(slow_percentage),
            )

            performance_score = round(
                (uptime_score * 0.60)
                + (latency_score * 0.25)
                + (slow_check_score * 0.15),
                1,
            )

            if performance_score >= 95:
                performance_grade = "A+"
            elif performance_score >= 90:
                performance_grade = "A"
            elif performance_score >= 80:
                performance_grade = "B"
            elif performance_score >= 70:
                performance_grade = "C"
            elif performance_score >= 60:
                performance_grade = "D"
            else:
                performance_grade = "F"

            score_breakdown = {
                "uptime": round(uptime_score, 1),
                "latency": round(latency_score, 1),
                "slow_checks": round(slow_check_score, 1),
            }

        return Response({
            "monitor_id": monitor.id,
            "name": monitor.name,
            "url": monitor.url,
            "status": monitor.status,
            "is_active": monitor.is_active,
            "period": period,
            "uptime_percentage": uptime,
            "downtime_percentage": (
                round(max(0, 100 - uptime), 2)
                if uptime is not None
                else None
            ),
            "avg_response_time": avg_response_time,
            "p95_latency": p95_latency,
            "total_checks": total,
            "up_checks": up_count,
            "down_checks": down_count,
            "slow_checks": slow_count,
            "slow_percentage": slow_percentage,
            "response_time_threshold_ms": (
                monitor.response_time_threshold_ms
            ),
            "performance_score": performance_score,
            "performance_grade": performance_grade,
            "score_breakdown": score_breakdown,
            "response_times": response_times,
            "rt_values": response_times,
            "history": history,
            "latency_trend": analytics_insights["latency_trend"],
            "insights": analytics_insights["insights"],
            "checks": recent,
            "recent_history": recent,
            "last_checked_at": monitor.last_checked_at,
            "response_time": monitor.response_time,
        })


# =============================================================================
# GLOBAL ANALYTICS
# =============================================================================

class GlobalAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        monitor_id = request.query_params.get("monitor_id")
        period = request.query_params.get("period", "7d")

        if period not in ("24h", "7d", "30d"):
            period = "7d"

        monitors = (
            _monitor_queryset_for_user(request.user)
            .order_by("-id")
        )

        if not monitor_id:
            return Response([
                {
                    "monitor_id": monitor.id,
                    "name": monitor.name,
                    "url": monitor.url,
                    "status": monitor.status,
                    "is_active": monitor.is_active,
                    "last_checked_at": monitor.last_checked_at,
                    "response_time": monitor.response_time,
                }
                for monitor in monitors
            ])

        try:
            monitor = monitors.get(pk=monitor_id)
        except APIMonitor.DoesNotExist:
            return Response(
                {"error": "Not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        hours, bucket_seconds = _analytics_period(period)

        start_time = (
            timezone.now()
            - timedelta(hours=hours)
        )

        logs = (
            APILog.objects
            .filter(
                api_monitor=monitor,
                checked_at__gte=start_time,
            )
            .order_by("-checked_at")
        )

        total = logs.count()
        up_count = logs.filter(status="UP").count()
        down_count = total - up_count

        uptime = (
            round((up_count / total) * 100, 2)
            if total
            else None
        )

        response_times = list(
            logs
            .exclude(response_time_ms=None)
            .values_list("response_time_ms", flat=True)
        )

        numeric_times = []
        for value in response_times:
            try:
                numeric_times.append(float(value))
            except (TypeError, ValueError):
                continue

        avg_response_time = (
            round(
                sum(numeric_times) / len(numeric_times),
                1,
            )
            if numeric_times
            else None
        )

        sorted_times = sorted(numeric_times)
        p95_latency = None

        if sorted_times:
            rank = max(
                1,
                math.ceil(0.95 * len(sorted_times)),
            )
            p95_latency = round(
                sorted_times[rank - 1],
                1,
            )

        slow_count = sum(
            1
            for value in numeric_times
            if value > monitor.response_time_threshold_ms
        )

        slow_percentage = (
            round(
                (slow_count / len(numeric_times)) * 100,
                2,
            )
            if numeric_times
            else 0
        )

        history = _build_analytics_history(
            logs,
            bucket_seconds,
        )

        analytics_insights = _build_analytics_insights(
            history=history,
            uptime=uptime,
            avg_response_time=avg_response_time,
            p95_latency=p95_latency,
            slow_percentage=slow_percentage,
            total_checks=total,
        )

        recent_checks = list(
            logs[:20].values(
                "status",
                "status_code",
                "response_time_ms",
                "checked_at",
                "error_message",
            )
        )

        # ---------------------------------------------------------------------
        # PERFORMANCE SCORE
        # ---------------------------------------------------------------------
        # The score is calculated only from real monitoring data.
        # 60% uptime + 25% latency health + 15% slow-check health.
        performance_score = None
        performance_grade = None
        score_breakdown = {
            "uptime": None,
            "latency": None,
            "slow_checks": None,
        }

        if total > 0:
            uptime_score = float(uptime or 0)

            if avg_response_time is None:
                latency_score = 100.0
            else:
                threshold = float(
                    monitor.response_time_threshold_ms or 1000
                )
                if threshold <= 0:
                    threshold = 1000.0

                # At or below the configured threshold = 100.
                # At 2x threshold = 50, at 3x or more = 0.
                latency_score = max(
                    0.0,
                    min(
                        100.0,
                        100.0 - max(0.0, (
                            (avg_response_time / threshold) - 1.0
                        )) * 50.0,
                    ),
                )

            slow_check_score = max(
                0.0,
                100.0 - float(slow_percentage),
            )

            performance_score = round(
                (uptime_score * 0.60)
                + (latency_score * 0.25)
                + (slow_check_score * 0.15),
                1,
            )

            if performance_score >= 95:
                performance_grade = "A+"
            elif performance_score >= 90:
                performance_grade = "A"
            elif performance_score >= 80:
                performance_grade = "B"
            elif performance_score >= 70:
                performance_grade = "C"
            elif performance_score >= 60:
                performance_grade = "D"
            else:
                performance_grade = "F"

            score_breakdown = {
                "uptime": round(uptime_score, 1),
                "latency": round(latency_score, 1),
                "slow_checks": round(slow_check_score, 1),
            }

        return Response({
            "monitor_id": monitor.id,
            "name": monitor.name,
            "url": monitor.url,
            "status": monitor.status,
            "is_active": monitor.is_active,
            "period": period,
            "uptime_percentage": uptime,
            "downtime_percentage": (
                round(max(0, 100 - uptime), 2)
                if uptime is not None
                else None
            ),
            "avg_response_time": avg_response_time,
            "p95_latency": p95_latency,
            "total_checks": total,
            "up_checks": up_count,
            "down_checks": down_count,
            "slow_checks": slow_count,
            "slow_percentage": slow_percentage,
            "response_time_threshold_ms": (
                monitor.response_time_threshold_ms
            ),
            "performance_score": performance_score,
            "performance_grade": performance_grade,
            "score_breakdown": score_breakdown,
            "response_times": response_times,
            "rt_values": response_times,
            "history": history,
            "latency_trend": analytics_insights["latency_trend"],
            "insights": analytics_insights["insights"],
            "checks": recent_checks,
            "recent_history": recent_checks,
            "last_checked_at": monitor.last_checked_at,
            "response_time": monitor.response_time,
        })

