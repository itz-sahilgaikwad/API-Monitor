from django.contrib import admin
from .models import APIMonitor 
# Register your models here.
@admin.register(APIMonitor)
class APIMonitorAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'method', 'url', 'is_active', 'owner')
    list_filter =('method', 'is_active')
    search_fields=('name', 'url')