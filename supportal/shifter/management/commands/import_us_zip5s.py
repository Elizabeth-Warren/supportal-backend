import csv
import gzip
import os

from django.conf import settings
from django.contrib.gis.geos import Point
from django.core.management import BaseCommand
from django.db import transaction

from supportal.shifter.models import USZip5

MIN_EXPECTED_ZIPS = 41000


class Command(BaseCommand):
    """Import zipcode data from a gzipped csv. See tc/data"""

    def add_arguments(self, parser):
        default_file_path = os.path.join(
            settings.BASE_DIR, "..", "datasets", "us_zip5s.csv.gz"
        )
        parser.add_argument(
            "--file",
            nargs="?",
            default=default_file_path,
            help="Full path to the zipcode file",
        )
        parser.add_argument(
            "--expect_at_least",
            nargs="?",
            default=MIN_EXPECTED_ZIPS,
            help="Minimum number of expected zips, for validation",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        min_expected = int(options["expect_at_least"])
        fpath = options["file"]
        p = 0
        with gzip.open(fpath, "rt") as f:
            reader = csv.DictReader(f)
            USZip5.objects.all().delete()
            for line in reader:
                p += 1
                if p % 25 == 0:
                    print(p)
                lat = line["latitude"]
                lng = line["longitude"]
                coordinates = None
                if lat and lng:
                    coordinates = Point(float(lng), float(lat), srid=4326)
                fips = int(line["county_fips"]) if line["county_fips"] else None
                accuracy = int(line["accuracy"]) if line["accuracy"] else None
                USZip5.objects.create(
                    zip5=line["zip5"],
                    city=line["city"],
                    state=line["state"],
                    county=line["county"],
                    county_fips=fips,
                    accuracy=accuracy,
                    coordinates=coordinates,
                )
        count = USZip5.objects.all().count()
        if count < min_expected:
            raise Exception(f"Wrote fewer zips than expected ({count}), rolling back")
        return f"Wrote {count} zips"
