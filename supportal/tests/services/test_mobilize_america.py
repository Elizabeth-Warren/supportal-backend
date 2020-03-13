import json

import pytest
import responses
from requests.exceptions import ConnectionError

from supportal import settings
from supportal.services import mobilize_america
from supportal.services.mobilize_america import (
    AttendanceRequestPerson,
    MobilizeAmericaAPIException,
    MobilizeAmericaClient,
)
from supportal.tests.services.mock_mobilize_america_responses import (
    CREATE_ATTENDANCE_RESPONSE,
    LIST_EVENTS_RESPONSE,
    LIST_EVENTS_RESPONSE_PAGE_2,
    NOT_FOUND_RESPONSE,
)


@responses.activate
def test_list_events():
    responses.add(
        responses.GET,
        "https://localhost:8000/mobilize/v1/organizations/1/events?visibility=PUBLIC",
        body=json.dumps(LIST_EVENTS_RESPONSE),
        match_querystring=True,
    )
    responses.add(
        responses.GET,
        "https://localhost:8000/mobilize/v1/organizations/1/events?page=2&visibility=PUBLIC",
        body=json.dumps(LIST_EVENTS_RESPONSE_PAGE_2),
        match_querystring=True,
    )
    res = mobilize_america.get_global_client().list_organization_events()
    page1 = next(res)
    assert {e["id"] for e in page1["data"]} == {172958, 175252, 179454}
    assert len(responses.calls) == 1  # make sure pagination is lazy

    page2 = next(res)
    assert {e["id"] for e in page2["data"]} == {9620}
    with pytest.raises(StopIteration):
        next(res)
    assert len(responses.calls) == 2


@responses.activate
def test_connection_error_retry():
    n = 0

    def callback(resp):
        nonlocal n
        n += 1
        if n == 1:
            raise ConnectionError("Connection reset by peer")
        return resp

    with responses.RequestsMock(response_callback=callback) as r:
        r.add(
            responses.GET,
            "https://localhost:8000/mobilize/v1/organizations/1/events?visibility=PUBLIC",
            body=json.dumps(LIST_EVENTS_RESPONSE),
            match_querystring=True,
        )
        res = mobilize_america.get_global_client().list_organization_events()
        page1 = next(res)
        assert n == 2
        assert {e["id"] for e in page1["data"]} == {172958, 175252, 179454}


@responses.activate
def test_list_events_visibility():
    client = MobilizeAmericaClient(
        1,
        "PRIVATE",
        settings.MOBILIZE_AMERICA_BASE_URL,
        settings.MOBILIZE_AMERICA_API_KEY,
    )
    responses.add(
        responses.GET,
        "https://localhost:8000/mobilize/v1/organizations/1/events?visibility=PRIVATE",
        body=json.dumps(LIST_EVENTS_RESPONSE),
        match_querystring=True,
    )
    client.list_organization_events()
    assert len(responses.calls) == 1


@responses.activate
def test_create_event_attendance():
    responses.add(
        responses.POST,
        "https://localhost:8000/mobilize/v1/organizations/1/events/17/attendances",
        body=json.dumps(CREATE_ATTENDANCE_RESPONSE),
    )
    responses.add(
        responses.GET,
        f"https://localhost:8000/mobilize/v1/organizations/1/events/17/attendances",
        body=json.dumps({"data": []}),
    )
    mobilize_america.get_global_client().create_event_attendance(
        17,
        timeslot_ids=[40896, 40894],
        person=AttendanceRequestPerson(
            given_name="Matteo",
            family_name="B",
            email_address="mbanerjee@elizabethwarren.com",
            postal_code="11238",
        ),
    )
    assert len(responses.calls) == 2


@responses.activate
def test_create_event_attendance_already_exists():
    responses.add(
        responses.GET,
        f"https://localhost:8000/mobilize/v1/organizations/1/events/17/attendances",
        body=json.dumps(CREATE_ATTENDANCE_RESPONSE),
    )
    mobilize_america.get_global_client().create_event_attendance(
        17,
        timeslot_ids=[40896, 40894],
        person=AttendanceRequestPerson(
            given_name="Matteo",
            family_name="B",
            email_address="mbanerjee@elizabethwarren.com",
            postal_code="11238",
        ),
    )
    assert len(responses.calls) == 1


@responses.activate
def test_error_mapping():
    responses.add(
        responses.GET,
        "https://localhost:8000/mobilize/v1/organizations/1/events",
        body=json.dumps(NOT_FOUND_RESPONSE),
        status=404,
    )
    with pytest.raises(MobilizeAmericaAPIException) as exec_info:
        mobilize_america.get_global_client().list_organization_events()
    assert exec_info.value.response["error"]["detail"] == "Not found."
