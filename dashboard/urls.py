from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'), # empty path means home page
    path("setup/", views.setup_view, name="setup"),
    path("save-colors/", views.save_colors_view, name="save_colors"),
    path("sync/", views.sync_records_view, name="sync_records"),
]
