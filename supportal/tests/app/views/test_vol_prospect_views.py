import json
import unittest
from datetime import datetime, timezone

import pytest
from model_bakery import baker
from rest_framework import status

from supportal.app.common.enums import CanvassResult, VolProspectAssignmentStatus
from supportal.tests import utils


@pytest.mark.django_db
def test_retrieve_assignment(api_client, cambridge_prospect_unreachable_event):
    assignment = cambridge_prospect_unreachable_event.vol_prospect_assignment
    auth = utils.id_auth(assignment.user)
    assignment_id = cambridge_prospect_unreachable_event.vol_prospect_assignment.id
    res = api_client.get(f"/v1/vol_prospect_assignments/{assignment_id}/", **auth)
    data = res.data
    assert res.status_code == 200
    assert data["person"]["phone"] == assignment.person.phone
    assert data["person"]["last_name"] == "W."
    assert data["status"] == "CONTACTED_UNREACHABLE"
    assert data["note"] == "note"
    assert len(data["vol_prospect_contact_events"]) == 1
    assert data["vol_prospect_contact_events"][0]["result"] == "UNREACHABLE_MOVED"


@pytest.mark.django_db
def test_cannot_retrieve_expired_assignment(
    api_client, cambridge_prospect_unreachable_event
):
    vpa = cambridge_prospect_unreachable_event.vol_prospect_assignment
    vpa.expired_at = datetime(2019, 10, 27, tzinfo=timezone.utc)
    vpa.save()
    auth = utils.id_auth(
        cambridge_prospect_unreachable_event.vol_prospect_assignment.user
    )
    assignment_id = cambridge_prospect_unreachable_event.vol_prospect_assignment.id
    res = api_client.get(f"/v1/vol_prospect_assignments/{assignment_id}/", **auth)
    assert res.status_code == 404


@pytest.mark.django_db
def test_assignments_no_email(api_client, cambridge_leader_user, cambridge_prospect):
    cambridge_prospect.email = ""
    cambridge_prospect.save()

    baker.make(
        "VolProspectAssignment",
        user=cambridge_leader_user,
        person=cambridge_prospect,
        suppressed_at=datetime(2019, 10, 27, tzinfo=timezone.utc),
    )

    auth = utils.id_auth(cambridge_leader_user)
    all_res = api_client.get(f"/v1/vol_prospect_assignments/", **auth)
    assert all_res.status_code == 200
    assert len(all_res.data) == 1
    assert all_res.data[0]["person"]["has_email"] is False


@pytest.mark.django_db
def test_assignments_has_email(api_client, cambridge_leader_user, cambridge_prospect):
    baker.make(
        "VolProspectAssignment",
        user=cambridge_leader_user,
        person=cambridge_prospect,
        suppressed_at=datetime(2019, 10, 27, tzinfo=timezone.utc),
    )

    auth = utils.id_auth(cambridge_leader_user)
    all_res = api_client.get(f"/v1/vol_prospect_assignments/", **auth)
    assert all_res.status_code == 200
    assert len(all_res.data) == 1
    assert all_res.data[0]["person"]["has_email"]


