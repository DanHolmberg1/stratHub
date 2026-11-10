import io
import json
import shutil
import tempfile
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from org.models import Invite, Team

from .embeds import embed_src
from .models import Comment, Gameplan, Lineup, Map, Opponent, OpponentNote, Strat

TMP_MEDIA = tempfile.mkdtemp(prefix="strathub-test-media-")
User = get_user_model()


def png_bytes(w=64, h=64):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), "gray").save(buf, "PNG")
    return buf.getvalue()


@override_settings(MEDIA_ROOT=TMP_MEDIA, MEDIA_X_ACCEL=False)
class Base(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TMP_MEDIA, ignore_errors=True)

    def setUp(self):
        call_command("seed_maps", stdout=io.StringIO())
        self.mirage = Map.objects.get(slug="mirage")
        self.nuke = Map.objects.get(slug="nuke")
        self.main = Team.objects.create(name="Main")
        self.academy = Team.objects.create(name="Academy")
        self.alice = User.objects.create_user("alice", password="pw-alice-123!")  # Main
        self.bob = User.objects.create_user("bob", password="pw-bob-123!")  # Academy
        self.admin = User.objects.create_user("boss", password="pw-boss-123!", is_staff=True, is_superuser=True)
        self.main.members.add(self.alice)
        self.academy.members.add(self.bob)
        self.layer = self.mirage.layers.first()

    def lineup(self, team, **kw):
        defaults = dict(
            map=self.mirage, layer=self.layer, title="Window smoke", side="T", nade="smoke",
            from_x=0.1, from_y=0.2, to_x=0.5, to_y=0.5, team=team,
        )
        defaults.update(kw)
        return Lineup.objects.create(**defaults)

    def strat(self, team, **kw):
        defaults = dict(map=self.mirage, title="A exec", side="T", kind="execute", team=team)
        defaults.update(kw)
        return Strat.objects.create(**defaults)


class LoginTests(Base):
    def test_everything_requires_login(self):
        for url in [reverse("dashboard"), reverse("map_detail", args=["mirage"]), reverse("gameplan_list")]:
            r = self.client.get(url)
            self.assertEqual(r.status_code, 302)
            self.assertTrue(r["Location"].startswith(reverse("login")))

    def test_login_page_and_login(self):
        self.assertEqual(self.client.get(reverse("login")).status_code, 200)
        r = self.client.post(reverse("login"), {"username": "alice", "password": "pw-alice-123!"})
        self.assertRedirects(r, reverse("dashboard"))


