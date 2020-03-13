from unittest.mock import Mock

import pytest
from django.conf import settings

from supportal.app.management.commands.normalize_emails import Command
from supportal.app.models import User
from supportal.app.models.user import UserManager, _cognito_client


@pytest.mark.django_db
def test_normalize_email_command(mocker):
    mock_cognito = Mock()
    mocker.patch(
        "supportal.app.models.user._get_cognito_client", return_value=mock_cognito
    )

    user1 = User.objects.create_user(
        "user1", "ishouldntchange@example.com", skip_cognito=True
    )
    user1.refresh_from_db()
    original_u1_updated_at = user1.updated_at
    u2_email = "LowerCaseMe@example.com"
    user2 = User.objects.create_user("user2", u2_email, skip_cognito=True)
    # need to set this manually because create_user normalizes emails before save
    user2.email = u2_email
    user2.save()

    Command().handle()

    user1.refresh_from_db()
    user2.refresh_from_db()
    mock_cognito.admin_update_user_attributes.assert_called_once_with(
        UserPoolId=settings.COGNITO_USER_POOL,
        Username="user2",
        UserAttributes=[
            {"Name": "email", "Value": "lowercaseme@example.com"},
            {"Name": "email_verified", "Value": "True"},
        ],
    )
    assert user2.email == "lowercaseme@example.com"
    assert user1.updated_at == original_u1_updated_at
