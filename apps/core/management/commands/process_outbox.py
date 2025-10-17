"""Drain the vector-sync outbox.

Cron mode (default)::

    python manage.py process_outbox --once

Long-running worker (systemd/supervisord)::

    python manage.py process_outbox --loop --interval 10
"""

import time

from django.core.management.base import BaseCommand

from apps.ingestion.outbox import process_pending


class Command(BaseCommand):
    help = "Process pending VectorSyncJob rows (vector-store outbox)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--once",
            action="store_true",
            help="Process the current backlog once and exit.",
        )
        parser.add_argument(
            "--loop",
            action="store_true",
            help="Run forever, polling for new jobs.",
        )
        parser.add_argument(
            "--interval",
            type=int,
            default=10,
            help="Seconds between polls in --loop mode.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Max jobs per pass (default: all pending).",
        )

    def handle(self, *args, **options):
        if options["loop"]:
            self.stdout.write(f"process_outbox: looping every {options['interval']}s")
            try:
                while True:
                    summary = process_pending(limit=options["limit"])
                    if summary["done"] or summary["failed"]:
                        self.stdout.write(str(summary))
                    time.sleep(options["interval"])
            except KeyboardInterrupt:
                self.stdout.write("process_outbox: stopped")
        else:
            summary = process_pending(limit=options["limit"])
            self.stdout.write(str(summary))
