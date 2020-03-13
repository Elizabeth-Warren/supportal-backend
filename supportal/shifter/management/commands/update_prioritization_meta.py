import logging

from django.conf import settings
from django.core.management import BaseCommand

from supportal.services.google_sheets_service import GoogleSheetsClient
from supportal.shifter.models import MobilizeAmericaEvent, State

STATE_CODE_COLUMN_NAME = "STATE"
USE_PRIORITIZE_DOC_COLUMN_NAME = "USE_DOC"
PRIORITIZATION_DOC_URL_COLUMN_NAME = "PRIORITIZATION_DOC"
PRIORITIZATIONS_TAB = "National Prioritizations"


class Command(BaseCommand):
    help = "Get the prioritization meta data from the national doc"

    def handle(self, *args, **options):
        logging.info(f"Starting to update prioritizations")

        google_sheets_client = GoogleSheetsClient(settings.GOOGLE_DOCS_CREDENTIALS)
        state_metas = google_sheets_client.get_values_from_sheet(
            url=settings.PRIORITIZATION_META,
            tab_name=PRIORITIZATIONS_TAB,
            columns=[
                STATE_CODE_COLUMN_NAME,
                USE_PRIORITIZE_DOC_COLUMN_NAME,
                PRIORITIZATION_DOC_URL_COLUMN_NAME,
            ],
        )
        for state_meta in state_metas:
            state_code = state_meta[STATE_CODE_COLUMN_NAME]
            should_use_doc = state_meta[USE_PRIORITIZE_DOC_COLUMN_NAME] == "TRUE"
            doc_url = state_meta[PRIORITIZATION_DOC_URL_COLUMN_NAME]
            if state_code and doc_url:
                State.objects.filter(state_code=state_code).update(
                    use_prioritization_doc=should_use_doc, prioritization_doc=doc_url
                )

        return f"Updated {len(state_metas)} metas"
