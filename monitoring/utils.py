import requests
import time
from logs.models import APILog

def check_api_health(api_monitor):
    try:
        start_time = time.time()

        response = requests.request(
            method=api_monitor.method,
            url=api_monitor.url,
            timeout=10
        )

        response_time = (time.time() - start_time) * 1000

        if 200 <= response.status_code < 300:
            status = "UP"
        else:
            status = "DOWN"

        APILog.objects.create(
            api_monitor=api_monitor,
            status=status,
            status_code=response.status_code,
            response_time_ms=response_time,
            error_message=None
        )

        return status

    except Exception as e:
        APILog.objects.create(
            api_monitor=api_monitor,
            status="DOWN",
            status_code=None,
            response_time_ms=None,
            error_message=str(e)
        )

        return "DOWN"