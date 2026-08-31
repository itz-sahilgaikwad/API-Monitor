from celery import shared_task
from django.utils import timezone
import os
import requests
import time
from django.core.cache import cache
from django.conf import settings
from django.core.mail import send_mail

from .models import APIMonitor, Incident
from logs.models import APILog


# =============================================================================
# EMAIL HELPERS
# =============================================================================

def _collect_alert_emails(monitor):
    emails = set()
    owner = monitor.owner

    if not owner:
        return []

    if not getattr(owner, "email_alerts_enabled", True):
        return []

    if owner.email:
        emails.add(owner.email)

    return list(emails)


def _can_alert(monitor):
    owner = monitor.owner

    if not owner:
        return True

    try:
        return owner.can_send_alert()
    except Exception:
        return True


def _mark_alerted(monitor):
    owner = monitor.owner

    if not owner:
        return

    try:
        owner.mark_alert_sent()
    except Exception:
        pass


def _send_email(monitor, subject, body, use_cooldown=True):
    emails = _collect_alert_emails(monitor)

    if not emails:
        print(f"No alert email configured for {monitor.name}")
        return False

    if use_cooldown and not _can_alert(monitor):
        print(f"Email cooldown active for {monitor.name}")
        return False

    from_email = getattr(
        settings,
        "DEFAULT_FROM_EMAIL",
        ""
    ).strip()

    if not from_email:
        print(
            f"Email alert failed for {monitor.name}: "
            "DEFAULT_FROM_EMAIL is not configured"
        )
        return False

    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=from_email,
            recipient_list=emails,
            fail_silently=False,
        )

        print(
            f"Email alert sent for {monitor.name} "
            f"to {', '.join(emails)} via Gmail SMTP"
        )

        if use_cooldown:
            _mark_alerted(monitor)

        return True

    except Exception as exc:
        print(f"Email alert failed for {monitor.name}: {exc}")
        return False


# =============================================================================
# ERROR HELPERS
# =============================================================================

def _classify_error(exc):
    message = str(exc).lower()

    if "timeout" in message or "timed out" in message:
        return "Timeout"

    if "connection refused" in message:
        return "Connection Refused"

    if "connection error" in message or "connectionerror" in message:
        return "Connection Error"

    if (
        "name or service not known" in message
        or "getaddrinfo" in message
        or "name resolution" in message
    ):
        return "DNS Error"

    if "ssl" in message or "certificate" in message:
        return "SSL Error"

    return f"Request Error: {str(exc)[:100]}"


def _classify_http_error(status_code):
    descriptions = {
        400: "HTTP 400 Bad Request",
        401: "HTTP 401 Unauthorized",
        403: "HTTP 403 Forbidden",
        404: "HTTP 404 Not Found",
        408: "HTTP 408 Request Timeout",
        429: "HTTP 429 Too Many Requests",
        500: "HTTP 500 Server Error",
        502: "HTTP 502 Bad Gateway",
        503: "HTTP 503 Service Unavailable",
        504: "HTTP 504 Gateway Timeout",
    }

    return descriptions.get(
        status_code,
        f"HTTP {status_code} Error",
    )


# =============================================================================
# HTTP REQUEST
# =============================================================================

def _attempt_request(monitor, timeout=10):
    """
    Perform one HTTP request using the monitor configuration.

    Authentication:
        none      -> no authentication header
        bearer    -> Authorization: Bearer <key>
        x_api_key -> X-API-Key: <key>

    Custom request headers:
        Any headers configured in monitor.request_headers are added
        to the outgoing HTTP request.

    Returns:
        response
        response_time_ms
        error_message
    """

    headers = {}

    # -------------------------------------------------------------------------
    # Custom request headers
    # -------------------------------------------------------------------------

    request_headers = getattr(monitor, "request_headers", None)

    if isinstance(request_headers, dict):
        for key, value in request_headers.items():
            if key and value is not None:
                headers[str(key)] = str(value)

    # -------------------------------------------------------------------------
    # Authentication headers
    # -------------------------------------------------------------------------

    if monitor.api_key:
        if monitor.auth_type == "bearer":
            headers["Authorization"] = f"Bearer {monitor.api_key}"

        elif monitor.auth_type == "x_api_key":
            headers["X-API-Key"] = monitor.api_key

    # -------------------------------------------------------------------------
    # Request body
    # -------------------------------------------------------------------------
    # Only send bodies for methods that support a request payload in this
    # monitor. The body is sent as-is so JSON formatting/content-type remain
    # controlled by the configured request headers.
    request_body = getattr(monitor, "request_body", "") or ""
    data = None

    if monitor.method in ("POST", "PUT", "PATCH") and request_body:
        data = request_body.encode("utf-8")

        # JSON is the supported request-body format. Add a content type only
        # when the user did not already configure one in custom headers.
        if not any(str(key).lower() == "content-type" for key in headers):
            headers["Content-Type"] = "application/json"

    start = time.perf_counter()

    try:
        response = requests.request(
            monitor.method,
            monitor.url,
            headers=headers,
            data=data,
            timeout=timeout,
            allow_redirects=True,
        )

        elapsed_ms = (time.perf_counter() - start) * 1000

        return response, elapsed_ms, None

    except requests.exceptions.Timeout:
        elapsed_ms = (time.perf_counter() - start) * 1000

        return None, elapsed_ms, "Timeout"

    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000

        return None, elapsed_ms, _classify_error(exc)


