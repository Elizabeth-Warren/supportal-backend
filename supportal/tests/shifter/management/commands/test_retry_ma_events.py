import unittest

import pytest
from localflavor.us.models import USZipCodeField
from model_bakery import baker

from supportal.shifter.management.commands.retry_ma_events import Command
from supportal.shifter.models import EventSignup


@pytest.mark.django_db
def test_retry_ma_events():
    event_1 = baker.make("EventSignup", zip5="94102", ma_creation_successful=False)
    event_2 = baker.make("EventSignup", zip5="94102", ma_creation_successful=True)

    with unittest.mock.patch.object(
        EventSignup, "sync_to_mobilize_america", return_value=(True, None)
    ):
        Command().handle()

    event_1.refresh_from_db()
    event_2.refresh_from_db()

    assert event_1.retried_at is not None
    assert event_2.retried_at is None
