from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("monitoring", "0012_apimonitor_request_headers"),
    ]

    operations = [
        migrations.AddField(
            model_name="apimonitor",
            name="request_body",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Optional request body for POST, PUT, and PATCH requests.",
            ),
        ),
    ]
