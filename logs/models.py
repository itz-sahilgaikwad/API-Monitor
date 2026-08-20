from django.db import models
from monitoring.models import APIMonitor


class APILog(models.Model):
    STATUS_CHOICES = (
        ('UP', 'UP'),
        ('DOWN', 'DOWN'),
    )

    api_monitor = models.ForeignKey(
        APIMonitor,
        on_delete=models.CASCADE,
        related_name='logs'
    )

    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    status_code = models.IntegerField(null=True, blank=True)
    response_time_ms = models.FloatField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)

    checked_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.api_monitor.name} - {self.status}"