@pytest.mark.django_db
def test_list_assignments(
    api_client,
    cambridge_leader_user,
    roslindale_leader_user,
    roslindale_prospect,
    jamaica_plain_prospect,
    cambridge_prospect,
    somerville_prospect,
    medford_prospect,
    malden_prospect,
    california_prospect,
):
    baker.make(
        "VolProspectAssignment",
        user=cambridge_leader_user,
        person=cambridge_prospect,
        suppressed_at=datetime(2019, 10, 27, tzinfo=timezone.utc),
    )
    baker.make(
        "VolProspectAssignment", user=cambridge_leader_user, person=medford_prospect
    )
    jp_vpa = baker.make(
        "VolProspectAssignment",
        user=cambridge_leader_user,
        person=jamaica_plain_prospect,
    )
    jp_vpa.create_contact_event(result=CanvassResult.SUCCESSFUL_CANVASSED)

    malden_vpa = baker.make(
        "VolProspectAssignment", user=cambridge_leader_user, person=malden_prospect
    )
    malden_vpa.create_contact_event(result=CanvassResult.UNAVAILABLE_LEFT_MESSAGE)

    ca_vpa = baker.make(
        "VolProspectAssignment", user=cambridge_leader_user, person=california_prospect
    )
    ca_vpa.create_contact_event(result=CanvassResult.UNREACHABLE_MOVED)

    # these shouldn't be included
    baker.make(
        "VolProspectAssignment",
        user=cambridge_leader_user,
        person=somerville_prospect,
        expired_at=datetime(2019, 10, 27, tzinfo=timezone.utc),
    )
    baker.make(
        "VolProspectAssignment", user=roslindale_leader_user, person=roslindale_prospect
    )
    auth = utils.id_auth(cambridge_leader_user)
    expected = sorted(
        [
            {"status": "SKIPPED", "person_id": cambridge_prospect.id},
            {"status": "ASSIGNED", "person_id": medford_prospect.id},
            {"status": "CONTACTED_SUCCESSFUL", "person_id": jamaica_plain_prospect.id},
            {"status": "CONTACTED_UNAVAILABLE", "person_id": malden_prospect.id},
            {"status": "CONTACTED_UNREACHABLE", "person_id": california_prospect.id},
        ],
        key=lambda x: x["person_id"],
    )

    def compare(actual_vpa_res, expected_vpa):
        assert actual_vpa_res["status"] == expected_vpa["status"]
        assert actual_vpa_res["person"]["id"] == expected_vpa["person_id"]

    all_res = api_client.get(f"/v1/vol_prospect_assignments/", **auth)
    assert all_res.status_code == 200
    for i, res in enumerate(sorted(all_res.data, key=lambda x: x["person"]["id"])):
        compare(res, expected[i])

    for expected_result in expected:
        res = api_client.get(
            f"/v1/vol_prospect_assignments/?status={expected_result['status']}", **auth
        )
        assert res.status_code == 200
        assert len(res.data) == 1
        compare(res.data[0], expected_result)


@pytest.mark.django_db
def test_demo_list_assignments(api_client, cambridge_leader_user, cambridge_prospect):
    cambridge_leader_user.verified_at = None
    cambridge_leader_user.save()

    # add demo assignments via api call
    auth = utils.id_auth(cambridge_leader_user)
    api_client.post(f"/v1/vol_prospect_assignments/assign/", **auth)

    # list back the demo assignments
    all_res = api_client.get(f"/v1/vol_prospect_assignments/", **auth)
    assert len(all_res.data) == 10
    for res in all_res.data:
        assert res["person"]["is_demo"]

    cambridge_leader_user.verified_at = datetime.now(tz=timezone.utc)
    cambridge_leader_user.save()

    baker.make(
        "VolProspectAssignment", user=cambridge_leader_user, person=cambridge_prospect
    )

    all_res = api_client.get(f"/v1/vol_prospect_assignments/", **auth)
    assert len(all_res.data) == 1
    for res in all_res.data:
        assert res["person"]["is_demo"] is False


@pytest.mark.django_db
def test_skip(api_client, cambridge_prospect_assignment):
    assert cambridge_prospect_assignment.status != VolProspectAssignmentStatus.SKIPPED
    auth = utils.id_auth(cambridge_prospect_assignment.user)
    res = api_client.patch(
        f"/v1/vol_prospect_assignments/{cambridge_prospect_assignment.id}/",
        # TODO: figure out why this requires json.dumps
        data=json.dumps({"status": "SKIPPED"}),
        content_type="application/json",
        **auth,
    )
    cambridge_prospect_assignment.refresh_from_db()
    assert cambridge_prospect_assignment.status == VolProspectAssignmentStatus.SKIPPED


@pytest.mark.django_db
def test_skip_with_assignments(api_client, cambridge_prospect_assignment):
    cambridge_prospect_assignment.create_contact_event(
        result=CanvassResult.SUCCESSFUL_CANVASSED
    )
    assert cambridge_prospect_assignment.status != VolProspectAssignmentStatus.SKIPPED
    auth = utils.id_auth(cambridge_prospect_assignment.user)
    api_client.patch(
        f"/v1/vol_prospect_assignments/{cambridge_prospect_assignment.id}/",
        # TODO: figure out why this requires json.dumps
        data=json.dumps({"status": "SKIPPED"}),
        content_type="application/json",
        **auth,
    )
    cambridge_prospect_assignment.refresh_from_db()
    assert cambridge_prospect_assignment.status == VolProspectAssignmentStatus.SKIPPED

    get_res = api_client.get(f"/v1/vol_prospect_assignments/", **auth)
    assert len(get_res.data) == 1
    assert get_res.data[0]["status"] == "SKIPPED"
    assert len(get_res.data[0]["vol_prospect_contact_events"]) == 1


