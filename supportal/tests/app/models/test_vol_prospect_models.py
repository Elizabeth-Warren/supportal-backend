import datetime
import unittest

import pytest
from django.utils import timezone
from model_bakery import baker

from supportal.app.common.enums import (
    CanvassResult,
    CanvassResultCategory,
    VolProspectAssignmentStatus,
)
from supportal.app.models import (
    MobilizeAmericaEventSignupExcpetion,
    VolProspectAssignment,
    VolProspectContactEvent,
)


@pytest.mark.django_db
def test_assign_priority_one_by_one(
    norwood_prospect,
    roslindale_prospect,
    jamaica_plain_prospect,
    west_roxbury_prospect,
    cambridge_leader_user,
    cambridge_prospect,
    somerville_prospect,
    medford_prospect,
    malden_prospect,
    california_prospect,
):
    assert cambridge_leader_user.vol_prospect_assignments.count() == 0

    assigned_cities_in_order = []
    while True:
        assignments = VolProspectAssignment.objects.assign(cambridge_leader_user, 1)
        if not assignments:
            break

        assert len(assignments) == 1
        assigned_cities_in_order.append(assignments[0].person.city)

    assert assigned_cities_in_order == [
        "Medford",
        "Somerville",
        "Cambridge",
        "Roslindale",
        "West Roxbury",
        "Jamaica Plain",
        "Malden",
        "Norwood",
    ]


@pytest.mark.django_db
def test_assign_different_location(
    norwood_prospect,
    roslindale_prospect,
    jamaica_plain_prospect,
    west_roxbury_prospect,
    hayes_valley_leader_user,
    cambridge_leader_user,
    cambridge_prospect,
    somerville_prospect,
    medford_prospect,
    malden_prospect,
    california_prospect,
):
    assert hayes_valley_leader_user.vol_prospect_assignments.count() == 0
    assignments = VolProspectAssignment.objects.assign(hayes_valley_leader_user, 10)
    assert len(assignments) == 0

    assignments = VolProspectAssignment.objects.assign(
        hayes_valley_leader_user, 10, cambridge_leader_user.coordinates
    )
    assigned_cities_in_order = [assignment.person.city for assignment in assignments]

    assert assigned_cities_in_order == [
        "Medford",
        "Somerville",
        "Cambridge",
        "Roslindale",
        "West Roxbury",
        "Jamaica Plain",
        "Malden",
        "Norwood",
    ]


@pytest.mark.django_db
def test_assign_priority_all_at_once(
    norwood_prospect,
    roslindale_prospect,
    jamaica_plain_prospect,
    west_roxbury_prospect,
    cambridge_leader_user,
    cambridge_prospect,
    somerville_prospect,
    medford_prospect,
    malden_prospect,
    california_prospect,
):
    assignments = VolProspectAssignment.objects.assign(cambridge_leader_user)
    assigned_cities_in_order = {assignment.person.city for assignment in assignments}

    assert assigned_cities_in_order == {
        "Medford",
        "Somerville",
        "Cambridge",
        "Roslindale",
        "West Roxbury",
        "Jamaica Plain",
        "Malden",
        "Norwood",
    }


@pytest.mark.django_db
def test_delete_demo_does_not_affect_nondemo(
    norwood_prospect,
    roslindale_prospect,
    jamaica_plain_prospect,
    west_roxbury_prospect,
    cambridge_leader_user,
    cambridge_prospect,
    somerville_prospect,
    medford_prospect,
    malden_prospect,
    california_prospect,
):
    VolProspectAssignment.objects.assign(cambridge_leader_user)
    VolProspectAssignment.objects.delete_demo_assignments(cambridge_leader_user)
    assignments = VolProspectAssignment.objects.filter(user=cambridge_leader_user)
    assigned_cities_in_order = {assignment.person.city for assignment in assignments}

    assert assigned_cities_in_order == {
        "Medford",
        "Somerville",
        "Cambridge",
        "Roslindale",
        "West Roxbury",
        "Jamaica Plain",
        "Malden",
        "Norwood",
    }


