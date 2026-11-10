from django.contrib import admin

from .models import Invite, Team


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ["name", "member_count"]
    filter_horizontal = ["members"]

    @admin.display(description="Members")
    def member_count(self, obj):
        return obj.members.count()


@admin.register(Invite)
class InviteAdmin(admin.ModelAdmin):
    list_display = ["note", "make_admin", "uses", "max_uses", "expires_at", "created_by"]
    filter_horizontal = ["teams"]
    readonly_fields = ["token", "uses", "created_by"]
