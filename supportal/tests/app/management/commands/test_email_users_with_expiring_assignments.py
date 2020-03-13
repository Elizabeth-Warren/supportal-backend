from datetime import datetime, timezone
from io import StringIO
from unittest import mock

import freezegun
import pytest
from django.conf import settings
from django.core.management import call_command
from django.utils import timezone
from model_bakery import baker

from supportal.app.common.enums import CanvassResult
from supportal.app.models import EmailSend

CREATED_AT = datetime(2019, 10, 26, 1, tzinfo=timezone.utc)
CREATED_AT_EARLIER = datetime(2019, 10, 26, tzinfo=timezone.utc)
DAY_BEFORE_EXPIRE = datetime(2019, 11, 1, tzinfo=timezone.utc)
TWO_DAY_BEFORE_EXPIRE = datetime(2019, 10, 31, tzinfo=timezone.utc)
EXPIRED_AT = datetime(2019, 11, 2, 1, tzinfo=timezone.utc)
EXPIRED_EARLIER = datetime(2019, 11, 2, tzinfo=timezone.utc)
AFTER_EXPIRATION_DATE = datetime(2019, 11, 3, tzinfo=timezone.utc)
SIX_DAYS_BEFORE_EXPIRE = datetime(2019, 10, 27, tzinfo=timezone.utc)


def email_expiring_users(*args, **kwargs):
    call_command("email_users_with_expiring_assignments", **kwargs)


@pytest.fixture
def first_cambridge_assignment(cambridge_leader_user, cambridge_prospect):
    cambridge_assignment = baker.make(
        "VolProspectAssignment", user=cambridge_leader_user, person=cambridge_prospect
    )
    cambridge_assignment.created_at = CREATED_AT
    cambridge_assignment.save()
    return cambridge_assignment


@pytest.fixture
def hayes_assignment(hayes_valley_leader_user, california_prospect):
    hayes_valley_assignment = baker.make(
        "VolProspectAssignment",
        user=hayes_valley_leader_user,
        person=california_prospect,
    )
    hayes_valley_assignment.created_at = CREATED_AT_EARLIER
    hayes_valley_assignment.save()
    return hayes_valley_assignment


@pytest.fixture
def hayes_cambrdige_assignment(hayes_valley_leader_user, cambridge_prospect):
    hayes_valley_assignment = baker.make(
        "VolProspectAssignment",
        user=hayes_valley_leader_user,
        person=cambridge_prospect,
    )
    hayes_valley_assignment.created_at = CREATED_AT
    hayes_valley_assignment.save()
    return hayes_valley_assignment


@pytest.fixture
def second_cambridge_assignment(cambridge_leader_user, california_prospect):
    cambridge_assignment = baker.make(
        "VolProspectAssignment", user=cambridge_leader_user, person=california_prospect
    )
    cambridge_assignment.created_at = CREATED_AT
    cambridge_assignment.save()
    return cambridge_assignment


@pytest.fixture
def expired_assignment(cambridge_leader_user, somerville_prospect):
    cambridge_assignment = baker.make(
        "VolProspectAssignment", user=cambridge_leader_user, person=somerville_prospect
    )
    cambridge_assignment.created_at = CREATED_AT
    cambridge_assignment.expired_at = EXPIRED_AT
    cambridge_assignment.save()
    return cambridge_assignment


DEFAULT_TEMPLATE_DATA = {
    "assignment_count": "",
    "email": "",
    "expiration_date": "",
    "switchboard_login_url": settings.SUPPORTAL_BASE_URL,
    "first_name": "",
    "last_name": "",
}


def make_payload(assignment_count, email, expiration, first_name, last_name):
    return {
        "assignment_count": assignment_count,
        "email": email,
        "expiration_date": expiration.strftime("%a %b %d, %Y"),
        "switchboard_login_url": settings.SUPPORTAL_BASE_URL,
        "first_name": first_name,
        "last_name": last_name,
    }


def check_email_sends(user, assignment_count, expiration, single_call_mock=None):
    assert EmailSend.objects.filter(user=user).count() == 1
    email_sent = EmailSend.objects.get(user=user)
    assert email_sent.template_name == "expiring_contacts_email"
    assert email_sent.payload == {
        "assignment_count": assignment_count,
        "email": user.email,
        "expiration_date": expiration.strftime("%a %b %d, %Y"),
        "switchboard_login_url": settings.SUPPORTAL_BASE_URL,
        "first_name": user.first_name,
        "last_name": user.last_name,
    }
    if single_call_mock:
        single_call_mock.return_value.send_bulk_email.assert_called_once_with(
            configuration_set_name="organizing_emails",
            default_template_data=DEFAULT_TEMPLATE_DATA,
            from_email=settings.FROM_EMAIL,
            payload_array=[
                make_payload(
                    assignment_count,
                    user.email,
                    expiration,
                    user.first_name,
                    user.last_name,
                )
            ],
            reply_to_email=settings.REPLY_TO_EMAIL,
            template="expiring_contacts_email",
            application_name="supportal",
        )


