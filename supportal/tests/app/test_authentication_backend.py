import pytest
from rest_framework.authentication import exceptions

from supportal.app.authentication_backend import CognitoJWTAuthentication, validate_jwt
from supportal.app.models import APIKey
from supportal.tests import utils

CLIENT_ID = "1234abcdef"


@pytest.fixture
def api_key(superuser):
    return APIKey.objects.create(client_id=CLIENT_ID, user=superuser)


@pytest.fixture
def backend():
    return CognitoJWTAuthentication()


@pytest.mark.django_db
def test_access_token_auth(rf, superuser, api_key, backend):
    token = utils.create_access_jwt(api_key.client_id)
    req = rf.get("/foo", HTTP_AUTHORIZATION=utils.auth_header(token))
    user, token_data = backend.authenticate(req)
    assert user == superuser
    assert token_data["client_id"] == CLIENT_ID


@pytest.mark.django_db
def test_id_token_auth(rf, user, backend):
    token = utils.create_id_jwt(user)
    req = rf.get("/foo", HTTP_AUTHORIZATION=utils.auth_header(token))
    res_user, token_data = backend.authenticate(req)
    assert res_user == user
    assert token_data["cognito:username"] == "testuser"


@pytest.mark.django_db
def test_that_kid_jwks_misalignment_throws_403(user):
    with pytest.raises(exceptions.AuthenticationFailed):
        assert validate_jwt(
            utils.create_id_jwt(user, key_id="this is not going to work")
        )


@pytest.mark.django_db
def test_inactive_users_fail_auth(rf, user, backend):
    user.is_active = False
    user.save()
    with pytest.raises(exceptions.AuthenticationFailed):
        token = utils.create_id_jwt(user)
        req = rf.get("/foo", HTTP_AUTHORIZATION=utils.auth_header(token))
        backend.authenticate(req)


@pytest.mark.django_db
def test_user_impersonation(rf, user, roslindale_leader_user, backend):
    user.is_admin = True
    user.impersonated_user = roslindale_leader_user
    user.save()
    u, _ = backend.authenticate(rf.get("/foo", **utils.id_auth(user)))
    assert u == roslindale_leader_user


@pytest.mark.django_db
def test_non_admins_cannot_impersonate(rf, user, roslindale_leader_user, backend):
    user.is_admin = False
    user.impersonated_user = roslindale_leader_user
    user.save()
    u, _ = backend.authenticate(rf.get("/foo", **utils.id_auth(user)))
    assert u != roslindale_leader_user
