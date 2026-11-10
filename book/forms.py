import os

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model

from org.access import current_team, editable_teams

from .models import (
    SIDES,
    Comment,
    Gameplan,
    Lineup,
    Map,
    Opponent,
    OpponentNote,
    Strat,
    StratSlot,
)


def validate_video(f):
    if not f or not hasattr(f, "size"):
        return f
    ext = os.path.splitext(f.name)[1].lower()
    if ext not in settings.VIDEO_EXTENSIONS:
        raise forms.ValidationError(
            f"Use a browser-playable video ({', '.join(settings.VIDEO_EXTENSIONS)})."
        )
    if f.size > settings.MAX_VIDEO_MB * 1024 * 1024:
        raise forms.ValidationError(f"Video is larger than {settings.MAX_VIDEO_MB} MB.")
    return f


def validate_image(f):
    if f and hasattr(f, "size") and f.size > settings.MAX_IMAGE_MB * 1024 * 1024:
        raise forms.ValidationError(f"Image is larger than {settings.MAX_IMAGE_MB} MB.")
    return f


class TeamOwnedForm(forms.ModelForm):
    """Restricts the team picker to teams the user may post for."""

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.fields["team"].queryset = editable_teams(request.user)
        self.fields["team"].empty_label = None
        if not self.instance.pk:
            self.fields["team"].initial = current_team(request)


class VideoFieldsMixin:
    def clean_video_file(self):
        return validate_video(self.cleaned_data.get("video_file"))


class LineupForm(VideoFieldsMixin, TeamOwnedForm):
    class Meta:
        model = Lineup
        fields = [
            "title", "side", "nade", "layer",
            "from_x", "from_y", "to_x", "to_y",
            "from_callout", "to_callout", "technique", "click",
            "description", "tags", "video_file", "video_url",
            "pos_image", "aim_image", "team", "shared",
        ]
        widgets = {
            "from_x": forms.HiddenInput, "from_y": forms.HiddenInput,
            "to_x": forms.HiddenInput, "to_y": forms.HiddenInput,
            "description": forms.Textarea(attrs={"rows": 4}),
            "video_file": forms.ClearableFileInput(attrs={"accept": "video/mp4,video/webm"}),
        }

    def __init__(self, *args, map=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.map = map
        self.fields["layer"].queryset = map.layers.all()
        self.fields["layer"].empty_label = None
        self.fields["layer"].required = True
        for f in ("from_callout", "to_callout"):
            self.fields[f].widget.attrs["list"] = "callouts"
        for f in ("from_x", "from_y", "to_x", "to_y"):
            self.fields[f].required = False  # checked together in clean()

    def clean(self):
        data = super().clean()
        for f in ("from_x", "from_y", "to_x", "to_y"):
            v = data.get(f)
            if v is None or not 0 <= v <= 1:
                raise forms.ValidationError("Click the radar to set both the throw spot and where it lands.")
        return data

    def clean_pos_image(self):
        return validate_image(self.cleaned_data.get("pos_image"))

    def clean_aim_image(self):
        return validate_image(self.cleaned_data.get("aim_image"))


class StratForm(VideoFieldsMixin, TeamOwnedForm):
    class Meta:
        model = Strat
        fields = [
            "title", "side", "kind", "area", "status", "description", "tags",
            "video_file", "video_url", "lineups", "team", "shared",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 8}),
            "lineups": forms.CheckboxSelectMultiple,
            "video_file": forms.ClearableFileInput(attrs={"accept": "video/mp4,video/webm"}),
        }

    def __init__(self, *args, map=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.map = map
        self.fields["lineups"].queryset = (
            Lineup.objects.visible_to(self.request.user).filter(map=map).select_related("team")
        )


class SlotForm(forms.ModelForm):
    class Meta:
        model = StratSlot
        fields = ["role", "player", "instructions", "lineups"]
        widgets = {
            "instructions": forms.Textarea(attrs={"rows": 2}),
            "lineups": forms.SelectMultiple(attrs={"size": 5, "class": "slot-util"}),
        }

    def __init__(self, *args, lineup_qs=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["lineups"].queryset = lineup_qs
        self.fields["lineups"].label = "Util they throw"
        self.fields["player"].queryset = get_user_model().objects.filter(is_active=True).order_by("username")
        self.fields["role"].widget.attrs.update(list="roles", placeholder="Role (Entry, AWP, Lurk…)")

    def has_content(self):
        d = self.cleaned_data
        return bool(d.get("role") or d.get("player") or d.get("instructions") or d.get("lineups"))


class GameplanForm(forms.ModelForm):
    class Meta:
        model = Gameplan
        fields = ["title", "team", "opponent", "match_date", "notes", "strats"]
        widgets = {
            "match_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 5}),
            "strats": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        user = request.user
        self.fields["team"].queryset = editable_teams(user)
        self.fields["team"].empty_label = None
        if not self.instance.pk:
            self.fields["team"].initial = current_team(request)
        self.fields["opponent"].queryset = Opponent.objects.visible_to(user)
        self.fields["strats"].queryset = (
            Strat.objects.visible_to(user).exclude(status="retired").select_related("map")
        )


class OpponentForm(TeamOwnedForm):
    class Meta:
        model = Opponent
        fields = ["name", "notes", "team", "shared"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 5})}


class OpponentNoteForm(forms.ModelForm):
    class Meta:
        model = OpponentNote
        fields = ["map", "side", "body"]
        widgets = {"body": forms.Textarea(attrs={"rows": 3, "placeholder": "e.g. They stack B on pistol, AWPer peeks mid early…"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["map"].queryset = Map.objects.all()
        self.fields["side"].choices = [("", "Either side"), *SIDES]


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ["body"]
        widgets = {"body": forms.Textarea(attrs={"rows": 2, "placeholder": "Add a comment…"})}
        labels = {"body": ""}
