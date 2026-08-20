from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, generics
from rest_framework.permissions import IsAuthenticated

from django.utils import timezone
from django.db.models import Avg, F, ExpressionWrapper, DurationField, Q

from datetime import timedelta
import math

from .models import APIMonitor, Incident
from logs.models import APILog
from .serializers import APIMonitorSerializer, IncidentSerializer
from users.models import _log


# =============================================================================
# MONITOR OWNERSHIP
# =============================================================================

def _monitor_queryset_for_user(request):
    """
    Return only monitors belonging to the currently authenticated user.

    There is intentionally NO admin bypass here.
    Every authenticated user can access only their own monitors.
    """
    return APIMonitor.objects.filter(
        owner=request.user
    )


# =============================================================================
# MONITORS
# =============================================================================

class APIMonitorListCreateView(generics.ListCreateAPIView):
    """
    GET:
        Return only the authenticated user's monitors.

    POST:
        Create a new monitor owned by the authenticated user.
    """

    serializer_class = APIMonitorSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return _monitor_queryset_for_user(self.request).order_by("-id")

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def create(self, request, *args, **kwargs):

        # ---------------------------------------------------------------------
        # Duplicate monitor prevention
        # ---------------------------------------------------------------------

        url = (
            request.data.get("url") or ""
        ).strip().rstrip("/")

        method = (
            request.data.get("method") or "GET"
        ).upper()

        owner = request.user

        existing_monitors = APIMonitor.objects.filter(
            owner=owner,
            method=method,
        )

        for monitor in existing_monitors:

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
        # Minimum monitoring interval
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

        # ---------------------------------------------------------------------
        # Create monitor
        # ---------------------------------------------------------------------

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
    """
    Retrieve, update or delete a monitor.

    IMPORTANT:
    The queryset is restricted to the logged-in user's monitors.
    Therefore another user's monitor cannot be accessed by ID.
    """

    serializer_class = APIMonitorSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return _monitor_queryset_for_user(self.request)

    def perform_destroy(self, instance):

        _log(
            self.request.user,
            "MONITOR_DELETED",
            resource=instance.name,
            request=self.request,
        )

        instance.delete()


# =============================================================================
# MONITOR TOGGLE
# =============================================================================

