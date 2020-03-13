import pytest
from django.contrib.gis.geos import fromstr as geos_fromstr
from model_bakery import baker
from rest_framework import status

from supportal.app.models import Person
from supportal.app.serializers import FullPersonSerializer
from supportal.tests.utils import id_auth

CAMBRIDGE_LEADER_PAYLOAD = {
    "city": "Cambridge",
    "coordinates": "SRID=4326;POINT (-71.121898 42.39568)",
    "email": "marlenesmith@example.com",
    "first_name": "Marlene",
    "is_vol_leader": True,
    "is_vol_prospect": False,
    "last_name": "Smith",
    "middle_name": "",
    "myc_state_and_id": None,
    "ngp_id": "",
    "phone": "+16175555555",
    "address": "74 Winthrop St",
    "state": "MA",
    "suffix": "",
    "vol_yes_at": None,
    "zip5": "02138",
}

SOMERVILLE_PROSPECT_PAYLOAD = {
    "city": "Somerville",
    "coordinates": "SRID=4326;POINT (-71.081398 42.386637)",
    "email": "jkb@example.com",
    "first_name": "J",
    "is_vol_leader": False,
    "is_vol_prospect": True,
    "last_name": "",
    "middle_name": "",
    "myc_state_and_id": None,
    "ngp_id": "",
    "phone": "+",
    "address": "10 Fake St.",
    "state": "MA",
    "suffix": "",
    "vol_yes_at": "2019-10-13",
    "zip5": "02145",
}

CALIFORNIA_PROSPECT_PAYLOAD = {
    "city": "Richmond",
    "coordinates": "SRID=4326;POINT (-19 2.386383 37.921534)",
    "email": "r@example.com",
    "first_name": "R",
    "is_vol_leader": False,
    "is_vol_prospect": True,
    "last_name": "K",
    "middle_name": "",
    "myc_state_and_id": None,
    "ngp_id": "",
    "phone": "+",
    "address": "",
    "state": "CA",
    "suffix": "",
    "vol_yes_at": "2019-10-21",
    "zip5": "94801",
}


def assert_person_payloads_same(a, b):
    for k in a.keys():
        if k == "coordinates":
            point_a = geos_fromstr(a[k])
            point_b = geos_fromstr(b[k])
            assert pytest.approx(point_a.x, point_b.x)
            assert pytest.approx(point_a.y, point_b.y)
        elif k in {"id", "created_at", "updated_at"}:
            pass
        else:
            assert a[k] == b[k]


@pytest.mark.django_db
def test_list_unauthorized(api_client, cambridge_leader_user):
    resp = api_client.get("/v1/people/")

    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_list_fails_nonadmin(
    api_client, cambridge_leader_user, somerville_prospect, california_prospect
):
    resp = api_client.get("/v1/people/", **id_auth(cambridge_leader_user))

    assert resp.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_create_forbidden(api_client, cambridge_leader_user):
    payload = SOMERVILLE_PROSPECT_PAYLOAD
    resp = api_client.post("/v1/people/", payload, **id_auth(cambridge_leader_user))

    assert resp.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_create_one(api_client, superuser):
    payload = SOMERVILLE_PROSPECT_PAYLOAD
    resp = api_client.post("/v1/people/", payload, **id_auth(superuser))
    assert resp.status_code == status.HTTP_201_CREATED

    golden_person = FullPersonSerializer(
        baker.prepare_recipe("supportal.tests.somerville_prospect")
    ).data

    person = Person.objects.get(ngp_id="")
    assert_person_payloads_same(FullPersonSerializer(person).data, golden_person)


@pytest.mark.django_db
def test_update_one(api_client, superuser, somerville_prospect):
    count = Person.objects.filter(ngp_id="123456").count()
    payload = {**SOMERVILLE_PROSPECT_PAYLOAD, "phone": "+"}
    resp = api_client.post("/v1/people/", payload, **id_auth(superuser))
    assert resp.status_code == status.HTTP_201_CREATED

    count = Person.objects.filter(ngp_id="").count()
    person = Person.objects.get(ngp_id="")
    assert person.phone == "+"


@pytest.mark.django_db
def test_create_two_with_null_ngp_id(api_client, superuser):
    """Test that creation with null NGP id works as intended.

    i.e. no upsert, only create.
    """
    payload = {**SOMERVILLE_PROSPECT_PAYLOAD, "ngp_id": None}
    resp = api_client.post("/v1/people/", payload, **id_auth(superuser))
    assert resp.status_code == status.HTTP_201_CREATED

    payload = {**CALIFORNIA_PROSPECT_PAYLOAD, "ngp_id": None}
    resp = api_client.post("/v1/people/", payload, **id_auth(superuser))
    assert resp.status_code == status.HTTP_201_CREATED

    people = Person.objects.filter(ngp_id=None, is_demo=False).all()
    assert len(people) == 2


@pytest.mark.django_db
def test_create_many(api_client, superuser):
    payload = [
        CAMBRIDGE_LEADER_PAYLOAD,
        SOMERVILLE_PROSPECT_PAYLOAD,
        CALIFORNIA_PROSPECT_PAYLOAD,
    ]
    resp = api_client.post("/v1/people/", payload, **id_auth(superuser))

    golden_cambridge_leader = FullPersonSerializer(
        baker.prepare_recipe("supportal.tests.cambridge_leader")
    ).data
    golden_somerville_prospect = FullPersonSerializer(
        baker.prepare_recipe("supportal.tests.somerville_prospect")
    ).data
    golden_california_prospect = FullPersonSerializer(
        baker.prepare_recipe("supportal.tests.california_prospect")
    ).data

    assert_person_payloads_same(
        FullPersonSerializer(
            Person.objects.get(ngp_id=golden_cambridge_leader["ngp_id"])
        ).data,
        golden_cambridge_leader,
    )
    assert_person_payloads_same(
        FullPersonSerializer(
            Person.objects.get(ngp_id=golden_somerville_prospect["ngp_id"])
        ).data,
        golden_somerville_prospect,
    )
    assert_person_payloads_same(
        FullPersonSerializer(
            Person.objects.get(ngp_id=golden_california_prospect["ngp_id"])
        ).data,
        golden_california_prospect,
    )
