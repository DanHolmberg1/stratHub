import os
import uuid

from django.conf import settings
from django.db import models
from django.urls import reverse

from org.access import TeamOnlyQuerySet, TeamScopedQuerySet
from org.models import Team

SIDES = [("T", "T"), ("CT", "CT")]

NADES = [
    ("smoke", "Smoke"),
    ("flash", "Flash"),
    ("molotov", "Molotov / Incendiary"),
    ("he", "HE"),
    ("decoy", "Decoy"),
]

TECHNIQUES = [
    ("stand", "Standing"),
    ("crouch", "Crouching"),
    ("jumpthrow", "Jump throw"),
    ("run_jumpthrow", "Run + jump throw"),
    ("walk_jumpthrow", "Walk + jump throw"),
    ("run", "Running throw"),
    ("walk", "Walking throw"),
    ("jump", "Jump, throw at peak"),
]

CLICKS = [("left", "Left click"), ("right", "Right click"), ("both", "Left + right")]

STRAT_KINDS = [
    ("default", "Default"),
    ("execute", "Execute"),
    ("split", "Split"),
    ("fake", "Fake"),
    ("contact", "Contact / rush"),
    ("pistol", "Pistol round"),
    ("eco", "Eco"),
    ("force", "Force buy"),
    ("anti_eco", "Anti-eco"),
    ("ct_setup", "CT setup"),
    ("retake", "Retake"),
    ("play", "Spot-specific play"),
    ("mid_round", "Mid-round call"),
    ("other", "Other"),
]

STATUSES = [
    ("draft", "Draft"),
    ("testing", "Testing"),
    ("active", "In rotation"),
    ("retired", "Retired"),
]


def _random_name(folder, filename):
    """Random, unguessable file names (the original name is not kept)."""
    ext = os.path.splitext(filename)[1].lower()[:8]
    return f"{folder}/{uuid.uuid4().hex}{ext}"


def upload_lineup(instance, filename):
    return _random_name("lineups", filename)


def upload_strat(instance, filename):
    return _random_name("strats", filename)


def upload_radar(instance, filename):
    return _random_name("radars", filename)


def split_tags(value):
    return [t.strip() for t in (value or "").split(",") if t.strip()]


class Map(models.Model):
    """A map in the pool. Flip ``active`` when the pool changes; content is kept."""

    name = models.CharField(max_length=40)
    slug = models.SlugField(unique=True, help_text="Used in URLs, e.g. 'mirage'")
    game_id = models.CharField(
        max_length=40, blank=True, help_text="In-game name, e.g. de_mirage (used by import_radars)"
    )
    active = models.BooleanField(default=True, help_text="In the active duty pool")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-active", "order", "name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("map_detail", args=[self.slug])


class MapLayer(models.Model):
    """One radar image. Most maps have one; Nuke/Vertigo have upper + lower."""

    map = models.ForeignKey(Map, on_delete=models.CASCADE, related_name="layers")
    name = models.CharField(max_length=40, default="Default")
    key = models.CharField(
        max_length=20, blank=True, help_text="'' for the main radar, 'lower' for the lower floor"
    )
    order = models.PositiveIntegerField(default=0)
    radar = models.ImageField(
        upload_to=upload_radar, blank=True, width_field="radar_width", height_field="radar_height"
    )
    radar_width = models.PositiveIntegerField(null=True, blank=True, editable=False)
    radar_height = models.PositiveIntegerField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.map} – {self.name}"

    @property
    def aspect(self):
        if self.radar_width and self.radar_height:
            return self.radar_height / self.radar_width
        return 1.0


