import datetime
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone
from model_bakery import baker

OLD_CREATED_DATE = datetime.datetime(2019, 10, 26, tzinfo=timezone.utc)


@pytest.fixture
def old_cambridge_assignment(cambridge_leader_user, cambridge_prospect):
    cambridge_assignment = baker.make(
        "VolProspectAssignment",
        user=cambridge_leader_user,
        person=cambridge_prospect,
        suppressed_at=timezone.now(),
        expired_at=timezone.now(),
    )
    cambridge_assignment.created_at = OLD_CREATED_DATE
    cambridge_assignment.save()
    return cambridge_assignment


@pytest.fixture
def current_new_assignment(hayes_valley_leader_user, cambridge_prospect):
    cambridge_assignment = baker.make(
        "VolProspectAssignment",
        user=hayes_valley_leader_user,
        person=cambridge_prospect,
    )
    return cambridge_assignment


@pytest.mark.django_db
def test_unskip_assignments(old_cambridge_assignment):
    out = StringIO()
    call_command(
        "unskip_prospects",
        stdout=out,
        user=old_cambridge_assignment.user.email,
        run=True,
    )

    old_cambridge_assignment.refresh_from_db()
    assert old_cambridge_assignment.suppressed_at is None
    assert old_cambridge_assignment.expired_at is None
    assert old_cambridge_assignment.created_at > OLD_CREATED_DATE


@pytest.mark.django_db
def test_if_person_supressed_dont_unskip(old_cambridge_assignment):
    out = StringIO()
    old_cambridge_assignment.person.suppressed_at = timezone.now()
    old_cambridge_assignment.person.save()
    call_command(
        "unskip_prospects",
        stdout=out,
        user=old_cambridge_assignment.user.email,
        run=True,
    )

    old_cambridge_assignment.refresh_from_db()
    assert old_cambridge_assignment.suppressed_at is not None
    assert old_cambridge_assignment.expired_at is not None
    assert old_cambridge_assignment.created_at == OLD_CREATED_DATE


@pytest.mark.django_db
def test_if_active_assignments_dont_unskip(
    old_cambridge_assignment, current_new_assignment
):
    out = StringIO()
    call_command(
        "unskip_prospects",
        stdout=out,
        user=old_cambridge_assignment.user.email,
        run=True,
    )

    old_cambridge_assignment.refresh_from_db()
    assert old_cambridge_assignment.suppressed_at is not None
    assert old_cambridge_assignment.expired_at is not None
    assert old_cambridge_assignment.created_at == OLD_CREATED_DATE
