import json
import mimetypes
import os
import re
from itertools import groupby

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied, SuspiciousFileOperation
from django.db.models import Count, Q
from django.http import (
    FileResponse,
    Http404,
    HttpResponse,
    HttpResponseBadRequest,
    JsonResponse,
    StreamingHttpResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils._os import safe_join
from django.views.decorators.http import require_POST

from org.access import can_edit, editable_teams

from .embeds import embed_src
from .forms import (
    CommentForm,
    GameplanForm,
    LineupForm,
    OpponentForm,
    OpponentNoteForm,
    SlotForm,
    StratForm,
)
from .models import (
    NADES,
    SIDES,
    STATUSES,
    STRAT_KINDS,
    Comment,
    Gameplan,
    Lineup,
    Map,
    Opponent,
    OpponentNote,
    Strat,
    StratSlot,
)

SLOT_COUNT = 5


# ---------------------------------------------------------------- helpers

def _visible(model, request, **kw):
    return get_object_or_404(model.objects.visible_to(request.user), **kw)


def _require_edit(request, obj):
    if not can_edit(request.user, obj):
        raise PermissionDenied("Only the owning team can change this.")


def _has_team(request):
    if editable_teams(request.user).exists():
        return True
    messages.error(request, "You're not on a team yet. Ask an org admin to add you to one.")
    return False


def _save_new(form, request):
    obj = form.save(commit=False)
    if not obj.pk:
        obj.created_by = request.user
    obj.save()
    form.save_m2m()
    return obj


def video_info(obj):
    if obj.video_file:
        return {"file": obj.video_file.url}
    if obj.video_url:
        src = embed_src(obj.video_url)
        return {"embed": src} if src else {"link": obj.video_url}
    return None


def layers_json(map):
    if not map.layers.exists():  # e.g. a map just added in the admin without a layer
        map.layers.create(name="Default")
    return [
        {
            "id": layer.id,
            "name": layer.name,
            "radar": layer.radar.url if layer.radar else None,
            "aspect": layer.aspect,
        }
        for layer in map.layers.all()
    ]


def lineup_json(lineup, user):
    return {
        "id": lineup.id,
        "title": lineup.title,
        "side": lineup.side,
        "nade": lineup.nade,
        "nadeLabel": lineup.get_nade_display(),
        "layer": lineup.layer_id,
        "from": [lineup.from_x, lineup.from_y],
        "to": [lineup.to_x, lineup.to_y],
        "fromCallout": lineup.from_callout,
        "toCallout": lineup.to_callout,
        "technique": lineup.get_technique_display(),
        "click": lineup.get_click_display(),
        "tags": lineup.tag_list,
        "description": lineup.description,
        "team": lineup.team.name,
        "shared": lineup.shared,
        "video": video_info(lineup),
        "posImage": lineup.pos_image.url if lineup.pos_image else None,
        "aimImage": lineup.aim_image.url if lineup.aim_image else None,
        "url": lineup.get_absolute_url(),
        "editUrl": reverse("lineup_edit", args=[lineup.pk]) if can_edit(user, lineup) else None,
    }


def _comment_post(request, **target):
    form = CommentForm(request.POST)
    if form.is_valid():
        Comment.objects.create(author=request.user, body=form.cleaned_data["body"], **target)
    return redirect(request.path + "#comments")


# ---------------------------------------------------------------- dashboard

def dashboard(request):
    user = request.user
    maps = list(Map.objects.all())
    lc = dict(Lineup.objects.visible_to(user).values_list("map").annotate(n=Count("id")))
    sc = dict(Strat.objects.visible_to(user).values_list("map").annotate(n=Count("id")))
    for m in maps:
        m.n_lineups, m.n_strats = lc.get(m.id, 0), sc.get(m.id, 0)
    return render(request, "book/dashboard.html", {
        "active_maps": [m for m in maps if m.active],
        "archived_maps": [m for m in maps if not m.active],
        "recent_strats": Strat.objects.visible_to(user).select_related("map", "team").order_by("-updated_at")[:8],
        "recent_lineups": Lineup.objects.visible_to(user).select_related("map", "team").order_by("-updated_at")[:8],
        "upcoming": Gameplan.objects.visible_to(user)
            .filter(match_date__gte=timezone.localdate()).select_related("opponent").order_by("match_date")[:5],
    })


# ---------------------------------------------------------------- lineups

def map_detail(request, slug):
    map = get_object_or_404(Map, slug=slug)
    lineups = Lineup.objects.visible_to(request.user).filter(map=map).select_related("team")
    return render(request, "book/map_detail.html", {
        "map": map,
        "tab": "util",
        "data": {
            "layers": layers_json(map),
            "lineups": [lineup_json(lu, request.user) for lu in lineups],
            "nades": NADES,
        },
        "nades": NADES,
        "lineup_count": len(lineups),
    })


def _lineup_form(request, map, instance=None):
    if instance is None and not _has_team(request):
        return redirect("map_detail", map.slug)
    form = LineupForm(
        request.POST or None, request.FILES or None, instance=instance, map=map, request=request
    )
    if request.method == "POST" and form.is_valid():
        lineup = form.save(commit=False)
        lineup.map = map
        lineup = _save_new(form, request)
        messages.success(request, f"Saved “{lineup.title}”.")
        return redirect(lineup)
    callouts = set()
    for a, b in Lineup.objects.visible_to(request.user).filter(map=map).values_list("from_callout", "to_callout"):
        callouts.update(x for x in (a, b) if x)
    return render(request, "book/lineup_form.html", {
        "form": form,
        "map": map,
        "lineup": instance,
        "callouts": sorted(callouts, key=str.lower),
        "data": {"layers": layers_json(map)},
    })


def lineup_create(request, slug):
    return _lineup_form(request, get_object_or_404(Map, slug=slug))


def lineup_edit(request, pk):
    lineup = _visible(Lineup, request, pk=pk)
    _require_edit(request, lineup)
    return _lineup_form(request, lineup.map, lineup)


def lineup_detail(request, pk):
    lineup = _visible(Lineup, request, pk=pk)
    if request.method == "POST":
        return _comment_post(request, lineup=lineup)
    return render(request, "book/lineup_detail.html", {
        "lineup": lineup,
        "map": lineup.map,
        "can_edit": can_edit(request.user, lineup),
        "strats": lineup.strats.visible_to(request.user).select_related("map"),
        "comments": lineup.comments.select_related("author"),
        "comment_form": CommentForm(),
        "data": {
            "layers": layers_json(lineup.map),
            "lineups": [lineup_json(lineup, request.user)],
            "selected": lineup.id,
        },
    })


def _delete(request, obj, what, next_url):
    _require_edit(request, obj)
    if request.method == "POST":
        name = str(obj)
        obj.delete()
        messages.success(request, f"Deleted {what} “{name}”.")
        return redirect(next_url)
    return render(request, "book/confirm_delete.html", {"obj": obj, "what": what})


def lineup_delete(request, pk):
    lineup = _visible(Lineup, request, pk=pk)
    return _delete(request, lineup, "lineup", lineup.map.get_absolute_url())


# ---------------------------------------------------------------- strats

def strat_list(request, slug):
    map = get_object_or_404(Map, slug=slug)
    g = request.GET
    qs = Strat.objects.visible_to(request.user).filter(map=map).select_related("team").annotate(
        n_util=Count("lineups", distinct=True)
    )
    if g.get("side") in ("T", "CT"):
        qs = qs.filter(side=g["side"])
    if g.get("kind"):
        qs = qs.filter(kind=g["kind"])
    status = g.get("status", "")
    if status == "all":
        pass
    elif status:
        qs = qs.filter(status=status)
    else:
        qs = qs.exclude(status="retired")
    if g.get("q"):
        q = g["q"]
        qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q) | Q(tags__icontains=q) | Q(area__icontains=q))
    return render(request, "book/strat_list.html", {
        "map": map,
        "tab": "strats",
        "strats": qs,
        "kinds": STRAT_KINDS,
        "statuses": STATUSES,
        "sides": SIDES,
        "f": g,
    })


