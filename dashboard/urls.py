from django.urls import path
from . import views

urlpatterns = [
    # Public / proth
    path('', views.landing, name='landing'),
    path('proth/', views.home, name='home'),
    path("setup/", views.setup_view, name="setup"),
    path("proth/save-colors/", views.save_colors_view, name="save_colors"),
    path("proth/sync/", views.sync_records_view, name="sync_records"),
    path("proth/loading-status/", views.loading_status_view, name="loading_status"),
    path("proth/fetch-act/", views.fetch_act_view, name="fetch_act"),
    path("proth/confirm-act/", views.confirm_act_view, name="confirm_act"),

    # Intra (PIN-protected)
    path("intra/", views.intra_pin_view, name="intra_pin"),
    path("intra/home/", views.intra_landing_view, name="intra_landing"),
    path("intra/recettes/", views.recettes_view, name="recettes"),
    path("intra/recettes/refresh/", views.recettes_refresh_view, name="recettes_refresh"),
    path("intra/recettes/data/", views.recettes_data_view, name="recettes_data"),
    path("intra/recettes/loading-status/", views.recettes_loading_status_view, name="recettes_loading_status"),
    path("intra/recettes/compare/", views.recettes_compare_view, name="recettes_compare"),

    # Prévisions
    path("intra/previsions/", views.previsions_view, name="previsions"),
    path("intra/previsions/refresh/", views.previsions_refresh_view, name="previsions_refresh"),
    path("intra/previsions/data/", views.previsions_data_view, name="previsions_data"),
    path("intra/previsions/loading-status/", views.previsions_loading_status_view, name="previsions_loading_status"),

    # Calendar (journées types + RDV réels)
    path("intra/calendar/", views.planning_view, name="planning"),
    path("intra/calendar/refresh/", views.planning_refresh_view, name="planning_refresh"),
    path("intra/calendar/loading-status/", views.planning_loading_status_view, name="planning_loading_status"),
    path("intra/calendar/data/", views.planning_data_view, name="planning_data"),

    # Analyse ortho (public)
    path("analyse/", views.analyse_view, name="analyse"),
    path("analyse/refresh/", views.analyse_refresh_view, name="analyse_refresh"),
    path("analyse/loading-status/", views.analyse_loading_status_view, name="analyse_loading_status"),
    path("analyse/data/", views.analyse_data_view, name="analyse_data"),
    path("analyse/download/<str:report>/", views.analyse_download_csv_view, name="analyse_download"),

    # Stats CA (intra)
    path("intra/stats-ca/", views.stats_ca_view, name="stats_ca"),
    path("intra/stats-ca/refresh/", views.stats_ca_refresh_view, name="stats_ca_refresh"),
    path("intra/stats-ca/loading-status/", views.stats_ca_loading_status_view, name="stats_ca_loading_status"),
    path("intra/stats-ca/data/", views.stats_ca_data_view, name="stats_ca_data"),
]
