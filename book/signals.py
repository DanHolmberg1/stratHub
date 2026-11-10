"""Remove uploaded files from disk when they're replaced, cleared or their item is deleted."""

from django.db.models.signals import post_delete, pre_save

from .models import Lineup, MapLayer, Strat

FILE_FIELDS = {
    Lineup: ("video_file", "pos_image", "aim_image"),
    Strat: ("video_file",),
    MapLayer: ("radar",),
}


def _remove(f):
    if f and f.name:
        f.storage.delete(f.name)


def _on_delete(sender, instance, **kwargs):
    for name in FILE_FIELDS[sender]:
        _remove(getattr(instance, name))


def _on_save(sender, instance, **kwargs):
    if not instance.pk:
        return
    old = sender.objects.filter(pk=instance.pk).first()
    if not old:
        return
    for name in FILE_FIELDS[sender]:
        before, after = getattr(old, name), getattr(instance, name)
        if before and before.name != (after.name if after else None):
            _remove(before)


for model in FILE_FIELDS:
    post_delete.connect(_on_delete, sender=model, dispatch_uid=f"files-del-{model.__name__}")
    pre_save.connect(_on_save, sender=model, dispatch_uid=f"files-save-{model.__name__}")
