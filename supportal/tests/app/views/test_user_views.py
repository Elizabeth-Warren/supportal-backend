import datetime

import freezegun
import pytest
import responses
from django.utils import timezone

from supportal.app.common.enums import ActivityStatus
from supportal.app.models.user import User, UserManager
from supportal.tests import utils


def _test_create_user_operation(
    client, request_user_object, request_user, user_to_create, user_email, monkeypatch
):
    user_payload = {
        "email": user_email,
        "first_name": user_to_create.first_name,
        "last_name": user_to_create.last_name,
        "address": user_to_create.address,
        "person": user_to_create.id,
    }

    # Create
    # Until we have a better way of mocking Cognito in tests, mokeypatch
    # the create_cognito_user method on the user manager
    monkeypatch.setattr(
        UserManager,
        "create_cognito_user",
        lambda self, e: {"User": {"Username": "12345"}},
    )
    create_res = client.post("/v1/users/", data=user_payload, **request_user)
    assert create_res.status_code == 201
    assert create_res.data["added_by"]["id"] == request_user_object.id
    user_id = create_res.data["id"]
    assert User.objects.get(id=user_id).verified_at is not None
    return user_id


def _test_read_user_operation(
    client,
    request_user,
    user_to_create,
    user_id,
    active_user_id,
    churning_user_id,
    innactive_user_id,
):
    # Read
    get_res = client.get(f"/v1/users/{user_id}/", **request_user)
    assert get_res.status_code == 200
    assert get_res.data["email"] == "newuser@example.com"
    assert get_res.data["activity_status"] == ActivityStatus.NEW

    # List
    with freezegun.freeze_time("2019-10-13T22:23:24Z"):
        list_res = client.get("/v1/users/", **request_user)
        assert list_res.status_code == 200
        full_get_list = list_res.data["results"]
        assert len(full_get_list) >= 2
        assert user_id in [u["id"] for u in full_get_list]

        # activity_status active for users who logged in < 7 days ago
        for u in full_get_list:
            if u["id"] == active_user_id:
                assert u["activity_status"] == ActivityStatus.ACTIVE

        # is_active_user false for users who logged in > 7 days ago
        for u in full_get_list:
            if u["id"] == churning_user_id:
                assert u["activity_status"] == ActivityStatus.CHURNING

        # is_active_user false for users who logged in < 14 days ago
        for u in full_get_list:
            if u["id"] == innactive_user_id:
                assert u["activity_status"] == ActivityStatus.INACTIVE


def _test_update_user_operation(client, request_user, user_id, user_email):
    # Update via PATCH
    patch_res = client.patch(
        f"/v1/users/{user_id}/",
        data={"first_name": "Maggie"},
        content_type="application/json",
        **request_user,
    )
    assert patch_res.status_code == 200
    assert patch_res.data["id"] == user_id
    assert patch_res.data["first_name"] == "Maggie"

    # Update via POST
    post_update_res = client.post(
        f"/v1/users/",
        data={"email": user_email, "first_name": "Marge"},
        content_type="application/json",
        **request_user,
    )
    assert post_update_res.status_code == 201
    assert post_update_res.data["id"] == user_id
    assert post_update_res.data["email"] == User.objects.normalize_email(user_email)
    assert post_update_res.data["first_name"] == "Marge"


def _test_delete_user_operation(client, user):
    # Delete
    assert user.is_active
    del_res = client.delete(f"/v1/users/{user.id}/", **utils.id_auth(user))
    assert del_res.status_code == 204

    user.refresh_from_db()
    assert not user.is_active
    get_res = client.get(f"/v1/users/{user.id}/", **utils.id_auth(user))
    assert get_res.status_code == 401