@pytest.mark.django_db
def test_patch_fails_when_user_mismatch(
    api_client, cambridge_prospect_assignment, roslindale_prospect_assignment
):
    auth = utils.id_auth(cambridge_prospect_assignment.user)
    res = api_client.patch(
        f"/v1/vol_prospect_assignments/{roslindale_prospect_assignment.id}/",
        data=json.dumps({"note": "not allowed"}),
        content_type="application/json",
        **auth,
    )
    assert res.status_code == 404


@pytest.mark.django_db
def test_patch_notes(api_client, cambridge_prospect_assignment):
    auth = utils.id_auth(cambridge_prospect_assignment.user)
    note = "It me, a note"
    res = api_client.patch(
        f"/v1/vol_prospect_assignments/{cambridge_prospect_assignment.id}/",
        data=json.dumps({"note": note}),
        content_type="application/json",
        **auth,
    )
    cambridge_prospect_assignment.refresh_from_db()
    assert cambridge_prospect_assignment.note == note


@pytest.mark.django_db
def test_empty_patch_notes(api_client, cambridge_prospect_assignment):
    auth = utils.id_auth(cambridge_prospect_assignment.user)
    res = api_client.patch(
        f"/v1/vol_prospect_assignments/{cambridge_prospect_assignment.id}/",
        data=json.dumps({"note": ""}),
        content_type="application/json",
        **auth,
    )
    cambridge_prospect_assignment.refresh_from_db()
    assert cambridge_prospect_assignment.note == ""


