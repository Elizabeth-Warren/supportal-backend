import datetime
import json
from copy import deepcopy

import pytest
import responses
from django.conf import settings
from django.utils import timezone
from model_bakery import baker

from supportal.services.mobilize_america import PRIVATE_VISIBILITY, PUBLIC_VISIBILITY
from supportal.shifter.common.error_codes import ErrorCodes
from supportal.shifter.models import EventSignup, MobilizeAmericaEvent, State
from supportal.tests.services.mock_mobilize_america_responses import (
    CREATE_ATTENDANCE_RESPONSE,
    LIST_EVENTS_IA_GOTC_RESPONSE,
    LIST_EVENTS_INVALID_ZIP_RESPONSE,
    LIST_EVENTS_RESPONSE,
    PRIVATE_ADDRESS_EVENT,
)


def _event_signup_payload(session_id=None, event_id=17, timeslot_ids=[1, 2, 3]):
    payload = {
        "email": "mbanerjee@elizabethwarren.com",
        "given_name": "",
        "family_name": "",
        "sms_opt_in": False,
        "zip5": "11238",
        "ma_event_id": event_id,
        "ma_timeslot_ids": timeslot_ids,
        "heap_id": "123abc",
    }
    if session_id:
        payload["session_id"] = session_id
    return payload


def _setup_event_attendance_mocks(
    get_event_response_body=None,
    post_response_status=201,
    post_response_body=None,
    attendance_get_body=None,
    event_id=17,
    event_visibility=PUBLIC_VISIBILITY,
):
    baker.make(
        "MobilizeAmericaEvent",
        id=event_id,
        raw={},
        title="Test",
        visibility=event_visibility,
    )
    responses.add(
        responses.GET,
        f"https://localhost:8000/mobilize/v1/organizations/1/events/{event_id}",
        body=json.dumps(
            {"data": get_event_response_body or LIST_EVENTS_RESPONSE["data"][0]}
        ),
    )
    responses.add(
        responses.GET,
        f"https://localhost:8000/mobilize/v1/organizations/1/events/{event_id}/attendances",
        body=json.dumps(attendance_get_body or {"data": []}),
    )

    if post_response_status != 500:
        responses.add(
            responses.POST,
            f"https://localhost:8000/mobilize/v1/organizations/1/events/{event_id}/attendances",
            body=json.dumps(post_response_body or CREATE_ATTENDANCE_RESPONSE),
            status=post_response_status,
        )
    else:
        responses.add(
            responses.POST,
            f"https://localhost:8000/mobilize/v1/organizations/1/events/{event_id}/attendances",
            body=post_response_body,
            status=post_response_status,
        )


@pytest.mark.django_db
@responses.activate
def test_post_event_signup(api_client):
    _setup_event_attendance_mocks(event_id=17)
    res = api_client.post(
        "/v1/shifter/event_signups", data=_event_signup_payload("abcdef", event_id=17)
    )
    assert res.status_code == 201
    assert res.data["ma_response"]["data"] == CREATE_ATTENDANCE_RESPONSE["data"]
    assert EventSignup.objects.filter(session_id="abcdef").exists()
    assert EventSignup.objects.get(session_id="abcdef").heap_id


@pytest.mark.django_db
@responses.activate
def test_post_event_signup_invalid_data(api_client):
    _setup_event_attendance_mocks(event_id=17)
    res = api_client.post("/v1/shifter/event_signups", data={})
    assert res.status_code == 400
    assert res.data["code"] == ErrorCodes.VALIDATION.name


