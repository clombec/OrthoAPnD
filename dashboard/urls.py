from django.urls import path
from . import views

urlpatterns = [
    path('', views.landing, name='landing'),
    path('proth/', views.home, name='home'),
    path("setup/", views.setup_view, name="setup"),
    path("proth/save-colors/", views.save_colors_view, name="save_colors"),
    path("proth/sync/", views.sync_records_view, name="sync_records"),
    path("proth/loading-status/", views.loading_status_view, name="loading_status"),
]
