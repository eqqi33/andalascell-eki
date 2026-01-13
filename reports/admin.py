from datetime import datetime, time, timedelta
from io import BytesIO
from urllib.parse import urlencode

from django.contrib import admin

from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Case, F, IntegerField, Q, Sum, Value, When, Window
from django.db.models.functions import Coalesce
from django.urls import path, reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.template.response import TemplateResponse
from django.http import HttpResponseBadRequest

from unfold.admin import ModelAdmin
from unfold.contrib.filters.admin import AutocompleteSelectFilter

from andalas_cell_test.helper.admin_mixins import StaffReadOnlyAdminMixin
from andalas_cell_test.helper.report import build_stockcard_movement_filter, compute_opening_balance
from andalas_cell_test.helper.warehouses import get_primary_warehouse_id

from inventory.models import StockMovement

from master.models import Product

from .models import ReportProduct, ReportStockCardMovement
from .filters import RangeDateTimeByDateFilter, _parse_flexible_date
from .sections import StockCardMovementDetailSection


@admin.register(ReportProduct)
class ReportProductAdmin(StaffReadOnlyAdminMixin, ModelAdmin):
    list_display = ("sku", "name")
    search_fields = ("sku", "name")


@admin.register(ReportStockCardMovement)
class StockCardMovementAdmin(StaffReadOnlyAdminMixin, ModelAdmin):
    # Tetap pakai Django admin/Unfold changelist (filters/search/pagination).
    # Tapi area tabel hasil kita ganti jadi ringkasan per produk.
    change_list_template = "admin/reports/stock_card_movement_changelist.html"

    autocomplete_fields = ("product",)

    list_display = (
        "created_at",
        "product",
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

    def _sanitize_sheet_title(self, title: str, used: set[str]) -> str:
        # Excel sheet title constraints:
        # - max 31 chars
        # - cannot contain: : \ / ? * [ ]
        # - must be unique within workbook
        cleaned = (title or "").strip() or "Sheet"
        for ch in (":", "\\", "/", "?", "*", "[", "]"):
            cleaned = cleaned.replace(ch, " ")
        cleaned = " ".join(cleaned.split())
        cleaned = cleaned[:31].rstrip() or "Sheet"

        if cleaned not in used:
            used.add(cleaned)
            return cleaned

        base = cleaned[:28].rstrip() or "Sheet"
        for i in range(2, 1000):
            candidate = f"{base} {i}"
            candidate = candidate[:31].rstrip()
            if candidate not in used:
                used.add(candidate)
                return candidate
        # fallback
        candidate = f"{base[:26]} XX"[:31].rstrip() or "Sheet"
        used.add(candidate)
        return candidate

    def _build_export_url(self, request, fmt: str) -> str:
        params = request.GET.copy()
        params.pop("p", None)
        params["export"] = fmt
        return f"{request.path}?{params.urlencode()}"

    def _get_export_date_range(self, request):
        start_dt = self._get_filter_start_datetime(request)
        end_dt = self._get_filter_end_datetime(request)

        # Default safety: kalau tidak ada filter tanggal, batasi export ke 30 hari terakhir
        # supaya tidak berat/terlalu besar.
        if start_dt is None and end_dt is None:
            end_dt = timezone.now()
            start_dt = end_dt - timedelta(days=30)
            return start_dt, end_dt, True

        return start_dt, end_dt, False

    def _export_stock_card_xlsx(self, request):
        # Build a ChangeList-based queryset that respects admin filters/search.
        export_request = request
        if "export" in request.GET:
            from copy import copy as _copy

            export_request = _copy(request)
            export_request.GET = request.GET.copy()
            export_request.GET.pop("export", None)

        cl = self.get_changelist_instance(export_request)
        qs = cl.get_queryset(export_request)

        warehouse_id = get_primary_warehouse_id()
        if warehouse_id is not None:
            qs = qs.filter(warehouse_id=warehouse_id)

        start_dt, end_dt, used_default_range = self._get_export_date_range(export_request)

        product_rows = list(
            qs.values("product_id", "product__sku", "product__name")
            .distinct()
            .order_by("product__sku")
        )
        product_ids = [int(r["product_id"]) for r in product_rows if r.get("product_id")]

        # Precompute opening balance per product (one query) when start_dt exists.
        opening_map: dict[int, int] = {}
        if start_dt is not None and product_ids:
            before_qs = StockMovement.objects.filter(product_id__in=product_ids, created_at__lt=start_dt)
            if warehouse_id is not None:
                before_qs = before_qs.filter(warehouse_id=warehouse_id)
            opening_rows = before_qs.values("product_id").annotate(
                opening_in=Coalesce(
                    Sum("qty", filter=Q(movement_type=StockMovement.TYPE_IN)),
                    Value(0),
                    output_field=IntegerField(),
                ),
                opening_out=Coalesce(
                    Sum("qty", filter=Q(movement_type=StockMovement.TYPE_OUT)),
                    Value(0),
                    output_field=IntegerField(),
                ),
            )
            opening_map = {
                int(r["product_id"]): int(r.get("opening_in", 0) or 0) - int(r.get("opening_out", 0) or 0)
                for r in opening_rows
            }

        from openpyxl import Workbook

        wb = Workbook()
        # Remove default sheet; we'll add per product.
        wb.remove(wb.active)

        used_titles: set[str] = set()

        def _local_dt_str(dt):
            if not dt:
                return ""
            return timezone.localtime(dt).strftime("%Y-%m-%d %H:%M")

        def _range_label():
            if not used_default_range:
                return ""
            return "(default 30 hari terakhir)"

        if not product_rows:
            ws = wb.create_sheet(self._sanitize_sheet_title("Stock Card", used_titles))
            ws.append(["Tidak ada data untuk filter saat ini."])
        else:
            for pr in product_rows:
                product_id = int(pr["product_id"])
                sku = (pr.get("product__sku") or "").strip()
                name = (pr.get("product__name") or "").strip()
                product_label = f"{sku} — {name}" if sku and name else (sku or name or str(product_id))

                sheet_title = sku or name or f"Product {product_id}"
                ws = wb.create_sheet(self._sanitize_sheet_title(sheet_title, used_titles))

                ws.append(["Produk", product_label])
                if used_default_range:
                    ws.append(["Filter created_at_from", _local_dt_str(start_dt)])
                    ws.append(["Filter created_at_to", _local_dt_str(end_dt)])
                    ws.append(["Catatan", _range_label()])
                else:
                    ws.append(["Filter created_at_from", (export_request.GET.get("created_at_from") or "").strip()])
                    ws.append(["Filter created_at_to", (export_request.GET.get("created_at_to") or "").strip()])
                ws.append([])
                ws.append(["Tgl", "Keterangan", "Masuk", "Keluar", "Sisa"]) 

                opening = int(opening_map.get(product_id, 0) or 0)
                running = opening
                ws.append(["", "Saldo Awal", 0, 0, running])

                # Period movements: align with the report logic (date range + warehouse + product).
                movement_q = build_stockcard_movement_filter(
                    warehouse_id=warehouse_id,
                    product_id=product_id,
                    start_dt=start_dt,
                    end_dt=end_dt,
                )
                movements = (
                    StockMovement.objects.filter(movement_q)
                    .only("id", "created_at", "movement_type", "qty", "invoice_id")
                    .order_by("created_at", "id")
                )

                period_in = 0
                period_out = 0
                for m in movements:
                    in_qty = int(m.qty) if m.movement_type == StockMovement.TYPE_IN else 0
                    out_qty = int(m.qty) if m.movement_type == StockMovement.TYPE_OUT else 0
                    running += in_qty - out_qty
                    period_in += in_qty
                    period_out += out_qty
                    desc = f"{m.get_movement_type_display()} · {m.invoice_id}"
                    ws.append([_local_dt_str(m.created_at), desc, in_qty, out_qty, running])

                ws.append([])
                ws.append(["", "TOTAL", period_in, period_out, opening + period_in - period_out])

        from django.http import HttpResponse

        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = 'attachment; filename="stock_card.xlsx"'
        wb.save(response)
        return response

    def _export_stock_card_pdf(self, request):
        # Build a ChangeList-based queryset that respects admin filters/search.
        export_request = request
        if "export" in request.GET:
            from copy import copy as _copy

            export_request = _copy(request)
            export_request.GET = request.GET.copy()
            export_request.GET.pop("export", None)

        cl = self.get_changelist_instance(export_request)
        qs = cl.get_queryset(export_request)

        warehouse_id = get_primary_warehouse_id()
        if warehouse_id is not None:
            qs = qs.filter(warehouse_id=warehouse_id)

        start_dt, end_dt, used_default_range = self._get_export_date_range(export_request)

        product_rows = list(
            qs.values("product_id", "product__sku", "product__name")
            .distinct()
            .order_by("product__sku")
        )

        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        styles = getSampleStyleSheet()
        buf = BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=A4,
            leftMargin=12 * mm,
            rightMargin=12 * mm,
            topMargin=12 * mm,
            bottomMargin=12 * mm,
            title="Stock Card",
        )

        def _local_dt_str(dt):
            if not dt:
                return ""
            return timezone.localtime(dt).strftime("%Y-%m-%d %H:%M")

        date_range_text = ""
        if start_dt and end_dt:
            date_range_text = f"Periode: {_local_dt_str(start_dt)} s/d {_local_dt_str(end_dt)}"
            if used_default_range:
                date_range_text += " (default 30 hari terakhir)"

        story = []
        story.append(Paragraph("Stock Card", styles["Title"]))
        if date_range_text:
            story.append(Paragraph(date_range_text, styles["Normal"]))
        story.append(Spacer(1, 6 * mm))

        if not product_rows:
            story.append(Paragraph("Tidak ada data untuk filter saat ini.", styles["Normal"]))
        else:
            for idx, pr in enumerate(product_rows):
                product_id = int(pr["product_id"])
                sku = (pr.get("product__sku") or "").strip()
                name = (pr.get("product__name") or "").strip()
                product_label = f"{sku} — {name}" if sku and name else (sku or name or str(product_id))

                opening = compute_opening_balance(
                    warehouse_id=warehouse_id,
                    product_id=product_id,
                    start_dt=start_dt,
                )

                movement_q = build_stockcard_movement_filter(
                    warehouse_id=warehouse_id,
                    product_id=product_id,
                    start_dt=start_dt,
                    end_dt=end_dt,
                )
                movements = (
                    StockMovement.objects.filter(movement_q)
                    .only("id", "created_at", "movement_type", "qty", "invoice_id")
                    .order_by("created_at", "id")
                )

                story.append(Paragraph(product_label, styles["Heading2"]))
                story.append(Paragraph(f"Saldo awal: {opening}", styles["Normal"]))
                story.append(Spacer(1, 3 * mm))

                data = [["Tgl", "Keterangan", "Masuk", "Keluar", "Sisa"]]
                running = int(opening)
                period_in = 0
                period_out = 0

                for m in movements:
                    in_qty = int(m.qty) if m.movement_type == StockMovement.TYPE_IN else 0
                    out_qty = int(m.qty) if m.movement_type == StockMovement.TYPE_OUT else 0
                    running += in_qty - out_qty
                    period_in += in_qty
                    period_out += out_qty
                    desc = f"{m.get_movement_type_display()} · {m.invoice_id}"
                    data.append([_local_dt_str(m.created_at), desc, in_qty, out_qty, running])

                # Summary row
                data.append(["", "TOTAL", period_in, period_out, opening + period_in - period_out])

                table = Table(
                    data,
                    colWidths=[28 * mm, 86 * mm, 20 * mm, 20 * mm, 20 * mm],
                    repeatRows=1,
                )
                table.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F3F4F6")),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                            ("FONTSIZE", (0, 0), (-1, -1), 8),
                            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
                            ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                        ]
                    )
                )
                story.append(table)

                if idx < len(product_rows) - 1:
                    story.append(PageBreak())

        doc.build(story)

        from django.http import HttpResponse

        response = HttpResponse(content_type="application/pdf")
        response["Content-Disposition"] = 'attachment; filename="stock_card.pdf"'
        response.write(buf.getvalue())
        return response

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "stock-card-detail/",
                self.admin_site.admin_view(self.stock_card_detail_view),
                name="reports_reportstockcardmovement_stockcard_detail",
            ),
        ]
        return custom + urls

    def _get_filter_start_datetime(self, request):
        date_str = (request.GET.get("created_at_from") or "").strip()
        if not date_str:
            return None

        day = _parse_flexible_date(date_str)
        if day is None:
            return None

        dt = datetime.combine(day, time.min)
        return timezone.make_aware(dt, timezone.get_current_timezone())

    def _get_filter_end_datetime(self, request):
        date_str = (request.GET.get("created_at_to") or "").strip()
        if not date_str:
            return None

        day = _parse_flexible_date(date_str)
        if day is None:
            return None

        dt = datetime.combine(day, time.max)
        return timezone.make_aware(dt, timezone.get_current_timezone())


    def _compute_opening_balance(self, request):
        product_id = (request.GET.get("product__id__exact") or "").strip()
        start_dt = self._get_filter_start_datetime(request)
        if not product_id or not start_dt:
            return 0

        warehouse_id = get_primary_warehouse_id()
        return compute_opening_balance(
            warehouse_id=warehouse_id,
            product_id=int(product_id),
            start_dt=start_dt,
        )

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
        export = (request.GET.get("export") or "").strip().lower()
        if export in {"xlsx", "excel"}:
            return self._export_stock_card_xlsx(request)
        if export in {"pdf"}:
            return self._export_stock_card_pdf(request)

        opening = int(getattr(request, "_stock_card_opening_balance", 0) or 0)
        extra_context = {
            **(extra_context or {}),
            "title": _( "Kartu Stok Produk"),
            "opening_balance": opening,
        }

        response = super().changelist_view(request, extra_context=extra_context)
        if getattr(response, "context_data", None) is None:
            return response

        cl = response.context_data.get("cl")
        if cl is None:
            return response

        warehouse_id = get_primary_warehouse_id()
        qs = cl.queryset
        if warehouse_id is not None:
            qs = qs.filter(warehouse_id=warehouse_id)

        summary_qs = (
            qs.values("product_id", "product__sku", "product__name")
            .annotate(
                period_in=Coalesce(
                    Sum("qty", filter=Q(movement_type=StockMovement.TYPE_IN)),
                    Value(0),
                    output_field=IntegerField(),
                ),
                period_out=Coalesce(
                    Sum("qty", filter=Q(movement_type=StockMovement.TYPE_OUT)),
                    Value(0),
                    output_field=IntegerField(),
                ),
            )
            .order_by("product__sku")
        )

        # Pagination harus berbasis produk (grouped), bukan baris StockMovement.
        per_page = int(getattr(self, "list_per_page", 50) or 50)
        raw_page_index = (request.GET.get("p") or "0").strip()
        try:
            page_index = max(int(raw_page_index), 0)
        except (TypeError, ValueError):
            page_index = 0
        page_number = page_index + 1  # Django Paginator is 1-based

        product_paginator = Paginator(summary_qs, per_page)
        try:
            product_page_obj = product_paginator.page(page_number)
        except PageNotAnInteger:
            product_page_obj = product_paginator.page(1)
        except EmptyPage:
            product_page_obj = product_paginator.page(product_paginator.num_pages or 1)

        page_summaries = list(product_page_obj.object_list)

        start_dt = self._get_filter_start_datetime(request)

        opening_map: dict[int, int] = {}
        product_ids = [int(r["product_id"]) for r in page_summaries if r.get("product_id")]
        if start_dt is not None and product_ids:
            before_qs = StockMovement.objects.filter(product_id__in=product_ids, created_at__lt=start_dt)
            if warehouse_id is not None:
                before_qs = before_qs.filter(warehouse_id=warehouse_id)
            opening_rows = before_qs.values("product_id").annotate(
                opening_in=Coalesce(
                    Sum("qty", filter=Q(movement_type=StockMovement.TYPE_IN)),
                    Value(0),
                    output_field=IntegerField(),
                ),
                opening_out=Coalesce(
                    Sum("qty", filter=Q(movement_type=StockMovement.TYPE_OUT)),
                    Value(0),
                    output_field=IntegerField(),
                ),
            )
            opening_map = {
                int(r["product_id"]): int(r.get("opening_in", 0) or 0) - int(r.get("opening_out", 0) or 0)
                for r in opening_rows
            }

        base_params: dict[str, str] = {}
        created_at_from = (request.GET.get("created_at_from") or "").strip()
        created_at_to = (request.GET.get("created_at_to") or "").strip()
        if created_at_from:
            base_params["created_at_from"] = created_at_from
        if created_at_to:
            base_params["created_at_to"] = created_at_to

        detail_base = reverse("admin:reports_reportstockcardmovement_stockcard_detail")

        rows = []
        for r in page_summaries:
            pid = int(r["product_id"]) if r.get("product_id") else None
            if pid is None:
                continue
            sku = (r.get("product__sku") or "").strip()
            name = (r.get("product__name") or "").strip()
            product_label = f"{sku} — {name}" if sku and name else (sku or name or str(pid))

            opening_balance = int(opening_map.get(pid, 0) or 0)
            in_qty = int(r.get("period_in", 0) or 0)
            out_qty = int(r.get("period_out", 0) or 0)
            closing_balance = opening_balance + in_qty - out_qty

            params = {**base_params, "product_id": pid}
            detail_url = f"{detail_base}?{urlencode(params)}"

            rows.append(
                {
                    "product_id": pid,
                    "product_label": product_label,
                    "opening_balance": opening_balance,
                    "period_in": in_qty,
                    "period_out": out_qty,
                    "closing_balance": closing_balance,
                    "detail_url": detail_url,
                }
            )

        def _build_page_url(target_page_index: int) -> str:
            params = request.GET.copy()
            if target_page_index <= 0:
                params.pop("p", None)
            else:
                params["p"] = str(target_page_index)
            qs_str = params.urlencode()
            return f"{request.path}?{qs_str}" if qs_str else request.path

        # Build a compact page range (with ellipses) for template rendering.
        num_pages = int(product_paginator.num_pages or 1)
        current = int(product_page_obj.number or 1)
        if num_pages <= 11:
            page_numbers = list(range(1, num_pages + 1))
        else:
            around = {1, 2, num_pages - 1, num_pages}
            around.update(range(max(1, current - 2), min(num_pages, current + 2) + 1))
            page_numbers = sorted(n for n in around if 1 <= n <= num_pages)

        product_pagination = []
        last = None
        for n in page_numbers:
            if last is not None and n - last > 1:
                product_pagination.append({"is_gap": True})
            product_pagination.append(
                {
                    "is_gap": False,
                    "number": n,
                    "index": n - 1,
                    "url": _build_page_url(n - 1),
                    "is_current": n == current,
                }
            )
            last = n

        response.context_data["rows"] = rows
        response.context_data["export_xlsx_url"] = self._build_export_url(request, "xlsx")
        response.context_data["export_pdf_url"] = self._build_export_url(request, "pdf")
        response.context_data["product_count"] = int(product_paginator.count or 0)
        response.context_data["product_page_obj"] = product_page_obj
        response.context_data["product_pagination_required"] = bool(
            (product_paginator.num_pages or 0) > 1
        )
        response.context_data["product_pagination"] = product_pagination
        response.context_data["product_prev_url"] = (
            _build_page_url((product_page_obj.previous_page_number() - 1)) if product_page_obj.has_previous() else ""
        )
        response.context_data["product_next_url"] = (
            _build_page_url((product_page_obj.next_page_number() - 1)) if product_page_obj.has_next() else ""
        )
        return response

    def stock_card_detail_view(self, request):
        raw_product_id = (request.GET.get("product_id") or "").strip()
        if not raw_product_id.isdigit():
            return HttpResponseBadRequest("Missing or invalid product_id")

        product_id = int(raw_product_id)

        try:
            product = Product.objects.only("id", "sku", "name").get(pk=product_id)
        except Product.DoesNotExist:
            return HttpResponseBadRequest("Product not found")

        warehouse_id = get_primary_warehouse_id()
        start_dt = self._get_filter_start_datetime(request)
        end_dt = self._get_filter_end_datetime(request)

        # Default safety: kalau user belum set filter tanggal, batasi detail ke 30 hari terakhir.
        if start_dt is None and end_dt is None:
            end_dt = timezone.now()
            start_dt = end_dt - timedelta(days=30)

        opening = compute_opening_balance(
            warehouse_id=warehouse_id,
            product_id=product_id,
            start_dt=start_dt,
        )

        movement_q = build_stockcard_movement_filter(
            warehouse_id=warehouse_id,
            product_id=product_id,
            start_dt=start_dt,
            end_dt=end_dt,
        )
        movements = (
            StockMovement.objects.filter(movement_q)
            .only("id", "created_at", "movement_type", "qty", "invoice_id")
            .order_by("created_at", "id")
        )

        running = opening
        movement_rows = []
        period_in = 0
        period_out = 0
        for m in movements:
            in_qty = int(m.qty) if m.movement_type == StockMovement.TYPE_IN else 0
            out_qty = int(m.qty) if m.movement_type == StockMovement.TYPE_OUT else 0
            running += in_qty - out_qty
            period_in += in_qty
            period_out += out_qty
            movement_rows.append(
                {
                    "created_at": m.created_at,
                    "description": f"{m.get_movement_type_display()} · {m.invoice_id}",
                    "in_qty": in_qty,
                    "out_qty": out_qty,
                    "running_balance": running,
                }
            )

        ctx = {
            "product": product,
            "opening_balance": opening,
            "period_in": period_in,
            "period_out": period_out,
            "closing_balance": opening + period_in - period_out,
            "movements": movement_rows,
        }
        return TemplateResponse(request, "admin/reports/partials/stock_card_product_detail.html", ctx)
