import logging
from datetime import timedelta

from django.core.management import BaseCommand
from django.utils import timezone

from supportal.shifter.models import EventSignup


class Command(BaseCommand):
    help = "If MA goes down retry the sends that failed"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit", type=int, nargs="?", help="Number of events to retry"
        )
        parser.add_argument(
            "--days", type=int, nargs="?", help="How many days back should we look"
        )
        parser.add_argument(
            "--no_response",
            action="store_true",
            help="only resignup people who weren't sent to mobilize",
        )

    def handle(self, *args, **options):
        logging.info(f"Starting to retry sends")
        limit = options.get("limit", None)
        days = options.get("days", None)
        not_sent = options.get("no_response")
        failed_events = EventSignup.objects.filter(ma_creation_successful=False)

        if days is not None:
            create_at_cutoff = timezone.now() - timedelta(days=days)
            failed_events = failed_events.filter(created_at__gte=create_at_cutoff)

        if not_sent:
            failed_events = failed_events.filter(ma_response__isnull=True)

        if limit:
            failed_events = failed_events[:limit]

        events_successfull_resyncd_count = 0
        for event in failed_events:
            success, _ = event.sync_to_mobilize_america()
            if success:
                logging.info(f"Successfully sent signup with id {event.id} to MA")
                events_successfull_resyncd_count += 1
            else:
                logging.info(f"Still unable to send signup {event.id} to MA")
            event.retried_at = timezone.now()
            event.save()

        return f"Resent {events_successfull_resyncd_count} signups"