@pytest.mark.django_db
def test_assign(
    api_client,
    mattapan_leader_user,
    roslindale_leader_user,
    roslindale_prospect,
    jamaica_plain_prospect,
    west_roxbury_prospect,
    cambridge_leader_user,
    cambridge_prospect,
    somerville_prospect,
    medford_prospect,
    malden_prospect,
    malden_prospect_suppressed,
    california_prospect,
):
    assert cambridge_leader_user.vol_prospect_assignments.count() == 0

    # Cambridge prospect: Previously assigned to Mattapan and Cambridge
    # leaders, suppressed for both.
    # Should *not* be (re)assigned to Cambridge leader.
    baker.make(
        "VolProspectAssignment",
        user=mattapan_leader_user,
        person=cambridge_prospect,
        suppressed_at=datetime(2019, 10, 27, tzinfo=timezone.utc),
    )
    baker.make(
        "VolProspectAssignment",
        user=cambridge_leader_user,
        person=cambridge_prospect,
        suppressed_at=datetime(2019, 10, 27, tzinfo=timezone.utc),
    )

    # Somerville prospect: Previously assigned to Cambridge leader, suppressed.
    # Should *not* be (re)assigned to Cambridge leader.
    baker.make(
        "VolProspectAssignment",
        user=cambridge_leader_user,
        person=somerville_prospect,
        expired_at=datetime(2019, 10, 27, tzinfo=timezone.utc),
    )

    # Medford prospect: Assigned to and contacted by Cambridge leader.
    # Should *not* be (re)assigned to Cambridge leader.
    medford_prospect_assignment = baker.make(
        "VolProspectAssignment", user=cambridge_leader_user, person=medford_prospect
    )
    medford_prospect_assignment.create_contact_event(
        result=CanvassResult.SUCCESSFUL_CANVASSED
    )

    # We'll set up also assignments for the Roslindale volunteer leader. The
    # suppressed and expired ones will be assigned to the Cambridge volunteer
    # leader; the live one will not be:

    # Roslindale prospect: Previously assigned to Roslindale leader, suppressed.
    # *Should* be assigned to Cambridge leader.
    baker.make(
        "VolProspectAssignment",
        user=roslindale_leader_user,
        person=roslindale_prospect,
        suppressed_at=datetime(2019, 10, 27, tzinfo=timezone.utc),
    )

    # Jamaica Plain prospect: Previously assigned to Roslindale leader, expired.
    # *Should* be assigned to Cambridge leader.
    baker.make(
        "VolProspectAssignment",
        user=roslindale_leader_user,
        person=jamaica_plain_prospect,
        expired_at=datetime(2019, 10, 27, tzinfo=timezone.utc),
    )

    # West Roxbury prospect: Assigned to Roslindale leader, still live assignment.
    # Should *not* be assigned to Cambridge leader.
    baker.make(
        "VolProspectAssignment",
        user=roslindale_leader_user,
        person=west_roxbury_prospect,
    )

    # And there are two volunteer prospects who have never had assignments. One
    # is nearby, one is too far away:

    # Malden prospect: Never assigned to anybody.
    # *Should* be assigned to Cambridge leader.

    # Malden prospect suppressed.
    # Should *not* be assigned to Cambridge leader.

    # California prospect: Never assigned to anybody.
    # Should *not* be assigned to Cambridge leader (too far away).

    assignments = cambridge_leader_user.vol_prospect_assignments.all()
    assert [x.person.city for x in assignments] == [
        "Cambridge",
        "Somerville",
        "Medford",
    ]
    # none of the assignments should be demo users
    assert (
        cambridge_leader_user.vol_prospect_assignments.get_demo_queryset().count() == 0
    )

    auth = utils.id_auth(cambridge_leader_user)
    res = api_client.post(f"/v1/vol_prospect_assignments/assign/", **auth)
    assert res.status_code == status.HTTP_201_CREATED

    assignments = cambridge_leader_user.vol_prospect_assignments.all()
    # none of the assignments should be demo users
    assert (
        cambridge_leader_user.vol_prospect_assignments.get_demo_queryset().count() == 0
    )

    assert {x.person.city for x in assignments} == set(
        ["Cambridge", "Somerville", "Medford", "Roslindale", "Jamaica Plain", "Malden"]
    )

    # Trying to request more is a 400 because there are outstanding requests.
    res = api_client.post(f"/v1/vol_prospect_assignments/assign/", **auth)
    assert res.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_demo_assign(api_client, cambridge_leader_user, cambridge_prospect):
    cambridge_leader_user.verified_at = None
    cambridge_leader_user.save()

    auth = utils.id_auth(cambridge_leader_user)
    res = api_client.post(f"/v1/vol_prospect_assignments/assign/", **auth)
    assert res.status_code == status.HTTP_201_CREATED

    assignments = cambridge_leader_user.vol_prospect_assignments.all()
    assert (
        cambridge_leader_user.vol_prospect_assignments.get_demo_queryset().count() == 10
    )
    # VPA assignment manager get_queryset is overwritten to not return demo users
    assert assignments.filter(person__is_demo=False).count() == 0

    cambridge_leader_user.verified_at = datetime.now(tz=timezone.utc)
    cambridge_leader_user.save()
    cambridge_leader_user.vol_prospect_assignments.delete_demo_assignments(
        user=cambridge_leader_user
    )

    auth = utils.id_auth(cambridge_leader_user)
    res = api_client.post(f"/v1/vol_prospect_assignments/assign/", **auth)
    assert res.status_code == status.HTTP_201_CREATED

    assignments = cambridge_leader_user.vol_prospect_assignments.all()
    # none of the assignments should be demo users
    assert (
        cambridge_leader_user.vol_prospect_assignments.get_demo_queryset().count() == 0
    )
    assert assignments.count() == 1


@pytest.mark.django_db
def test_assign_in_another_location(
    api_client, hayes_valley_leader_user, cambridge_prospect
):
    auth = utils.id_auth(hayes_valley_leader_user)
    res = api_client.post(
        f"/v1/vol_prospect_assignments/assign/",
        **auth,
        data={"location": {"latitude": 42.371949, "longitude": -71.120276}},
    )
    assert res.status_code == status.HTTP_201_CREATED

    assignments = hayes_valley_leader_user.vol_prospect_assignments.all()
    assert assignments.count() == 1
    assert assignments[0].person == cambridge_prospect


@pytest.mark.django_db
def test_get_contact_event(api_client, cambridge_prospect_unreachable_event):
    event = cambridge_prospect_unreachable_event
    user = event.vol_prospect_assignment.user
    auth = utils.id_auth(user)
    res = api_client.get(f"/v1/vol_prospect_contact_events/{event.id}/", **auth)
    assert res.status_code == 200
    assert res.data["id"] == event.id
    assert res.data["vol_prospect_assignment"] == event.vol_prospect_assignment.id
    assert res.data["result"] == "UNREACHABLE_MOVED"
    assert res.data["note"] == "test"


