from django.utils.translation import gettext_lazy as _

from inventory.models import StockMovement
from master.models import Product


class ReportProduct(Product):
    class Meta:
        proxy = True
        app_label = "reports"
        verbose_name = _("Daftar Produk")
        verbose_name_plural = _("Daftar Produk")


class ReportStockCardMovement(StockMovement):
    @property
    def in_qty(self) -> int:
        return int(getattr(self, "_in_qty", 0) or 0)

    @property
    def out_qty(self) -> int:
        return int(getattr(self, "_out_qty", 0) or 0)

    @property
    def running_balance(self) -> int:
        return int(getattr(self, "_running_balance", 0) or 0)

    class Meta:
        proxy = True
        app_label = "reports"
        verbose_name = "Stock Card"
        verbose_name_plural = "Stock Card"
