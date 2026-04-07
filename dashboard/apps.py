import os
from orthoaget.logger import setup_logger
import logging

from django.apps import AppConfig


class DashboardConfig(AppConfig):
    name = "dashboard"
    default_auto_field = "django.db.models.BigAutoField"
    name = "dashboard"

    def ready(self):
        # Avoid double execution with Django's autoreloader
        if os.environ.get("RUN_MAIN") != "true":
            return

        # Setup shared logger — once for the entire process
        setup_logger()

        # Now logging.info() works everywhere in both projects
        logging.info("Dashboard app ready — logger initialized")
