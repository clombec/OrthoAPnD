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

    # Intra (PIN-protected)
    path("intra/", views.intra_pin_view, name="intra_pin"),
    path("intra/home/", views.intra_landing_view, name="intra_landing"),
    path("intra/recettes/", views.recettes_view, name="recettes"),
    path("intra/recettes/refresh/", views.recettes_refresh_view, name="recettes_refresh"),
    path("intra/recettes/data/", views.recettes_data_view, name="recettes_data"),
    path("intra/recettes/loading-status/", views.recettes_loading_status_view, name="recettes_loading_status"),
    path("intra/recettes/compare/", views.recettes_compare_view, name="recettes_compare"),

    # Calendar (journées types + RDV réels)
    path("intra/calendar/", views.planning_view, name="planning"),
    path("intra/calendar/refresh/", views.planning_refresh_view, name="planning_refresh"),
    path("intra/calendar/loading-status/", views.planning_loading_status_view, name="planning_loading_status"),
    path("intra/calendar/data/", views.planning_data_view, name="planning_data"),
]
