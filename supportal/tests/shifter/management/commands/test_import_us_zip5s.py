import os

import pytest

from supportal.shifter.management.commands.import_us_zip5s import Command
from supportal.shifter.models import USZip5

TEST_FILE_PATH = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), "us_10_test_zip5s.csv.gz"
)


@pytest.mark.django_db
def test_handle():
    assert USZip5.objects.count() == 0
    processed_incrementally = Command().handle(file=TEST_FILE_PATH, expect_at_least=10)
    zips = list(USZip5.objects.all())
    assert USZip5.objects.count() == 10