@pytest.mark.django_db
@freezegun.freeze_time(TWO_DAY_BEFORE_EXPIRE)
def test_email_with_uncontacted_assignments(
    first_cambridge_assignment, expired_assignment
):
    out = StringIO()
    assert EmailSend.objects.filter(user=first_cambridge_assignment.user).count() == 0

    with mock.patch(
        "supportal.app.management.commands.base_email_command.EmailService"
    ) as email_service_mock:
        email_expiring_users(stdout=out, send=True)
    first_cambridge_assignment.refresh_from_db()

    assert EmailSend.objects.all().count() == 1
    check_email_sends(
        first_cambridge_assignment.user, 1, EXPIRED_AT, email_service_mock
    )
    assert "Found 1 users to email." in out.getvalue()


@pytest.mark.django_db
@freezegun.freeze_time(TWO_DAY_BEFORE_EXPIRE)
def test_dryrun(first_cambridge_assignment, expired_assignment):
    out = StringIO()
    assert EmailSend.objects.filter(user=first_cambridge_assignment.user).count() == 0

    with mock.patch(
        "supportal.app.management.commands.base_email_command.EmailService"
    ) as email_service_mock:
        email_expiring_users(stdout=out)
    first_cambridge_assignment.refresh_from_db()

    assert EmailSend.objects.all().count() == 0

    assert first_cambridge_assignment.user.email in out.getvalue()
    assert "Found 1 users to email." in out.getvalue()


@pytest.mark.django_db
@freezegun.freeze_time(DAY_BEFORE_EXPIRE)
def test_dont_email_outside_of_two_days(first_cambridge_assignment, expired_assignment):
    out = StringIO()
    email_expiring_users(stdout=out, send=True)

    assert EmailSend.objects.all().count() == 0
    assert EmailSend.objects.filter(user=first_cambridge_assignment.user).count() == 0
    assert "Found 0 users to email." in out.getvalue()


@pytest.mark.django_db
@freezegun.freeze_time(TWO_DAY_BEFORE_EXPIRE)
def test_email_with_two_assignments(
    first_cambridge_assignment, second_cambridge_assignment, expired_assignment
):
    out = StringIO()
    with mock.patch(
        "supportal.app.management.commands.base_email_command.EmailService"
    ) as email_service_mock:
        email_expiring_users(stdout=out, send=True)

    assert EmailSend.objects.all().count() == 1
    check_email_sends(
        first_cambridge_assignment.user, 2, EXPIRED_AT, email_service_mock
    )
    assert "Found 1 users to email." in out.getvalue()


@pytest.mark.django_db
@freezegun.freeze_time(TWO_DAY_BEFORE_EXPIRE)
def test_email_with_two_users(
    first_cambridge_assignment,
    hayes_assignment,
    hayes_cambrdige_assignment,
    expired_assignment,
):
    out = StringIO()
    with mock.patch(
        "supportal.app.management.commands.base_email_command.EmailService"
    ) as email_service_mock:
        email_expiring_users(stdout=out, send=True)

    assert EmailSend.objects.all().count() == 2
    check_email_sends(first_cambridge_assignment.user, 1, EXPIRED_AT)
    check_email_sends(hayes_assignment.user, 2, EXPIRED_EARLIER)
    email_service_mock.return_value.send_bulk_email.assert_called_once_with(
        configuration_set_name="organizing_emails",
        default_template_data=DEFAULT_TEMPLATE_DATA,
        from_email=settings.FROM_EMAIL,
        payload_array=[
            make_payload(
                1,
                first_cambridge_assignment.user.email,
                EXPIRED_AT,
                first_cambridge_assignment.user.first_name,
                first_cambridge_assignment.user.last_name,
            ),
            make_payload(
                2,
                hayes_assignment.user.email,
                EXPIRED_EARLIER,
                hayes_assignment.user.first_name,
                hayes_assignment.user.last_name,
            ),
        ],
        reply_to_email=settings.REPLY_TO_EMAIL,
        template="expiring_contacts_email",
        application_name="supportal",
    )
    assert "Found 2 users to email." in out.getvalue()


@pytest.mark.django_db
@freezegun.freeze_time(TWO_DAY_BEFORE_EXPIRE)
def test_email_with_two_users_send_all_to_flag(
    first_cambridge_assignment,
    hayes_assignment,
    hayes_cambrdige_assignment,
    expired_assignment,
):
    out = StringIO()
    with mock.patch(
        "supportal.app.management.commands.base_email_command.EmailService"
    ) as email_service_mock:
        email_expiring_users(
            stdout=out, send=True, send_all_to="sgoldblatt+ts@elizabethwarren.com"
        )

    assert EmailSend.objects.all().count() == 0
    email_service_mock.return_value.send_bulk_email.assert_called_once_with(
        configuration_set_name="organizing_emails",
        default_template_data=DEFAULT_TEMPLATE_DATA,
        from_email=settings.FROM_EMAIL,
        payload_array=[
            make_payload(
                1,
                "sgoldblatt+ts@elizabethwarren.com",
                EXPIRED_AT,
                first_cambridge_assignment.user.first_name,
                first_cambridge_assignment.user.last_name,
            ),
            make_payload(
                2,
                "sgoldblatt+ts@elizabethwarren.com",
                EXPIRED_EARLIER,
                hayes_assignment.user.first_name,
                hayes_assignment.user.last_name,
            ),
        ],
        reply_to_email=settings.REPLY_TO_EMAIL,
        template="expiring_contacts_email",
        application_name="supportal",
    )
    assert "Found 2 users to email." in out.getvalue()