class ScopingTests(Base):
    def test_other_team_private_content_is_404(self):
        lu = self.lineup(self.main)
        st = self.strat(self.main)
        opp = Opponent.objects.create(name="Rivals", team=self.main)
        plan = Gameplan.objects.create(title="Cup", team=self.main)
        self.client.force_login(self.bob)
        for url in [
            reverse("lineup_detail", args=[lu.pk]), reverse("lineup_edit", args=[lu.pk]),
            reverse("strat_detail", args=[st.pk]), reverse("strat_edit", args=[st.pk]),
            reverse("strat_board", args=[st.pk]), reverse("opponent_detail", args=[opp.pk]),
            reverse("gameplan_detail", args=[plan.pk]), reverse("gameplan_edit", args=[plan.pk]),
        ]:
            self.assertEqual(self.client.get(url).status_code, 404, url)
        r = self.client.get(reverse("map_detail", args=["mirage"]))
        self.assertNotContains(r, "Window smoke")
        r = self.client.get(reverse("strat_list", args=["mirage"]))
        self.assertNotContains(r, "A exec")

    def test_shared_content_visible_but_not_editable(self):
        lu = self.lineup(self.main, shared=True)
        st = self.strat(self.main, shared=True)
        self.client.force_login(self.bob)
        self.assertEqual(self.client.get(reverse("lineup_detail", args=[lu.pk])).status_code, 200)
        self.assertContains(self.client.get(reverse("map_detail", args=["mirage"])), "Window smoke")
        self.assertEqual(self.client.get(reverse("strat_detail", args=[st.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("lineup_edit", args=[lu.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("strat_delete", args=[st.pk])).status_code, 403)
        self.assertTrue(Strat.objects.filter(pk=st.pk).exists())
        self.assertEqual(self.client.post(reverse("strat_board", args=[st.pk]), "{}", content_type="application/json").status_code, 403)

    def test_admin_sees_everything(self):
        lu = self.lineup(self.academy)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("lineup_edit", args=[lu.pk])).status_code, 200)

    def test_cannot_post_content_for_other_team(self):
        self.client.force_login(self.bob)
        r = self.client.post(reverse("strat_create", args=["mirage"]), {
            "title": "Sneaky", "side": "T", "kind": "default", "status": "draft", "team": self.main.pk,
        })
        self.assertEqual(r.status_code, 200)  # form error, not saved
        self.assertFalse(Strat.objects.filter(title="Sneaky").exists())

    def test_shared_strat_hides_private_linked_util(self):
        private = self.lineup(self.main, title="Secret flash")
        st = self.strat(self.main, shared=True)
        st.lineups.add(private)
        self.client.force_login(self.bob)
        r = self.client.get(reverse("strat_detail", args=[st.pk]))
        self.assertNotContains(r, "Secret flash")
        self.assertContains(r, "not shared")

    def test_user_without_team_cannot_create(self):
        loner = User.objects.create_user("loner", password="x-123456789!")
        self.client.force_login(loner)
        r = self.client.get(reverse("lineup_create", args=["mirage"]))
        self.assertRedirects(r, reverse("map_detail", args=["mirage"]))

    def test_comment_delete_rules(self):
        lu = self.lineup(self.main, shared=True)
        c = Comment.objects.create(author=self.alice, body="nice", lineup=lu)
        self.client.force_login(self.bob)
        self.assertEqual(self.client.post(reverse("comment_delete", args=[c.pk])).status_code, 403)
        self.client.force_login(self.alice)
        self.client.post(reverse("comment_delete", args=[c.pk]))
        self.assertFalse(Comment.objects.filter(pk=c.pk).exists())


class LineupFlowTests(Base):
    def test_create_lineup_with_upload_and_link(self):
        self.client.force_login(self.alice)
        r = self.client.post(reverse("lineup_create", args=["mirage"]), {
            "title": "CT smoke", "side": "T", "nade": "smoke", "layer": self.layer.pk,
            "from_x": "0.2", "from_y": "0.3", "to_x": "0.6", "to_y": "0.4",
            "technique": "jumpthrow", "click": "left", "team": self.main.pk,
            "video_url": "https://youtu.be/dQw4w9WgXcQ?t=30",
            "video_file": SimpleUploadedFile("clip.mp4", b"\x00" * 2048, content_type="video/mp4"),
            "pos_image": SimpleUploadedFile("pos.png", png_bytes(), content_type="image/png"),
        })
        lu = Lineup.objects.get(title="CT smoke")
        self.assertRedirects(r, lu.get_absolute_url())
        self.assertEqual(lu.created_by, self.alice)
        self.assertTrue(lu.video_file.name.startswith("lineups/"))
        self.assertNotIn("clip", lu.video_file.name)  # random names
        page = self.client.get(reverse("map_detail", args=["mirage"]))
        data = page.context["data"]["lineups"][0]
        self.assertEqual(data["video"], {"file": lu.video_file.url})

    def test_lineup_needs_positions(self):
        self.client.force_login(self.alice)
        r = self.client.post(reverse("lineup_create", args=["mirage"]), {
            "title": "x", "side": "T", "nade": "smoke", "layer": self.layer.pk,
            "technique": "stand", "click": "left", "team": self.main.pk,
        })
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Click the radar")

    def test_rejects_non_video_upload(self):
        self.client.force_login(self.alice)
        r = self.client.post(reverse("lineup_create", args=["mirage"]), {
            "title": "x", "side": "T", "nade": "smoke", "layer": self.layer.pk,
            "from_x": "0.2", "from_y": "0.3", "to_x": "0.6", "to_y": "0.4",
            "technique": "stand", "click": "left", "team": self.main.pk,
            "video_file": SimpleUploadedFile("evil.exe", b"MZ", content_type="video/mp4"),
        })
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Lineup.objects.exists())

    def test_layer_must_belong_to_map(self):
        self.client.force_login(self.alice)
        r = self.client.post(reverse("lineup_create", args=["mirage"]), {
            "title": "x", "side": "T", "nade": "smoke", "layer": self.nuke.layers.first().pk,
            "from_x": "0.2", "from_y": "0.3", "to_x": "0.6", "to_y": "0.4",
            "technique": "stand", "click": "left", "team": self.main.pk,
        })
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Lineup.objects.exists())


