from django.urls import path
from .views import APILogListView

urlpatterns = [
    path('', APILogListView.as_view(), name='api-logs'),
]