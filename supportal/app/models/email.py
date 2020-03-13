from django.contrib.postgres.fields import JSONField
from django.db import models

from supportal.app.models.base_model_mixin import BaseModelMixin


class EmailSend(BaseModelMixin):
    INVITE_EMAIL = "switchboard_invite_email"
    EXPIRING_PROSPECTS = "expiring_contacts_email"
    INACTIVE_USER_EMAIL = "switchboard_inactive_user_email"
    BLAST_EMAIL = "switchboard_blast_send"
    VERIFIED_EMAIL = "switchboard_verified_email"

    EMAIL_CHOICES = [
        (INVITE_EMAIL, "Invite Email"),
        (EXPIRING_PROSPECTS, "Expiring Prospects"),
        (INACTIVE_USER_EMAIL, "Invite Inactive Users"),
        (BLAST_EMAIL, "Blast Email"),
        (VERIFIED_EMAIL, "User Verified"),
    ]
    user = models.ForeignKey(
        "app.User", on_delete=models.CASCADE, related_name="email_sends"
    )
    template_name = models.CharField(
        choices=EMAIL_CHOICES, db_index=True, max_length=250
    )
    payload = JSONField(null=True)
