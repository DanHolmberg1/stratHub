from datetime import timedelta

from django import forms
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.forms import UserCreationForm
from django.db import transaction
from django.db.models import F
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .access import editable_teams
from .models import Invite, Team


class JoinForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ["username"]


@login_not_required
def join(request, token):
    invite = get_object_or_404(Invite, token=token)
    if not invite.is_valid:
        return render(request, "org/join.html", {"expired": True}, status=410)
    form = JoinForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            # Re-check under the transaction so a 1-use link can't be used twice.
            updated = Invite.objects.filter(
                pk=invite.pk, uses__lt=F("max_uses"), expires_at__gt=timezone.now()
            ).update(uses=F("uses") + 1)
            if not updated:
                return render(request, "org/join.html", {"expired": True}, status=410)
            user = form.save(commit=False)
            user.is_staff = user.is_superuser = invite.make_admin
            user.save()
            user.teams.set(invite.teams.all())
        login(request, user)
        messages.success(request, f"Welcome, {user.username}!")
        return redirect("dashboard")
    return render(request, "org/join.html", {"form": form, "invite": invite})


@require_POST
def switch_team(request):
    team_id = request.POST.get("team")
    if team_id and editable_teams(request.user).filter(pk=team_id).exists():
        request.session["team_id"] = int(team_id)
    nxt = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(nxt, {request.get_host()}):
        nxt = "dashboard"
    return redirect(nxt)


class InviteForm(forms.ModelForm):
    days = forms.IntegerField(min_value=1, max_value=60, initial=7, label="Valid for (days)")

    class Meta:
        model = Invite
        fields = ["note", "teams", "make_admin", "max_uses"]
        widgets = {"teams": forms.CheckboxSelectMultiple}


@staff_member_required
def invites(request):
    form = InviteForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        inv = form.save(commit=False)
        inv.created_by = request.user
        inv.expires_at = timezone.now() + timedelta(days=form.cleaned_data["days"])
        inv.save()
        form.save_m2m()
        messages.success(request, "Invite created. Copy the link below and send it.")
        return redirect("invites")
    return render(request, "org/invites.html", {
        "form": form,
        "invites": Invite.objects.prefetch_related("teams")[:50],
        "teams": Team.objects.prefetch_related("members"),
    })


@staff_member_required
@require_POST
def invite_revoke(request, pk):
    Invite.objects.filter(pk=pk).update(expires_at=timezone.now())
    return redirect("invites")
