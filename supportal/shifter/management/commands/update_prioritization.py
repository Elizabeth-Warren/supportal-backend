import logging

from django.conf import settings
from django.core.management import BaseCommand

from supportal.services.google_sheets_service import GoogleSheetsClient
from supportal.shifter.models import MAX_INTEGER_SIZE, MobilizeAmericaEvent, State


PRIORITIZATIONS_TAB = "prioritizations"

MA_EVENT_ID_COLUMN = "ma_event_id"
PRIORITIZATION_COLUMN = "prioritization"


class Command(BaseCommand):
    help = "Get the prioritizations from the state sheets"

    def handle(self, *args, **options):
        logging.info(f"Starting to update prioritizations")

        states_with_prioritization = State.objects.filter(
            use_prioritization_doc=True, prioritization_doc__isnull=False
        )

        google_sheets_client = GoogleSheetsClient(settings.GOOGLE_DOCS_CREDENTIALS)
        for state in states_with_prioritization:
            prioritizations = google_sheets_client.get_values_from_sheet(
                url=state.prioritization_doc,
                tab_name=PRIORITIZATIONS_TAB,
                columns=[MA_EVENT_ID_COLUMN, PRIORITIZATION_COLUMN],
            )

            for prioritization in prioritizations:
                event_id = prioritization[MA_EVENT_ID_COLUMN]
                state_prioritization_value = prioritization[PRIORITIZATION_COLUMN]

                if isinstance(event_id, int):
                    if (
                        isinstance(state_prioritization_value, str)
                        and state_prioritization_value.strip() == ""
                    ) or state_prioritization_value > 10:
                        state_prioritization_value = MAX_INTEGER_SIZE
                    event = MobilizeAmericaEvent.objects.filter(id=event_id).first()
                    if event:
                        event.state_prioritization = state_prioritization_value
                        event.save()

        return f"Priotized {states_with_prioritization.count()} states"