# =============================================================================
# RESPONSE BODY VALIDATION
# =============================================================================

def _validate_response_body(monitor, response):
    """
    Validate the response body according to the monitor configuration.

    Supported validation types:
        none     -> no body validation
        contains -> expected response text must exist in response body
        exact    -> response body must exactly match expected response
        json     -> response JSON must match the expected JSON value
    """

    validation_type = getattr(
        monitor,
        "response_validation_type",
        "none",
    ) or "none"

    expected_response = getattr(
        monitor,
        "expected_response",
        "",
    )

    validation_type = str(validation_type).strip().lower()

    # No response-body validation configured.
    if validation_type in ("", "none"):
        return True, None

    if expected_response is None:
        expected_response = ""

    expected_response = str(expected_response)

    try:
        actual_text = response.text or ""
    except Exception:
        actual_text = ""

    # -------------------------------------------------------------------------
    # CONTAINS
    # -------------------------------------------------------------------------

    if validation_type == "contains":
        if expected_response in actual_text:
            return True, None

        return (
            False,
            "Response body does not contain the expected value",
        )

    # -------------------------------------------------------------------------
    # EXACT
    # -------------------------------------------------------------------------

    if validation_type == "exact":
        if actual_text.strip() == expected_response.strip():
            return True, None

        return (
            False,
            "Response body does not exactly match the expected value",
        )

    # -------------------------------------------------------------------------
    # JSON
    # -------------------------------------------------------------------------

    if validation_type == "json":
        import json

        try:
            expected_json = json.loads(expected_response)
        except json.JSONDecodeError:
            return (
                False,
                "Configured expected response is not valid JSON",
            )

        try:
            actual_json = response.json()
        except ValueError:
            return (
                False,
                "API response is not valid JSON",
            )

        if actual_json == expected_json:
            return True, None

        return (
            False,
            "API JSON response does not match the expected response",
        )

    # Unknown validation type.
    return (
        False,
        f"Unsupported response validation type: {validation_type}",
    )


# =============================================================================
# UPTIME
# =============================================================================

def _recalc_uptime(monitor):
    total = APILog.objects.filter(
        api_monitor=monitor
    ).count()

    if total == 0:
        return None

    successful = APILog.objects.filter(
        api_monitor=monitor,
        status__in=["UP", "SLOW"],
    ).count()

    return round((successful / total) * 100, 2)


# =============================================================================
# ALERTS
# =============================================================================

def _send_slow_alert(monitor, response_time_ms, threshold):
    if response_time_ms is None:
        return

    if threshold is None:
        return

    if response_time_ms <= threshold:
        return

    timestamp = timezone.now().strftime(
        "%d %b %Y, %H:%M UTC"
    )

    body = (
        "Hello,\n\n"
        "Your monitored API is responding slowly.\n\n"
        f"Monitor Name : {monitor.name}\n"
        f"URL          : {monitor.url}\n"
        f"Response Time: {response_time_ms:.0f} ms\n"
        f"Threshold    : {threshold:.0f} ms\n"
        f"Detected At  : {timestamp}\n\n"
        "The API is still responding successfully, "
        "but its response time is above the configured threshold.\n\n"
        "— API Monitor"
    )

    _send_email(
        monitor,
        f"⚠️ {monitor.name} Slow Response",
        body,
        use_cooldown=True,
    )


def _send_down_alert(monitor, error_message):
    timestamp = timezone.now().strftime(
        "%d %b %Y, %H:%M UTC"
    )

    body = (
        "Hello,\n\n"
        "Your monitored API is DOWN.\n\n"
        f"Monitor Name : {monitor.name}\n"
        f"URL          : {monitor.url}\n"
        f"Detected At  : {timestamp}\n"
        f"Reason       : {error_message or 'Request failed'}\n\n"
        "The system will notify you when the API recovers.\n\n"
        "— API Monitor"
    )

    return _send_email(
        monitor,
        f"🔴 {monitor.name} is DOWN",
        body,
        use_cooldown=False,
    )