class StratFlowTests(Base):
    def test_create_strat_with_slots_links_util(self):
        smoke = self.lineup(self.main)
        flash = self.lineup(self.main, title="Pop flash", nade="flash")
        self.client.force_login(self.alice)
        r = self.client.post(reverse("strat_create", args=["mirage"]), {
            "title": "A split", "side": "T", "kind": "split", "status": "testing", "team": self.main.pk,
            "description": "Go A on 1:30", "lineups": [smoke.pk],
            "slot1-role": "Entry", "slot1-instructions": "Swing first", "slot1-lineups": [flash.pk],
            "slot1-player": self.alice.pk,
        })
        st = Strat.objects.get(title="A split")
        self.assertRedirects(r, st.get_absolute_url())
        self.assertEqual(set(st.lineups.values_list("pk", flat=True)), {smoke.pk, flash.pk})
        self.assertEqual(st.slots.count(), 1)
        page = self.client.get(st.get_absolute_url())
        self.assertContains(page, "Swing first")
        self.assertContains(page, "Pop flash")

        # Editing: clearing a slot removes it
        r = self.client.post(reverse("strat_edit", args=[st.pk]), {
            "title": "A split", "side": "T", "kind": "split", "status": "active", "team": self.main.pk,
            "lineups": [smoke.pk],
        })
        self.assertEqual(st.slots.count(), 0)

    def test_strat_list_filters(self):
        self.strat(self.main, title="CT stack B", side="CT", kind="ct_setup")
        self.strat(self.main, title="Old rush", status="retired")
        self.strat(self.main, title="T default", kind="default")
        self.client.force_login(self.alice)
        url = reverse("strat_list", args=["mirage"])
        r = self.client.get(url, {"side": "CT"})
        self.assertContains(r, "CT stack B")
        self.assertNotContains(r, "T default")
        r = self.client.get(url)
        self.assertNotContains(r, "Old rush")
        self.assertContains(self.client.get(url, {"status": "all"}), "Old rush")
        self.assertContains(self.client.get(url, {"q": "stack"}), "CT stack B")

    def test_board_save_and_validation(self):
        st = self.strat(self.main)
        self.client.force_login(self.alice)
        url = reverse("strat_board", args=[st.pk])
        board = {str(self.layer.pk): [{"t": "arrow", "a": [0.1, 0.1], "b": [0.2, 0.2], "c": "#fff"}, {"t": "evil"}], "99999": [{"t": "pen"}]}
        r = self.client.post(url, json.dumps(board), content_type="application/json")
        self.assertEqual(r.status_code, 200)
        st.refresh_from_db()
        self.assertEqual(list(st.board), [str(self.layer.pk)])
        self.assertEqual(len(st.board[str(self.layer.pk)]), 1)
        self.assertEqual(self.client.post(url, "not json", content_type="application/json").status_code, 400)


