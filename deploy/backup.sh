#!/bin/sh
# Nightly backup: consistent SQLite snapshot + media mirror. Needs sqlite3 and rsync.
# Cron example: 30 4 * * * /srv/strathub/app/deploy/backup.sh /srv/backups/strathub
set -eu
DATA=${STRATHUB_DATA_DIR:-/srv/strathub/data}
DEST=${1:?usage: backup.sh DEST_DIR}
STAMP=$(date +%Y%m%d-%H%M)
mkdir -p "$DEST"
sqlite3 "$DATA/db.sqlite3" ".backup '$DEST/db-$STAMP.sqlite3'"
# Videos are big: mirror them incrementally instead of re-archiving every night.
# (No --delete, so files removed in the app are still kept in the backup.)
rsync -a "$DATA/media/" "$DEST/media/"
# keep 14 days of database snapshots
find "$DEST" -name 'db-*.sqlite3' -mtime +14 -delete
