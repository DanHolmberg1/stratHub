# stratHub

A self-hosted stratbook for a CS2 org: utility lineups on the radar, strats with
player roles and linked util, a drawing board, match-day gameplans and opponent notes.

Built with Django + SQLite and plain JavaScript (no Node/build step).

## Features

- **Util map** per map: lineups drawn on the radar (throw spot → landing spot). Filter by side
  (T/CT), grenade type and text. Shift-click a chip for "only this one". The filter is kept in the URL,
  so `…/maps/mirage/#side=CT&nade=flash` is a shareable "CT flashes" link.
- **Lineups**: video upload *or* YouTube/Medal/Streamable link, position + aim screenshots,
  callouts (autocompleted per map), throw technique, tags, comments.
- **Strats**: type (default, execute, split, fake, pistol, eco, anti-eco, retake, CT setup, spot-specific
  play…), status (draft → testing → in rotation → retired), description, round video, linked util,
  a role/job/util for each of players 1–5, and a **drawing board** (arrows, freehand, areas, players,
  enemies, smokes/flashes/mollies, text) per radar layer.
- **Gameplans**: pick strats for a match/opponent. Shows your notes on that opponent alongside.
- **Opponents**: anti-strat notes per map and side.
- **Teams**: one org, several rosters. Content belongs to a team; tick *Shared* to let every
  roster see it (only the owning team can edit). Org admins see and edit everything.
- **Invite-only accounts**: admins create invite links at `/invites/`.
- **Map pool changes**: maps are database rows. Untick *active* in Admin → Maps to archive one
  (its content is kept); add a new map + radar there too. Multi-floor maps (Nuke) have several layers.

## Local development

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_maps          # current active duty pool + a few archived maps
.venv/bin/python manage.py createsuperuser    # your org admin account
.venv/bin/python manage.py runserver
```

Then log in at http://127.0.0.1:8000, create a team in **Admin → Teams** (add yourself to it), and
invite your players from **Invites**.

Run the tests with `.venv/bin/python manage.py test`.

## Radar images

The app does not ship radar images. Either upload one per layer in **Admin → Maps**, or import a folder:

```sh
.venv/bin/python manage.py import_radars /path/to/radars
```

Files are matched by in-game name: `de_mirage_radar_psd.png`, `de_nuke_radar_psd.png`,
`de_nuke_lower_radar_psd.png` (plain `de_mirage.png` also works). These are the names CS2 uses under
`panorama/images/overheadmaps/` inside `game/csgo/pak01_dir.vpk`. You can extract them with
[Source 2 Viewer](https://valveresourceformat.github.io/). Lineup positions are stored relative to the
image, so use the same radar for everyone and avoid swapping in one with a different crop later.

## When the map pool changes

1. **Admin → Maps**: untick *Active* on the outgoing map (lineups and strats stay, under "Archived maps").
2. Add the incoming map (or re-activate it). Give it a slug, its `de_…` game id and a layer with a radar.
   For a two-floor map add a second layer with key `lower`.

## Deploying on your own server

Tested here: the app, tests and browser UI on the dev server. **Not tested here**: the files in
`deploy/` (systemd, Caddy, backup). They're a standard setup, but check them on your box.

```sh
# as root, on the server (Debian/Ubuntu/Arch alike)
useradd --system --home /srv/strathub strathub
mkdir -p /srv/strathub/data && chown -R strathub: /srv/strathub
git clone <this repo> /srv/strathub/app      # or copy the folder
cd /srv/strathub/app && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp deploy/strathub.env.example /etc/strathub.env && chmod 600 /etc/strathub.env   # edit it!
set -a; . /etc/strathub.env; set +a
sudo -E -u strathub .venv/bin/python manage.py migrate
sudo -E -u strathub .venv/bin/python manage.py collectstatic --noinput
sudo -E -u strathub .venv/bin/python manage.py seed_maps
sudo -E -u strathub .venv/bin/python manage.py createsuperuser
cp deploy/strathub.service /etc/systemd/system/ && systemctl enable --now strathub
cp deploy/Caddyfile /etc/caddy/Caddyfile   # set your domain, then: systemctl reload caddy
```

Caddy is set up for HTTPS. Uploaded media is never served as a public folder: every `/media/…`
request goes through Django, which checks login and team access, then hands the file to Caddy
(`X-Accel-Redirect`). With `STRATHUB_MEDIA_X_ACCEL=0`, Django streams files itself, which is fine for
small orgs and supports video seeking.

**Backups**: everything lives in `STRATHUB_DATA_DIR` (`db.sqlite3` + `media/`).
`deploy/backup.sh /path/to/backups` makes a safe SQLite snapshot and mirrors the media folder.
Run it from cron.

**Updating**: `git pull && .venv/bin/pip install -r requirements.txt && manage.py migrate && manage.py collectstatic --noinput && systemctl restart strathub`.