@pytest.mark.django_db
@responses.activate
def test_post_event_signup_already_signed_up(api_client):
    event_id = 113
    email = "mbanerjee@elizabethwarren.com"
    _setup_event_attendance_mocks(
        attendance_get_body=CREATE_ATTENDANCE_RESPONSE, event_id=event_id
    )
    timeslot_id = CREATE_ATTENDANCE_RESPONSE["data"][0]["timeslot"]["id"]
    res = api_client.post(
        "/v1/shifter/event_signups",
        data=_event_signup_payload(
            "abc", event_id=event_id, timeslot_ids=[timeslot_id]
        ),
    )
    assert res.status_code == 201
    assert res.data["ma_response"]["data"] == [CREATE_ATTENDANCE_RESPONSE["data"][0]]
    event = EventSignup.objects.filter(email=email, ma_event_id=event_id)
    assert event.count() == 1
    assert event.first().signed_up_via_shifter == []


@pytest.mark.django_db
@responses.activate
def test_post_event_signup_for_private_event_fails(api_client):
    event_id = 19
    private_event = deepcopy(LIST_EVENTS_RESPONSE["data"][0])
    private_event["visibility"] = PRIVATE_VISIBILITY
    _setup_event_attendance_mocks(
        get_event_response_body=private_event,
        event_id=event_id,
        event_visibility=PRIVATE_VISIBILITY,
    )
    res = api_client.post(
        "/v1/shifter/event_signups", data=_event_signup_payload(event_id=event_id)
    )
    assert res.status_code == 404


@pytest.mark.django_db
@responses.activate
def test_post_event_signup_no_email_or_phone(api_client):
    payload = {
        "given_name": "",
        "family_name": "",
        "sms_opt_in": False,
        "ma_event_id": 1,
        "ma_timeslot_ids": [1],
    }

    res = api_client.post("/v1/shifter/event_signups", data=payload)
    assert res.status_code == 400
    assert res.data["code"] == ErrorCodes.VALIDATION.name


@pytest.mark.django_db
@responses.activate
def test_post_event_signup_no_email_with_phone(api_client, cambridge_event):
    payload = {
        "given_name": "M",
        "family_name": "",
        "sms_opt_in": False,
        "ma_event_id": cambridge_event.id,
        "ma_timeslot_ids": [1],
        "phone": "+1",
    }

    res = api_client.post("/v1/shifter/event_signups", data=payload)

    assert res.status_code == 201
    event_signup = EventSignup.objects.get(ma_event_id=cambridge_event.id)
    assert event_signup.ma_creation_successful is False


@pytest.mark.django_db
@responses.activate
def test_post_event_signup_no_email_no_phone_with_zip5(api_client, cambridge_event):
    payload = {
        "given_name": "M",
        "family_name": "",
        "sms_opt_in": False,
        "ma_event_id": cambridge_event.id,
        "ma_timeslot_ids": [1],
        "zip5": "02145",
    }

    res = api_client.post("/v1/shifter/event_signups", data=payload)

    assert res.status_code == 201
    event_signup = EventSignup.objects.get(ma_event_id=cambridge_event.id)
    assert event_signup.ma_creation_successful is False


@pytest.mark.django_db
@responses.activate
def test_post_event_signup_ma_sync_failure(api_client):
    event_id = 20
    original_error = {"detail": "Not found."}
    _setup_event_attendance_mocks(
        post_response_body={"error": original_error},
        post_response_status=404,
        event_id=event_id,
    )
    res = api_client.post(
        "/v1/shifter/event_signups", data=_event_signup_payload(event_id=event_id)
    )
    assert res.status_code == 404
    assert res.data["code"] == ErrorCodes.NOT_FOUND.name
    assert res.data["detail"] == "Not found."


@pytest.mark.django_db
@responses.activate
def test_post_event_signup_ma_sync_zip_failure(api_client):
    event_id = 20
    original_error = {
        "person": {"postal_code": ["111 does not appear to be a valid U.S. zipcode."]}
    }
    _setup_event_attendance_mocks(
        post_response_body={"error": original_error},
        post_response_status=400,
        event_id=event_id,
    )
    res = api_client.post(
        "/v1/shifter/event_signups", data=_event_signup_payload(event_id=event_id)
    )
    assert res.status_code == 400
    assert res.data["code"] == ErrorCodes.VALIDATION.name
    assert res.data["detail"] == {"zip5": ["The zip entered is not valid."]}


