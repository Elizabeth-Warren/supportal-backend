# pylint: skip-file
#
# We use this to run the expire handler
#

import supportal.wsgi  # isort:skip
from django.core import management  # isort:skip

# from ew_common.telemetry import telemetry  # isort:skip


# @telemetry.timed
# @telemetry.report_exceptions(raise_exception=False)  # suppress retries
def import_mobilize_america_events(*args, **kwargs):
    management.call_command("import_mobilize_america_events", **kwargs)

# @telemetry.timed
# @telemetry.report_exceptions  # allow this to retry
def expire_assignments(event, context):
    management.call_command("expire_assignments")