def _strat_form(request, map, instance=None):
    if instance is None and not _has_team(request):
        return redirect("strat_list", map.slug)
    post, files = request.POST or None, request.FILES or None
    form = StratForm(post, files, instance=instance, map=map, request=request)
    lineup_qs = form.fields["lineups"].queryset
    existing = {s.number: s for s in instance.slots.all()} if instance else {}
    slot_forms = [
        SlotForm(post, instance=existing.get(n), prefix=f"slot{n}", lineup_qs=lineup_qs)
        for n in range(1, SLOT_COUNT + 1)
    ]
    if request.method == "POST" and form.is_valid() and all(sf.is_valid() for sf in slot_forms):
        strat = form.save(commit=False)
        strat.map = map
        strat = _save_new(form, request)
        slot_util = set()
        for n, sf in enumerate(slot_forms, start=1):
            if sf.has_content():
                slot = sf.save(commit=False)
                slot.strat, slot.number = strat, n
                slot.save()
                sf.save_m2m()
                slot_util.update(sf.cleaned_data["lineups"])
            elif n in existing:
                existing[n].delete()
        strat.lineups.add(*slot_util)
        messages.success(request, f"Saved “{strat.title}”.")
        return redirect(strat)
    selected = {int(v) for v in form["lineups"].value() or [] if str(v).isdigit()}
    return render(request, "book/strat_form.html", {
        "form": form,
        "slot_forms": slot_forms,
        "map": map,
        "strat": instance,
        "util_choices": lineup_qs,
        "selected_util": selected,
        "roles": ["Entry", "Second entry", "AWP", "Lurk", "Support", "Anchor", "Rotator", "IGL"],
    })


