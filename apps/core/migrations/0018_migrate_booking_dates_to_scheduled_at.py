"""Copy free-text Booking.date values into scheduled_at (typed).

Unparseable or blank values map to NULL and are reported via stdout so the
operator can reconcile them. Reverse is a noop: the old text column is
dropped in 0019.
"""

from django.db import migrations


def parse_booking_date(value):
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    from datetime import datetime

    try:
        return datetime.strptime(text, "%Y-%m-%d")
    except (ValueError, TypeError):
        pass
    try:
        import dateparser

        return dateparser.parse(text)
    except Exception:
        return None


def forwards(apps, schema_editor):
    Booking = apps.get_model("core", "Booking")
    nulled = 0
    copied = 0
    qs = Booking.objects.exclude(date__isnull=True).exclude(date="")
    for booking in qs.iterator():
        parsed = parse_booking_date(booking.date)
        if parsed is None:
            nulled += 1
            print(f"booking #{booking.pk}: unparseable date {booking.date!r} -> NULL")
        else:
            copied += 1
        Booking.objects.filter(pk=booking.pk).update(scheduled_at=parsed)
    print(f"booking date migration: {copied} parsed, {nulled} nulled")


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0017_remove_conversation_core_conver_company_141da1_idx_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, reverse_code=migrations.RunPython.noop),
    ]