# common fixture for the next couple of tests
def setup_assignments_and_events(cambridge_event, somerville_prospect):
    user = cambridge_event.vol_prospect_assignment.user
    somerville_assignment = baker.make(
        "VolProspectAssignment", user=user, person=somerville_prospect
    )
    somerville_assignment.create_contact_event(
        result=CanvassResult.SUCCESSFUL_CANVASSED
    )
    auth = utils.id_auth(user)
    return auth, somerville_assignment


@pytest.mark.django_db
def test_list_contact_events(
    api_client, cambridge_prospect_unreachable_event, somerville_prospect
):
    auth, somerville_assignment = setup_assignments_and_events(
        cambridge_prospect_unreachable_event, somerville_prospect
    )
    res = api_client.get(f"/v1/vol_prospect_contact_events/", **auth)
    assert res.status_code == 200
    assert len(res.data) == 2
    # default ordering is by created at desc
    assert [d["result"] for d in res.data] == [
        "SUCCESSFUL_CANVASSED",
        "UNREACHABLE_MOVED",
    ]
    asc_res = api_client.get(
        f"/v1/vol_prospect_contact_events/?ordering=created_at", **auth
    )
    assert [d["result"] for d in asc_res.data] == [
        "UNREACHABLE_MOVED",
        "SUCCESSFUL_CANVASSED",
    ]


@pytest.mark.django_db
def test_list_contact_events_for_assignment(
    api_client, cambridge_prospect_unreachable_event, somerville_prospect
):
    auth, somerville_assignment = setup_assignments_and_events(
        cambridge_prospect_unreachable_event, somerville_prospect
    )
    sa_id = somerville_assignment.id
    res = api_client.get(
        f"/v1/vol_prospect_contact_events/?vol_prospect_assignment={sa_id}", **auth
    )
    assert res.status_code == 200
    assert len(res.data) == 1
    assert res.data[0]["result"] == "SUCCESSFUL_CANVASSED"
    assert res.data[0]["vol_prospect_assignment"] == sa_id


@pytest.mark.django_db
def test_create_contact_event(api_client, cambridge_prospect_assignment):
    auth = utils.id_auth(cambridge_prospect_assignment.user)
    payload = {
        "vol_prospect_assignment": cambridge_prospect_assignment.id,
        "result": "UNAVAILABLE_BUSY",
        "note": "",
    }
    res = api_client.post(f"/v1/vol_prospect_contact_events/", data=payload, **auth)
    assert res.status_code == 201
    assert res.data["result"] == "UNAVAILABLE_BUSY"
    assert res.data["note"] == ""

    new_event = {
        "vol_prospect_assignment": cambridge_prospect_assignment.id,
        "result": "SUCCESSFUL_CANVASSED",
        "metadata": {"survey_response_id": "12345"},
        "note": "note",
    }
    res = api_client.post(f"/v1/vol_prospect_contact_events/", data=new_event, **auth)
    assert res.data["note"] == "note"

    list_res = api_client.get(f"/v1/vol_prospect_contact_events/", **auth)
    assert list_res.status_code == 200
    assert len(list_res.data) == 2
    assert [d["result"] for d in list_res.data] == [
        "SUCCESSFUL_CANVASSED",
        "UNAVAILABLE_BUSY",
    ]


@pytest.mark.django_db
def test_create_contact_event_demo(
    api_client, cambridge_leader_user, somerville_prospect
):
    cambridge_leader_user.verified_at = None
    cambridge_leader_user.save()
    somerville_prospect.is_demo = True
    somerville_prospect.save()

    auth = utils.id_auth(cambridge_leader_user)
    assignment = baker.make(
        "VolProspectAssignment", user=cambridge_leader_user, person=somerville_prospect
    )
    payload = {
        "vol_prospect_assignment": assignment.id,
        "result": "UNAVAILABLE_BUSY",
        "note": "",
    }
    res = api_client.post(f"/v1/vol_prospect_contact_events/", data=payload, **auth)
    assert res.status_code == 201