class MediaTests(Base):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.alice)
        self.client.post(reverse("lineup_create", args=["mirage"]), {
            "title": "Vid", "side": "T", "nade": "smoke", "layer": self.layer.pk,
            "from_x": "0.2", "from_y": "0.3", "to_x": "0.6", "to_y": "0.4",
            "technique": "stand", "click": "left", "team": self.main.pk,
            "video_file": SimpleUploadedFile("c.mp4", bytes(range(256)) * 4, content_type="video/mp4"),
        })
        self.lu = Lineup.objects.get(title="Vid")
        self.url = self.lu.video_file.url

    def test_owner_can_stream_with_range(self):
        r = self.client.get(self.url, HTTP_RANGE="bytes=10-19")
        self.assertEqual(r.status_code, 206)
        self.assertEqual(b"".join(r.streaming_content), bytes(range(10, 20)))
        self.assertEqual(r["Content-Range"], "bytes 10-19/1024")
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Accept-Ranges"], "bytes")

    def test_media_needs_login_and_visibility(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.client.force_login(self.bob)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.lu.shared = True
        self.lu.save()
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_path_traversal_and_orphans(self):
        self.assertEqual(self.client.get("/media/../strathub/settings.py").status_code, 404)
        self.assertEqual(self.client.get("/media/lineups/doesnotexist.mp4").status_code, 404)

    @override_settings(MEDIA_X_ACCEL=True)
    def test_x_accel(self):
        r = self.client.get(self.url)
        self.assertEqual(r["X-Accel-Redirect"], "/" + self.lu.video_file.name)


class InviteTests(Base):
    def test_join_with_invite(self):
        inv = Invite.objects.create(expires_at=timezone.now() + timedelta(days=1), note="Carl")
        inv.teams.add(self.academy)
        url = reverse("join", args=[inv.token])
        self.assertEqual(self.client.get(url).status_code, 200)
        r = self.client.post(url, {"username": "carl", "password1": "Sup3r-secret-pw", "password2": "Sup3r-secret-pw"})
        self.assertRedirects(r, reverse("dashboard"))
        carl = User.objects.get(username="carl")
        self.assertEqual(list(carl.teams.all()), [self.academy])
        self.assertFalse(carl.is_staff)
        # single use
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 410)

    def test_expired_invite(self):
        inv = Invite.objects.create(expires_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(self.client.get(reverse("join", args=[inv.token])).status_code, 410)

    def test_only_staff_manage_invites(self):
        self.client.force_login(self.alice)
        self.assertNotEqual(self.client.get(reverse("invites")).status_code, 200)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("invites")).status_code, 200)
        r = self.client.post(reverse("invites"), {"note": "x", "teams": [self.main.pk], "max_uses": 1, "days": 7})
        self.assertRedirects(r, reverse("invites"))
        self.assertEqual(Invite.objects.count(), 1)

    def test_team_switch(self):
        self.academy.members.add(self.alice)
        self.client.force_login(self.alice)
        self.client.post(reverse("switch_team"), {"team": self.academy.pk, "next": "https://evil.example"})
        self.assertEqual(self.client.session["team_id"], self.academy.pk)
        # can't switch to a team you're not on
        other = Team.objects.create(name="Other")
        self.client.post(reverse("switch_team"), {"team": other.pk})
        self.assertEqual(self.client.session["team_id"], self.academy.pk)


class PagesRenderTests(Base):
    """Every page renders for a normal member (catches template errors)."""

    def test_all_pages(self):
        lu = self.lineup(self.main, video_url="https://streamable.com/abc123")
        st = self.strat(self.main, video_url="https://example.com/vid")
        st.lineups.add(lu)
        st.slots.create(number=1, role="AWP")
        opp = Opponent.objects.create(name="Rivals", team=self.main)
        OpponentNote.objects.create(opponent=opp, body="Stack B", map=self.mirage, author=self.alice)
        plan = Gameplan.objects.create(title="Cup", team=self.main, opponent=opp, match_date=timezone.localdate())
        plan.strats.add(st)
        Comment.objects.create(author=self.alice, body="gg", strat=st)
        self.client.force_login(self.alice)
        urls = [
            reverse("dashboard"), reverse("map_detail", args=["mirage"]), reverse("map_detail", args=["nuke"]),
            reverse("lineup_create", args=["mirage"]), reverse("lineup_detail", args=[lu.pk]),
            reverse("lineup_edit", args=[lu.pk]), reverse("lineup_delete", args=[lu.pk]),
            reverse("strat_list", args=["mirage"]), reverse("strat_create", args=["mirage"]),
            reverse("strat_detail", args=[st.pk]), reverse("strat_edit", args=[st.pk]),
            reverse("strat_board", args=[st.pk]), reverse("strat_delete", args=[st.pk]),
            reverse("gameplan_list"), reverse("gameplan_create"), reverse("gameplan_detail", args=[plan.pk]),
            reverse("gameplan_edit", args=[plan.pk]), reverse("opponent_list"), reverse("opponent_create"),
            reverse("opponent_detail", args=[opp.pk]), reverse("opponent_edit", args=[opp.pk]),
            reverse("password_change"),
        ]
        for url in urls:
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200, url)
        self.client.force_login(self.admin)
        for url in [reverse("invites"), reverse("admin:book_map_change", args=[self.nuke.pk])]:
            self.assertEqual(self.client.get(url).status_code, 200, url)


