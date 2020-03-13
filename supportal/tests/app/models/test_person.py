import pytest
from django.contrib.gis.geos import Point
from model_bakery import baker

from supportal.app.models import Person


@pytest.mark.django_db
def test_full_name(somerville_prospect):
    assert somerville_prospect.full_name == ""


@pytest.mark.django_db
def test_trimmed_name(somerville_prospect):
    assert somerville_prospect.trimmed_last_name() == "K."


@pytest.mark.django_db
def test_coordinates(somerville_prospect):
    assert somerville_prospect.coordinates == Point(-71.081398, 42.386637, srid=4326)


@pytest.mark.django_db
def test_coordinates_serialize_deserialize_to_from_db(somerville_prospect):
    fetched_person = Person.objects.get(pk=somerville_prospect.id)
    assert fetched_person.coordinates == Point(-71.081398, 42.386637, srid=4326)


@pytest.mark.django_db
def test_from_reference(
    cambridge_leader, cambridge_prospect, somerville_prospect, california_prospect
):
    result = (
        Person.objects.from_reference(cambridge_leader.coordinates, radius_mi=100)
        .exclude(pk=cambridge_leader.pk)
        .all()
    )

    # Result is ordered with nearest first. Does not include the prospect in
    # California, which is too far away.
    assert [x.city for x in result] == ["Cambridge", "Somerville"]


@pytest.mark.django_db
def test_null_coordinates():
    locationless_person = baker.make("Person", coordinates=None)
    fetched_person = Person.objects.get(pk=locationless_person.id)
    assert fetched_person.coordinates is None
