from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path

from book import views as b
from org import views as o

admin.site.site_header = "stratHub admin"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("login/", auth_views.LoginView.as_view(redirect_authenticated_user=True), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("password/", auth_views.PasswordChangeView.as_view(success_url="/"), name="password_change"),
    path("join/<str:token>/", o.join, name="join"),
    path("team/switch/", o.switch_team, name="switch_team"),
    path("invites/", o.invites, name="invites"),
    path("invites/<int:pk>/revoke/", o.invite_revoke, name="invite_revoke"),

    path("", b.dashboard, name="dashboard"),
    path("maps/<slug:slug>/", b.map_detail, name="map_detail"),
    path("maps/<slug:slug>/lineups/new/", b.lineup_create, name="lineup_create"),
    path("maps/<slug:slug>/strats/", b.strat_list, name="strat_list"),
    path("maps/<slug:slug>/strats/new/", b.strat_create, name="strat_create"),
    path("lineups/<int:pk>/", b.lineup_detail, name="lineup_detail"),
    path("lineups/<int:pk>/edit/", b.lineup_edit, name="lineup_edit"),
    path("lineups/<int:pk>/delete/", b.lineup_delete, name="lineup_delete"),
    path("strats/<int:pk>/", b.strat_detail, name="strat_detail"),
    path("strats/<int:pk>/edit/", b.strat_edit, name="strat_edit"),
    path("strats/<int:pk>/board/", b.strat_board, name="strat_board"),
    path("strats/<int:pk>/delete/", b.strat_delete, name="strat_delete"),
    path("gameplans/", b.gameplan_list, name="gameplan_list"),
    path("gameplans/new/", b.gameplan_create, name="gameplan_create"),
    path("gameplans/<int:pk>/", b.gameplan_detail, name="gameplan_detail"),
    path("gameplans/<int:pk>/edit/", b.gameplan_edit, name="gameplan_edit"),
    path("gameplans/<int:pk>/delete/", b.gameplan_delete, name="gameplan_delete"),
    path("opponents/", b.opponent_list, name="opponent_list"),
    path("opponents/new/", b.opponent_create, name="opponent_create"),
    path("opponents/<int:pk>/", b.opponent_detail, name="opponent_detail"),
    path("opponents/<int:pk>/edit/", b.opponent_edit, name="opponent_edit"),
    path("opponents/<int:pk>/delete/", b.opponent_delete, name="opponent_delete"),
    path("opponent-notes/<int:pk>/delete/", b.opponent_note_delete, name="opponent_note_delete"),
    path("comments/<int:pk>/delete/", b.comment_delete, name="comment_delete"),
    path("media/<path:path>", b.protected_media, name="media"),
]