@pytest.mark.django_db
def test_delete_demo(cambridge_leader_user):
    cambridge_leader_user.verified_at = None
    cambridge_leader_user.save()

    VolProspectAssignment.objects.assign(cambridge_leader_user)
    assert VolProspectAssignment.objects.get_demo_queryset().count() == 10

    vpa = VolProspectAssignment.objects.get_demo_queryset().first()
    vpa.create_contact_event(
        result_category=CanvassResultCategory.UNREACHABLE,
        result=CanvassResult.UNREACHABLE_DISCONNECTED,
    )
    vpa_count = VolProspectContactEvent.objects.all().count()
    assert (
        VolProspectContactEvent.objects.filter(
            vol_prospect_assignment__user=cambridge_leader_user
        ).count()
        == 1
    )

    VolProspectAssignment.objects.delete_demo_assignments(cambridge_leader_user)
    assert VolProspectAssignment.objects.get_demo_queryset().count() == 0
    assert VolProspectContactEvent.objects.all().count() == (vpa_count - 1)
    assert (
        VolProspectContactEvent.objects.filter(
            vol_prospect_assignment__user=cambridge_leader_user
        ).count()
        == 0
    )


@pytest.mark.django_db
def test_expire_assignments(
    roslindale_leader_user,
    roslindale_prospect,
    jamaica_plain_prospect,
    west_roxbury_prospect,
    cambridge_leader_user,
    cambridge_prospect,
    somerville_prospect,
    medford_prospect,
):
    # Cambridge prospect: Created more than a week ago.
    # *Should* be expired.
    cambridge_assignment = baker.make(
        "VolProspectAssignment", user=cambridge_leader_user, person=cambridge_prospect
    )
    cambridge_assignment.created_at = datetime.datetime(
        2019, 10, 26, tzinfo=timezone.utc
    )
    cambridge_assignment.save()
    cambridge_assignment.refresh_from_db()
    assert cambridge_assignment.created_at == datetime.datetime(
        2019, 10, 26, tzinfo=timezone.utc
    )
    assert cambridge_assignment.expired_at is None

    # Somerville prospect: Just created.
    # Should *not* be expired.
    somerville_assignment = baker.make(
        "VolProspectAssignment", user=cambridge_leader_user, person=somerville_prospect
    )

    # Medford prospect: Assigned to and contacted by Cambridge leader.
    # Should *not* be expired.
    medford_assignment = baker.make(
        "VolProspectAssignment", user=cambridge_leader_user, person=medford_prospect
    )
    medford_assignment.create_contact_event(result=CanvassResult.SUCCESSFUL_CANVASSED)

    # Roslindale prospect: Previously assigned to Roslindale leader, suppressed.
    # Should *not* be expired.
    roslindale_assignment = baker.make(
        "VolProspectAssignment",
        user=roslindale_leader_user,
        person=roslindale_prospect,
        suppressed_at=datetime.datetime(2019, 10, 27, tzinfo=timezone.utc),
    )
    roslindale_assignment.created_at = datetime.datetime(
        2019, 10, 26, tzinfo=timezone.utc
    )
    roslindale_assignment.save()

    # Jamaica Plain prospect: Previously assigned to Roslindale leader, expired.
    # Alrady expired, so a no-op.
    jamaica_plain_assignment = baker.make(
        "VolProspectAssignment",
        user=roslindale_leader_user,
        person=jamaica_plain_prospect,
        expired_at=datetime.datetime(2019, 10, 27, tzinfo=timezone.utc),
    )
    # Explicitly call 'update' so we can fix 'updated_at'.
    VolProspectAssignment.objects.filter(pk=jamaica_plain_assignment.pk).update(
        updated_at=datetime.datetime(2019, 10, 27, tzinfo=timezone.utc),
        created_at=datetime.datetime(2019, 10, 26, tzinfo=timezone.utc),
    )

    # West Roxbury prospect: Assigned to Roslindale leader more than a week ago.
    # *Should* be expired.
    west_roxbury_assignment = baker.make(
        "VolProspectAssignment",
        user=roslindale_leader_user,
        person=west_roxbury_prospect,
    )
    west_roxbury_assignment.created_at = datetime.datetime(
        2019, 10, 26, tzinfo=timezone.utc
    )
    west_roxbury_assignment.save()

    VolProspectAssignment.objects.expire_assignments()

    cambridge_assignment.refresh_from_db()
    assert cambridge_assignment.expired_at is not None

    somerville_assignment.refresh_from_db()
    assert somerville_assignment.expired_at is None

    medford_assignment.refresh_from_db()
    assert medford_assignment.expired_at is None

    roslindale_assignment.refresh_from_db()
    assert roslindale_assignment.expired_at is None

    jamaica_plain_assignment.refresh_from_db()
    assert jamaica_plain_assignment.expired_at == datetime.datetime(
        2019, 10, 27, tzinfo=timezone.utc
    )
    assert jamaica_plain_assignment.updated_at == datetime.datetime(
        2019, 10, 27, tzinfo=timezone.utc
    )

    west_roxbury_assignment.refresh_from_db()
    assert west_roxbury_assignment.expired_at is not None