class MonitorToggleView(APIView):

    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):

        try:

            monitor = _monitor_queryset_for_user(
                request
            ).get(
                pk=pk
            )

        except APIMonitor.DoesNotExist:

            return Response(
                {
                    "error": "Not found"
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        monitor.is_active = not monitor.is_active

        monitor.save(
            update_fields=[
                "is_active"
            ]
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
# MONITOR LOGS
# =============================================================================

class MonitorLogsView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):

        # ---------------------------------------------------------------------
        # Security:
        # Only retrieve a monitor belonging to this user.
        # ---------------------------------------------------------------------

        try:

            monitor = _monitor_queryset_for_user(
                request
            ).get(
                pk=pk
            )

        except APIMonitor.DoesNotExist:

            return Response(
                {
                    "error": "Not found"
                },
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
        # Logs
        # ---------------------------------------------------------------------

        logs_qs = (
            APILog.objects
            .filter(
                api_monitor=monitor
            )
            .order_by(
                "-checked_at"
            )
        )

        total = logs_qs.count()

        total_pages = max(
            1,
            math.ceil(
                total / page_size
            ),
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

        # ---------------------------------------------------------------------
        # Only incidents belonging to this user's monitors.
        # ---------------------------------------------------------------------

        incidents = (
            Incident.objects
            .filter(
                monitor__owner=request.user
            )
            .select_related(
                "monitor"
            )
            .order_by(
                "-started_at"
            )
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

    def get(
        self,
        request,
        monitor_id,
    ):

        # ---------------------------------------------------------------------
        # Security:
        # User can only access incidents for their own monitor.
        # ---------------------------------------------------------------------

        try:

            monitor = _monitor_queryset_for_user(
                request
            ).get(
                pk=monitor_id
            )

        except APIMonitor.DoesNotExist:

            return Response(
                {
                    "error": "Not found"
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # ---------------------------------------------------------------------
        # Incidents for this monitor
        # ---------------------------------------------------------------------

        incidents = (
            Incident.objects
            .filter(
                monitor=monitor
            )
            .order_by(
                "-started_at"
            )
        )

        total_incidents = incidents.count()

        unresolved = incidents.filter(
            status="ONGOING"
        ).count()

        # ---------------------------------------------------------------------
        # Resolved incident duration
        # ---------------------------------------------------------------------

        resolved_incidents = (
            incidents
            .filter(
                status="RESOLVED"
            )
            .annotate(
                duration=ExpressionWrapper(
                    F("resolved_at") - F("started_at"),
                    output_field=DurationField(),
                )
            )
        )

        avg_duration = (
            resolved_incidents
            .aggregate(
                avg=Avg("duration")
            )
            ["avg"]
        )

        avg_downtime = (
            avg_duration.total_seconds()
            if avg_duration
            else None
        )

        # ---------------------------------------------------------------------
        # Recent incidents
        # ---------------------------------------------------------------------

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
# ANALYTICS HELPERS
# =============================================================================

def _percentile(values, percentile):
    """
    Return a percentile using linear interpolation.
    """

    if not values:
        return 0

    ordered = sorted(
        float(value)
        for value in values
    )

    if len(ordered) == 1:
        return round(
            ordered[0],
            1,
        )

    rank = (
        len(ordered) - 1
    ) * percentile

    lower = math.floor(
        rank
    )

    upper = math.ceil(
        rank
    )

    if lower == upper:
        return round(
            ordered[lower],
            1,
        )

    value = (
        ordered[lower]
        +
        (
            ordered[upper]
            - ordered[lower]
        )
        *
        (
            rank
            - lower
        )
    )

    return round(
        value,
        1,
    )


def _analytics_period(period):
    """
    Convert the UI period into:

    - lookback duration
    - chart bucket size
    - display label
    """

    choices = {

        "24h": (
            timedelta(hours=24),
            30 * 60,
            "24 hours",
        ),

        "7d": (
            timedelta(days=7),
            3 * 60 * 60,
            "7 days",
        ),

        "30d": (
            timedelta(days=30),
            12 * 60 * 60,
            "30 days",
        ),
    }

    return choices.get(
        period,
        choices["7d"],
    )


def _bucket_history(
    log_rows,
    start_time,
    bucket_seconds,
):
    """
    Build a compact time-series for the selected range.

    24h -> 48 buckets
    7d  -> 56 buckets
    30d -> 60 buckets
    """

    buckets = {}

    start_epoch = (
        start_time.timestamp()
    )

    for row in log_rows:

        checked_at = row[
            "checked_at"
        ]

        if not checked_at:
            continue

        offset = (
            checked_at.timestamp()
            - start_epoch
        )

        bucket_index = max(
            0,
            int(
                offset
                // bucket_seconds
            ),
        )

        bucket_start = (
            start_time
            +
            timedelta(
                seconds=(
                    bucket_index
                    * bucket_seconds
                )
            )
        )

        bucket = buckets.setdefault(
            bucket_start,
            {
                "latencies": [],
                "total": 0,
                "up": 0,
                "down": 0,
            },
        )

        bucket["total"] += 1

        if row["status"] == "UP":

            bucket["up"] += 1

        else:

            bucket["down"] += 1

        if row["response_time_ms"] is not None:

            bucket[
                "latencies"
            ].append(
                float(
                    row[
                        "response_time_ms"
                    ]
                )
            )

    history = []

    bucket_count = max(
        1,
        math.ceil(
            (
                timezone.now()
                - start_time
            ).total_seconds()
            / bucket_seconds
        ),
    )

    for index in range(
        bucket_count
    ):

        bucket_start = (
            start_time
            +
            timedelta(
                seconds=(
                    index
                    * bucket_seconds
                )
            )
        )

        bucket = buckets.get(
            bucket_start,
            {
                "latencies": [],
                "total": 0,
                "up": 0,
                "down": 0,
            },
        )

        latencies = bucket[
            "latencies"
        ]

        history.append(
            {
                "timestamp": bucket_start.isoformat(),

                "latency": (
                    round(
                        sum(latencies)
                        / len(latencies),
                        1,
                    )
                    if latencies
                    else None
                ),

                "uptime": (
                    round(
                        (
                            bucket["up"]
                            / bucket["total"]
                        )
                        * 100,
                        2,
                    )
                    if bucket["total"]
                    else None
                ),

                "checks": bucket[
                    "total"
                ],

                "up_checks": bucket[
                    "up"
                ],

                "down_checks": bucket[
                    "down"
                ],
            }
        )

    return history


# =============================================================================
# MONITOR ANALYTICS
# =============================================================================

def _monitor_analytics(
    monitor,
    period="7d",
    page=1,
    page_size=30,
    status_filter="",
    search="",
):

    lookback, bucket_seconds, period_label = (
        _analytics_period(
            period
        )
    )

    now = timezone.now()

    start_time = (
        now - lookback
    )

    # -------------------------------------------------------------------------
    # Base logs for selected period
    # -------------------------------------------------------------------------

    base_logs_qs = (
        APILog.objects
        .filter(
            api_monitor=monitor,
            checked_at__gte=start_time,
            checked_at__lte=now,
        )
        .order_by(
            "-checked_at"
        )
    )

    # -------------------------------------------------------------------------
    # Summary statistics
    # -------------------------------------------------------------------------

    summary_total = (
        base_logs_qs.count()
    )

    summary_up_count = (
        base_logs_qs
        .filter(
            status="UP"
        )
        .count()
    )

    summary_down_count = (
        summary_total
        - summary_up_count
    )

    # -------------------------------------------------------------------------
    # Filters
    # -------------------------------------------------------------------------

    normalized_status = (
        str(
            status_filter or ""
        )
        .strip()
        .upper()
    )

    normalized_search = (
        str(
            search or ""
        )
        .strip()
    )

    logs_qs = base_logs_qs

    if normalized_status in {
        "UP",
        "DOWN",
    }:

        logs_qs = logs_qs.filter(
            status=normalized_status
        )

    if normalized_search:

        search_query = (
            Q(
                status__icontains=(
                    normalized_search
                )
            )
            |
            Q(
                error_message__icontains=(
                    normalized_search
                )
            )
        )

        try:

            search_code = int(
                normalized_search
            )

            search_query |= Q(
                status_code=search_code
            )

        except (
            TypeError,
            ValueError,
        ):

            pass

        logs_qs = logs_qs.filter(
            search_query
        )

    # -------------------------------------------------------------------------
    # Filtered statistics
    # -------------------------------------------------------------------------

    total = logs_qs.count()

    up_count = (
        logs_qs
        .filter(
            status="UP"
        )
        .count()
    )

    down_count = (
        total
        - up_count
    )

    # -------------------------------------------------------------------------
    # Uptime
    #
    # Important:
    # Uptime uses the COMPLETE selected period, not the filtered table.
    # -------------------------------------------------------------------------

    uptime = (
        round(
            (
                summary_up_count
                / summary_total
            )
            * 100,
            2,
        )
        if summary_total
        else 0
    )

    # -------------------------------------------------------------------------
    # Error rate
    # -------------------------------------------------------------------------

    error_rate = (
        round(
            (
                down_count
                / total
            )
            * 100,
            2,
        )
        if total
        else 0
    )

    # -------------------------------------------------------------------------
    # Response latency
    # -------------------------------------------------------------------------

    latency_values = list(
        base_logs_qs
        .exclude(
            response_time_ms=None
        )
        .values_list(
            "response_time_ms",
            flat=True,
        )
    )

    avg_response = (
        round(
            sum(
                float(value)
                for value in latency_values
            )
            / len(
                latency_values
            ),
            1,
        )
        if latency_values
        else 0
    )

    p95_response = _percentile(
        latency_values,
        0.95,
    )

    # -------------------------------------------------------------------------
    # Filtered table rows
    # -------------------------------------------------------------------------

    rows = list(
        logs_qs.values(
            "status",
            "status_code",
            "response_time_ms",
            "checked_at",
            "error_message",
        )
    )

    # -------------------------------------------------------------------------
    # History graph
    #
    # Always uses complete period.
    # -------------------------------------------------------------------------

    history_rows = list(
        base_logs_qs.values(
            "status",
            "status_code",
            "response_time_ms",
            "checked_at",
            "error_message",
        )
    )

    history = _bucket_history(
        history_rows,
        start_time,
        bucket_seconds,
    )

    # -------------------------------------------------------------------------
    # Pagination
    # -------------------------------------------------------------------------

    try:

        page = max(
            1,
            int(page),
        )

    except (
        TypeError,
        ValueError,
    ):

        page = 1

    try:

        page_size = int(
            page_size
        )

    except (
        TypeError,
        ValueError,
    ):

        page_size = 30

    page_size = min(
        max(
            page_size,
            10,
        ),
        100,
    )

    checks_total = len(
        rows
    )

    checks_total_pages = max(
        1,
        math.ceil(
            checks_total
            / page_size
        ),
    )

    page = min(
        page,
        checks_total_pages,
    )

    start_index = (
        page - 1
    ) * page_size

    recent = rows[
        start_index:
        start_index + page_size
    ]

    # -------------------------------------------------------------------------
    # Response
    # -------------------------------------------------------------------------

    return {

        "monitor_id": monitor.id,

        "name": monitor.name,

        "url": monitor.url,

        "status": monitor.status,

        "is_active": monitor.is_active,

        "period": period,

        "period_label": period_label,

        "uptime_percentage": uptime,

        "downtime_percentage": round(
            max(
                0,
                100 - uptime,
            ),
            2,
        ),

        "error_rate": error_rate,

        "avg_response_time": avg_response,

        "p95_latency": p95_response,

        "total_checks": total,

        "up_checks": up_count,

        "down_checks": down_count,

        "response_time_threshold_ms": (
            monitor.response_time_threshold_ms
        ),

        "last_checked_at": (
            monitor.last_checked_at
        ),

        "response_time": (
            monitor.response_time
        ),

        "history": history,

        "checks": recent,

        "checks_total": checks_total,

        "summary_total_checks": (
            summary_total
        ),

        "summary_up_checks": (
            summary_up_count
        ),

        "summary_down_checks": (
            summary_down_count
        ),

        "checks_page": page,

        "checks_page_size": page_size,

        "checks_total_pages": (
            checks_total_pages
        ),

        "checks_status_filter": (
            normalized_status
        ),

        "checks_search": (
            normalized_search
        ),
    }


# =============================================================================
# ANALYTICS — SINGLE MONITOR
# =============================================================================

class MonitorAnalyticsView(APIView):

    permission_classes = [IsAuthenticated]

    def get(
        self,
        request,
        monitor_id,
    ):

        try:

            monitor = (
                _monitor_queryset_for_user(
                    request
                ).get(
                    pk=monitor_id
                )
            )

        except APIMonitor.DoesNotExist:

            return Response(
                {
                    "error": "Not found"
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        period = (
            request.query_params
            .get(
                "period",
                "7d",
            )
            .lower()
        )

        if period not in {
            "24h",
            "7d",
            "30d",
        }:

            period = "7d"

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

        except (
            TypeError,
            ValueError,
        ):

            page = 1

        try:

            page_size = int(
                request.query_params.get(
                    "page_size",
                    30,
                )
            )

        except (
            TypeError,
            ValueError,
        ):

            page_size = 30

        return Response(
            _monitor_analytics(
                monitor,
                period,
                page=page,
                page_size=page_size,
                status_filter=(
                    request.query_params.get(
                        "status",
                        "",
                    )
                ),
                search=(
                    request.query_params.get(
                        "search",
                        "",
                    )
                ),
            )
        )


# =============================================================================
# GLOBAL ANALYTICS
# =============================================================================

class GlobalAnalyticsView(APIView):

    permission_classes = [IsAuthenticated]

    def get(
        self,
        request,
    ):

        # ---------------------------------------------------------------------
        # Only this user's monitors
        # ---------------------------------------------------------------------

        monitors = (
            _monitor_queryset_for_user(
                request
            )
            .order_by(
                "-id"
            )
        )

        monitor_id = (
            request.query_params.get(
                "monitor_id"
            )
        )

        period = (
            request.query_params
            .get(
                "period",
                "7d",
            )
            .lower()
        )

        if period not in {
            "24h",
            "7d",
            "30d",
        }:

            period = "7d"

        # ---------------------------------------------------------------------
        # Specific monitor requested
        # ---------------------------------------------------------------------

        if monitor_id:

            try:

                monitor = monitors.get(
                    pk=monitor_id
                )

            except APIMonitor.DoesNotExist:

                return Response(
                    {
                        "error": "Not found"
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

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

            except (
                TypeError,
                ValueError,
            ):

                page = 1

            try:

                page_size = int(
                    request.query_params.get(
                        "page_size",
                        30,
                    )
                )

            except (
                TypeError,
                ValueError,
            ):

                page_size = 30

            return Response(
                _monitor_analytics(
                    monitor,
                    period,
                    page=page,
                    page_size=page_size,
                    status_filter=(
                        request.query_params.get(
                            "status",
                            "",
                        )
                    ),
                    search=(
                        request.query_params.get(
                            "search",
                            "",
                        )
                    ),
                )
            )

        # ---------------------------------------------------------------------
        # No monitor selected:
        # return monitor selector list.
        # ---------------------------------------------------------------------

        result = []

        for monitor in monitors:

            result.append(
                {
                    "monitor_id": monitor.id,

                    "name": monitor.name,

                    "url": monitor.url,

                    "status": monitor.status,

                    "is_active": monitor.is_active,

                    "uptime_percentage": (
                        monitor.uptime_percentage
                    ),

                    "response_time": (
                        monitor.response_time
                    ),

                    "last_checked_at": (
                        monitor.last_checked_at
                    ),
                }
            )

        return Response(
            {
                "monitors": result,
                "default_period": period,
            }
        )