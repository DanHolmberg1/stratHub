"""Team scoping rules, in one place.

* Org admins (``user.is_staff``) see and edit everything.
* Members see content owned by their teams plus anything marked ``shared``.
* Members edit only content owned by one of their teams.
"""

from django.db import models
from django.db.models import Q

from .models import Team


def team_ids(user):
    if not user.is_authenticated:
        return set()
    if not hasattr(user, "_strathub_team_ids"):
        user._strathub_team_ids = set(user.teams.values_list("id", flat=True))
    return user._strathub_team_ids


def editable_teams(user):
    if user.is_staff:
        return Team.objects.all()
    return Team.objects.filter(id__in=team_ids(user))


def can_edit(user, obj):
    return user.is_staff or obj.team_id in team_ids(user)


def current_team(request):
    """The team selected in the header switcher (used as the default for new content)."""
    teams = list(editable_teams(request.user))
    wanted = request.session.get("team_id")
    for t in teams:
        if t.id == wanted:
            return t
    return teams[0] if teams else None


class TeamScopedQuerySet(models.QuerySet):
    shared_field = "shared"

    def visible_to(self, user):
        if user.is_staff:
            return self
        q = Q(team__in=team_ids(user))
        if self.shared_field:
            q |= Q(**{self.shared_field: True})
        return self.filter(q)

    def editable_by(self, user):
        if user.is_staff:
            return self
        return self.filter(team__in=team_ids(user))


class TeamOnlyQuerySet(TeamScopedQuerySet):
    """For things that are never shared across teams (gameplans)."""

    shared_field = None