def strat_create(request, slug):
    return _strat_form(request, get_object_or_404(Map, slug=slug))


def strat_edit(request, pk):
    strat = _visible(Strat, request, pk=pk)
    _require_edit(request, strat)
    return _strat_form(request, strat.map, strat)


def strat_detail(request, pk):
    strat = _visible(Strat, request, pk=pk)
    if request.method == "POST":
        return _comment_post(request, strat=strat)
    user = request.user
    all_util = list(strat.lineups.select_related("team"))
    visible = set(Lineup.objects.visible_to(user).filter(strats=strat).values_list("pk", flat=True))
    util = [lu for lu in all_util if lu.pk in visible]
    util_ids = {lu.id for lu in util}
    slots = list(strat.slots.select_related("player").prefetch_related("lineups"))
    in_slot = set()
    for s in slots:
        s.visible_util = [lu for lu in s.lineups.all() if lu.id in util_ids]
        in_slot.update(lu.id for lu in s.visible_util)
    return render(request, "book/strat_detail.html", {
        "strat": strat,
        "map": strat.map,
        "can_edit": can_edit(user, strat),
        "slots": slots,
        "other_util": [lu for lu in util if lu.id not in in_slot],
        "hidden_util": len(all_util) - len(util),
        "gameplans": strat.gameplans.visible_to(user),
        "comments": strat.comments.select_related("author"),
        "comment_form": CommentForm(),
        "data": {
            "layers": layers_json(strat.map),
            "lineups": [lineup_json(lu, user) for lu in util],
            "board": strat.board,
        },
    })


def strat_delete(request, pk):
    strat = _visible(Strat, request, pk=pk)
    return _delete(request, strat, "strat", reverse("strat_list", args=[strat.map.slug]))


BOARD_SHAPES = {"pen", "arrow", "circle", "player", "enemy", "nade", "text"}
MAX_BOARD_BYTES = 512 * 1024


def clean_board(data, layer_ids):
    if not isinstance(data, dict):
        raise ValueError("board must be an object")
    out = {}
    for key, shapes in data.items():
        if str(key) not in layer_ids:
            continue
        if not isinstance(shapes, list) or len(shapes) > 1000:
            raise ValueError("bad shape list")
        out[str(key)] = [s for s in shapes if isinstance(s, dict) and s.get("t") in BOARD_SHAPES]
    return out


