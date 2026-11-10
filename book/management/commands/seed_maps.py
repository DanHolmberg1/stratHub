from django.core.management.base import BaseCommand

from book.models import Map

# (name, slug, game_id, active, [(layer name, key), ...])
# Active duty pool as of Nov 2026. After a pool change, flip `active` in the
# admin (Maps page) or edit this list and re-run; existing maps are left alone
# except for `active`, which is only set with --sync-active.
POOL = [
    ("Ancient", "ancient", "de_ancient", True, [("Default", "")]),
    ("Anubis", "anubis", "de_anubis", True, [("Default", "")]),
    ("Cache", "cache", "de_cache", True, [("Default", "")]),
    ("Dust II", "dust2", "de_dust2", True, [("Default", "")]),
    ("Inferno", "inferno", "de_inferno", True, [("Default", "")]),
    ("Mirage", "mirage", "de_mirage", True, [("Default", "")]),
    ("Nuke", "nuke", "de_nuke", True, [("Upper", ""), ("Lower", "lower")]),
    ("Overpass", "overpass", "de_overpass", False, [("Default", "")]),
    ("Train", "train", "de_train", False, [("Upper", ""), ("Lower", "lower")]),
    ("Vertigo", "vertigo", "de_vertigo", False, [("Upper", ""), ("Lower", "lower")]),
]


class Command(BaseCommand):
    help = "Create the CS2 maps (and their radar layers) if they don't exist yet."

    def add_arguments(self, parser):
        parser.add_argument(
            "--sync-active", action="store_true",
            help="Also set active/inactive on existing maps to match the list above",
        )

    def handle(self, *args, sync_active=False, **opts):
        for order, (name, slug, game_id, active, layers) in enumerate(POOL):
            m, created = Map.objects.get_or_create(
                slug=slug, defaults={"name": name, "game_id": game_id, "active": active, "order": order}
            )
            if not created and sync_active and m.active != active:
                m.active = active
                m.save(update_fields=["active"])
                self.stdout.write(f"{name}: active={active}")
            if not m.layers.exists():
                for i, (lname, key) in enumerate(layers):
                    m.layers.create(name=lname, key=key, order=i)
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created {name}"))
        self.stdout.write("Done. Upload radar images in the admin or run import_radars.")