@pytest.mark.django_db
@responses.activate
def test_post_event_signup_ma_sync_failure_500(api_client):
    event_id = 20
    _setup_event_attendance_mocks(
        post_response_body="<html>MobilizeErrorslikethisfor500s</html>",
        post_response_status=500,
        event_id=event_id,
    )
    res = api_client.post(
        "/v1/shifter/event_signups", data=_event_signup_payload(event_id=event_id)
    )
    assert res.status_code == 201
    assert not res.data["ma_creation_successful"]


@pytest.mark.django_db
@responses.activate
def test_post_event_signup_ma_sync_failure_429(api_client):
    event_id = 20
    _setup_event_attendance_mocks(
        post_response_body={"error": {"detail": "Can't reach server."}},
        post_response_status=429,
        event_id=event_id,
    )
    res = api_client.post(
        "/v1/shifter/event_signups", data=_event_signup_payload(event_id=event_id)
    )
    assert res.status_code == 201
    assert not res.data["ma_creation_successful"]


@pytest.mark.django_db
def test_cannot_get_signups(api_client, cambridge_event_signup):
    res = api_client.get(f"/v1/shifter/event_signups/{cambridge_event_signup.id}")
    assert res.status_code == 404


@pytest.mark.django_db
@responses.activate
def test_get_event_goes_to_ma(api_client):
    responses.add(
        responses.GET,
        "https://localhost:8000/mobilize/v1/organizations/1/events/17",
        body=json.dumps({"data": LIST_EVENTS_RESPONSE["data"][0]}),
    )

    res = api_client.get(f"/v1/shifter/events/17")
    assert res.status_code == 200
    assert res.data["id"] == LIST_EVENTS_RESPONSE["data"][0]["id"]
    assert (
        res.data["timeslots"][0]["id"]
        == LIST_EVENTS_RESPONSE["data"][0]["timeslots"][0]["id"]
    )


@pytest.mark.django_db
@responses.activate
def test_cannot_get_inactive_event(api_client, cambridge_event):
    responses.add(
        responses.GET,
        f"https://localhost:8000/mobilize/v1/organizations/1/events/{cambridge_event.id}",
        body=json.dumps({"error": {"detail": "Not found."}}),
        status=404,
    )

    cambridge_event.is_active = False
    cambridge_event.save()

    res = api_client.get(f"/v1/shifter/events/{cambridge_event.id}")
    assert res.status_code == 404


@pytest.mark.django_db
@responses.activate
def test_get_event_goes_to_ma_and404s(api_client):
    responses.add(
        responses.GET,
        "https://localhost:8000/mobilize/v1/organizations/1/events/17",
        body=json.dumps({"error": {"detail": "Not found."}}),
        status=404,
    )

    res = api_client.get(f"/v1/shifter/events/17")
    assert res.status_code == 404
    assert res.data["detail"] == "Not found."


@pytest.mark.django_db
def test_get_event_invalid_data(api_client):
    res = api_client.get(f"/v1/shifter/events/badid")
    assert res.status_code == 400


@pytest.mark.django_db
def test_get_event(api_client, cambridge_event):
    cambridge_event.raw = LIST_EVENTS_RESPONSE["data"][0]
    cambridge_event.save()
    start_date = datetime.datetime(2019, 9, 12, 15, 0, 0, tzinfo=timezone.utc)
    end_date = datetime.datetime(2019, 9, 12, 16, 0, 0, tzinfo=timezone.utc)
    cambridge_event_timeslot = baker.make(
        "MobilizeAmericaTimeslot",
        event=cambridge_event,
        start_date=start_date,
        end_date=end_date,
    )

    res = api_client.get(f"/v1/shifter/events/{cambridge_event.id}")
    assert res.status_code == 200
    assert res.data["id"] == LIST_EVENTS_RESPONSE["data"][0]["id"]
    assert (
        res.data["timeslots"][0]["id"]
        == LIST_EVENTS_RESPONSE["data"][0]["timeslots"][0]["id"]
    )