@pytest.mark.django_db
@freezegun.freeze_time(TWO_DAY_BEFORE_EXPIRE)
def test_email_with_two_users_limit_flag(
    first_cambridge_assignment,
    hayes_assignment,
    hayes_cambrdige_assignment,
    expired_assignment,
):
    out = StringIO()
    with mock.patch(
        "supportal.app.management.commands.base_email_command.EmailService"
    ) as email_service_mock:
        email_expiring_users(stdout=out, limit=1, send=True)

    assert EmailSend.objects.all().count() == 1
    check_email_sends(first_cambridge_assignment.user, 1, EXPIRED_AT)

    assert "Found 1 users to email." in out.getvalue()


@pytest.mark.django_db
@freezegun.freeze_time(TWO_DAY_BEFORE_EXPIRE)
def test_email_unsuccessfully_contacted_assignments(
    first_cambridge_assignment, expired_assignment
):
    first_cambridge_assignment.create_contact_event(
        result=CanvassResult.UNAVAILABLE_LEFT_MESSAGE
    )
    first_cambridge_assignment.save()
    out = StringIO()

    with mock.patch(
        "supportal.app.management.commands.base_email_command.EmailService"
    ) as email_service_mock:
        email_expiring_users(stdout=out, send=True)

    assert EmailSend.objects.all().count() == 1
    check_email_sends(
        first_cambridge_assignment.user, 1, EXPIRED_AT, email_service_mock
    )
    assert "Found 1 users to email." in out.getvalue()


@pytest.mark.django_db
@freezegun.freeze_time(TWO_DAY_BEFORE_EXPIRE)
def test_dont_email_unsubscribed_user(first_cambridge_assignment, expired_assignment):
    first_cambridge_assignment.user.unsubscribed_at = datetime.now(tz=timezone.utc)
    first_cambridge_assignment.user.save()
    out = StringIO()
    email_expiring_users(stdout=out, send=True)

    assert EmailSend.objects.all().count() == 0
    assert EmailSend.objects.filter(user=first_cambridge_assignment.user).count() == 0
    assert "Found 0 users to email." in out.getvalue()


@pytest.mark.django_db
@freezegun.freeze_time(TWO_DAY_BEFORE_EXPIRE)
def test_dont_email_user_who_was_emailed_recently(
    first_cambridge_assignment, expired_assignment
):
    EmailSend.objects.create(
        user=first_cambridge_assignment.user,
        template_name=EmailSend.EXPIRING_PROSPECTS,
        payload={},
    )
    assert first_cambridge_assignment.user.unsubscribed_at is None

    out = StringIO()
    email_expiring_users(stdout=out, send=True)

    assert EmailSend.objects.all().count() == 1
    assert EmailSend.objects.filter(user=first_cambridge_assignment.user).count() == 1
    assert "Found 0 users to email." in out.getvalue()


@pytest.mark.django_db
@freezegun.freeze_time(TWO_DAY_BEFORE_EXPIRE)
def test_email_user_who_was_invited_recently(
    first_cambridge_assignment, expired_assignment
):
    EmailSend.objects.create(
        user=first_cambridge_assignment.user,
        template_name=EmailSend.INVITE_EMAIL,
        payload={},
    )
    assert first_cambridge_assignment.user.unsubscribed_at is None

    out = StringIO()

    with mock.patch(
        "supportal.app.management.commands.base_email_command.EmailService"
    ) as email_service_mock:
        email_expiring_users(stdout=out, send=True)

    assert EmailSend.objects.all().count() == 2
    assert EmailSend.objects.filter(user=first_cambridge_assignment.user).count() == 2
    assert "Found 1 users to email." in out.getvalue()


@pytest.mark.django_db
@freezegun.freeze_time(TWO_DAY_BEFORE_EXPIRE)
def test_successfully_contacted_dont_email(
    first_cambridge_assignment, expired_assignment
):
    # Make sure that having a previous unsuccessful contact event doesn't cause
    # the contact to get expired.
    first_cambridge_assignment.create_contact_event(
        result=CanvassResult.UNAVAILABLE_LEFT_MESSAGE
    )
    first_cambridge_assignment.create_contact_event(
        result=CanvassResult.SUCCESSFUL_CANVASSED
    )

    first_cambridge_assignment.save()
    out = StringIO()
    email_expiring_users(stdout=out, send=True)
    first_cambridge_assignment.refresh_from_db()

    assert EmailSend.objects.all().count() == 0
    assert "Found 0 users to email." in out.getvalue()


@pytest.mark.django_db
def test_expire_zero_assignments():
    out = StringIO()
    email_expiring_users(stdout=out, send=True)

    assert EmailSend.objects.all().count() == 0
    assert "Found 0 users to email." in out.getvalue()
