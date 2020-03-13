import os
import unittest

import pytest

from supportal.shifter.management.commands.update_prioritization import (
    MA_EVENT_ID_COLUMN,
    PRIORITIZATION_COLUMN,
    Command,
)
from supportal.shifter.models import MAX_INTEGER_SIZE, MobilizeAmericaEvent, State

TEST_FILE_PATH = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), "us_10_test_zip5s.csv.gz"
)


@pytest.mark.django_db
def test_handle(
    iowa_state, cambridge_event, virtual_phone_bank, high_pri_virtual_phone_bank
):
    with unittest.mock.patch(
        "supportal.shifter.management.commands.update_prioritization.GoogleSheetsClient"
    ) as mock:
        mock.return_value.get_values_from_sheet.return_value = [
            {MA_EVENT_ID_COLUMN: cambridge_event.id, PRIORITIZATION_COLUMN: ""},
            {MA_EVENT_ID_COLUMN: 123, PRIORITIZATION_COLUMN: ""},
            {MA_EVENT_ID_COLUMN: virtual_phone_bank.id, PRIORITIZATION_COLUMN: 11},
            {
                MA_EVENT_ID_COLUMN: high_pri_virtual_phone_bank.id,
                PRIORITIZATION_COLUMN: 5,
            },
        ]
        assert cambridge_event.state_prioritization == MAX_INTEGER_SIZE
        assert virtual_phone_bank.state_prioritization == MAX_INTEGER_SIZE
        assert high_pri_virtual_phone_bank.state_prioritization == MAX_INTEGER_SIZE

        Command().handle()

        cambridge_event.refresh_from_db()
        virtual_phone_bank.refresh_from_db()
        high_pri_virtual_phone_bank.refresh_from_db()

        assert cambridge_event.state_prioritization == MAX_INTEGER_SIZE
        assert virtual_phone_bank.state_prioritization == MAX_INTEGER_SIZE
        assert high_pri_virtual_phone_bank.state_prioritization == 5
