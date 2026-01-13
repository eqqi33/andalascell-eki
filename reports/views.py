import copy
from django.contrib import admin
from django.db.models import BooleanField, Case, F, IntegerField, OuterRef, Q, Subquery, Value, When
from django.db.models.functions import Coalesce
from django.utils.translation import gettext as _
from django.utils.html import format_html
from django.views import View

from django.contrib.admin.views.main import ChangeList

from unfold.admin import ModelAdmin
from unfold.views import BaseAutocompleteView

from andalas_cell_test.helper.admin_mixins import StaffReadOnlyAdminMixin
from andalas_cell_test.helper.warehouses import get_primary_warehouse_id

from master.models import StockBalance
from master.models import Product

from .models import ReportProduct, ReportStockCardMovement


class ProductAutocompleteView(BaseAutocompleteView):
    model = Product
    paginate_by = 20

    def get_queryset(self):
        qs = (
            super()
            .get_queryset()
            .only("id", "sku", "name")
            .order_by("sku")
        )
        term = (self.request.GET.get("term") or "").strip()
        if term:
            qs = qs.filter(Q(sku__icontains=term) | Q(name__icontains=term))
        return qs


class ProductReportAdmin(StaffReadOnlyAdminMixin, ModelAdmin):
    change_list_template = "admin/reports/products_changelist.html"

    list_display = (
        "sku",
        "name",
        "category",
        "uom",
        "stok_display",
    )
    search_fields = ("sku", "name", "category__name")
    list_per_page = 25
    ordering = ("sku",)

    def get_changelist(self, request, **kwargs):
        return ProductReportChangeList

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("category", "uom")
        warehouse_id = get_primary_warehouse_id()

        balance_qty_expr = Value(0)
        if warehouse_id is not None:
            balance_qty_expr = Subquery(
                StockBalance.objects.filter(product_id=OuterRef("pk"), warehouse_id=warehouse_id)
                .values("qty_on_hand")[:1]
            )

        qs = qs.annotate(
            warehouse_qty=Coalesce(balance_qty_expr, Value(0), output_field=IntegerField())
        )
        qs = qs.annotate(
            low_stock=Case(
                When(warehouse_qty__lt=F("min_stock"), then=Value(True)),
                default=Value(False),
                output_field=BooleanField(),
            )
        )
        return qs

    @admin.display(description=_("Stok"), ordering="warehouse_qty")
    def stok_display(self, obj):
        qty = int(getattr(obj, "warehouse_qty", 0) or 0)
        is_low = bool(getattr(obj, "low_stock", False))
        if is_low:
            min_stock = int(getattr(obj, "min_stock", 0) or 0)
            return format_html(
                '<div class="flex flex-col gap-1">'
                '<span>{}</span>'
                '<span class="inline-flex items-center gap-1 font-semibold h-6 leading-6 px-2 rounded-default text-[11px] uppercase whitespace-nowrap bg-orange-100 text-orange-700 dark:bg-orange-500/20 dark:text-orange-400">'
                '<span class="material-symbols-outlined text-sm">warning</span>'
                '<span>{} · {} {}</span>'
                '</span>'
                "</div>",
                qty,
                _("Stok Rendah"),
                _("Minimal"),
                min_stock,
            )
        return str(qty)

    def changelist_view(self, request, extra_context=None):
        export = (request.GET.get("export") or "").strip().lower()

        # Bikin URL export yang tetap pakai filter/sort/search, tapi tanpa pagination
        export_params = request.GET.copy()
        export_params.pop("p", None)
        export_params["export"] = "xlsx"
        export_url = f"{request.path}?{export_params.urlencode()}"

        if export in {"xlsx", "excel"}:
            # Django admin anggap querystring yang nggak dikenal sebagai filter
            # Kalau ada 'export' di request.GET, bisa dianggap lookup
            # dan bisa bikin error IncorrectLookupParameters
            export_request = copy.copy(request)
            export_request.GET = request.GET.copy()
            export_request.GET.pop("export", None)

            cl = self.get_changelist_instance(export_request)
            qs = cl.get_queryset(export_request)

            from openpyxl import Workbook

            wb = Workbook()
            ws = wb.active
            ws.title = "Produk"
            ws.append([
                "SKU",
                "Nama",
                "Kategori",
                "Satuan",
                "Stok",
            ])

            for p in qs:
                qty = int(getattr(p, "warehouse_qty", 0) or 0)
                is_low = bool(getattr(p, "low_stock", False))
                min_stock = int(getattr(p, "min_stock", 0) or 0)
                ws.append([
                    p.sku,
                    p.name,
                    str(p.category),
                    str(p.uom),
                    f"{qty} ({_('Stok Rendah')} - {_('Minimal')} {min_stock})" if is_low else qty,
                ])

            response = HttpResponse(
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            response["Content-Disposition"] = 'attachment; filename="products.xlsx"'
            wb.save(response)
            return response

        extra_context = {
            **(extra_context or {}),
            "title": _("Daftar Produk"),
            "export_url": export_url,
        }
        return super().changelist_view(request, extra_context=extra_context)


class ProductListView(View):
    def get(self, request, *args, **kwargs):
        report_admin = ProductReportAdmin(ReportProduct, admin.site)
        return report_admin.changelist_view(request)


class ProductReportChangeList(ChangeList):
    def get_ordering(self, request, queryset):
        ordering = list(super().get_ordering(request, queryset))

        # Perilaku khusus untuk kolom "Stok":
        # - Kalau klik naik di "Stok", tampilkan stok terbanyak dulu
        # - Kalau klik turun di "Stok", tampilkan stok paling sedikit dulu
        #   (yang low_stock=True dulu, baru qty terkecil)
        expanded: list[str] = []
        for term in ordering:
            if isinstance(term, str) and term.lstrip("-") == "warehouse_qty":
                if term.startswith("-"):
                    expanded.extend(["-low_stock", "warehouse_qty", "-min_stock"])
                else:
                    expanded.extend(["-warehouse_qty"])
            else:
                expanded.append(term)

        return expanded