def strat_board(request, pk):
    strat = _visible(Strat, request, pk=pk)
    _require_edit(request, strat)
    if request.method == "POST":
        if len(request.body) > MAX_BOARD_BYTES:
            return HttpResponseBadRequest("Board too large")
        try:
            layer_ids = {str(i) for i in strat.map.layers.values_list("id", flat=True)}
            strat.board = clean_board(json.loads(request.body), layer_ids)
        except (ValueError, json.JSONDecodeError) as e:
            return HttpResponseBadRequest(str(e))
        strat.save(update_fields=["board", "updated_at"])
        return JsonResponse({"ok": True})
    util = Lineup.objects.visible_to(request.user).filter(pk__in=strat.lineups.all()).select_related("team")
    return render(request, "book/strat_board.html", {
        "strat": strat,
        "map": strat.map,
        "data": {
            "layers": layers_json(strat.map),
            "board": strat.board,
            "lineups": [lineup_json(lu, request.user) for lu in util],
        },
    })


# ---------------------------------------------------------------- gameplans

def gameplan_list(request):
    plans = Gameplan.objects.visible_to(request.user).select_related("team", "opponent").annotate(n=Count("strats"))
    today = timezone.localdate()
    return render(request, "book/gameplan_list.html", {
        "upcoming": [p for p in plans if p.match_date is None or p.match_date >= today],
        "past": [p for p in plans if p.match_date and p.match_date < today],
    })


def _gameplan_form(request, instance=None):
    if instance is None and not _has_team(request):
        return redirect("gameplan_list")
    initial = {}
    if instance is None and request.GET.get("opponent", "").isdigit():
        initial["opponent"] = request.GET["opponent"]
    form = GameplanForm(request.POST or None, instance=instance, request=request, initial=initial)
    if request.method == "POST" and form.is_valid():
        plan = _save_new(form, request)
        messages.success(request, f"Saved gameplan “{plan.title}”.")
        return redirect(plan)
    strats = form.fields["strats"].queryset.order_by("map__order", "map__name", "side", "kind", "title")
    selected = {int(v) for v in form["strats"].value() or [] if str(v).isdigit()}
    return render(request, "book/gameplan_form.html", {
        "form": form,
        "plan": instance,
        "strat_groups": [(m, list(g)) for m, g in groupby(strats, key=lambda s: s.map)],
        "selected": selected,
    })


def gameplan_create(request):
    return _gameplan_form(request)


def gameplan_edit(request, pk):
    plan = _visible(Gameplan, request, pk=pk)
    _require_edit(request, plan)
    return _gameplan_form(request, plan)


def gameplan_detail(request, pk):
    plan = _visible(Gameplan, request, pk=pk)
    strats = (
        plan.strats.visible_to(request.user)
        .select_related("map")
        .annotate(n_util=Count("lineups", distinct=True))
        .order_by("map__order", "map__name", "side", "kind", "title")
    )
    notes = []
    if plan.opponent and plan.opponent in Opponent.objects.visible_to(request.user):
        notes = plan.opponent.entries.select_related("map", "author")
    return render(request, "book/gameplan_detail.html", {
        "plan": plan,
        "can_edit": can_edit(request.user, plan),
        "groups": [(m, list(g)) for m, g in groupby(strats, key=lambda s: s.map)],
        "opponent_notes": notes,
    })


def gameplan_delete(request, pk):
    plan = _visible(Gameplan, request, pk=pk)
    return _delete(request, plan, "gameplan", reverse("gameplan_list"))


# ---------------------------------------------------------------- opponents

def opponent_list(request):
    return render(request, "book/opponent_list.html", {
        "opponents": Opponent.objects.visible_to(request.user).select_related("team").annotate(
            n_notes=Count("entries", distinct=True)
        ),
    })


def _opponent_form(request, instance=None):
    if instance is None and not _has_team(request):
        return redirect("opponent_list")
    form = OpponentForm(request.POST or None, instance=instance, request=request)
    if request.method == "POST" and form.is_valid():
        opp = _save_new(form, request)
        return redirect(opp)
    return render(request, "book/opponent_form.html", {"form": form, "opponent": instance})


def opponent_create(request):
    return _opponent_form(request)


