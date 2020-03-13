import json
from copy import deepcopy
from datetime import datetime, timedelta

import freezegun
import pytest
import responses
from model_bakery import baker

from supportal.services.mobilize_america import EVENT_TYPES
from supportal.shifter.management.commands.import_mobilize_america_events import Command
from supportal.shifter.models import MobilizeAmericaEvent
from supportal.tests.services.mock_mobilize_america_responses import (
    LIST_EVENTS_IA_GOTC_RESPONSE,
    LIST_EVENTS_RESPONSE,
    LIST_EVENTS_RESPONSE_PAGE_2,
)


def _add_event_type_response(visibility, list_events_response):
    responses.add(
        responses.GET,
        f"https://localhost:8000/mobilize/v1/organizations/1/events?visibility={visibility}&timeslot_start=gte_now",
        body=json.dumps(list_events_response),
        match_querystring=True,
    )


@pytest.mark.django_db
@responses.activate
def test_handle():
    assert MobilizeAmericaEvent.objects.count() == 0
    page2_url = "https://localhost:8000/mobilize/v1/organizations/1/events?page=2&visibility=PUBLIC&timeslot_start=gte_now&event_types=PHONE_BANK"
    list_events_response = deepcopy(LIST_EVENTS_RESPONSE)
    list_events_response["next"] = page2_url
    private_res = deepcopy(LIST_EVENTS_IA_GOTC_RESPONSE)
    private_res["data"] = [private_res["data"][0]]
    private_res["next"] = None
    private_res["count"] = 1
    private_res["data"][0]["visibility"] = "PRIVATE"
    _add_event_type_response("PUBLIC", list_events_response)
    responses.add(
        responses.GET,
        f"https://localhost:8000/mobilize/v1/organizations/1/events?page=2&visibility=PUBLIC&timeslot_start=gte_now&event_types=PHONE_BANK",
        body=json.dumps(LIST_EVENTS_RESPONSE_PAGE_2),
        match_querystring=True,
    )
    _add_event_type_response("PRIVATE", private_res)

    processed = Command().handle()
    events = list(MobilizeAmericaEvent.objects.all())
    total_events_count = (
        len(list_events_response["data"])
        + len(LIST_EVENTS_RESPONSE_PAGE_2["data"])
        + len(private_res["data"])
    )
    assert processed == f"Loaded events: {str(total_events_count)}"
    assert {e.id for e in events} == {9620, 172958, 175252, 179454, 173342}


@freezegun.freeze_time(datetime.now() + timedelta(days=1))
@pytest.mark.django_db
@responses.activate
def test_marks_old_events_as_inactive(cambridge_event):
    assert MobilizeAmericaEvent.objects.count() == 1
    assert cambridge_event.is_active
    list_events_response = deepcopy(LIST_EVENTS_RESPONSE)
    list_events_response["next"] = None
    _add_event_type_response("PUBLIC", list_events_response)
    _add_event_type_response("PRIVATE", list_events_response)

    processed = Command().handle()
    events = list(MobilizeAmericaEvent.objects.exclude(id=cambridge_event.id))
    assert {e.id for e in events} == {172958, 175252, 179454}
    for e in events:
        assert e.is_active
    cambridge_event.refresh_from_db()
    assert not cambridge_event.is_active


@freezegun.freeze_time(datetime.now() + timedelta(days=1))
@pytest.mark.django_db
@responses.activate
def test_marks_events_as_active(cambridge_event):
    assert MobilizeAmericaEvent.objects.count() == 1
    cambridge_event.is_active = False
    cambridge_event.save()

    list_events_response = deepcopy(LIST_EVENTS_RESPONSE)
    list_events_response["data"] = [list_events_response["data"][0]]
    list_events_response["data"][0]["id"] = cambridge_event.id
    list_events_response["next"] = None
    _add_event_type_response("PUBLIC", list_events_response)
    _add_event_type_response("PRIVATE", list_events_response)

    Command().handle()
    event = MobilizeAmericaEvent.objects.get(id=cambridge_event.id)
    assert event.is_active
