from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class MasterConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "master"
    verbose_name = _("Master Data")
