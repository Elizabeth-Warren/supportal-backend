import unittest

import pytest

from supportal.shifter.management.commands.update_prioritization_meta import (
    PRIORITIZATION_DOC_URL_COLUMN_NAME,
    STATE_CODE_COLUMN_NAME,
    USE_PRIORITIZE_DOC_COLUMN_NAME,
    Command,
)
from supportal.shifter.models import State


@pytest.mark.django_db
def test_handle():
    hawaii_state = State.objects.create(state_code="HI")
    california_state = State.objects.create(state_code="CA")
    ri_state = State.objects.create(state_code="RI")

    with unittest.mock.patch(
        "supportal.shifter.management.commands.update_prioritization_meta.GoogleSheetsClient"
    ) as mock:
        mock.return_value.get_values_from_sheet.return_value = [
            {
                STATE_CODE_COLUMN_NAME: hawaii_state.state_code,
                USE_PRIORITIZE_DOC_COLUMN_NAME: "FALSE",
                PRIORITIZATION_DOC_URL_COLUMN_NAME: "woot",
            },
            {
                STATE_CODE_COLUMN_NAME: california_state.state_code,
                USE_PRIORITIZE_DOC_COLUMN_NAME: "TRUE",
                PRIORITIZATION_DOC_URL_COLUMN_NAME: "",
            },
            {
                STATE_CODE_COLUMN_NAME: ri_state.state_code,
                USE_PRIORITIZE_DOC_COLUMN_NAME: "TRUE",
                PRIORITIZATION_DOC_URL_COLUMN_NAME: "woot",
            },
        ]
        assert hawaii_state.use_prioritization_doc is False
        assert california_state.use_prioritization_doc is False
        assert ri_state.use_prioritization_doc is False

        Command().handle()

        hawaii_state.refresh_from_db()
        california_state.refresh_from_db()
        ri_state.refresh_from_db()

        assert hawaii_state.use_prioritization_doc is False
        assert california_state.use_prioritization_doc is False
        assert ri_state.use_prioritization_doc

        assert hawaii_state.prioritization_doc == "woot"
        assert california_state.prioritization_doc == ""
        assert ri_state.prioritization_doc == "woot"
