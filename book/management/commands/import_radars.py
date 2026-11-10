from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

from book.models import MapLayer


class Command(BaseCommand):
    help = (
        "Attach radar images from a folder. Files are matched by the map's game_id "
        "and layer key, e.g. de_mirage_radar_psd.png, de_nuke_radar_psd.png and "
        "de_nuke_lower_radar_psd.png (the names CS2 uses in "
        "panorama/images/overheadmaps). Plain de_mirage.png / de_nuke_lower.png also work."
    )

    def add_arguments(self, parser):
        parser.add_argument("folder")
        parser.add_argument("--overwrite", action="store_true", help="Replace radars that are already set")

    def handle(self, folder, overwrite=False, **opts):
        root = Path(folder)
        if not root.is_dir():
            raise CommandError(f"{root} is not a folder")
        files = {p.stem.lower(): p for p in root.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")}
        for layer in MapLayer.objects.select_related("map"):
            if not layer.map.game_id or (layer.radar and not overwrite):
                continue
            base = layer.map.game_id.lower() + (f"_{layer.key}" if layer.key else "")
            for stem in (f"{base}_radar_psd", f"{base}_radar", base):
                if stem in files:
                    with files[stem].open("rb") as fh:
                        layer.radar.save(files[stem].name, File(fh), save=True)
                    self.stdout.write(self.style.SUCCESS(f"{layer}: {files[stem].name}"))
                    break
            else:
                self.stdout.write(f"{layer}: no file found (looked for {base}_radar_psd.png)")
