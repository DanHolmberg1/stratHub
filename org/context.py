from .access import current_team, editable_teams


def org_context(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}
    from book.models import Map

    return {
        "current_team": current_team(request),
        "my_teams": editable_teams(user),
        "nav_maps": Map.objects.filter(active=True),
    }
