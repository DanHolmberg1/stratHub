from django.contrib import admin

from .models import Gameplan, Lineup, Map, MapLayer, Opponent, Strat


class MapLayerInline(admin.TabularInline):
    model = MapLayer
    extra = 0
    fields = ["name", "key", "order", "radar"]


@admin.register(Map)
class MapAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "game_id", "active", "order"]
    list_editable = ["active", "order"]
    prepopulated_fields = {"slug": ["name"]}
    inlines = [MapLayerInline]

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        if not form.instance.layers.exists():
            form.instance.layers.create(name="Default")


@admin.register(Lineup)
class LineupAdmin(admin.ModelAdmin):
    list_display = ["title", "map", "side", "nade", "team", "shared"]
    list_filter = ["map", "side", "nade", "team", "shared"]
    search_fields = ["title", "from_callout", "to_callout", "tags"]


@admin.register(Strat)
class StratAdmin(admin.ModelAdmin):
    list_display = ["title", "map", "side", "kind", "status", "team", "shared"]
    list_filter = ["map", "side", "kind", "status", "team"]
    search_fields = ["title", "description", "tags"]
    filter_horizontal = ["lineups"]
    exclude = ["board"]


admin.site.register(Gameplan)
admin.site.register(Opponent)
