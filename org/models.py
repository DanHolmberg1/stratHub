import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


class Team(models.Model):
    """A roster inside the org (e.g. Main, Academy). Content belongs to a team."""

    name = models.CharField(max_length=80, unique=True)
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name="teams", blank=True
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


def _new_token():
    return secrets.token_urlsafe(24)


class Invite(models.Model):
    """Sign-up link. There is no open registration: you need one of these."""

    token = models.CharField(max_length=64, unique=True, default=_new_token, editable=False)
    note = models.CharField(max_length=120, blank=True, help_text="Who is this for?")
    teams = models.ManyToManyField(Team, blank=True, help_text="Teams the new user joins")
    make_admin = models.BooleanField(
        default=False, help_text="Org admin: can manage maps, teams, invites and all content"
    )
    max_uses = models.PositiveIntegerField(default=1)
    uses = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.note or f"Invite {self.pk}"

    @property
    def is_valid(self):
        return self.uses < self.max_uses and self.expires_at > timezone.now()
