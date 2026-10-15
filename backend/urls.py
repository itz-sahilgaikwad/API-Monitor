from pathlib import Path

import redis
from django.conf import settings
from django.contrib import admin
from django.db import connection
from django.http import JsonResponse
from django.urls import include, path
from django.views.generic import RedirectView
from django.views.static import serve as static_serve

from monitoring.admin_views import AdminSystemOverviewView


def health_check(request):
    """Return application and dependency health for deployment checks."""
    checks = {}
    healthy = True

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        checks["database"] = "ok"
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
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "error"
        healthy = False

    response_status = 200 if healthy else 503

    return JsonResponse(
        {
            "status": "ok" if healthy else "error",
            "service": "API Monitor",
            "checks": checks,
        },
        status=response_status,
    )


def frontend_serve(request, path):
    """Serve frontend files without browser caching for HTML pages."""
    response = static_serve(
        request,
        path,
        document_root=str(Path(settings.BASE_DIR) / "frontend"),
    )

    if path.endswith(".html"):
        response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response["Pragma"] = "no-cache"
        response["Expires"] = "0"

    return response


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health_check, name="health"),
    path(
        "api/admin/system-overview/",
        AdminSystemOverviewView.as_view(),
        name="admin-system-overview",
    ),

    path("api/monitoring/", include("monitoring.urls")),
    path("api/users/", include("users.urls")),
    path("api/auth/", include("users.urls")),
    path("api/logs/", include("logs.urls")),

    path(
        "",
        RedirectView.as_view(
            url="/app/user_login.html",
            permanent=False,
        ),
        name="home",
    ),
    path("app/<path:path>", frontend_serve),
]
