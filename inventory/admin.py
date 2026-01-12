from django.contrib import admin
from django.contrib.admin.widgets import RelatedFieldWidgetWrapper
from django.db.models import Sum
from django.forms.models import BaseInlineFormSet
from unfold.admin import ModelAdmin, TabularInline

from andalas_cell_test.helper.warehouses import get_primary_warehouse, get_primary_warehouse_id
from andalas_cell_test.helper.admin_mixins import GatedAdminAccessMixin

from .models import StockIn, StockInItem, StockMovement, StockOut, StockOutItem
from .permissions import user_can_access_stock_movement
from master.models import StockBalance, Warehouse


class StockOutItemInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()

        # Kalau sudah ada error di form, nggak usah ditambah-tambah lagi
        if any(form.errors for form in self.forms):
            return

        instance = getattr(self, "instance", None)
        warehouse_id = getattr(instance, "warehouse_id", None)
        if not warehouse_id:
            warehouse_id = get_primary_warehouse_id()
        if not warehouse_id:
            return

        new_totals: dict[int, int] = {}
        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue
            if form.cleaned_data.get("DELETE"):
                continue
            product = form.cleaned_data.get("product")
            qty = form.cleaned_data.get("qty")
            if not product or qty is None:
                continue
            new_totals[int(product.pk)] = new_totals.get(int(product.pk), 0) + int(qty)

        old_totals: dict[int, int] = {}
        if getattr(instance, "pk", None):
            for row in (
                StockOutItem.objects.filter(stock_out_id=instance.pk)
                .values("product_id")
                .annotate(total=Sum("qty"))
            ):
                old_totals[int(row["product_id"])] = int(row["total"] or 0)

        product_ids = set(new_totals) | set(old_totals)
        if not product_ids:
            return

        balances = {
            int(row["product_id"]): int(row["qty_on_hand"] or 0)
            for row in StockBalance.objects.filter(warehouse_id=warehouse_id, product_id__in=product_ids)
            .values("product_id", "qty_on_hand")
        }

        insufficient: set[int] = set()
        for product_id in product_ids:
            current_on_hand = balances.get(product_id, 0)
            old_total = old_totals.get(product_id, 0)
            new_total = new_totals.get(product_id, 0)

            # Saldo stok sudah sesuai dengan total lama dokumen ini
            # Prediksi saldo setelah simpan: saldo sekarang + total lama - total baru
            projected = current_on_hand + old_total - new_total
            if projected < 0:
                insufficient.add(product_id)

        if not insufficient:
            return

        # Error ditempel langsung ke baris yang bermasalah biar kelihatan di inline
        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue
            if form.cleaned_data.get("DELETE"):
                continue
            product = form.cleaned_data.get("product")
            if product and int(product.pk) in insufficient:
                form.add_error("qty", "Stok tidak cukup (stok akan menjadi minus).")


class StockInItemInline(TabularInline):
    model = StockInItem
    extra = 1
    autocomplete_fields = ("product",)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == "product" and formfield is not None:
            widget = getattr(formfield, "widget", None)
            # Django bungkus widget FK pakai RelatedFieldWidgetWrapper setelah formfield_for_foreignkey
            # Set flag di wrapper dan widget biar cuma ikon view yang muncul
            targets = []
            if widget is not None:
                targets.append(widget)
                if isinstance(widget, RelatedFieldWidgetWrapper):
                    targets.append(widget.widget)

            for target in targets:
                for attr, value in (
                    ("can_add_related", False),
                    ("can_change_related", False),
                    ("can_delete_related", False),
                    ("can_view_related", True),
                ):
                    if target is not None and hasattr(target, attr):
                        setattr(target, attr, value)

        return formfield


@admin.register(StockIn)
class StockInAdmin(ModelAdmin):
    list_display = ("invoice_id", "created_at")
    search_fields = ("invoice_id",)
    inlines = [StockInItemInline]

    fields = ("note",)

    def save_model(self, request, obj, form, change):
        wh = get_primary_warehouse()
        if wh is not None:
            obj.warehouse = wh
        obj.save(user=request.user)
        return super().save_model(request, obj, form, change)

    def get_readonly_fields(self, request, obj=None):
        return ["invoice_id", "created_at"]


class StockOutItemInline(TabularInline):
    model = StockOutItem
    extra = 1
    autocomplete_fields = ("product",)
    formset = StockOutItemInlineFormSet

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == "product" and formfield is not None:
            widget = getattr(formfield, "widget", None)
            targets = []
            if widget is not None:
                targets.append(widget)
                if isinstance(widget, RelatedFieldWidgetWrapper):
                    targets.append(widget.widget)

            for target in targets:
                for attr, value in (
                    ("can_add_related", False),
                    ("can_change_related", False),
                    ("can_delete_related", False),
                    ("can_view_related", True),
                ):
                    if target is not None and hasattr(target, attr):
                        setattr(target, attr, value)

        return formfield


@admin.register(StockOut)
class StockOutAdmin(ModelAdmin):
    list_display = ("invoice_id", "created_at")
    search_fields = ("invoice_id",)
    inlines = [StockOutItemInline]

    fields = ("note",)

    def save_model(self, request, obj, form, change):
        wh = get_primary_warehouse()
        if wh is not None:
            obj.warehouse = wh
        obj.save(user=request.user)
        return super().save_model(request, obj, form, change)

    def get_readonly_fields(self, request, obj=None):
        return ["invoice_id", "created_at"]


@admin.register(StockMovement)
class StockMovementAdmin(GatedAdminAccessMixin, ModelAdmin):
    list_display = ("created_at", "movement_type", "product", "qty", "invoice_id")
    list_filter = ("movement_type", "product")
    search_fields = ("invoice_id", "product__sku", "product__name")

    readonly_fields = (
        "movement_type",
        "created_at",
        "warehouse",
        "product",
        "qty",
        "invoice_id",
        "source_item_id",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def user_can_access(self, request) -> bool:
        return bool(user_can_access_stock_movement(request.user))
