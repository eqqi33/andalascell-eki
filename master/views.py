import csv

from django.contrib import admin
from django.core.paginator import Paginator
from django.db.models import BooleanField, Case, F, IntegerField, OuterRef, Q, Subquery, Value, When
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.template.response import TemplateResponse
from django.utils.translation import gettext as _
from django.views import View

from andalas_cell_test.helper.warehouses import get_primary_warehouse_id

from master.models import Product, StockBalance, Warehouse


class StockMonitoringView(View):
    def get(self, request, *args, **kwargs):
        q = (request.GET.get("q") or "").strip()
        low = (request.GET.get("low") or "").strip() in {"1", "true", "yes", "on"}
        sort = (request.GET.get("sort") or "sku").strip()
        direction = (request.GET.get("dir") or "asc").strip().lower()
        export = (request.GET.get("export") or "").strip().lower()
        page_number = request.GET.get("page")

        warehouse_id = get_primary_warehouse_id()

        balance_qty_expr = Value(0)
        if warehouse_id is not None:
            balance_qty_expr = Subquery(
                StockBalance.objects.filter(product_id=OuterRef("pk"), warehouse_id=warehouse_id)
                .values("qty_on_hand")[:1]
            )

        products = Product.objects.select_related("category", "uom")
        products = products.annotate(
            warehouse_qty=Coalesce(balance_qty_expr, Value(0), output_field=IntegerField())
        )
        products = products.annotate(
            low_stock=Case(
                When(warehouse_qty__lt=F("min_stock"), then=Value(True)),
                default=Value(False),
                output_field=BooleanField(),
            )
        )

        if q:
            products = products.filter(Q(sku__icontains=q) | Q(name__icontains=q))
        if low:
            products = products.filter(low_stock=True)

        allowed_sorts = {
            "sku": "sku",
            "name": "name",
            "category": "category__name",
            "uom": "uom__name",
            "qty": "warehouse_qty",
            "min_stock": "min_stock",
            "low_stock": "low_stock",
            "active": "is_active",
        }
        sort_key = allowed_sorts.get(sort, "sku")
        prefix = "-" if direction == "desc" else ""
        products = products.order_by(f"{prefix}{sort_key}", "sku")

        if export in {"xlsx", "excel"}:
            from openpyxl import Workbook

            wb = Workbook()
            ws = wb.active
            ws.title = "Stock"
            ws.append([
                _("SKU"),
                _("Nama"),
                _("Kategori"),
                _("Satuan"),
                _("Stok"),
                _("Stok minimum"),
                _("Low stock"),
                _("Aktif"),
            ])

            for p in products:
                ws.append([
                    p.sku,
                    p.name,
                    str(p.category),
                    str(p.uom),
                    int(p.warehouse_qty),
                    int(p.min_stock),
                    "1" if bool(p.low_stock) else "0",
                    "1" if bool(p.is_active) else "0",
                ])

            response = HttpResponse(
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            response["Content-Disposition"] = 'attachment; filename="stock.xlsx"'
            wb.save(response)
            return response

        if export == "csv":
            response = HttpResponse(content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = 'attachment; filename="stock.csv"'

            writer = csv.writer(response)
            writer.writerow([
                _("SKU"),
                _("Nama"),
                _("Kategori"),
                _("Satuan"),
                _("Stok"),
                _("Stok minimum"),
                _("Low stock"),
                _("Aktif"),
            ])

            for p in products:
                writer.writerow([
                    p.sku,
                    p.name,
                    str(p.category),
                    str(p.uom),
                    int(p.warehouse_qty),
                    int(p.min_stock),
                    "1" if bool(p.low_stock) else "0",
                    "1" if p.is_active else "0",
                ])

            return response

        paginator = Paginator(products, 25)
        page_obj = paginator.get_page(page_number)

        get_qs = request.GET.copy()
        get_qs.pop("page", None)
        base_qs = get_qs.urlencode()

        context = admin.site.each_context(request)
        context.update(
            {
                "title": _("Stok"),
                "products": page_obj.object_list,
                "page_obj": page_obj,
                "paginator": paginator,
                "sort": sort,
                "dir": direction,
                "base_qs": base_qs,
                "q": q,
                "low": low,
            }
        )
        return TemplateResponse(request, "admin/master/stock.html", context)