@pytest.mark.django_db
def test_vol_prospect_assignment_status(cambridge_prospect_assignment):
    """A non-suppressed VolProspectAssignment with no contact history is marked as ASSIGNED"""
    assert cambridge_prospect_assignment.status == VolProspectAssignmentStatus.ASSIGNED


@pytest.mark.django_db
def test_skip(cambridge_prospect_assignment):
    """Suppressing a VolProspectAssignment without adding an UNREACHABLE event marks it as SKIPPED"""
    cambridge_prospect_assignment.suppress()
    assert cambridge_prospect_assignment.status == VolProspectAssignmentStatus.SKIPPED


@pytest.mark.django_db
def test_add_unreachable_contact_event(cambridge_prospect_assignment):
    """
    Adding an UNREACHABLE contact event suppresses the person, suppresses the
    VolProspectAssignment and marks it as CONTACTED_UNREACHABLE.
    """
    cambridge_prospect_assignment.create_contact_event(
        result_category=CanvassResultCategory.UNREACHABLE,
        result=CanvassResult.UNREACHABLE_DISCONNECTED,
    )
    assert cambridge_prospect_assignment.suppressed_at is not None
    assert (
        cambridge_prospect_assignment.status
        == VolProspectAssignmentStatus.CONTACTED_UNREACHABLE
    )
    assert cambridge_prospect_assignment.person.suppressed_at is not None


@pytest.mark.django_db
def test_add_successful_contact_event(cambridge_prospect_assignment):
    """Adding a SUCCESSFUL contact event marks the VolProspectAssignment as CONTACTED_SUCCESSFUL."""
    cambridge_prospect_assignment.create_contact_event(
        result_category=CanvassResultCategory.SUCCESSFUL,
        result=CanvassResult.SUCCESSFUL_CANVASSED,
        metadata={"note": "had a great conversation!"},
    )
    assert cambridge_prospect_assignment.suppressed_at is None
    assert (
        cambridge_prospect_assignment.status
        == VolProspectAssignmentStatus.CONTACTED_SUCCESSFUL
    )


@pytest.mark.django_db
def test_add_successful_contact_ma_signup(cambridge_prospect_assignment):
    """Adding a SUCCESSFUL contact event marks the VolProspectAssignment as CONTACTED_SUCCESSFUL."""

    with unittest.mock.patch(
        "supportal.app.models.vol_prospect_models.EventSignup"
    ) as event_sign_up_mock:
        event_sign_up_mock.return_value.sync_to_mobilize_america.return_value = (
            True,
            None,
        )
        cambridge_prospect_assignment.create_contact_event(
            result_category=CanvassResultCategory.SUCCESSFUL,
            result=CanvassResult.SUCCESSFUL_CANVASSED,
            ma_event_id=123,
            ma_timeslot_ids=[1],
            metadata={"note": "had a great conversation!"},
        )
    assert cambridge_prospect_assignment.suppressed_at is None
    assert (
        cambridge_prospect_assignment.status
        == VolProspectAssignmentStatus.CONTACTED_SUCCESSFUL
    )


