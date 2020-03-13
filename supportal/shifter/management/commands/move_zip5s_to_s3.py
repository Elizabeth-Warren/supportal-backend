import json
import os

import boto3
from django.conf import settings
from django.contrib.gis.geos import Point
from django.core.management import BaseCommand
from django.db import transaction

from supportal.shifter.models import USZip5
from supportal.shifter.serializers import USZip5Serializer

MIN_EXPECTED_ZIPS = 41000


class Command(BaseCommand):
    """Turn zipcode data for website
    pipenv run python manage.py move_zip5s_to_s3
    """

    _s3 = None

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            nargs="?",
            type=int,
            default=1,
            help="limit of zip files to produce",
        )
        parser.add_argument(
            "--path_to_files",
            nargs="?",
            default="zip5",
            help="path to location of the files",
        )
        parser.add_argument("--use_s3", action="store_true", help="Should send to s3")

    def _get_or_create_s3(self):
        if self._s3:
            return self._s3
        self._s3 = boto3.resource("s3")
        return self._s3

    def send_to_s3(self, data_to_write, file_path):
        s3 = self._get_or_create_s3()
        s3.Bucket("cdn.elizabethwarren.com").put_object(
            Key=file_path, Body=data_to_write
        )

    def write_to_file(self, data_to_write, file_path):
        with open(file_path, "w+") as zip_file:
            zip_file.write(data_to_write)

    @transaction.atomic
    def handle(self, *args, **options):
        limit = options["limit"]
        base_path = options["path_to_files"]
        should_use_s3 = options["use_s3"]
        for zip_object in USZip5.objects.all()[:limit]:
            file_path = f"{base_path}/{zip_object.zip5}"
            zip5ser = USZip5Serializer()
            zip5ser.to_representation(zip_object)
            data_to_write = json.dumps(zip5ser.to_representation(zip_object))
            if should_use_s3:
                self.send_to_s3(data_to_write, file_path)
            else:
                self.write_to_file(data_to_write, file_path)