@pytest.mark.django_db
def test_get_event_private_address(api_client, cambridge_event):
    cambridge_event.raw = PRIVATE_ADDRESS_EVENT["data"][0]
    cambridge_event.save()
    start_date = datetime.datetime(2019, 9, 12, 15, 0, 0, tzinfo=timezone.utc)
    end_date = datetime.datetime(2019, 9, 12, 16, 0, 0, tzinfo=timezone.utc)
    cambridge_event_timeslot = baker.make(
        "MobilizeAmericaTimeslot",
        event=cambridge_event,
        start_date=start_date,
        end_date=end_date,
    )

    res = api_client.get(f"/v1/shifter/events/{cambridge_event.id}")
    assert res.status_code == 200
    assert res.data["location"]["location"]["latitude"] == 37.786
    assert res.data["location"]["location"]["longitude"] == -122.4373


def check_results_ia_gotc_result(res):
    assert res.status_code == 200
    assert res.data["count"] == 1
    assert len(res.data["data"]) == 1
    e = res.data["data"][0]
    assert e["title"] == "West Des Moines (Dallas County) Weekend of Action Canvass"
    assert (
        e["browser_url"]
        == "https://events.elizabethwarren.com/event/173342/?utm_source=SMS"
    )
    assert (
        e["times_synopsis"]
        == "9AM, 12PM, 3PM, or 6PM on Sat Jan 11; or 12PM, 3PM, or 6PM on Sun Jan 12"
    )
    if e["timeslots"]:
        assert e["timeslots"][0]["local_start_time"] == "2020-01-11T09:00:00"


@pytest.mark.django_db
@responses.activate
def test_get_ia_gotc_event_recommendations(api_client):
    """Tests the single-event-near-zip-code case.

    As would be used for Mobile Commons mdata, for example.
    """
    responses.add(
        responses.GET,
        "https://localhost:8000/mobilize/v1/organizations/1/events?visibility=PUBLIC&timeslot_start=gte_now&tag_id=34&tag_id=35&event_types=CANVASS&zipcode=11238&max_dist=50",
        json=LIST_EVENTS_IA_GOTC_RESPONSE,
    )
    # check backwards compatibility with previous format
    check_results_ia_gotc_result(
        api_client.get(
            "/v1/shifter/recommended_events?zip5=11238&event_types=CANVASS&tag_id=34,35&max_dist=50&utm_source=SMS&limit=1&strategy=mobilize_america"
        )
    )
    # new format
    check_results_ia_gotc_result(
        api_client.get(
            "/v1/shifter/recommended_events?zip5=11238&event_types=CANVASS&tag_ids=34,35&max_dist=50&utm_source=SMS&limit=1&strategy=mobilize_america"
        )
    )


@pytest.mark.django_db
@responses.activate
def test_non_zip(api_client):
    """Tests search with invalid zip code that fails our zip validation"""
    res = api_client.get(
        "/v1/shifter/recommended_events?zip5=hopeoverfear&event_types=CANVASS&tag_ids=34,35&max_dist=50&utm_source=SMS&limit=1&strategy=mobilize_america"
    )
    assert res.status_code == 400
    assert res.data["code"] == "BAD_REQUEST"


@pytest.mark.django_db
@responses.activate
def test_invalid_zip(api_client):
    """Tests search with invalid zip code that fails Mobilize America's zip validation"""
    responses.add(
        responses.GET,
        "https://localhost:8000/mobilize/v1/organizations/1/events?visibility=PUBLIC&timeslot_start=gte_now&tag_id=34&tag_id=35&event_types=CANVASS&zipcode=00000&max_dist=50",
        json=LIST_EVENTS_INVALID_ZIP_RESPONSE,
        status=400,
    )

    res = api_client.get(
        "/v1/shifter/recommended_events?zip5=00000&event_types=CANVASS&tag_ids=34,35&max_dist=50&utm_source=SMS&limit=1&strategy=mobilize_america"
    )
    assert res.status_code == 400
    assert res.data["code"] == ErrorCodes.VALIDATION.name


