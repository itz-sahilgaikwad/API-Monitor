from django.contrib import admin
from .models import APILog


@admin.register(APILog)
class APILogAdmin(admin.ModelAdmin):
    list_display = (
        'api_monitor',
        'status',
        'status_code',
        'response_time_ms',
        'checked_at',
    )