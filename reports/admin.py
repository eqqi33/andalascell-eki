from django.contrib import admin
from datetime import datetime, time

from django.db.models import Case, F, IntegerField, Sum, Value, When, Window
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from unfold.admin import ModelAdmin
from unfold.contrib.filters.admin import AutocompleteSelectFilter

from andalas_cell_test.helper.admin_mixins import StaffReadOnlyAdminMixin

from inventory.models import StockMovement

from .models import ReportProduct, ReportStockCardMovement
from .filters import RangeDateTimeByDateFilter, _parse_flexible_date
from .sections import StockCardMovementDetailSection


@admin.register(ReportProduct)
class ReportProductAdmin(StaffReadOnlyAdminMixin, ModelAdmin):
    list_display = ("sku", "name")
    search_fields = ("sku", "name")


@admin.register(ReportStockCardMovement)
class StockCardMovementAdmin(StaffReadOnlyAdminMixin, ModelAdmin):
    autocomplete_fields = ("product",)

    list_display = (
        "created_at",
        "invoice",
        "movement_type_badge",
    )
    search_fields = ("invoice_id", "product__sku", "product__name")
    ordering = ("created_at", "id")
    list_per_page = 50

    # Filter di sidebar pakai Unfold
    list_filter_submit = True
    list_filter = (
        ["product", AutocompleteSelectFilter],
        ("created_at", RangeDateTimeByDateFilter),
    )

    # Detail baris bisa open dan hide, pakai Unfold
    list_sections = [StockCardMovementDetailSection]

    def _get_filter_start_datetime(self, request):
        date_str = (request.GET.get("created_at_from") or "").strip()
        if not date_str:
            return None

        day = _parse_flexible_date(date_str)
        if day is None:
            return None

        dt = datetime.combine(day, time.min)
        return timezone.make_aware(dt, timezone.get_current_timezone())

    def _compute_opening_balance(self, request):
        product_id = (request.GET.get("product__id__exact") or "").strip()
        start_dt = self._get_filter_start_datetime(request)
        if not product_id or not start_dt:
            return 0

        before = StockMovement.objects.filter(product_id=product_id, created_at__lt=start_dt)
        opening_in = before.filter(movement_type=StockMovement.TYPE_IN).aggregate(s=Sum("qty"))["s"] or 0
        opening_out = before.filter(movement_type=StockMovement.TYPE_OUT).aggregate(s=Sum("qty"))["s"] or 0
        return int(opening_in) - int(opening_out)

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("product", "warehouse")

        opening = self._compute_opening_balance(request)
        setattr(request, "_stock_card_opening_balance", opening)

        delta_expr = Case(
            When(movement_type=StockMovement.TYPE_IN, then=F("qty")),
            When(movement_type=StockMovement.TYPE_OUT, then=Value(0) - F("qty")),
            default=Value(0),
            output_field=IntegerField(),
        )

        running_expr = Window(
            expression=Sum(delta_expr),
            order_by=(F("created_at").asc(), F("id").asc()),
        )

        return qs.annotate(
            _in_qty=Case(
                When(movement_type=StockMovement.TYPE_IN, then=F("qty")),
                default=Value(0),
                output_field=IntegerField(),
            ),
            _out_qty=Case(
                When(movement_type=StockMovement.TYPE_OUT, then=F("qty")),
                default=Value(0),
                output_field=IntegerField(),
            ),
            _running_balance=running_expr + Value(opening, output_field=IntegerField()),
        )

    @admin.display(description=_("Tipe"))
    def movement_type_badge(self, obj):
        # Biar simpel aja, Unfold udah cukup buat styling pilihan.
        return obj.get_movement_type_display()

    @admin.display(description=_("Invoice"), ordering="invoice_id")
    def invoice(self, obj):
        # Link ke detail StockIn/StockOut di admin
        if obj.movement_type == obj.TYPE_IN:
            model = "stockin"
        else:
            model = "stockout"
        return f'{obj.invoice_id}'

    invoice.allow_tags = True
    def get_list_display_links(self, request, list_display):
        # Kolom invoice aja yang bisa diklik
        return ["invoice"]

    def changelist_view(self, request, extra_context=None):
        opening = int(getattr(request, "_stock_card_opening_balance", 0) or 0)
        extra_context = {
            **(extra_context or {}),
            "title": _("Kartu Stok"),
            "opening_balance": opening,
        }
        return super().changelist_view(request, extra_context=extra_context)