def _test_crud_user_operation(
    client,
    user_object,
    request_user,
    user_to_create,
    active_user_id,
    churning_user_id,
    innactive_user_id,
    monkeypatch,
):
    email = "NewUser@Example.com"
    created_user_id = _test_create_user_operation(
        client, user_object, request_user, user_to_create, email, monkeypatch
    )
    _test_read_user_operation(
        client,
        request_user,
        user_to_create,
        created_user_id,
        active_user_id,
        churning_user_id,
        innactive_user_id,
    )
    _test_update_user_operation(client, request_user, created_user_id, email)
    _test_delete_user_operation(client, user_object)


@pytest.mark.django_db
def test_adding_demo_user(client, supportal_admin_user, monkeypatch):
    email = "newemail+test@example.com"
    user_payload = {
        "email": email,
        "first_name": "Susan",
        "last_name": "",
        "address": "123 Fake St, Somerville MA 941045",
        "is_mobilize_america_signup": True,
    }

    # Create
    # Until we have a better way of mocking Cognito in tests, mokeypatch
    # the create_cognito_user method on the user manager
    monkeypatch.setattr(
        UserManager,
        "create_cognito_user",
        lambda self, e: {"User": {"Username": "12345"}},
    )
    create_res = client.post(
        "/v1/users/",
        data=user_payload,
        **utils.id_auth(supportal_admin_user),
        content_type="application/json",
    )
    assert create_res.status_code == 201
    user = User.objects.get_user_by_email(email)
    assert user.verified_at is None


@pytest.mark.django_db
def test_bulk_adding_user(client, supportal_admin_user, monkeypatch):
    email = "newemail+test@example.com"
    assert (
        User.objects.filter(email__in=[supportal_admin_user.email, email]).count() == 1
    )
    user_payload = [
        {
            "email": "bad",
            "first_name": "Susan",
            "last_name": "",
            "address": "123 Fake St, Somerville MA 941045",
            "is_mobilize_america_signup": True,
        },
        {
            "email": email,
            "first_name": "Susan",
            "last_name": "",
            "address": "123 Fake St, Somerville MA 941045",
            "is_mobilize_america_signup": True,
        },
        {
            "email": supportal_admin_user.email,
            "first_name": "Susan",
            "last_name": "",
            "address": "123 Fake St, Somerville MA 941045",
            "is_mobilize_america_signup": False,
        },
    ]

    # Create
    # Until we have a better way of mocking Cognito in tests, mokeypatch
    # the create_cognito_user method on the user manager
    monkeypatch.setattr(
        UserManager,
        "create_cognito_user",
        lambda self, e: {"User": {"Username": "12345"}},
    )
    create_res = client.post(
        "/v1/users/",
        data=user_payload,
        **utils.id_auth(supportal_admin_user),
        content_type="application/json",
    )

    assert create_res.data[0]["error"] and create_res.data[0]["email"] == "bad"
    assert (User.objects.filter(email="bad").count()) == 0
    assert create_res.status_code == 201
    user = User.objects.get_user_by_email(email)
    assert user.verified_at is None
    assert (
        User.objects.filter(email__in=[supportal_admin_user.email, email]).count() == 2
    )


@pytest.mark.django_db
def test_adding_demo_user_already_exists(
    client, supportal_admin_user, cambridge_leader_user, monkeypatch
):
    assert cambridge_leader_user.verified_at is not None
    user_payload = {
        "email": cambridge_leader_user.email,
        "first_name": "Susan",
        "last_name": "",
        "address": "123 Fake St, Somerville MA 941045",
        "is_mobilize_america_signup": True,
    }

    # Create
    # Until we have a better way of mocking Cognito in tests, mokeypatch
    # the create_cognito_user method on the user manager
    monkeypatch.setattr(
        UserManager,
        "create_cognito_user",
        lambda self, e: {"User": {"Username": "12345"}},
    )
    create_res = client.post(
        "/v1/users/",
        data=user_payload,
        **utils.id_auth(supportal_admin_user),
        content_type="application/json",
    )
    assert create_res.status_code == 201
    cambridge_leader_user.refresh_from_db
    assert cambridge_leader_user.verified_at is not None