@pytest.mark.django_db
def test_get_ia_gotc_event_recommendations_high_limit(
    api_client, cambridge_event, ma_zip5
):
    """Tests the single-event-near-zip-code case.

    As would be used for Mobile Commons mdata, for example.
    """
    event_json = deepcopy(LIST_EVENTS_IA_GOTC_RESPONSE["data"][0])
    event_json["id"] = cambridge_event.id
    MobilizeAmericaEvent.objects.update_or_create_from_json(event_json)

    start_date = datetime.datetime(2029, 9, 12, 15, 0, 0, tzinfo=timezone.utc)
    end_date = datetime.datetime(2029, 9, 12, 16, 0, 0, tzinfo=timezone.utc)

    cambridge_event_timeslot = baker.make(
        "MobilizeAmericaTimeslot",
        event=cambridge_event,
        start_date=start_date,
        end_date=end_date,
    )

    cambridge_event_timeslot2 = baker.make(
        "MobilizeAmericaTimeslot",
        event=cambridge_event,
        start_date=start_date,
        end_date=end_date,
    )

    res = api_client.get(
        f"/v1/shifter/recommended_events?zip5={ma_zip5}&limit=20&strategy=shifter_engine"
    )
    assert res.data["count"] == 1
    assert len(res.data["data"]) == 1
    assert res.data["data"][0]["id"] == cambridge_event.id


@pytest.mark.django_db
def test_get_event_recommendations_no_show_full_timeslots(
    api_client, cambridge_event, ma_zip5
):
    """Tests the single-event-near-zip-code case.

    As would be used for Mobile Commons mdata, for example.
    """
    event_json = deepcopy(LIST_EVENTS_IA_GOTC_RESPONSE["data"][0])
    event_json["id"] = cambridge_event.id
    event_json["timeslots"][0]["is_full"] = True
    MobilizeAmericaEvent.objects.update_or_create_from_json(event_json)

    start_date = datetime.datetime(2029, 9, 12, 15, 0, 0, tzinfo=timezone.utc)
    end_date = datetime.datetime(2029, 9, 12, 16, 0, 0, tzinfo=timezone.utc)

    cambridge_event_timeslot = baker.make(
        "MobilizeAmericaTimeslot",
        event=cambridge_event,
        start_date=start_date,
        end_date=end_date,
    )

    cambridge_event_timeslot2 = baker.make(
        "MobilizeAmericaTimeslot",
        event=cambridge_event,
        start_date=start_date,
        end_date=end_date,
    )

    res = api_client.get(
        f"/v1/shifter/recommended_events?zip5={ma_zip5}&limit=20&strategy=shifter_engine"
    )
    assert res.data["count"] == 1
    assert len(res.data["data"]) == 1
    assert res.data["data"][0]["id"] == cambridge_event.id
    assert event_json["timeslots"][0]["id"] not in list(
        map(lambda x: x["id"], res.data["data"][0]["timeslots"])
    )


@pytest.mark.django_db
def test_get_event_recommendations_does_not_return_full_timeslots(
    api_client, cambridge_event, ma_zip5
):
    """Tests the single-event-near-zip-code case.

    As would be used for Mobile Commons mdata, for example.
    """
    event_json = deepcopy(LIST_EVENTS_IA_GOTC_RESPONSE["data"][0])
    event_json["id"] = cambridge_event.id
    event_json["timeslots"][0]["is_full"] = True
    event_json["timeslots"] = [event_json["timeslots"][0]]
    MobilizeAmericaEvent.objects.update_or_create_from_json(event_json)

    start_date = datetime.datetime(2029, 9, 12, 15, 0, 0, tzinfo=timezone.utc)
    end_date = datetime.datetime(2029, 9, 12, 16, 0, 0, tzinfo=timezone.utc)

    cambridge_event_timeslot = baker.make(
        "MobilizeAmericaTimeslot",
        event=cambridge_event,
        start_date=start_date,
        end_date=end_date,
    )

    cambridge_event_timeslot2 = baker.make(
        "MobilizeAmericaTimeslot",
        event=cambridge_event,
        start_date=start_date,
        end_date=end_date,
    )

    res = api_client.get(
        f"/v1/shifter/recommended_events?zip5={ma_zip5}&limit=20&strategy=shifter_engine"
    )
    assert res.data["count"] == 0
    assert len(res.data["data"]) == 0


