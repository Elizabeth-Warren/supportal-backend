import json
import time
from copy import deepcopy
from datetime import datetime, timezone

import pytest
import responses
from django.contrib.gis.geos import Point

from supportal.shifter.models import (
    EventSignup,
    MobilizeAmericaEvent,
    RecommendedEventRequestLog,
)
from supportal.tests.services.mock_mobilize_america_responses import (
    CREATE_ATTENDANCE_RESPONSE,
    LIST_EVENTS_RESPONSE,
)


@responses.activate
@pytest.mark.django_db
def test_create_event_signup_and_sync():
    responses.add(
        responses.POST,
        "https://localhost:8000/mobilize/v1/organizations/1/events/17/attendances",
        body=json.dumps(CREATE_ATTENDANCE_RESPONSE),
    )
    responses.add(
        responses.GET,
        f"https://localhost:8000/mobilize/v1/organizations/1/events/17/attendances",
        body=json.dumps({"data": []}),
    ),

    es = EventSignup(
        session_id="some-random-identifier",
        email="@elizabethwarren.com",
        given_name="",
        family_name="",
        sms_opt_in=False,
        zip5="11238",
        metadata={"foo": "bar"},
        source="web",
        ma_event_id=17,
        ma_timeslot_ids=[1, 2, 3],
    )
    es.save()
    assert es.id is not None
    assert not es.ma_creation_successful
    assert not es.ma_response
    assert len(responses.calls) == 0

    es.sync_to_mobilize_america()
    assert len(responses.calls) == 2
    assert es.ma_creation_successful
    assert es.ma_response == CREATE_ATTENDANCE_RESPONSE


@pytest.mark.django_db
def test_create_event_recommendation_log():
    log = RecommendedEventRequestLog(
        session_id="fadkfksdmf",
        email="@elizabethwarren.com",
        request_params={"zip5": "11238", "max_dist": 5},
        recommended_ma_event_ids=[17],
    )
    log.save()
    assert log.id is not None


def __same_ts(dt, ts):
    return dt == datetime.fromtimestamp(ts, timezone.utc)


def __check_timeslot(ma_event_id, payload, timeslot):
    assert timeslot.event_id == ma_event_id
    assert __same_ts(timeslot.start_date, payload["start_date"])
    assert __same_ts(timeslot.end_date, payload["end_date"])
    assert timeslot.is_full == payload["is_full"]
    assert timeslot.raw == payload


def __check_ma_event_matches_payload(
    ma_event, payload, virtual_expected, state_expected
):
    assert ma_event.id == payload["id"]
    assert ma_event.title == payload["title"]
    assert ma_event.event_type == payload["event_type"]
    assert ma_event.visibility == payload["visibility"]
    assert __same_ts(ma_event.modified_date, payload["modified_date"])
    assert ma_event.raw == payload
    assert ma_event.tag_ids == [t["id"] for t in payload["tags"]]
    timeslot_payloads = {d["id"]: d for d in payload["timeslots"]}
    for ts in ma_event.timeslots.all():
        assert ts.id in timeslot_payloads
        __check_timeslot(ma_event.id, timeslot_payloads[ts.id], ts)
    if virtual_expected:
        assert ma_event.is_virtual
        assert ma_event.coordinates is None
    else:
        assert not ma_event.is_virtual
        lat = payload["location"]["location"]["latitude"]
        lng = payload["location"]["location"]["longitude"]
        assert ma_event.coordinates == Point(lng, lat, srid=4326)
        assert state_expected == ma_event.state.state_code


@pytest.mark.django_db
def test_update_and_create_mobilize_america_event_from_json(ca_zip5):
    payload = deepcopy(LIST_EVENTS_RESPONSE["data"][0])
    payload["location"]["region"] = ca_zip5.state
    assert not MobilizeAmericaEvent.objects.filter(id=payload["id"]).exists()
    ma_event, created = MobilizeAmericaEvent.objects.update_or_create_from_json(payload)
    assert created
    __check_ma_event_matches_payload(
        ma_event, payload, virtual_expected=False, state_expected=ca_zip5.state
    )
    # test update
    del payload["location"]
    payload["title"] = "Changed title"
    ma_event, created = MobilizeAmericaEvent.objects.update_or_create_from_json(payload)
    assert not created
    __check_ma_event_matches_payload(
        ma_event, payload, virtual_expected=True, state_expected=None
    )


@pytest.mark.django_db
def test_create_update_delete_timeslot():
    payload = deepcopy(LIST_EVENTS_RESPONSE["data"][0])
    ma_event, _ = MobilizeAmericaEvent.objects.update_or_create_from_json(payload)
    created_timeslot_id = 123456789
    payload["timeslots"].append(
        {
            "id": created_timeslot_id,
            "start_date": 123,
            "end_date": int(time.time()),
            "is_full": False,
        }
    )
    assert not ma_event.timeslots.filter(id=created_timeslot_id).exists()
    ma_event, _ = MobilizeAmericaEvent.objects.update_or_create_from_json(payload)
    assert ma_event.timeslots.filter(id=created_timeslot_id).exists()

    deleted_timeslot_id = payload["timeslots"].pop()["id"]
    assert ma_event.timeslots.filter(id=deleted_timeslot_id).exists()
    ma_event, _ = MobilizeAmericaEvent.objects.update_or_create_from_json(payload)
    assert not ma_event.timeslots.filter(id=deleted_timeslot_id).exists()

    new_start_date = 1
    updated_timeslot_id = payload["timeslots"][0]["id"]
    payload["timeslots"][0]["start_date"] = new_start_date
    ts = ma_event.timeslots.filter(id=updated_timeslot_id).first()
    assert not __same_ts(ts.start_date, new_start_date)
    ma_event, _ = MobilizeAmericaEvent.objects.update_or_create_from_json(payload)
    ts = ma_event.timeslots.filter(id=updated_timeslot_id).first()
    assert __same_ts(ts.start_date, new_start_date)