def _send_recovery_alert(monitor, downtime_text=""):
    timestamp = timezone.now().strftime(
        "%d %b %Y, %H:%M UTC"
    )

    body = (
        "Hello,\n\n"
        "Good news! Your monitored API has recovered.\n\n"
        f"Monitor Name : {monitor.name}\n"
        f"URL          : {monitor.url}\n"
        f"Recovered At : {timestamp}\n"
    )

    if downtime_text:
        body += f"Downtime     : {downtime_text}\n"

    body += (
        "\nThe API is responding normally again.\n\n"
        "— API Monitor"
    )

    _send_email(
        monitor,
        f"✅ {monitor.name} has RECOVERED",
        body,
        use_cooldown=False,
    )


# =============================================================================
# INCIDENT HELPERS
# =============================================================================

def _get_ongoing_incident(monitor):
    return (
        Incident.objects
        .filter(
            monitor=monitor,
            status="ONGOING",
        )
        .order_by("-started_at")
        .first()
    )


def _start_incident(monitor, reason):
    incident = _get_ongoing_incident(monitor)

    if incident:
        return incident

    incident = Incident.objects.create(
        monitor=monitor,
        started_at=timezone.now(),
        status="ONGOING",
        reason=reason or "API request failed",
    )

    if not monitor.downtime_started_at:
        monitor.downtime_started_at = timezone.now()
        monitor.save(
            update_fields=["downtime_started_at"]
        )

    return incident


def _resolve_incident(monitor):
    incident = _get_ongoing_incident(monitor)

    if not incident:
        return

    incident.resolved_at = timezone.now()
    incident.status = "RESOLVED"
    incident.save(
        update_fields=[
            "resolved_at",
            "status",
        ]
    )


