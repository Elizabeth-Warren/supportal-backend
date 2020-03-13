from django.conf import settings
from django.db import models

from supportal.app.models.base_model_mixin import BaseModelMixin


class APIKey(BaseModelMixin):
    """
    Cognito API Keys for authenticating access tokens issued by the
    client_credentials OAuth grant. Each key receives the privileges of the
    User it is associated with.

    To add a new API Key:
      - Go to the Cognito User Pool > App Clients
      - Create a new client and make sure to check "Generate client secret"
      - In the sidebar go to "App Client Settings"
      - Find you app client and select 'Client credentials" under "Allowed OAuth Flows"
    """

    client_id = models.CharField(primary_key=True, max_length=100)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=False
    )