class TeamOwned(models.Model):
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="+")
    shared = models.BooleanField(
        default=False, help_text="Let every team in the org see this (only your team can edit it)"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TeamScopedQuerySet.as_manager()

    class Meta:
        abstract = True


class Lineup(TeamOwned):
    map = models.ForeignKey(Map, on_delete=models.PROTECT, related_name="lineups")
    layer = models.ForeignKey(MapLayer, null=True, on_delete=models.SET_NULL, related_name="+")
    title = models.CharField(max_length=120)
    side = models.CharField(max_length=2, choices=SIDES)
    nade = models.CharField(max_length=10, choices=NADES)
    # Positions are fractions (0..1) of the radar image's width/height.
    from_x = models.FloatField()
    from_y = models.FloatField()
    to_x = models.FloatField()
    to_y = models.FloatField()
    from_callout = models.CharField("thrown from", max_length=60, blank=True)
    to_callout = models.CharField("lands at", max_length=60, blank=True)
    technique = models.CharField(max_length=20, choices=TECHNIQUES, default="stand")
    click = models.CharField(max_length=10, choices=CLICKS, default="left")
    tags = models.CharField(max_length=200, blank=True, help_text="Comma separated, e.g. one-way, execute")
    description = models.TextField(blank=True, help_text="Where to stand, what to aim at, timing…")
    video_file = models.FileField(upload_to=upload_lineup, blank=True)
    video_url = models.URLField(blank=True, help_text="YouTube, Medal or Streamable link")
    pos_image = models.ImageField("position screenshot", upload_to=upload_lineup, blank=True)
    aim_image = models.ImageField("aim screenshot", upload_to=upload_lineup, blank=True)

    class Meta:
        ordering = ["map", "nade", "title"]

    def __str__(self):
        return f"{self.get_nade_display()}: {self.title}"

    def get_absolute_url(self):
        return reverse("lineup_detail", args=[self.pk])

    @property
    def tag_list(self):
        return split_tags(self.tags)


class Strat(TeamOwned):
    map = models.ForeignKey(Map, on_delete=models.PROTECT, related_name="strats")
    title = models.CharField(max_length=120)
    side = models.CharField(max_length=2, choices=SIDES)
    kind = models.CharField("type", max_length=20, choices=STRAT_KINDS, default="default")
    area = models.CharField(max_length=60, blank=True, help_text="Site / area, e.g. 'B', 'Mid', 'A short'")
    status = models.CharField(max_length=10, choices=STATUSES, default="draft")
    tags = models.CharField(max_length=200, blank=True, help_text="Comma separated")
    description = models.TextField(blank=True)
    video_file = models.FileField(upload_to=upload_strat, blank=True)
    video_url = models.URLField(blank=True, help_text="YouTube, Medal or Streamable link")
    lineups = models.ManyToManyField(Lineup, blank=True, related_name="strats")
    # Drawing board: {"<layer id>": [shape, ...]}
    board = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["map", "side", "kind", "title"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("strat_detail", args=[self.pk])

    @property
    def tag_list(self):
        return split_tags(self.tags)


class StratSlot(models.Model):
    """What player 1–5 does in a strat."""

    strat = models.ForeignKey(Strat, on_delete=models.CASCADE, related_name="slots")
    number = models.PositiveSmallIntegerField()
    role = models.CharField(max_length=40, blank=True, help_text="Entry, AWP, Lurk, Support, IGL…")
    player = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    instructions = models.TextField(blank=True)
    lineups = models.ManyToManyField(Lineup, blank=True, related_name="+")

    class Meta:
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(fields=["strat", "number"], name="unique_slot_per_strat")
        ]

    def __str__(self):
        return f"{self.strat} #{self.number}"


class Opponent(TeamOwned):
    name = models.CharField(max_length=80)
    notes = models.TextField(blank=True, help_text="General tendencies, players, links to demos…")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("opponent_detail", args=[self.pk])


class OpponentNote(models.Model):
    opponent = models.ForeignKey(Opponent, on_delete=models.CASCADE, related_name="entries")
    map = models.ForeignKey(Map, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    side = models.CharField(max_length=2, choices=SIDES, blank=True, help_text="Their side")
    body = models.TextField()
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Gameplan(models.Model):
    """Strats picked for a specific match/opponent. Always private to one team."""

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="+")
    title = models.CharField(max_length=120)
    opponent = models.ForeignKey(
        Opponent, null=True, blank=True, on_delete=models.SET_NULL, related_name="gameplans"
    )
    match_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    strats = models.ManyToManyField(Strat, blank=True, related_name="gameplans")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TeamOnlyQuerySet.as_manager()

    class Meta:
        ordering = ["-match_date", "-created_at"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("gameplan_detail", args=[self.pk])


class Comment(models.Model):
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    strat = models.ForeignKey(Strat, null=True, blank=True, on_delete=models.CASCADE, related_name="comments")
    lineup = models.ForeignKey(Lineup, null=True, blank=True, on_delete=models.CASCADE, related_name="comments")

    class Meta:
        ordering = ["created_at"]
