from datetime import datetime, timezone

import pytest
from model_bakery import baker

from supportal.app.common.enums import CanvassResult
from supportal.app.models import User


@pytest.mark.django_db
def test_create_normal_user(cambridge_leader):
    """Normal users should be created without usable passwords"""
    u = User.objects.create_user(
        "someusernamethatwedontcareabout",
        cambridge_leader.email,
        skip_cognito=True,
        first_name=cambridge_leader.first_name,
        last_name=cambridge_leader.last_name,
        phone=cambridge_leader.phone,
        address="123 Different St.",
        city="Different city",
        state="MA",
        zip5="12345",
        is_admin=False,
        self_reported_team_name="People who have inconsistent data",
        person=cambridge_leader,
        verified_at=datetime.now(tz=timezone.utc),
    )
    u.save()
    assert not u.has_usable_password()
    assert u.person.id == cambridge_leader.id
    assert u.assignment_contacts_count == 0
    assert u.has_invite is False
    assert u.is_admin is False
    assert u.is_staff is False


@pytest.mark.django_db
def test_create_ew_email_user(cambridge_leader):
    """Normal users should be created without usable passwords"""
    u = User.objects.create_user(
        "someusernamethatwedontcareabout",
        "sgoldblatt@elizabethwarren.com",
        skip_cognito=True,
        first_name=cambridge_leader.first_name,
        last_name=cambridge_leader.last_name,
        phone=cambridge_leader.phone,
        address="123 Different St.",
        city="Different city",
        state="MA",
        zip5="12345",
        self_reported_team_name="People who have inconsistent data",
    )
    u.save()
    assert not u.has_usable_password()
    assert u.assignment_contacts_count == 0
    assert u.is_admin
    assert u.is_staff
    assert u.is_superuser is False


@pytest.mark.django_db
def test_assignment_contact_count(cambridge_leader_user):
    assert cambridge_leader_user.assignment_contacts_count == 0
    vpa_unreachable = baker.make("VolProspectAssignment", user=cambridge_leader_user)
    vpa_unreachable.create_contact_event(
        result=CanvassResult.UNREACHABLE_MOVED, metadata={"moved_to": "CA"}
    )
    vpa_unavailable = baker.make("VolProspectAssignment", user=cambridge_leader_user)
    vpa_unavailable.create_contact_event(result=CanvassResult.UNAVAILABLE_CALL_BACK)
    vpa_unavailable.create_contact_event(result=CanvassResult.UNAVAILABLE_CALL_BACK)
    vpa_successful = baker.make("VolProspectAssignment", user=cambridge_leader_user)
    vpa_successful.create_contact_event(result=CanvassResult.SUCCESSFUL_CANVASSED)
    baker.make(
        "VolProspectAssignment",
        user=cambridge_leader_user,
        suppressed_at=datetime.now(tz=timezone.utc),
    )
    baker.make(
        "VolProspectAssignment",
        user=cambridge_leader_user,
        expired_at=datetime.now(tz=timezone.utc),
    )
    assert cambridge_leader_user.assignment_contacts_count == 3


@pytest.mark.django_db
def test_has_invite(
    cambridge_leader_user,
    hayes_valley_leader_user,
    mattapan_leader_user,
    roslindale_leader_user,
):
    assert hayes_valley_leader_user.has_invite is False
    cambridge_leader_user.added_by = hayes_valley_leader_user
    cambridge_leader_user.created_at = datetime.now(tz=timezone.utc)
    cambridge_leader_user.save()
    assert cambridge_leader_user.assignment_contacts_count == 0
    assert hayes_valley_leader_user.has_invite is False

    for i in range(0, 10):
        hvpa = baker.make("VolProspectAssignment", user=hayes_valley_leader_user)
        hvpa.create_contact_event(
            result=CanvassResult.UNREACHABLE_MOVED, metadata={"moved_to": "CA"}
        )
    assert hayes_valley_leader_user.has_invite is False

    for i in range(0, 10):
        vpa = baker.make("VolProspectAssignment", user=cambridge_leader_user)
        vpa.create_contact_event(result=CanvassResult.SUCCESSFUL_CANVASSED)

    assert hayes_valley_leader_user.assignment_contacts_count == 10
    assert hayes_valley_leader_user.has_invite

    for i in range(0, 2):
        mattapan_leader_user.added_by = hayes_valley_leader_user
        mattapan_leader_user.created_at = datetime.now(tz=timezone.utc)
        mattapan_leader_user.save()
        roslindale_leader_user.added_by = hayes_valley_leader_user
        roslindale_leader_user.created_at = datetime.now(tz=timezone.utc)
        roslindale_leader_user.save()

    hayes_valley_leader_user.refresh_from_db()
    assert hayes_valley_leader_user.has_invite is False


@pytest.mark.django_db
def test_last_login_does_not_update_on_save(mattapan_leader_user):
    previous_updated_at = mattapan_leader_user.updated_at
    previous_last_login = mattapan_leader_user.last_login

    mattapan_leader_user.first_name = "Apple"
    mattapan_leader_user.save()

    mattapan_leader_user.refresh_from_db()
    assert mattapan_leader_user.last_login == previous_last_login
    assert mattapan_leader_user.updated_at > previous_updated_at


@pytest.mark.django_db
def test_last_login_updates_on_login(client, user, auth):
    assert user.last_login is None
    res = client.get("/v1/me", **auth)
    assert res.status_code == 200

    user.refresh_from_db()
    assert user.last_login


@pytest.mark.django_db
def test_create_superuser():
    """Superusers should have usable passwords for admin access"""
    u = User.objects.create_superuser(
        "superuser",
        "superuser@fake.com",
        "My Super Secure P@ssw0rd!",
        skip_cognito=True,
        first_name="Abba",
        last_name="Zaba",
    )
    u.save()
    assert u.has_usable_password()
    assert u.person is None


@pytest.mark.django_db
def test_lower_case_email_address():
    u = User.objects.create_user(
        "some_user", "LowerCaseMe@example.com", skip_cognito=True
    )
    u.save()
    assert u.email == "lowercaseme@example.com"
