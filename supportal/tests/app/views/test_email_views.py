import json

import pytest
from rest_framework import status


@pytest.mark.django_db
def test_unsubscribes_user(api_client, supportal_admin_user):
    assert supportal_admin_user.unsubscribed_at is None
    res = api_client.post(
        f"/v1/unsubscribe",
        data=json.dumps({"email": supportal_admin_user.email}),
        content_type="application/json",
    )

    supportal_admin_user.refresh_from_db()
    assert supportal_admin_user.unsubscribed_at is not None
    assert res.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_fails_to_unsubscribe_non_existant_user(api_client, supportal_admin_user):
    assert supportal_admin_user.unsubscribed_at is None
    res = api_client.post(
        f"/v1/unsubscribe",
        data=json.dumps({"email": "fake-random-fake@fake.com"}),
        content_type="application/json",
    )

    supportal_admin_user.refresh_from_db()
    assert supportal_admin_user.unsubscribed_at is None
    assert res.status_code == status.HTTP_400_BAD_REQUEST
