from django.urls import path
from .views import (
    APIMonitorListCreateView,
    APIMonitorDetailView,
    MonitorToggleView,
    MonitorLogsView,
    AllIncidentsView,
    IncidentDashboardView,
    MonitorAnalyticsView,
    GlobalAnalyticsView,
)
from .analytics import PublicStatusPage

urlpatterns = [
    # Monitors
    path('',              APIMonitorListCreateView.as_view(), name='api-monitor-list'),
    path('<int:pk>/',     APIMonitorDetailView.as_view(),    name='api-monitor-detail'),
    path('<int:pk>/toggle/', MonitorToggleView.as_view(),    name='api-monitor-toggle'),
    path('<int:pk>/logs/',   MonitorLogsView.as_view(),      name='api-monitor-logs'),

    # Incidents
    path('incidents/',              AllIncidentsView.as_view(),       name='all-incidents'),
    path('incidents/<int:monitor_id>/', IncidentDashboardView.as_view(), name='incident-dashboard'),

    # Analytics
    path('analytics/',                  GlobalAnalyticsView.as_view(),   name='global-analytics'),
    path('analytics/<int:monitor_id>/', MonitorAnalyticsView.as_view(),  name='monitor-analytics'),

    # Public
    path('status/', PublicStatusPage.as_view(), name='public-status'),
]