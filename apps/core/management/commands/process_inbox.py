"""Answer queued WhatsApp messages.

Cron mode (default)::

    python manage.py process_inbox --once

Long-running worker (systemd/supervisord)::

    python manage.py process_inbox --loop --interval 15

Replaces the old `check_whatsapp` polling loop: ingestion now arrives via the
webhook, and this command only answers.
"""

import time

from django.core.management.base import BaseCommand

from apps.api.whatsapp_inbox import process_inbox


class Command(BaseCommand):
    help = "Reply to unprocessed WhatsAppMessage rows."

    def add_arguments(self, parser):
        parser.add_argument(
            "--once", action="store_true", help="One pass and exit."
        )
        parser.add_argument(
            "--loop", action="store_true", help="Run forever, polling."
        )
        parser.add_argument(
            "--interval", type=int, default=15, help="Seconds between polls."
        )
        parser.add_argument(
            "--limit", type=int, default=None, help="Max messages per pass."
        )

    def handle(self, *args, **options):
        if options["loop"]:
            self.stdout.write(
                f"process_inbox: looping every {options['interval']}s"
            )
            try:
                while True:
                    summary = process_inbox(limit=options["limit"])
                    if summary["sent"] or summary["failed"]:
                        self.stdout.write(str(summary))
                    time.sleep(options["interval"])
            except KeyboardInterrupt:
                self.stdout.write("process_inbox: stopped")
        else:
            self.stdout.write(str(process_inbox(limit=options["limit"])))
