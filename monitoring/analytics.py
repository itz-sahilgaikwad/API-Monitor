from rest_framework.views import APIView
from rest_framework.response import Response
from logs.models import APILog
from monitoring.models import APIMonitor


class MonitorAnalyticsView(APIView):

    def get(self, request, monitor_id):

        monitor = APIMonitor.objects.get(pk=monitor_id)
        logs = APILog.objects.filter(api_monitor=monitor)

        total_checks = logs.count()
        up_checks = logs.filter(status="UP").count()
        down_checks = logs.filter(status="DOWN").count()

        uptime_percentage = (up_checks / total_checks) * 100 if total_checks else 0

        response_times = logs.exclude(response_time_ms=None).values_list(
            "response_time_ms", flat=True
        )

        avg_response_time = (
            sum(response_times) / len(response_times)
            if response_times else 0
        )

        recent_history = logs.order_by("-checked_at")[:10].values(
            "status", "checked_at"
        )

        return Response({
            "monitor_id": monitor.id,
            "total_checks": total_checks,
            "up_checks": up_checks,
            "down_checks": down_checks,
            "uptime_percentage": uptime_percentage,
            "avg_response_time": avg_response_time,
            "recent_history": recent_history
        })
class GlobalMonitoringAnalytics(APIView):

    def get(self, request):

        monitors = APIMonitor.objects.all()
        result = []

        for monitor in monitors:

            logs = APILog.objects.filter(api_monitor=monitor)

            total_checks = logs.count()
            up_checks = logs.filter(status="UP").count()
            down_checks = logs.filter(status="DOWN").count()

            uptime_percentage = (up_checks / total_checks) * 100 if total_checks else 0

            result.append({
                "monitor_id": monitor.id,
                "name": monitor.name,
                "url": monitor.url,
                "status": monitor.status,
                "total_checks": total_checks,
                "uptime_percentage": uptime_percentage
            })

        return Response(result)

class PublicStatusPage(APIView):

    authentication_classes = []
    permission_classes = []

    def get(self, request):

        monitors = APIMonitor.objects.filter(is_active=True)

        result = []

        for monitor in monitors:

            logs = APILog.objects.filter(api_monitor=monitor)

            total_checks = logs.count()
            up_checks = logs.filter(status="UP").count()

            uptime = (up_checks / total_checks) * 100 if total_checks else 0

            last_log = logs.order_by("-checked_at").first()

            result.append({
                "name": monitor.name,
                "url": monitor.url,
                "status": monitor.status,
                "uptime_percentage": uptime,
                "last_checked": last_log.checked_at if last_log else None
            })

        services = result

        overall_status = "OPERATIONAL"

        for service in services:
            if service["status"] == "DOWN":
                overall_status = "DEGRADED"
                break

        return Response({
            "overall_status": overall_status,
            "services": services
})