@pytest.mark.django_db
def test_get_event_recommendations_filter_timeslots(
    api_client, cambridge_event, ma_zip5
):
    """Tests the single-event-near-zip-code case.

    As would be used for Mobile Commons mdata, for example.
    """
    event_json = deepcopy(LIST_EVENTS_IA_GOTC_RESPONSE["data"][0])
    event_json["id"] = cambridge_event.id
    start_date = datetime.datetime(2029, 9, 12, 15, 0, 0, tzinfo=timezone.utc)
    end_date = datetime.datetime(2029, 9, 12, 20, 0, 0, tzinfo=timezone.utc)

    event_json["timeslots"][0]["start_date"] = (
        start_date + datetime.timedelta(hours=1)
    ).timestamp()
    event_json["timeslots"][1]["start_date"] = (
        start_date - datetime.timedelta(hours=1)
    ).timestamp()
    MobilizeAmericaEvent.objects.update_or_create_from_json(event_json)

    cambridge_event_timeslot = baker.make(
        "MobilizeAmericaTimeslot",
        event=cambridge_event,
        start_date=start_date + datetime.timedelta(days=1),
        end_date=end_date + datetime.timedelta(days=1),
    )

    cambridge_event_timeslot2 = baker.make(
        "MobilizeAmericaTimeslot",
        event=cambridge_event,
        start_date=start_date + datetime.timedelta(days=1),
        end_date=end_date + datetime.timedelta(days=1),
    )
    res = api_client.get(
        f"/v1/shifter/recommended_events?zip5={ma_zip5}&limit=20&strategy=shifter_engine&timeslot_start={start_date.strftime('%Y-%m-%dT%H:%M:%S')}"
    )
    assert res.data["count"] == 1
    assert len(res.data["data"]) == 1
    assert event_json["timeslots"][0]["id"] in list(
        map(lambda x: x["id"], res.data["data"][0]["timeslots"])
    )
    assert event_json["timeslots"][1]["id"] not in list(
        map(lambda x: x["id"], res.data["data"][0]["timeslots"])
    )


@pytest.mark.django_db
def test_get_event_recommendations_inactive(api_client, cambridge_event, ma_zip5):
    """ Shouldn't return inactive events
    """
    event_json = deepcopy(LIST_EVENTS_IA_GOTC_RESPONSE["data"][0])
    event_json["id"] = cambridge_event.id
    MobilizeAmericaEvent.objects.update_or_create_from_json(event_json)

    start_date = datetime.datetime(2029, 9, 12, 15, 0, 0, tzinfo=timezone.utc)
    end_date = datetime.datetime(2029, 9, 12, 16, 0, 0, tzinfo=timezone.utc)

    cambridge_event_timeslot = baker.make(
        "MobilizeAmericaTimeslot",
        event=cambridge_event,
        start_date=start_date,
        end_date=end_date,
    )

    cambridge_event_timeslot2 = baker.make(
        "MobilizeAmericaTimeslot",
        event=cambridge_event,
        start_date=start_date,
        end_date=end_date,
    )

    cambridge_event.is_active = False
    cambridge_event.save()

    res = api_client.get(
        f"/v1/shifter/recommended_events?zip5={ma_zip5}&limit=20&strategy=shifter_engine"
    )
    assert res.data["count"] == 0
    assert len(res.data["data"]) == 0