@pytest.mark.django_db
def test_adding_non_demo_user(client, supportal_admin_user, monkeypatch):
    email = "newemail+test2@example.com"
    user_payload = {
        "email": email,
        "first_name": "Susan",
        "last_name": "",
        "address": "123 Fake St, Somerville MA 941045",
        "is_mobilize_america_signup": False,
    }

    # Create
    # Until we have a better way of mocking Cognito in tests, mokeypatch
    # the create_cognito_user method on the user manager
    monkeypatch.setattr(
        UserManager,
        "create_cognito_user",
        lambda self, e: {"User": {"Username": "12345"}},
    )
    create_res = client.post(
        "/v1/users/",
        data=user_payload,
        **utils.id_auth(supportal_admin_user),
        content_type="application/json",
    )
    assert create_res.status_code == 201
    user = User.objects.get_user_by_email(email)
    assert user.verified_at is not None


@pytest.mark.django_db
def test_admin_list_pagination(
    client, supportal_admin_user, cambridge_leader_user, mattapan_leader_user
):
    cambridge_leader_user.created_at = timezone.now()
    cambridge_leader_user.save()

    mattapan_leader_user.created_at = timezone.now() - datetime.timedelta(days=1)
    mattapan_leader_user.save()

    supportal_admin_user.created_at = timezone.now() - datetime.timedelta(days=2)
    supportal_admin_user.save()

    # List First Page
    list_res = client.get(
        "/v1/users/?page=1&page_size=1", **utils.id_auth(supportal_admin_user)
    )
    assert list_res.status_code == 200
    full_get_list = list_res.data["results"]
    assert len(full_get_list) == 1
    assert cambridge_leader_user.id == full_get_list[0]["id"]

    # List Second Page
    second_list_res = client.get(
        list_res.data["next"], **utils.id_auth(supportal_admin_user)
    )
    assert second_list_res.status_code == 200
    full_get_list = second_list_res.data["results"]
    assert len(full_get_list) == 1
    assert mattapan_leader_user.id == full_get_list[0]["id"]


@pytest.mark.django_db
def test_admin_list_user_ordering(
    client,
    supportal_admin_user,
    cambridge_leader_user,
    mattapan_leader_user,
    hayes_valley_leader_user,
):
    # List
    with freezegun.freeze_time("2019-10-13T22:23:24Z"):
        # List first page and state filter
        list_res = client.get(
            "/v1/users/?ordering=-state,email", **utils.id_auth(supportal_admin_user)
        )
        assert list_res.status_code == 200
        full_get_list = list_res.data["results"]
        assert len(full_get_list) == 4
        result_ids = [
            mattapan_leader_user.id,
            cambridge_leader_user.id,
            hayes_valley_leader_user.id,
            supportal_admin_user.id,
        ]
        for i, user in enumerate(full_get_list):
            assert result_ids[i] == user["id"]


@pytest.mark.django_db
def test_admin_list_user_doesnt_include_inactive(
    client,
    supportal_admin_user,
    cambridge_leader_user,
    mattapan_leader_user,
    hayes_valley_leader_user,
):

    client.delete(
        f"/v1/users/{cambridge_leader_user.id}/", **utils.id_auth(supportal_admin_user)
    )

    # List first page and state filter
    list_res = client.get(
        "/v1/users/?ordering=-state,email", **utils.id_auth(supportal_admin_user)
    )
    assert list_res.status_code == 200
    full_get_list = list_res.data["results"]
    assert len(full_get_list) == 3
    assert cambridge_leader_user.id not in [u["id"] for u in full_get_list]


@pytest.mark.django_db
def test_admin_user_meta(
    client,
    supportal_admin_user,
    cambridge_leader_user,
    mattapan_leader_user,
    hayes_valley_leader_user,
):
    hayes_valley_leader_user.is_active = False
    hayes_valley_leader_user.save()

    # List first page and state filter
    meta_res = client.get("/v1/users/meta/", **utils.id_auth(supportal_admin_user))
    assert meta_res.status_code == 200
    assert meta_res.data["all"]["count"] == 3
    assert len(meta_res.data["states"]) == 2
    assert meta_res.data["states"][0]["state"] == ""
    assert meta_res.data["states"][0]["count"] == 1
    assert meta_res.data["states"][1]["state"] == "MA"
    assert meta_res.data["states"][1]["count"] == 2


