import logging
from datetime import timedelta

from django.core.management import BaseCommand
from django.utils import timezone

from supportal.services.mobilize_america import (
    EVENT_TYPES,
    VISIBILITY_TYPES,
    get_global_client,
)
from supportal.shifter.models import MobilizeAmericaEvent

# from ew_common.telemetry import telemetry  # isort:skip

MA_EVENT_GET_MAX = 1000
EVENT_PER_PAGE = 20


class Command(BaseCommand):
    help = "Import all mobilize america"

    def handle(self, *args, **options):
        logging.info(f"Starting Mobilize America event import")
        event_count = 0

        for visibility in VISIBILITY_TYPES:
            created_events = []
            updated_events = []
            logging.info(f"Indexing {visibility} events")
            params = {"timeslot_start": "gte_now", "visibility": visibility}
            res = get_global_client().list_organization_events(params=params)
            page_count = 0
            events_for_visibiity = 0
            for page in res:
                logging.info(f"PAGE: {page_count}")
                page_count += 1
                for event in page["data"]:
                    events_for_visibiity += 1
                    shifter_event, created = MobilizeAmericaEvent.objects.update_or_create_from_json(
                        event
                    )
                    if created:
                        created_events.append(str(shifter_event.id))
                    else:
                        updated_events.append(str(shifter_event.id))
            event_count += events_for_visibiity
            if events_for_visibiity == MA_EVENT_GET_MAX:
                # telemetry.event(
                #     "Shifter Mobilize America Event Import at 1000",
                #     page_count=page_count,
                #     visibility=visibility,
                #     event_count=events_for_visibiity,
                # )
            created_event_ids_string = ", ".join(created_events)
            logging.info(
                f"Created the following {visibility} events: {created_event_ids_string}"
            )
            updated_event_ids_string = ", ".join(updated_events)
            logging.info(
                f"Updated the following {visibility} events: {updated_event_ids_string}"
            )

        # Find all the events that were not updated in the last 20 minutes
        # and mark them as inactive in the database
        updated_at_cut_off = timezone.now() - timedelta(minutes=20)
        MobilizeAmericaEvent.objects.filter(updated_at__lte=updated_at_cut_off).update(
            is_active=False
        )
        return f"Loaded events: {event_count}"