@pytest.mark.django_db
def test_add_successful_contact_ma_signup(cambridge_prospect_assignment):
    """Adding a SUCCESSFUL contact event marks the VolProspectAssignment as CONTACTED_SUCCESSFUL."""

    with unittest.mock.patch(
        "supportal.app.models.vol_prospect_models.EventSignup"
    ) as event_sign_up_mock:
        event_sign_up_mock.objects.create.return_value.sync_to_mobilize_america.return_value = (
            True,
            None,
        )
        cambridge_prospect_assignment.create_contact_event(
            result_category=CanvassResultCategory.SUCCESSFUL,
            result=CanvassResult.SUCCESSFUL_CANVASSED,
            ma_event_id=123456,
            ma_timeslot_ids=[1],
            metadata={"note": "had a great conversation!"},
        )
    assert cambridge_prospect_assignment.suppressed_at is None
    assert (
        cambridge_prospect_assignment.status
        == VolProspectAssignmentStatus.CONTACTED_SUCCESSFUL
    )
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
def test_add_successful_contact_ma_signup_fails(cambridge_prospect_assignment):
    """Adding a SUCCESSFUL contact event marks the VolProspectAssignment as CONTACTED_SUCCESSFUL."""

    with unittest.mock.patch(
        "supportal.app.models.vol_prospect_models.EventSignup"
    ) as event_sign_up_mock, pytest.raises(MobilizeAmericaEventSignupExcpetion):
        event_sign_up_mock.objects.create.return_value.sync_to_mobilize_america.return_value = (
            False,
            {"error": {"detail": "eek"}},
        )
        cambridge_prospect_assignment.create_contact_event(
            result_category=CanvassResultCategory.SUCCESSFUL,
            result=CanvassResult.SUCCESSFUL_CANVASSED,
            ma_event_id=123456,
            ma_timeslot_ids=[1],
            metadata={"note": "had a great conversation!"},
        )
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
    assert cambridge_prospect_assignment.vol_prospect_contact_events.count() == 0


@pytest.mark.django_db
def test_add_successful_contact_ma_signup_no_email(cambridge_prospect_assignment):
    """Adding a SUCCESSFUL contact event marks the VolProspectAssignment as CONTACTED_SUCCESSFUL."""
    cambridge_prospect_assignment.person.email = ""
    cambridge_prospect_assignment.person.save()
    with pytest.raises(MobilizeAmericaEventSignupExcpetion):
        cambridge_prospect_assignment.create_contact_event(
            result_category=CanvassResultCategory.SUCCESSFUL,
            result=CanvassResult.SUCCESSFUL_CANVASSED,
            ma_event_id=123,
            ma_timeslot_ids=[1],
            metadata={"note": "had a great conversation!"},
        )


@pytest.mark.django_db
def test_add_successful_contact_ma_signup_demo_person(cambridge_prospect_assignment):
    """Adding a SUCCESSFUL contact event marks the VolProspectAssignment as CONTACTED_SUCCESSFUL."""
    cambridge_prospect_assignment.person.is_demo = True
    cambridge_prospect_assignment.person.save()
    with unittest.mock.patch(
        "supportal.app.models.vol_prospect_models.EventSignup"
    ) as event_sign_up_mock:
        cambridge_prospect_assignment.create_contact_event(
            result_category=CanvassResultCategory.SUCCESSFUL,
            result=CanvassResult.SUCCESSFUL_CANVASSED,
            ma_event_id=123,
            ma_timeslot_ids=[1],
            metadata={"note": "had a great conversation!"},
        )
    assert not event_sign_up_mock.called


@pytest.mark.django_db
def test_add_unavailable_contact_event(cambridge_prospect_assignment):
    """Adding an UNAVAILABLE contact event marks the VolProspectAssignment as CONTACTED_UNAVAILABLE."""
    cambridge_prospect_assignment.create_contact_event(
        result_category=CanvassResultCategory.UNAVAILABLE,
        result=CanvassResult.UNAVAILABLE_LEFT_MESSAGE,
    )
    assert cambridge_prospect_assignment.suppressed_at is None
    assert (
        cambridge_prospect_assignment.status
        == VolProspectAssignmentStatus.CONTACTED_UNAVAILABLE
    )


@pytest.mark.django_db
def test_contact_event_roundtrip(cambridge_prospect_unreachable_event):
    fetched = VolProspectContactEvent.objects.get(
        pk=cambridge_prospect_unreachable_event.pk
    )
    assert fetched.result_category == CanvassResultCategory.UNREACHABLE
    assert fetched.result == CanvassResult.UNREACHABLE_MOVED
    assert fetched.metadata["moved_to"] == "CA"
