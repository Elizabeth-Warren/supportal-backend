import datetime
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone
from model_bakery import baker

from supportal.app.common.enums import CanvassResult


def expire_assignments(*args, **kwargs):
    call_command("expire_assignments", **kwargs)


@pytest.fixture
def old_cambridge_assignment(cambridge_leader_user, cambridge_prospect):
    cambridge_assignment = baker.make(
        "VolProspectAssignment", user=cambridge_leader_user, person=cambridge_prospect
    )
    cambridge_assignment.created_at = datetime.datetime(
        2019, 10, 26, tzinfo=timezone.utc
    )
    cambridge_assignment.save()
    assert cambridge_assignment.expired_at is None
    return cambridge_assignment


@pytest.mark.django_db
def test_expire_uncontacted_assignments(old_cambridge_assignment):
    out = StringIO()
    expire_assignments(stdout=out)
    old_cambridge_assignment.refresh_from_db()

    assert old_cambridge_assignment.expired_at is not None
    assert "Expired 1 assignments." in out.getvalue()


@pytest.mark.django_db
def test_expire_unsuccessfully_contacted_assignments(old_cambridge_assignment):
    old_cambridge_assignment.create_contact_event(
        result=CanvassResult.UNAVAILABLE_LEFT_MESSAGE
    )
    old_cambridge_assignment.save()
    out = StringIO()
    expire_assignments(stdout=out)

    old_cambridge_assignment.refresh_from_db()
    assert old_cambridge_assignment.expired_at is not None
    assert "Expired 1 assignments." in out.getvalue()


@pytest.mark.django_db
def test_successfully_contacted_dont_expire(old_cambridge_assignment):
    # Make sure that having a previous unsuccessful contact event doesn't cause
    # the contact to get expired.
    old_cambridge_assignment.create_contact_event(
        result=CanvassResult.UNAVAILABLE_LEFT_MESSAGE
    )
    old_cambridge_assignment.create_contact_event(
        result=CanvassResult.SUCCESSFUL_CANVASSED
    )

    old_cambridge_assignment.save()
    out = StringIO()
    expire_assignments(stdout=out)
    old_cambridge_assignment.refresh_from_db()

    assert old_cambridge_assignment.expired_at is None
    assert "Expired 0 assignments." in out.getvalue()


@pytest.mark.django_db
def test_expire_zero_assignments():
    out = StringIO()
    expire_assignments(stdout=out)
    assert "Expired 0 assignments." in out.getvalue()