@pytest.mark.django_db
def test_create_contact_event_with_ma(api_client, cambridge_prospect_assignment):
    auth = utils.id_auth(cambridge_prospect_assignment.user)
    payload = {
        "vol_prospect_assignment": cambridge_prospect_assignment.id,
        "result": "SUCCESSFUL_CANVASSED",
        "ma_event_id": 123456,
        "ma_timeslot_ids": [1],
    }
    with unittest.mock.patch(
        "supportal.app.models.vol_prospect_models.EventSignup"
    ) as event_sign_up_mock:
        event_sign_up_mock.objects.create.return_value.sync_to_mobilize_america.return_value = (
            True,
            None,
        )
        res = api_client.post(f"/v1/vol_prospect_contact_events/", data=payload, **auth)
        assert res.status_code == 201
    person = cambridge_prospect_assignment.person
    event_sign_up_mock.objects.create.assert_called_once_with(
        email=person.email,
        family_name=person.last_name,
        given_name=person.first_name,
        ma_event_id=123456,
        ma_timeslot_ids=[1],
        zip5=person.zip5,
        phone=person.phone,
        source="switchboard",
    )
    event_sign_up_mock.objects.create.return_value.sync_to_mobilize_america.assert_called_once_with()


@pytest.mark.django_db
def test_create_contact_event_with_ma_no_email(
    api_client, cambridge_prospect_assignment
):
    auth = utils.id_auth(cambridge_prospect_assignment.user)
    cambridge_prospect_assignment.person.email = ""
    cambridge_prospect_assignment.person.save()

    payload = {
        "vol_prospect_assignment": cambridge_prospect_assignment.id,
        "result": "SUCCESSFUL_CANVASSED",
        "ma_event_id": 123456,
        "ma_timeslot_ids": [1],
    }
    res = api_client.post(f"/v1/vol_prospect_contact_events/", data=payload, **auth)
    assert res.status_code == 400


@pytest.mark.django_db
def test_create_contact_event_with_ma_and_errors(
    api_client, cambridge_prospect_assignment
):
    auth = utils.id_auth(cambridge_prospect_assignment.user)

    with unittest.mock.patch(
        "supportal.app.models.vol_prospect_models.EventSignup"
    ) as event_sign_up_mock:
        event_sign_up_mock.objects.create.return_value.sync_to_mobilize_america.return_value = (
            False,
            {"error": {"detail": "eek"}},
        )
        payload = {
            "vol_prospect_assignment": cambridge_prospect_assignment.id,
            "result": "SUCCESSFUL_CANVASSED",
            "ma_event_id": 123456,
            "ma_timeslot_ids": [1],
        }
        res = api_client.post(f"/v1/vol_prospect_contact_events/", data=payload, **auth)
    assert res.status_code == 400


@pytest.mark.django_db
def test_create_permissions(api_client, user, cambridge_prospect_assignment):
    assert user != cambridge_prospect_assignment.user
    auth = utils.id_auth(user)
    # Post a payload that would be valid for cambridge_prospect_assignment.user
    payload = {
        "vol_prospect_assignment": cambridge_prospect_assignment.id,
        "result": "UNAVAILABLE_BUSY",
    }
    res = api_client.post(f"/v1/vol_prospect_contact_events/", data=payload, **auth)
    assert res.status_code == 404


@pytest.mark.django_db
def test_contact_events_creations_throttled(
    api_client, cambridge_prospect_assignment, settings
):
    throttle_settings = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
    assert "day.vol_prospect_contact_events.create" in throttle_settings
    assert "hour.vol_prospect_contact_events.create" in throttle_settings
    throttle_settings["hour.vol_prospect_contact_events.create"] = "1/hr"
    auth = utils.id_auth(cambridge_prospect_assignment.user)
    payload = {
        "vol_prospect_assignment": cambridge_prospect_assignment.id,
        "result": "SUCCESSFUL_CANVASSED",
    }
    res = api_client.post(f"/v1/vol_prospect_contact_events/", data=payload, **auth)
    assert res.status_code == 201
    res = api_client.post(f"/v1/vol_prospect_contact_events/", data=payload, **auth)
    assert res.status_code == 429


@pytest.mark.django_db
def test_assignments_are_throttled(api_client, cambridge_prospect_assignment, settings):
    throttle_settings = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
    assert "hour.vol_prospect_assignments" in throttle_settings
    assert "day.vol_prospect_assignments" in throttle_settings
    throttle_settings["day.vol_prospect_assignments"] = "1/day"
    auth = utils.id_auth(cambridge_prospect_assignment.user)
    res = api_client.get(
        f"/v1/vol_prospect_assignments/{cambridge_prospect_assignment.id}/", **auth
    )
    assert res.status_code == 200
    res = api_client.get(
        f"/v1/vol_prospect_assignments/{cambridge_prospect_assignment.id}/", **auth
    )
    assert res.status_code == 429
