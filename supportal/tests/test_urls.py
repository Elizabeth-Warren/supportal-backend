import pytest

from supportal.tests import utils


@pytest.mark.django_db
def test_index_auth(client):
    """The index (/) endpoint does not require authentication"""
    res = client.get("/")
    assert res.status_code == 200


@pytest.mark.django_db
def test_me_fails_no_token(client):
    """/me fails if not authenticated"""
    res = client.get("/v1/me")
    assert res.status_code == 401


@pytest.mark.django_db
def test_me_fails_invalid_token(client, user):
    """/me fails if receiving an expired token"""
    token = utils.create_id_jwt(user, expires_in_seconds=-100)
    res = client.get("/v1/me", HTTP_AUTHORIZATION=utils.auth_header(token))
    assert res.status_code == 401


@pytest.mark.django_db
def test_me_success(client, auth):
    """/me succeeds if properly authenticated"""
    res = client.get("/v1/me", **auth)
    assert res.status_code == 200