@pytest.mark.django_db
def test_get_ia_gotc_event_recommendations_prio(api_client, cambridge_event, ia_zip5):
    """Tests the single-event-near-zip-code case.

    As would be used for Mobile Commons mdata, for example.
    """
    state = State.objects.create(
        state_code="HI", use_prioritization_doc=True, prioritization_doc="woot"
    )
    for i, event_json in enumerate(LIST_EVENTS_IA_GOTC_RESPONSE["data"]):
        event, created = MobilizeAmericaEvent.objects.update_or_create_from_json(
            event_json
        )
        event.state = state
        event.state_prioritization = 3 - i  # just to mix it up
        event.save()
        start_date = datetime.datetime(2029, 9, 12, 15, 0, 0, tzinfo=timezone.utc)
        end_date = datetime.datetime(2029, 9, 12, 16, 0, 0, tzinfo=timezone.utc)
        final_event = event
        cambridge_event_timeslot = baker.make(
            "MobilizeAmericaTimeslot",
            event=event,
            start_date=start_date,
            end_date=end_date,
        )

        cambridge_event_timeslot2 = baker.make(
            "MobilizeAmericaTimeslot",
            event=event,
            start_date=start_date,
            end_date=end_date,
        )

    res = api_client.get(
        f"/v1/shifter/recommended_events?zip5={ia_zip5.zip5}&event_types=CANVASS&states={final_event.state.state_code}&limit=3&strategy=shifter_engine"
    )
    assert res.data["count"] == 3
    assert len(res.data["data"]) == 3
    assert res.data["data"][0]["id"] == LIST_EVENTS_IA_GOTC_RESPONSE["data"][2]["id"]
    assert res.data["data"][1]["id"] == LIST_EVENTS_IA_GOTC_RESPONSE["data"][1]["id"]
    assert res.data["data"][2]["id"] == LIST_EVENTS_IA_GOTC_RESPONSE["data"][0]["id"]


@pytest.mark.django_db
@responses.activate
def test_passing_timeslot_start_to_ma(api_client):
    """Tests the single-event-near-zip-code case.

    As would be used for Mobile Commons mdata, for example.
    """
    responses.add(
        responses.GET,
        "https://localhost:8000/mobilize/v1/organizations/1/events?visibility=PUBLIC&timeslot_start=gte_1577836801&event_types=CANVASS&timeslot_end=lte_1578787201&zipcode=11238",
        json=LIST_EVENTS_IA_GOTC_RESPONSE,
    )
    check_results_ia_gotc_result(
        api_client.get(
            "/v1/shifter/recommended_events?zip5=11238&event_types=CANVASS&limit=1&timeslot_start=2020-01-01T00:00:01Z&timeslot_end=2020-01-12T00:00:01Z&utm_source=SMS&strategy=mobilize_america"
        )
    )


@pytest.mark.django_db
def test_get_ia_gotc_event_recommendation_db_strategy(api_client, ia_zip5):
    for event_json in LIST_EVENTS_IA_GOTC_RESPONSE["data"]:
        MobilizeAmericaEvent.objects.update_or_create_from_json(event_json)

    check_results_ia_gotc_result(
        api_client.get(
            f"/v1/shifter/recommended_events?zip5={ia_zip5.zip5}&event_types=CANVASS&tag_ids=34,35&max_dist=500&utm_source=SMS&limit=1&timeslot_start=2020-01-01T00:00:01Z&strategy=shifter_engine"
        )
    )


@pytest.mark.django_db
def test_zip5_validation(api_client):
    res = api_client.get(
        f"/v1/shifter/recommended_events?event_types=CANVASS&strategy=shifter_engine"
    )
    assert res.status_code == 400
    assert "'zip5' is required for non-virtual events" in str(res.data)
    res = api_client.get(
        f"/v1/shifter/recommended_events?event_types=PHONE_BANK&is_virtual=True&strategy=shifter_engine"
    )
    assert res.status_code == 200


