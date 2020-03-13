import json
import unittest

import pytest
from django.conf import settings
from model_bakery import baker
from rest_framework import status

from supportal.app.common.enums import CanvassResult
from supportal.app.models import EmailSend, User, VolProspectAssignment
from supportal.app.models.user import UserManager
from supportal.tests import utils


@pytest.mark.django_db
def test_fails_with_no_input(api_client, supportal_admin_user):
    auth = utils.id_auth(supportal_admin_user)
    res = api_client.post(
        f"/v1/invites/", data=json.dumps({}), content_type="application/json", **auth
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_fails_with_invalid_email(api_client, supportal_admin_user):
    auth = utils.id_auth(supportal_admin_user)
    res = api_client.post(
        f"/v1/invites/",
        data=json.dumps({"email": "iamnotanemail"}),
        content_type="application/json",
        **auth,
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_invite_and_create_user(mocker, api_client, supportal_admin_user):
    email_to_send = "sgoldblatt@elizabethwarren.com"
    assert User.objects.filter(email=email_to_send).count() == 0
    auth = utils.id_auth(supportal_admin_user)

    mocker.patch.object(
        UserManager, "create_cognito_user", return_value={"User": {"Username": "12345"}}
    )

    with unittest.mock.patch(
        "supportal.app.models.user.get_email_service"
    ) as email_mock:
        res = api_client.post(
            f"/v1/invites/",
            data=json.dumps({"email": email_to_send}),
            content_type="application/json",
            **auth,
        )
        email_mock.return_value.send_email.assert_called_with(
            configuration_set_name="organizing_emails",
            from_email=settings.FROM_EMAIL,
            payload={
                "email": "sgoldblatt@elizabethwarren.com",
                "switchboard_signup_url": settings.SUPPORTAL_BASE_URL,
                "transactional": True,
            },
            recipient="sgoldblatt@elizabethwarren.com",
            reply_to_email=settings.REPLY_TO_EMAIL,
            template_name="switchboard_invite_email",
            application_name="supportal",
        )

    assert res.status_code == status.HTTP_201_CREATED
    users = User.objects.filter(email=email_to_send)
    assert users.count() == 1
    user = users.first()
    assert user.added_by == supportal_admin_user
    assert user.verified_at

    UserManager.create_cognito_user.assert_called_with(email_to_send)


@pytest.mark.django_db
@unittest.mock.patch("supportal.app.views.invite_views.get_email_service")
def test_invite_user_already_created(
    mock, api_client, cambridge_leader_user, hayes_valley_leader_user
):
    cambridge_leader_user.added_by = hayes_valley_leader_user
    cambridge_leader_user.save()

    assert not hayes_valley_leader_user.is_admin
    assert not hayes_valley_leader_user.is_staff
    assert not hayes_valley_leader_user.is_superuser

    for i in range(0, 10):
        vpa = baker.make("VolProspectAssignment", user=cambridge_leader_user)
        vpa.create_contact_event(
            result=CanvassResult.UNREACHABLE_MOVED, metadata={"moved_to": "CA"}
        )
        hvpa = baker.make("VolProspectAssignment", user=hayes_valley_leader_user)
        hvpa.create_contact_event(
            result=CanvassResult.UNREACHABLE_MOVED, metadata={"moved_to": "CA"}
        )

    email_to_send = cambridge_leader_user.email
    auth = utils.id_auth(hayes_valley_leader_user)

    res = api_client.post(
        f"/v1/invites/",
        data=json.dumps({"email": email_to_send}),
        content_type="application/json",
        **auth,
    )

    assert res.status_code == status.HTTP_204_NO_CONTENT
    assert User.objects.filter(email=email_to_send).count() == 1


@pytest.mark.django_db
@unittest.mock.patch("supportal.app.views.invite_views.get_email_service")
def test_invite_available(
    mock, api_client, cambridge_leader_user, hayes_valley_leader_user
):
    cambridge_leader_user.added_by = hayes_valley_leader_user
    cambridge_leader_user.save()

    assert not hayes_valley_leader_user.is_admin
    assert not hayes_valley_leader_user.is_staff
    assert not hayes_valley_leader_user.is_superuser

    email_to_send = cambridge_leader_user.email
    auth = utils.id_auth(hayes_valley_leader_user)

    res = api_client.get(f"/v1/invites/available/", **auth)

    assert res.status_code == status.HTTP_200_OK
    assert res.data["has_invite"] is False
    assert res.data["remaining_contacts_count"] == 10
    assert res.data["latest_invite"]["email"] == cambridge_leader_user.email
    assert res.data["latest_invite"]["remaining_contacts_count"] == 10

    for i in range(0, 15):
        vpa = baker.make("VolProspectAssignment", user=cambridge_leader_user)
        vpa.create_contact_event(
            result=CanvassResult.UNREACHABLE_MOVED, metadata={"moved_to": "CA"}
        )
        hvpa = baker.make("VolProspectAssignment", user=hayes_valley_leader_user)
        hvpa.create_contact_event(
            result=CanvassResult.UNREACHABLE_MOVED, metadata={"moved_to": "CA"}
        )

    res = api_client.get(f"/v1/invites/available/", **auth)

    assert res.status_code == status.HTTP_200_OK
    assert res.data["has_invite"]
    assert res.data["remaining_contacts_count"] == 0
    assert res.data["latest_invite"]["email"] == cambridge_leader_user.email
    assert res.data["latest_invite"]["remaining_contacts_count"] == 0


@pytest.mark.django_db
@unittest.mock.patch("supportal.app.views.invite_views.get_email_service")
def test_invite_cant_send(
    mock, api_client, cambridge_leader_user, hayes_valley_leader_user
):
    assert not hayes_valley_leader_user.is_admin
    assert not hayes_valley_leader_user.is_staff
    assert not hayes_valley_leader_user.is_superuser

    email_to_send = cambridge_leader_user.email
    auth = utils.id_auth(hayes_valley_leader_user)

    cambridge_leader_user.added_by = hayes_valley_leader_user
    cambridge_leader_user.save()

    res = api_client.post(
        f"/v1/invites/",
        data=json.dumps({"email": email_to_send}),
        content_type="application/json",
        **auth,
    )
    assert res.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_bulk_verify_view(
    api_client, supportal_admin_user, hayes_valley_leader_user, cambridge_leader_user
):
    hayes_valley_leader_user.verified_at = None
    cambridge_leader_user.verified_at = None
    hayes_valley_leader_user.save()
    cambridge_leader_user.save()

    auth = utils.id_auth(supportal_admin_user)
    with unittest.mock.patch(
        "supportal.app.views.invite_views.get_email_service"
    ) as email_mock:
        res = api_client.post(
            f"/v1/verify",
            data=json.dumps(
                {
                    "emails": [
                        hayes_valley_leader_user.email,
                        cambridge_leader_user.email,
                    ]
                }
            ),
            content_type="application/json",
            **auth,
        )
    assert res.status_code == status.HTTP_200_OK
    hayes_valley_leader_user.refresh_from_db()
    cambridge_leader_user.refresh_from_db()
    assert hayes_valley_leader_user.verified_at is not None
    assert cambridge_leader_user.verified_at is not None


@pytest.mark.django_db
def test_verify_view(api_client, supportal_admin_user, hayes_valley_leader_user):
    hayes_valley_leader_user.verified_at = None
    hayes_valley_leader_user.save()

    VolProspectAssignment.objects.assign(hayes_valley_leader_user)

    email_to_verify = hayes_valley_leader_user.email
    assert hayes_valley_leader_user.verified_at is None
    assert (
        hayes_valley_leader_user.vol_prospect_assignments.get_demo_queryset().count()
        == 10
    )
    assert (
        hayes_valley_leader_user.vol_prospect_assignments.filter(
            person__is_demo=False
        ).count()
        == 0
    )

    auth = utils.id_auth(supportal_admin_user)
    with unittest.mock.patch(
        "supportal.app.views.invite_views.get_email_service"
    ) as email_mock:
        res = api_client.post(
            f"/v1/verify",
            data=json.dumps({"email": email_to_verify}),
            content_type="application/json",
            **auth,
        )
        # call again because all these methods call twice
        api_client.post(
            f"/v1/verify",
            data=json.dumps({"email": email_to_verify}),
            content_type="application/json",
            **auth,
        )
    assert res.status_code == status.HTTP_200_OK

    email_mock.return_value.send_email.assert_called_once_with(
        configuration_set_name="organizing_emails",
        from_email=settings.FROM_EMAIL,
        payload={"email": email_to_verify, "transactional": True},
        recipient=email_to_verify,
        reply_to_email=settings.REPLY_TO_EMAIL,
        template_name=EmailSend.VERIFIED_EMAIL,
        application_name="supportal",
    )

    hayes_valley_leader_user.refresh_from_db()
    assert hayes_valley_leader_user.verified_at is not None
    assert (
        hayes_valley_leader_user.vol_prospect_assignments.get_demo_queryset().count()
        == 0
    )


@pytest.mark.django_db
def test_verify_view_non_admin(api_client, hayes_valley_leader_user):
    hayes_valley_leader_user.verified_at = None
    hayes_valley_leader_user.save()

    email_to_verify = hayes_valley_leader_user.email
    assert hayes_valley_leader_user.verified_at is None
    auth = utils.id_auth(hayes_valley_leader_user)
    res = api_client.post(
        f"/v1/verify",
        data=json.dumps({"email": email_to_verify}),
        content_type="application/json",
        **auth,
    )
    assert res.status_code == status.HTTP_403_FORBIDDEN
    hayes_valley_leader_user.refresh_from_db()
    assert hayes_valley_leader_user.verified_at is None


@pytest.mark.django_db
def test_verify_view_user_created(mocker, api_client, supportal_admin_user):
    email = "sgoldblatt-test@elizabethwarren.com"
    auth = utils.id_auth(supportal_admin_user)
    mocker.patch.object(
        UserManager, "create_cognito_user", return_value={"User": {"Username": "12345"}}
    )
    with unittest.mock.patch("supportal.app.views.invite_views.get_email_service"):
        res = api_client.post(
            f"/v1/verify",
            data=json.dumps({"email": email}),
            content_type="application/json",
            **auth,
        )
    assert res.status_code == status.HTTP_200_OK
    created_user = User.objects.get(email=email)
    assert created_user.verified_at is not None
