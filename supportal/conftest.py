import json
import os
import time

import pytest
from django.conf import settings
from django.contrib.gis.geos import Point
from django.core.serializers.json import DjangoJSONEncoder
from django.forms import model_to_dict
from model_bakery import baker
from nplusone.core import profiler
from rest_framework.test import APIClient

from supportal.app.common.enums import CanvassResult
from supportal.app.models import User
from supportal.settings import BASE_DIR
from supportal.shifter.models import USZip5
from supportal.tests import utils
from supportal.tests.baker_recipes import set_mobilize_america_event_raw

with open(os.path.join(BASE_DIR, "supportal", "tests", "jwk_rsa_pub.json")) as f:
    JWK_PUBLIC_KEY = json.load(f)

COGNITO_USER_POOL_JWKS = {"keys": [JWK_PUBLIC_KEY]}

# Avoid cache collisions by giving each test run a unique prefix
settings.CACHES["default"]["KEY_PREFIX"] = f"{int(time.time())}-test-supportal"
settings.SHIFTER_IP_RATE_LIMIT = "100/min"


@pytest.fixture(autouse=True)
def jwks_setup(mocker):
    mocker.patch(
        "supportal.app.authentication_backend.get_jwks",
        return_value=COGNITO_USER_POOL_JWKS,
    )


@pytest.fixture(autouse=True)
def no_nplusone():
    """Raise an exception on any nplusone query in any test."""
    with profiler.Profiler():
        yield


def _user(**extra_fields):
    return User.objects.create_user(
        "testuser", "fake@fake.com", skip_cognito=True, **extra_fields
    )


def _superuser():
    return User.objects.create_superuser(
        "super", "superfake@fake.com", "password2", skip_cognito=True
    )


@pytest.fixture()
def user():
    return _user()


@pytest.fixture()
def supportal_admin_user():
    return _user(is_admin=True)


@pytest.fixture
def superuser():
    return _superuser()


@pytest.fixture()
def auth(user):
    return utils.id_auth(user)


@pytest.fixture()
def auth_supportal_admin_user(supportal_admin_user):
    return utils.id_auth(supportal_admin_user)


@pytest.fixture()
def auth_superuser(superuser):
    return utils.id_auth(superuser)


@pytest.fixture()
def api_client():
    return APIClient()


@pytest.fixture
def mattapan_leader():
    return baker.make_recipe("supportal.tests.mattapan_leader")


@pytest.fixture
def roslindale_leader():
    return baker.make_recipe("supportal.tests.roslindale_leader")


@pytest.fixture
def norwood_prospect():
    return baker.make_recipe("supportal.tests.norwood_prospect")


@pytest.fixture
def roslindale_prospect():
    return baker.make_recipe("supportal.tests.roslindale_prospect")


@pytest.fixture
def jamaica_plain_prospect():
    return baker.make_recipe("supportal.tests.jamaica_plain_prospect")


@pytest.fixture
def west_roxbury_prospect():
    return baker.make_recipe("supportal.tests.west_roxbury_prospect")


@pytest.fixture
def cambridge_leader():
    return baker.make_recipe("supportal.tests.cambridge_leader")


@pytest.fixture
def cambridge_prospect():
    return baker.make_recipe("supportal.tests.cambridge_prospect")


@pytest.fixture
def somerville_prospect():
    return baker.make_recipe("supportal.tests.somerville_prospect")


@pytest.fixture
def medford_prospect():
    return baker.make_recipe("supportal.tests.medford_prospect")


@pytest.fixture
def malden_prospect():
    return baker.make_recipe("supportal.tests.malden_prospect")


@pytest.fixture
def malden_prospect_suppressed():
    return baker.make_recipe("supportal.tests.malden_prospect_suppressed")


@pytest.fixture
def cambridge_prospect_assignment():
    return baker.make_recipe("supportal.tests.cambridge_prospect_assignment")


@pytest.fixture
def roslindale_prospect_assignment():
    return baker.make_recipe("supportal.tests.roslindale_prospect_assignment")


@pytest.fixture
def cambridge_prospect_unreachable_event(cambridge_prospect_assignment):
    return cambridge_prospect_assignment.create_contact_event(
        result=CanvassResult.UNREACHABLE_MOVED, metadata={"moved_to": "CA"}, note="test"
    )


@pytest.fixture
def california_prospect():
    return baker.make_recipe("supportal.tests.california_prospect")


@pytest.fixture()
def mattapan_leader_user():
    return baker.make_recipe("supportal.tests.mattapan_leader_user")


@pytest.fixture()
def roslindale_leader_user():
    return baker.make_recipe("supportal.tests.roslindale_leader_user")


@pytest.fixture()
def hayes_valley_leader_user():
    return baker.make_recipe("supportal.tests.hayes_valley_leader_user")


@pytest.fixture()
def cambridge_leader_user():
    return baker.make_recipe("supportal.tests.cambridge_leader_user")


@pytest.fixture()
def cambridge_event_signup():
    return baker.make_recipe("supportal.tests.cambridge_event_signup")


@pytest.fixture()
def cambridge_event():
    return baker.make_recipe("supportal.tests.cambridge_event")


@pytest.fixture()
def virtual_phone_bank():
    return set_mobilize_america_event_raw(
        baker.make_recipe("supportal.tests.virtual_phone_bank")
    )


@pytest.fixture()
def high_pri_virtual_phone_bank():
    return set_mobilize_america_event_raw(
        baker.make_recipe("supportal.tests.high_pri_virtual_phone_bank")
    )


@pytest.fixture()
def iowa_state():
    return baker.make_recipe("supportal.tests.iowa_state")


@pytest.fixture()
def ia_zip5():
    return USZip5.objects.create(
        zip5="52240", state="IA", coordinates=Point(-91.5016, 41.6355, srid=4326)
    )


@pytest.fixture()
def nh_zip5():
    return USZip5.objects.create(
        zip5="03037", state="NH", coordinates=Point(-71.2513, 43.1378, srid=4326)
    )


@pytest.fixture()
def nv_zip5():
    return USZip5.objects.create(
        zip5="89006", state="NV", coordinates=Point(-114.9721, 35.9279, srid=4326)
    )


@pytest.fixture()
def sc_zip5():
    return USZip5.objects.create(
        zip5="29409", state="SC", coordinates=Point(-79.9605, 32.7961, srid=4326)
    )


@pytest.fixture()
def ca_zip5():
    return USZip5.objects.create(
        zip5="94102", state="CA", coordinates=Point(-124.4167, 37.7813, srid=4326)
    )


@pytest.fixture()
def ma_zip5():
    return USZip5.objects.create(
        zip5="02130", state="MA", coordinates=Point(-71.113845, 42.312759, srid=4326)
    )