class MapPoolTests(Base):
    def test_archived_maps_keep_content(self):
        self.lineup(self.main)
        self.mirage.active = False
        self.mirage.save()
        self.client.force_login(self.alice)
        r = self.client.get(reverse("dashboard"))
        self.assertContains(r, "Archived maps")
        self.assertEqual(self.client.get(reverse("map_detail", args=["mirage"])).status_code, 200)

    def test_import_radars(self):
        d = tempfile.mkdtemp()
        try:
            with open(f"{d}/de_nuke_radar_psd.png", "wb") as f:
                f.write(png_bytes(100, 80))
            with open(f"{d}/de_nuke_lower_radar_psd.png", "wb") as f:
                f.write(png_bytes())
            call_command("import_radars", d, stdout=io.StringIO())
            upper, lower = self.nuke.layers.all()
            self.assertTrue(upper.radar and lower.radar)
            self.assertAlmostEqual(upper.aspect, 0.8)
        finally:
            shutil.rmtree(d)


class EmbedTests(TestCase):
    def test_embeds(self):
        cases = {
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ": "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ?t=1m5s": "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ?start=65",
            "https://youtube.com/shorts/dQw4w9WgXcQ": "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ",
            "https://streamable.com/abc123": "https://streamable.com/e/abc123",
            "https://medal.tv/games/cs2/clips/iSdvIcSnF7T_H/d1337xBYlSUH?invite=x": "https://medal.tv/games/cs2/clips/iSdvIcSnF7T_H/d1337xBYlSUH?theater=true",
        }
        for url, want in cases.items():
            self.assertEqual(embed_src(url), want, url)
        for bad in ["javascript:alert(1)", "https://evil.com/watch?v=x", "https://youtube.com/watch?v=<script>", ""]:
            self.assertIsNone(embed_src(bad), bad)


class NewMapAndCleanupTests(Base):
    def test_add_map_in_admin_gets_default_layer(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse("admin:book_map_add"), {
            "name": "Mill", "slug": "mill", "game_id": "de_mill", "active": "on", "order": 20,
            "layers-TOTAL_FORMS": "0", "layers-INITIAL_FORMS": "0",
            "layers-MIN_NUM_FORMS": "0", "layers-MAX_NUM_FORMS": "1000",
        })
        self.assertEqual(r.status_code, 302)
        mill = Map.objects.get(slug="mill")
        self.assertEqual(mill.layers.count(), 1)
        self.client.force_login(self.alice)
        self.assertContains(self.client.get(reverse("dashboard")), "Mill")
        for url in [reverse("map_detail", args=["mill"]), reverse("lineup_create", args=["mill"])]:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_map_without_layers_still_renders(self):
        bare = Map.objects.create(name="Bare", slug="bare")
        self.client.force_login(self.alice)
        r = self.client.get(reverse("map_detail", args=["bare"]))
        self.assertEqual(len(r.context["data"]["layers"]), 1)

    def test_files_removed_on_replace_and_delete(self):
        import os
        self.client.force_login(self.alice)
        post = {
            "title": "Vid", "side": "T", "nade": "smoke", "layer": self.layer.pk,
            "from_x": "0.2", "from_y": "0.3", "to_x": "0.6", "to_y": "0.4",
            "technique": "stand", "click": "left", "team": self.main.pk,
        }
        self.client.post(reverse("lineup_create", args=["mirage"]), {**post, "video_file": SimpleUploadedFile("a.webm", b"1" * 100)})
        lu = Lineup.objects.get(title="Vid")
        first = lu.video_file.path
        self.client.post(reverse("lineup_edit", args=[lu.pk]), {**post, "video_file": SimpleUploadedFile("b.webm", b"2" * 100)})
        lu.refresh_from_db()
        self.assertFalse(os.path.exists(first))
        second = lu.video_file.path
        self.assertTrue(os.path.exists(second))
        self.client.post(reverse("lineup_delete", args=[lu.pk]))
        self.assertFalse(os.path.exists(second))

    def test_mov_rejected(self):
        self.client.force_login(self.alice)
        self.client.post(reverse("lineup_create", args=["mirage"]), {
            "title": "Mov", "side": "T", "nade": "smoke", "layer": self.layer.pk,
            "from_x": "0.2", "from_y": "0.3", "to_x": "0.6", "to_y": "0.4",
            "technique": "stand", "click": "left", "team": self.main.pk,
            "video_file": SimpleUploadedFile("a.mov", b"1" * 100),
        })
        self.assertFalse(Lineup.objects.filter(title="Mov").exists())