@pytest.mark.django_db
def test_zip5_validation_length(api_client):
    res = api_client.get(
        f"/v1/shifter/recommended_events?event_types=PHONE_BANK&zip5=123456&strategy=shifter_engine"
    )
    assert res.status_code == 400
    assert res.data["detail"]["zip5"][0] == "The zip entered is not valid."


@pytest.mark.django_db
def test_db_virtual_event_recommendations(
    api_client, virtual_phone_bank, high_pri_virtual_phone_bank
):
    res = api_client.get(
        f"/v1/shifter/recommended_events?event_types=PHONE_BANK&is_virtual=True&limit=2&strategy=shifter_engine"
    )
    assert res.status_code == 200
    assert res.data["count"] == 2
    assert res.data["data"][0]["id"] == high_pri_virtual_phone_bank.id
    assert res.data["data"][1]["id"] == virtual_phone_bank.id


@pytest.mark.django_db
def test_early_states(api_client, ia_zip5, nh_zip5, nv_zip5, sc_zip5, ma_zip5, ca_zip5):
    ca_res = api_client.get(f"/v1/shifter/early_states?zip5={ca_zip5.zip5}")
    assert ca_res.status_code == 200

    assert ca_res.data == {
        "count": 4,
        "data": [
            {"min_distance": 431, "state": "NV"},
            {"min_distance": 1659, "state": "IA"},
            {"min_distance": 2403, "state": "SC"},
            {"min_distance": 2679, "state": "NH"},
        ],
    }

    # No early state within 100 miles
    ca_res = api_client.get(
        f"/v1/shifter/early_states?zip5={ca_zip5.zip5}&max_dist=100"
    )
    assert ca_res.status_code == 200
    assert ca_res.data == {"count": 0, "data": []}

    ia_res = api_client.get(f"/v1/shifter/early_states?zip5={ia_zip5.zip5}&max_dist=25")
    assert ia_res.status_code == 200
    assert ia_res.data == {"count": 1, "data": [{"min_distance": 0, "state": "IA"}]}


@pytest.mark.django_db
def test_early_states_ma(
    api_client, ia_zip5, nh_zip5, nv_zip5, sc_zip5, ma_zip5, ca_zip5
):
    ma_res = api_client.get(f"/v1/shifter/early_states?zip5={ma_zip5.zip5}")
    assert ma_res.status_code == 200
    assert ma_res.data == {
        "count": 4,
        "data": [
            {"min_distance": 57, "state": "NH"},
            {"min_distance": 815, "state": "SC"},
            {"min_distance": 1048, "state": "IA"},
            {"min_distance": 2370, "state": "NV"},
        ],
    }


@pytest.mark.django_db
def test_get_us_zip5(api_client, ia_zip5):
    res = api_client.get(f"/v1/shifter/zip5s/{ia_zip5.zip5}")
    assert res.status_code == 200
    assert res.data["zip5"] == ia_zip5.zip5
    assert res.data["state"] == "IA"
    assert pytest.approx(41.6355, res.data["latitude"])
    assert pytest.approx(-91.5016, res.data["longitude"])


@pytest.mark.django_db
def test_get_us_zip5_404s(api_client):
    res = api_client.get(f"/v1/shifter/zip5s/12345")
    assert res.status_code == 404
    assert res.data["code"] == "NOT_FOUND"


@pytest.mark.django_db
def test_us_zip5s_cant_be_modified(api_client, ia_zip5):
    res = api_client.delete(f"/v1/shifter/zip5s/{ia_zip5.zip5}")
    assert res.status_code == 405
    res = api_client.patch(
        f"/v1/shifter/zip5s/{ia_zip5.zip5}",
        data=json.dumps({"state": "CA"}),
        content_type="application/json",
    )
    assert res.status_code == 405
    res = api_client.post(
        f"/v1/shifter/zip5s",
        data=json.dumps({"zip5": "94102", "state": "CA"}),
        content_type="application/json",
    )
    assert res.status_code == 404  # does not match route exist