def _calculate_downtime(monitor):
    if not monitor.downtime_started_at:
        return ""

    downtime_seconds = (
        timezone.now()
        - monitor.downtime_started_at
    ).total_seconds()

    minutes = int(downtime_seconds // 60)
    seconds = int(downtime_seconds % 60)

    if minutes:
        downtime_text = f"{minutes}m {seconds}s"
    else:
        downtime_text = f"{seconds}s"

    monitor.last_downtime_duration = downtime_seconds
    monitor.downtime_started_at = None

    monitor.save(
        update_fields=[
            "last_downtime_duration",
            "downtime_started_at",
        ]
    )

    return downtime_text


# =============================================================================
# MAIN CELERY TASK
# =============================================================================

@shared_task
def check_api_health(monitor_id=None, force=False):
    """
    Run health checks for active monitors.

    When ``monitor_id`` is supplied, only that monitor is checked.
    This is used by the Dashboard "Check Now" action so a manual check
    never triggers checks for every API.
    When called without an id, the normal scheduled all-monitors behavior
    is preserved. ``force=True`` bypasses the normal interval guard for a
    manual Dashboard check.
    """

    monitors = (
        APIMonitor.objects
        .filter(is_active=True)
        .select_related("owner")
    )

    if monitor_id is not None:
        monitors = monitors.filter(id=monitor_id)

    now = timezone.now()

    for monitor in monitors:

        # =====================================================================
        # CHECK INTERVAL
        # =====================================================================

        if monitor.last_checked_at and not (monitor_id is not None and force):
            elapsed = (
                now - monitor.last_checked_at
            ).total_seconds()

            if elapsed < monitor.check_interval:
                continue

        # =====================================================================
        # PREVIOUS STATE
        # =====================================================================

        previous_status = monitor.status
        previous_response_time = monitor.response_time
        previous_failure_count = monitor.failure_count or 0

        threshold = (
            monitor.response_time_threshold_ms
            or 1000
        )

        # =====================================================================
        # REQUEST + RETRIES
        # =====================================================================

        response = None
        response_time = None
        error_message = None

        retries = 3
        retry_delay = 2

        for attempt in range(retries):

            response, elapsed_ms, request_error = (
                _attempt_request(monitor)
            )

            response_time = elapsed_ms

            if response is not None:

                if response.status_code == monitor.expected_status:
                    body_valid, body_error = _validate_response_body(
                        monitor,
                        response,
                    )

                    if body_valid:
                        error_message = None
                        break

                    error_message = body_error

                else:
                    error_message = (
                        f"Expected HTTP "
                        f"{monitor.expected_status}, "
                        f"received HTTP "
                        f"{response.status_code}"
                    )

            else:
                error_message = request_error

            if attempt < retries - 1:
                time.sleep(retry_delay)

        # =====================================================================
        # RESULT
        # =====================================================================

        request_succeeded = (
            response is not None
            and response.status_code == monitor.expected_status
            and _validate_response_body(
                monitor,
                response,
            )[0]
        )

        status_code = (
            response.status_code
            if response is not None
            else None
        )

        log_error = (
            None
            if request_succeeded
            else (
                error_message
                or "Unknown Error"
            )
        )

        # =====================================================================
        # FAILURE COUNT
        # =====================================================================

        if request_succeeded:
            current_failure_count = 0
        else:
            current_failure_count = (
                previous_failure_count + 1
            )

        # =====================================================================
        # SLOW RESPONSE
        # =====================================================================

        is_slow = (
            request_succeeded
            and response_time is not None
            and response_time > threshold
        )

        # =====================================================================
        # CONFIRMED STATUS
        # =====================================================================

        if request_succeeded:
            new_status = "SLOW" if is_slow else "UP"

        elif previous_status == "DOWN":
            new_status = "DOWN"

        elif current_failure_count >= 1:
            # The task already performs 3 HTTP attempts above. If all
            # attempts fail (including response-body validation), the
            # current health check is considered a confirmed failure.
            new_status = "DOWN"

        else:
            new_status = "UP"

        # =====================================================================
        # UPDATE MONITOR STATE
        # =====================================================================

        monitor.status = new_status
        monitor.response_time = response_time
        monitor.last_checked_at = timezone.now()

        if request_succeeded:

            if is_slow:
                monitor.last_error = (
                    f"Slow response: "
                    f"{response_time:.0f} ms"
                )
            else:
                monitor.last_error = None

            monitor.failure_count = 0

        else:

            monitor.failure_count = (
                current_failure_count
            )

            # Do not display temporary failures
            # as an actual error until DOWN.
            if new_status == "DOWN":
                monitor.last_error = log_error
            else:
                monitor.last_error = None

        monitor.save()

        # =====================================================================
        # LOG
        # =====================================================================

        APILog.objects.create(
            api_monitor=monitor,
            status=(
                "SLOW"
                if is_slow
                else "UP"
                if request_succeeded
                else "DOWN"
            ),
            status_code=status_code,
            response_time_ms=response_time,
            error_message=log_error,
            checked_at=timezone.now(),
        )

        # =====================================================================
        # UPTIME
        # =====================================================================

        monitor.uptime_percentage = (
            _recalc_uptime(monitor)
        )

        monitor.save(
            update_fields=[
                "uptime_percentage"
            ]
        )

        # =====================================================================
        # CONSOLE LOG
        # =====================================================================

        print(
            f"Monitor {monitor.name}: "
            f"status={new_status}, "
            f"failures={monitor.failure_count}, "
            f"expected_status="
            f"{monitor.expected_status}, "
            f"actual_status={status_code}, "
            f"response_time="
            f"{response_time:.0f}ms"
            if response_time is not None
            else
            f"Monitor {monitor.name}: "
            f"status={new_status}, "
            f"failures={monitor.failure_count}, "
            f"expected_status="
            f"{monitor.expected_status}, "
            f"actual_status={status_code}"
        )

        # =====================================================================
        # DOWN LOGIC
        # =====================================================================

        if new_status == "DOWN":

            incident = _get_ongoing_incident(
                monitor
            )

            if not incident:
                _start_incident(
                    monitor,
                    log_error or "API request failed",
                )

            down_cache_key = (
                f"api_monitor:"
                f"down_alert_sent:"
                f"{monitor.id}"
            )

            if not cache.get(down_cache_key):

                email_sent = _send_down_alert(
                    monitor,
                    log_error,
                )

                if email_sent:

                    cache.set(
                        down_cache_key,
                        True,
                        timeout=7 * 24 * 60 * 60,
                    )

                    print(
                        f"DOWN email delivery confirmed "
                        f"for {monitor.name}"
                    )

                else:

                    print(
                        f"DOWN email delivery failed "
                        f"for {monitor.name}; "
                        f"will retry on the next check"
                    )

        # =====================================================================
        # RECOVERY LOGIC
        # =====================================================================

        elif (
            previous_status == "DOWN"
            and new_status in ("UP", "SLOW")
        ):

            _resolve_incident(monitor)

            downtime_text = _calculate_downtime(
                monitor
            )

            _send_recovery_alert(
                monitor,
                downtime_text,
            )

            cache.delete(
                f"api_monitor:"
                f"down_alert_sent:"
                f"{monitor.id}"
            )

        # =====================================================================
        # SLOW RESPONSE LOGIC
        # =====================================================================

        elif new_status in ("UP", "SLOW"):

            previously_slow = (
                previous_status == "SLOW"
                or (
                    previous_response_time is not None
                    and previous_response_time > threshold
                )
            )

            if is_slow and not previously_slow:

                _send_slow_alert(
                    monitor,
                    response_time,
                    threshold,
                )