from django.utils.translation import gettext_lazy as _

from unfold.sections import TemplateSection


class StockCardMovementDetailSection(TemplateSection):
    template_name = "admin/reports/sections/stock_card_movement_detail.html"