@pytest.mark.django_db
def test_admin_list_user_filter_and_pagination(
    client,
    auth_supportal_admin_user,
    cambridge_leader_user,
    mattapan_leader_user,
    hayes_valley_leader_user,
):
    cambridge_leader_user.created_at = timezone.now()
    cambridge_leader_user.save()

    mattapan_leader_user.created_at = timezone.now() - datetime.timedelta(days=1)
    mattapan_leader_user.save()

    # List
    with freezegun.freeze_time("2019-10-13T22:23:24Z"):
        # List first page and state filter
        list_res = client.get(
            "/v1/users/?state=MA&page=1&page_size=1", **auth_supportal_admin_user
        )
        assert list_res.status_code == 200
        full_get_list = list_res.data["results"]
        assert len(full_get_list) == 1
        assert cambridge_leader_user.id in [u["id"] for u in full_get_list]

        # List second page with state filter
        filtered_list_res = client.get(
            list_res.data["next"], **auth_supportal_admin_user
        )
        assert filtered_list_res.status_code == 200
        full_get_list = filtered_list_res.data["results"]
        assert len(full_get_list) == 1  # auth_supportal_admin_user has no state
        assert mattapan_leader_user.id in [u["id"] for u in full_get_list]

        # There is no third page
        assert filtered_list_res.data["next"] is None


@pytest.mark.django_db
def test_admin_list_user_filter(
    client,
    auth_supportal_admin_user,
    cambridge_leader_user,
    mattapan_leader_user,
    hayes_valley_leader_user,
):
    # List
    with freezegun.freeze_time("2019-10-13T22:23:24Z"):
        # List Full Page
        list_res = client.get("/v1/users/", **auth_supportal_admin_user)
        assert list_res.status_code == 200
        full_get_list = list_res.data["results"]
        assert len(full_get_list) == 4
        assert hayes_valley_leader_user.id in [u["id"] for u in full_get_list]

        # List with state Filter
        filtered_list_res = client.get(
            "/v1/users/?state=MA", **auth_supportal_admin_user
        )
        assert filtered_list_res.status_code == 200
        full_get_list = filtered_list_res.data["results"]
        assert len(full_get_list) == 2  # auth_supportal_admin_user has no state
        assert hayes_valley_leader_user.id not in [u["id"] for u in full_get_list]
        assert cambridge_leader_user.id in [u["id"] for u in full_get_list]


@pytest.mark.django_db
def test_admin_crud_operations_on_users(
    client,
    supportal_admin_user,
    auth_supportal_admin_user,
    cambridge_leader,
    mattapan_leader_user,
    roslindale_leader_user,
    hayes_valley_leader_user,
    monkeypatch,
):
    """/v1/users: supportal admins can perform all CRUD operations """
    _test_crud_user_operation(
        client,
        supportal_admin_user,
        auth_supportal_admin_user,
        cambridge_leader,
        mattapan_leader_user.id,
        roslindale_leader_user.id,
        hayes_valley_leader_user.id,
        monkeypatch,
    )


@pytest.mark.django_db
def test_normal_user_cannot_access_user_api(api_client, user, auth):
    """/v1/users: normal users can't access the /v1/users api at all"""
    other_user_payload = {
        "email": "newuser2@example.com",
        "first_name": "Dont",
        "last_name": "CreateMe",
    }
    create_res = api_client.post("/v1/users/", data=other_user_payload, **auth)
    assert create_res.status_code == 403
    read_res = api_client.get(f"/v1/users/{user.id}/", **auth)
    assert read_res.status_code == 403
    list_res = api_client.get(f"/v1/users/", **auth)
    assert list_res.status_code == 403
    patch_res = api_client.patch(
        f"/v1/users/{user.id}/",
        data={"first_name": "Maggie"},
        content_type="application/json",
        **auth,
    )
    assert patch_res.status_code == 403
    del_res = api_client.delete(f"/v1/users/{user.id}/", **auth)
    assert del_res.status_code == 403


