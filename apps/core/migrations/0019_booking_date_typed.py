"""Finish Booking.date typing: drop the text column, rename scheduled_at."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0018_migrate_booking_dates_to_scheduled_at"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="booking",
            name="date",
        ),
        migrations.RenameField(
            model_name="booking",
            old_name="scheduled_at",
            new_name="date",
        ),
        migrations.RemoveIndex(
            model_name="booking",
            name="core_bookin_company_af3a37_idx",
        ),
        migrations.AddIndex(
            model_name="booking",
            index=models.Index(
                fields=["company", "status", "date"],
                name="booking_company_status_date",
            ),
        ),
    ]
