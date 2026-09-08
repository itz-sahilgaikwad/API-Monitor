from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("monitoring", "0018_monitoralertsettings"),
    ]

    operations = [
        migrations.CreateModel(
            name="NotificationLog",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "alert_type",
                    models.CharField(
                        choices=[
                            ("DOWN", "DOWN"),
                            ("SLOW", "SLOW"),
                            ("RECOVERY", "RECOVERY"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "recipient_email",
                    models.EmailField(
                        max_length=254,
                    ),
                ),
                (
                    "subject",
                    models.CharField(
                        max_length=255,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("SENT", "SENT"),
                            ("FAILED", "FAILED"),
                        ],
                        max_length=10,
                    ),
                ),
                (
                    "error_message",
                    models.TextField(
                        blank=True,
                        default="",
                    ),
                ),
                (
                    "sent_at",
                    models.DateTimeField(
                        auto_now_add=True,
                    ),
                ),
                (
                    "monitor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notification_logs",
                        to="monitoring.apimonitor",
                    ),
                ),
            ],
        ),
    ]