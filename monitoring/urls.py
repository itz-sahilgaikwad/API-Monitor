from django.urls import path

from .views import (
    APIMonitorListCreateView,
    APIMonitorDetailView,
    MonitorToggleView,
    MonitorCheckNowView,
    MonitorLogsView,
    AllIncidentsView,
    IncidentDashboardView,
    MonitorAlertSettingsView,
    MonitorAnalyticsView,
    GlobalAnalyticsView,
)

from .analytics import PublicStatusPage


urlpatterns = [

    # =========================================================================
    # MONITORS
    # =========================================================================

    path(
        "",
        APIMonitorListCreateView.as_view(),
        name="api-monitor-list",
    ),

    path(
        "<int:pk>/",
        APIMonitorDetailView.as_view(),
        name="api-monitor-detail",
    ),

    path(
        "<int:pk>/toggle/",
        MonitorToggleView.as_view(),
        name="api-monitor-toggle",
    ),

    path(
        "<int:pk>/check-now/",
        MonitorCheckNowView.as_view(),
        name="api-monitor-check-now",
    ),

    path(
        "<int:pk>/logs/",
        MonitorLogsView.as_view(),
        name="api-monitor-logs",
    ),

    # =========================================================================
    # INCIDENTS
    # =========================================================================

    path(
        "incidents/",
        AllIncidentsView.as_view(),
        name="all-incidents",
    ),

    path(
        "incidents/<int:monitor_id>/",
        IncidentDashboardView.as_view(),
        name="incident-dashboard",
    ),

    # =========================================================================
    # ALERT SETTINGS
    # =========================================================================

    path(
        "<int:monitor_id>/alert-settings/",
        MonitorAlertSettingsView.as_view(),
        name="monitor-alert-settings",
    ),

    # =========================================================================
    # ANALYTICS
    # =========================================================================

    path(
        "analytics/",
        GlobalAnalyticsView.as_view(),
        name="global-analytics",
    ),

    path(
        "analytics/<int:monitor_id>/",
        MonitorAnalyticsView.as_view(),
        name="monitor-analytics",
    ),

    # =========================================================================
    # PUBLIC STATUS
    # =========================================================================

    path(
        "status/",
        PublicStatusPage.as_view(),
        name="public-status",
    ),
]