def opponent_edit(request, pk):
    opp = _visible(Opponent, request, pk=pk)
    _require_edit(request, opp)
    return _opponent_form(request, opp)


def opponent_detail(request, pk):
    opp = _visible(Opponent, request, pk=pk)
    form = OpponentNoteForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        note = form.save(commit=False)
        note.opponent, note.author = opp, request.user
        note.save()
        return redirect(opp)
    entries = opp.entries.select_related("map", "author")
    map_filter = request.GET.get("map", "")
    if map_filter:
        entries = entries.filter(map__slug=map_filter)
    return render(request, "book/opponent_detail.html", {
        "opponent": opp,
        "can_edit": can_edit(request.user, opp),
        "entries": entries,
        "maps": Map.objects.all(),
        "map_filter": map_filter,
        "form": form,
        "gameplans": opp.gameplans.visible_to(request.user),
    })


def opponent_delete(request, pk):
    opp = _visible(Opponent, request, pk=pk)
    return _delete(request, opp, "opponent", reverse("opponent_list"))


@require_POST
def opponent_note_delete(request, pk):
    note = get_object_or_404(OpponentNote, pk=pk, opponent__in=Opponent.objects.visible_to(request.user))
    if note.author_id != request.user.id and not can_edit(request.user, note.opponent):
        raise PermissionDenied
    note.delete()
    return redirect(note.opponent)


@require_POST
def comment_delete(request, pk):
    c = get_object_or_404(Comment, pk=pk)
    target = c.strat or c.lineup
    if not type(target).objects.visible_to(request.user).filter(pk=target.pk).exists():
        raise Http404
    if c.author_id != request.user.id and not request.user.is_staff:
        raise PermissionDenied
    c.delete()
    return redirect(target.get_absolute_url() + "#comments")


# ---------------------------------------------------------------- media

_RANGE = re.compile(r"bytes=(\d*)-(\d*)")


def _media_allowed(user, path):
    if path.startswith("radars/"):
        return True
    for model, fields in ((Lineup, ("video_file", "pos_image", "aim_image")), (Strat, ("video_file",))):
        q = Q()
        for f in fields:
            q |= Q(**{f: path})
        ids = list(model.objects.filter(q).values_list("pk", flat=True))
        if ids:
            return model.objects.visible_to(user).filter(pk__in=ids).exists()
    return False


def _file_chunks(f, length, chunk=64 * 1024):
    with f:
        while length > 0:
            data = f.read(min(chunk, length))
            if not data:
                break
            length -= len(data)
            yield data


def protected_media(request, path):
    """Uploaded files: login required, and only if you can see the owning item.

    Supports HTTP Range so videos can be scrubbed even without a proxy.
    """
    try:
        full = safe_join(settings.MEDIA_ROOT, path)
    except SuspiciousFileOperation:
        raise Http404
    if not os.path.isfile(full) or not _media_allowed(request.user, path):
        raise Http404
    ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
    if settings.MEDIA_X_ACCEL:
        resp = HttpResponse(content_type=ctype)
        resp["X-Accel-Redirect"] = "/" + path.lstrip("/")
        return resp
    size = os.path.getsize(full)
    m = _RANGE.fullmatch(request.headers.get("Range", "").strip())
    if m and m.group(1) + m.group(2):
        first, last = m.groups()
        if first:
            start, end = int(first), int(last) if last else size - 1
        else:
            start, end = max(size - int(last), 0), size - 1
        end = min(end, size - 1)
        if start > end:
            resp = HttpResponse(status=416)
            resp["Content-Range"] = f"bytes */{size}"
            return resp
        f = open(full, "rb")
        f.seek(start)
        resp = StreamingHttpResponse(_file_chunks(f, end - start + 1), status=206, content_type=ctype)
        resp["Content-Range"] = f"bytes {start}-{end}/{size}"
        resp["Content-Length"] = str(end - start + 1)
    else:
        resp = FileResponse(open(full, "rb"), content_type=ctype)
    resp["Accept-Ranges"] = "bytes"
    resp["Cache-Control"] = "private, max-age=86400"
    return resp
