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
]
