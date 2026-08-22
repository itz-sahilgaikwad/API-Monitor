from celery import shared_task
from django.utils import timezone
import os
import requests
import time

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
    """
    Check the user's normal alert cooldown.

    Used for SLOW alerts.
    DOWN and RECOVERY alerts do not use this cooldown.
    """

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


def _send_email(
    monitor,
    subject,
    body,
    use_cooldown=True,
):
    """
    Send an email alert.

    use_cooldown=True:
        Used for SLOW alerts.

    use_cooldown=False:
        Used for DOWN and RECOVERY alerts.
    """

    emails = _collect_alert_emails(monitor)

    if not emails:
        print(
            f"No alert email configured for {monitor.name}"
        )
        return False

    if use_cooldown and not _can_alert(monitor):
        print(
            f"Email cooldown active for {monitor.name}"
        )
        return False

    try:
        resend_api_key = os.getenv("RESEND_API_KEY")

        if not resend_api_key:
            print(
                f"Email alert failed for {monitor.name}: "
                "RESEND_API_KEY is not configured"
            )
            return False

        from_email = os.getenv(
            "RESEND_FROM_EMAIL",
            "onboarding@resend.dev",
        )

        payload = {
            "from": from_email,
            "to": emails,
            "subject": subject,
            "text": body,
        }

        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {resend_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=15,
        )

        if not response.ok:
            try:
                error_details = response.json()
            except ValueError:
                error_details = response.text[:500]

            raise RuntimeError(
                f"Resend HTTP {response.status_code}: {error_details}"
            )

        print(
            f"Email alert sent for {monitor.name} "
            f"to {', '.join(emails)} via Resend"
        )

        print(f"Resend response: {response.text[:500]}")

        if use_cooldown:
            _mark_alerted(monitor)

        return True

    except Exception as exc:
        print(
            f"Email alert failed for {monitor.name}: {exc}"
        )

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

    if (
        "connection error" in message
        or "connectionerror" in message
    ):
        return "Connection Error"

    if (
        "name or service not known" in message
        or "getaddrinfo" in message
        or "name resolution" in message
    ):
        return "DNS Error"

    if (
        "ssl" in message
        or "certificate" in message
    ):
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
    Perform one HTTP request.

    Returns:
        response
        response_time_ms
        error_message
    """

    headers = {}

    if monitor.api_key:
        headers["Authorization"] = (
            f"Bearer {monitor.api_key}"
        )

    start = time.perf_counter()

    try:
        response = requests.request(
            monitor.method,
            monitor.url,
            headers=headers,
            timeout=timeout,
            allow_redirects=True,
        )

        elapsed_ms = (
            time.perf_counter() - start
        ) * 1000

        return response, elapsed_ms, None

    except requests.exceptions.Timeout:
        elapsed_ms = (
            time.perf_counter() - start
        ) * 1000

        return (
            None,
            elapsed_ms,
            "Timeout",
        )

    except Exception as exc:
        elapsed_ms = (
            time.perf_counter() - start
        ) * 1000

        return (
            None,
            elapsed_ms,
            _classify_error(exc),
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
        status="UP",
    ).count()

    return round(
        (successful / total) * 100,
        2,
    )


# =============================================================================
# SLOW RESPONSE ALERT
# =============================================================================

def _send_slow_alert(
    monitor,
    response_time_ms,
    threshold,
):
    if not response_time_ms:
        return

    if response_time_ms <= threshold:
        return

    if not _can_alert(monitor):
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
        "but its response time is above the configured "
        "threshold.\n\n"
        "— API Monitor"
    )

    _send_email(
        monitor,
        f"⚠️ {monitor.name} Slow Response",
        body,
        use_cooldown=True,
    )


# =============================================================================
# DOWN ALERT
# =============================================================================

def _send_down_alert(
    monitor,
    error_message,
):
    timestamp = timezone.now().strftime(
        "%d %b %Y, %H:%M UTC"
    )

    body = (
        "Hello,\n\n"
        "Your monitored API is DOWN.\n\n"
        f"Monitor Name : {monitor.name}\n"
        f"URL          : {monitor.url}\n"
        f"Detected At  : {timestamp}\n"
        f"Reason       : "
        f"{error_message or 'Request failed'}\n\n"
        "The system will notify you when the API recovers.\n\n"
        "— API Monitor"
    )

    # DOWN alerts do NOT use the normal email cooldown.
    # The UP -> DOWN transition below prevents repeated
    # DOWN emails while the API remains DOWN.

    _send_email(
        monitor,
        f"🔴 {monitor.name} is DOWN",
        body,
        use_cooldown=False,
    )


# =============================================================================
# RECOVERY ALERT
# =============================================================================

def _send_recovery_alert(
    monitor,
    downtime_text="",
):
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
        body += (
            f"Downtime     : {downtime_text}\n"
        )

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
# MAIN CELERY TASK
# =============================================================================

@shared_task
def check_api_health():

    monitors = (
        APIMonitor.objects
        .filter(is_active=True)
        .select_related("owner")
    )

    now = timezone.now()

    for monitor in monitors:

        # ---------------------------------------------------------------------
        # CHECK INTERVAL
        # ---------------------------------------------------------------------

        if monitor.last_checked_at:

            elapsed = (
                now - monitor.last_checked_at
            ).total_seconds()

            if elapsed < monitor.check_interval:
                continue

        # ---------------------------------------------------------------------
        # SAVE PREVIOUS STATE
        # ---------------------------------------------------------------------

        previous_status = monitor.status

        previous_response_time = (
            monitor.response_time
        )

        previous_failure_count = (
            monitor.failure_count or 0
        )

        # ---------------------------------------------------------------------
        # RESPONSE TIME THRESHOLD
        # ---------------------------------------------------------------------

        threshold = monitor.response_time_threshold_ms

        # ---------------------------------------------------------------------
        # REQUEST WITH RETRIES
        # ---------------------------------------------------------------------

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

            # ---------------------------------------------------------------
            # SUCCESSFUL HTTP RESPONSE
            # ---------------------------------------------------------------

            if response is not None:

                if (
                    200 <= response.status_code <= 399
                ):

                    error_message = None
                    break

                # -----------------------------------------------------------
                # HTTP ERROR
                # -----------------------------------------------------------

                error_message = (
                    _classify_http_error(
                        response.status_code
                    )
                )

                if attempt < retries - 1:
                    time.sleep(retry_delay)

            # ----------------------------------------------------------------
            # REQUEST ERROR / TIMEOUT
            # ----------------------------------------------------------------

            else:

                error_message = request_error

                if attempt < retries - 1:
                    time.sleep(retry_delay)

        # ---------------------------------------------------------------------
        # DETERMINE ACTUAL CHECK RESULT
        # ---------------------------------------------------------------------

        request_succeeded = (
            response is not None
            and 200 <= response.status_code <= 399
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

        # ---------------------------------------------------------------------
        # FAILURE COUNT
        # ---------------------------------------------------------------------

        if request_succeeded:
            current_failure_count = 0
        else:
            current_failure_count = (
                previous_failure_count + 1
            )

        # ---------------------------------------------------------------------
        # CONFIRMED UP / DOWN STATE
        # ---------------------------------------------------------------------

        if request_succeeded:

            new_status = "UP"

        elif previous_status == "DOWN":

            new_status = "DOWN"

        elif current_failure_count >= 3:

            new_status = "DOWN"

        else:

            new_status = "UP"

        # ---------------------------------------------------------------------
        # SLOW STATUS
        # ---------------------------------------------------------------------

        is_slow = (
            request_succeeded
            and response_time is not None
            and response_time > threshold
        )

        # ---------------------------------------------------------------------
        # UPDATE MONITOR
        # ---------------------------------------------------------------------

        monitor.status = new_status

        monitor.response_time = response_time

        monitor.last_checked_at = timezone.now()

        if request_succeeded:

            monitor.last_error = (
                f"Slow response: "
                f"{response_time:.0f} ms"
                if is_slow
                else None
            )

            monitor.failure_count = 0

        else:

            monitor.last_error = log_error

            monitor.failure_count = (
                current_failure_count
            )

        monitor.save()

        # ---------------------------------------------------------------------
        # CREATE API LOG
        # ---------------------------------------------------------------------

        APILog.objects.create(
            api_monitor=monitor,
            status=(
                "UP"
                if request_succeeded
                else "DOWN"
            ),
            status_code=status_code,
            response_time_ms=response_time,
            error_message=log_error,
            checked_at=timezone.now(),
        )

        # ---------------------------------------------------------------------
        # UPDATE UPTIME
        # ---------------------------------------------------------------------

        uptime = _recalc_uptime(monitor)

        monitor.uptime_percentage = uptime

        monitor.save(
            update_fields=[
                "uptime_percentage",
            ]
        )

        # =====================================================================
        # DOWN LOGIC
        # =====================================================================

        if new_status == "DOWN":

            # ---------------------------------------------------------------
            # DOWN INCIDENT + EMAIL
            # ---------------------------------------------------------------
            # Create exactly one ONGOING incident for a downtime event.
            # Send the DOWN email only when a NEW incident is created.
            #
            # This is safer than checking previous_status alone because the
            # database status can already be DOWN while the incident record
            # is missing (for example after a manual test/reset).

            ongoing_incident = (
                Incident.objects
                .filter(
                    monitor=monitor,
                    status="ONGOING",
                )
                .first()
            )

            if not ongoing_incident:

                Incident.objects.create(
                    monitor=monitor,
                    started_at=timezone.now(),
                    status="ONGOING",
                    reason=(
                        log_error
                        or "API request failed"
                    ),
                )

                # Record the start of this downtime event.
                if not monitor.downtime_started_at:

                    monitor.downtime_started_at = (
                        timezone.now()
                    )

                    monitor.save(
                        update_fields=[
                            "downtime_started_at",
                        ]
                    )

                # NEW INCIDENT = SEND DOWN EMAIL.
                # _send_email() uses fail_silently=False, so any SMTP
                # problem is printed in the Celery worker log.
                _send_down_alert(
                    monitor,
                    log_error,
                )

        # =====================================================================
        # RECOVERY LOGIC
        # =====================================================================

        elif (
            previous_status == "DOWN"
            and new_status == "UP"
        ):

            incident = (
                Incident.objects
                .filter(
                    monitor=monitor,
                    status="ONGOING",
                )
                .last()
            )

            if incident:

                incident.resolved_at = (
                    timezone.now()
                )

                incident.status = "RESOLVED"

                incident.save()

            downtime_text = ""

            if monitor.downtime_started_at:

                downtime_seconds = (
                    timezone.now()
                    - monitor.downtime_started_at
                ).total_seconds()

                minutes = int(
                    downtime_seconds // 60
                )

                seconds = int(
                    downtime_seconds % 60
                )

                if minutes:

                    downtime_text = (
                        f"{minutes}m {seconds}s"
                    )

                else:

                    downtime_text = (
                        f"{seconds}s"
                    )

                monitor.last_downtime_duration = (
                    downtime_seconds
                )

                monitor.downtime_started_at = None

                monitor.save(
                    update_fields=[
                        "last_downtime_duration",
                        "downtime_started_at",
                    ]
                )

            _send_recovery_alert(
                monitor,
                downtime_text,
            )

        # =====================================================================
        # SLOW RESPONSE LOGIC
        # =====================================================================

        elif new_status == "UP":

            previously_slow = (
                previous_response_time is not None
                and previous_response_time > threshold
            )

            if is_slow and not previously_slow:

                _send_slow_alert(
                    monitor,
                    response_time,
                    threshold,
                )
        # ---------------------------------------------------------------------
        # UPDATE MONITOR
        # ---------------------------------------------------------------------

        monitor.status = new_status

        monitor.response_time = response_time

        monitor.last_checked_at = timezone.now()

        if request_succeeded:

            # Successful check clears the previous error.
            monitor.last_error = (
                f"Slow response: "
                f"{response_time:.0f} ms"
                if is_slow
                else None
            )

            monitor.failure_count = 0

        else:

            # Only show an error on the dashboard when the API is
            # actually confirmed DOWN.
            #
            # If this is only a temporary failed check and the API
            # has not reached the DOWN threshold yet, keep the
            # dashboard status clean.
            if new_status == "DOWN":
                monitor.last_error = log_error
            else:
                monitor.last_error = None

            monitor.failure_count = current_failure_count

        monitor.save()