@pytest.mark.django_db
def test_normal_user_me_endpoint(client, user, auth):
    """/me: users can access their own information"""
    get_res = client.get("/v1/me", **auth)
    assert get_res.status_code == 200
    assert get_res.data["id"] == user.id
    assert get_res.data["email"] == user.email
    assert get_res.data["is_admin"] == user.is_admin


@pytest.mark.django_db
def test_impersonated_me_api_call(client, user, roslindale_leader_user):
    """/me: users can access their own information"""
    user.is_admin = True
    user.impersonated_user = roslindale_leader_user
    user.save()
    res = client.get("/v1/me", **utils.id_auth(user))
    assert res.status_code == 200
    assert res.data["email"] != user.email
    assert res.data["email"] == roslindale_leader_user.email


@pytest.mark.django_db
def test_normal_user_can_update_self(client, user, auth):
    """/me: users can update their own info"""
    new_address = "NewAddr"
    assert user.address != new_address
    client.patch(
        f"/v1/me",
        data={"address": new_address},
        content_type="application/json",
        **auth,
    )
    user.refresh_from_db()
    assert user.address == new_address


@pytest.mark.django_db
def test_normal_user_cannot_update_email(client, user, auth):
    """/me: users can update cannot update their email address"""
    new_email = "otheremail@example.com"
    old_email = user.email
    client.patch(
        f"/v1/me", data={"email": new_email}, content_type="application/json", **auth
    )
    user.refresh_from_db()
    assert user.email == old_email


@pytest.mark.django_db
def test_normal_user_cannot_update_is_admin(client, user, auth):
    """/me: users can update cannot update their admin status"""
    client.patch(
        f"/v1/me", data={"is_admin": True}, content_type="application/json", **auth
    )
    user.refresh_from_db()
    assert user.is_admin is False


@pytest.mark.django_db
def test_superuser_cannot_update_email_through_rest_api(client, user, auth_superuser):
    new_email = "otheremail@example.com"
    old_email = user.email
    res = client.patch(
        f"/v1/users/{user.id}/",
        data={"email": new_email},
        content_type="application/json",
        **auth_superuser,
    )
    assert res.status_code == 400
    user.refresh_from_db()
    assert user.email == old_email


@pytest.mark.django_db
def test_update_phone_number_formats(client, user, auth):
    client.patch(
        f"/v1/me",
        data={"phone": ""},
        content_type="application/json",
        **auth,
    )
    user.refresh_from_db()
    assert user.phone == "+"


@pytest.mark.django_db
@responses.activate  # Just to make sure there are no live HTTP requests
def test_geocode_address(mocker, client, user, auth):
    mock_location = {"lat": 42.3865482, "lng": -71.0817715}
    mocker.patch(
        "supportal.app.serializers.user_serializers.geocode", return_value=mock_location
    )
    res = client.patch(
        f"/v1/me",
        data={
            "address": "10 Fake St.",
            "city": "Somerville",
            "state": "MA",
            "zip5": "02145",
        },
        content_type="application/json",
        **auth,
    )

    user.refresh_from_db()
    assert pytest.approx(user.coordinates.x, mock_location["lng"])
    assert pytest.approx(user.coordinates.y, mock_location["lat"])


@pytest.mark.django_db
@responses.activate
def test_geocode_address_failure(mocker, client, user, auth):
    mocker.patch(
        "supportal.app.serializers.user_serializers.geocode", return_value=None
    )
    res = client.patch(
        f"/v1/me",
        data={"address": "oogle boogle", "zip5": "02145"},
        content_type="application/json",
        **auth,
    )
    assert res.status_code == 400
