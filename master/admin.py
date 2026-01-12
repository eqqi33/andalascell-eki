from django.contrib import admin
from django import forms
from django.http import QueryDict
from unfold.admin import ModelAdmin
from unfold.widgets import UnfoldAdminTextareaWidget

from andalas_cell_test.helper.admin_mixins import SuperuserReadOnlyAdminMixin
from andalas_cell_test.helper.warehouses import get_primary_warehouse, get_primary_warehouse_id

from .models import ActivityLog, Product, ProductCategory, StockBalance, UnitOfMeasure, Warehouse


from andalas_cell_test.helper.admin_mixins import serialize_value


@admin.register(ActivityLog)
class ActivityLogAdmin(SuperuserReadOnlyAdminMixin, ModelAdmin):
    list_display = ("created_at", "user", "action", "object_repr", "note")
    list_filter = ("action", "created_at")
    search_fields = ("object_repr", "user__username")
    readonly_fields = (
        "created_at",
        "user",
        "action",
        "object_repr",
        "note",
        "changes",
        "content_type",
        "object_id",
    )


@admin.register(ProductCategory)
class ProductCategoryAdmin(ModelAdmin):
    list_display = ("name", "is_active", "created_at", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(UnitOfMeasure)
class UnitOfMeasureAdmin(ModelAdmin):
    list_display = ("name", "symbol", "is_active", "created_at", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "symbol")


@admin.register(Product)
class ProductAdmin(ModelAdmin):
    list_display = (
        "sku",
        "name",
        "category",
        "uom",
        "min_stock",
        "is_active",
    )
    list_filter = ("is_active", "category")
    search_fields = ("sku", "name")

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        if (
            request.GET.get("app_label") == "master"
            and request.GET.get("model_name") == "stockbalance"
            and request.GET.get("field_name") == "product"
        ):
            wh_id = get_primary_warehouse_id()
            if wh_id is not None:
                queryset = queryset.exclude(stock_balances__warehouse_id=wh_id, stock_balances__is_deleted=False)
                use_distinct = True

        return queryset, use_distinct


@admin.register(Warehouse)
class WarehouseAdmin(ModelAdmin):
    list_display = ("code", "name", "is_active", "created_at", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(StockBalance)
class StockBalanceAdmin(ModelAdmin):
    list_display = ("product", "qty_on_hand", "created_at", "updated_at")
    list_filter = ()
    search_fields = ("product__sku", "product__name")
    autocomplete_fields = ("product",)

    class StockBalanceAdminForm(forms.ModelForm):
        activity_note = forms.CharField(
            label="Catatan",
            required=True,
            widget=UnfoldAdminTextareaWidget(attrs={"rows": 3}),
            help_text="Wajib diisi.",
        )

        class Meta:
            model = StockBalance
            fields = ("product", "qty_on_hand")

    form = StockBalanceAdminForm
    fields = ("product", "qty_on_hand", "activity_note")

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("warehouse", "product")
        wh_id = get_primary_warehouse_id()
        if wh_id is None:
            return qs.none()
        return qs.filter(warehouse_id=wh_id)

    def save_model(self, request, obj, form, change):
        old = None
        if change and obj.pk:
            old = (
                StockBalance.all_objects.select_related("product", "warehouse")
                .only("id", "product_id", "warehouse_id", "qty_on_hand")
                .get(pk=obj.pk)
            )

        note = (form.cleaned_data.get("activity_note") or "").strip()

        wh = get_primary_warehouse()
        if wh is None:
            raise forms.ValidationError("Warehouse is not set up yet.")
        obj.warehouse = wh

        if not change and not getattr(obj, "created_by_id", None):
            obj.created_by = request.user
        obj.updated_by = request.user

        result = super().save_model(request, obj, form, change)

        if change:
            changes = {}
            if old is not None:
                if old.product_id != obj.product_id:
                    changes["product"] = {
                        "from": serialize_value(old.product_id),
                        "to": serialize_value(obj.product_id),
                    }
                if old.qty_on_hand != obj.qty_on_hand:
                    changes["qty_on_hand"] = {
                        "from": serialize_value(old.qty_on_hand),
                        "to": serialize_value(obj.qty_on_hand),
                    }
            ActivityLog.objects.create(
                user=request.user,
                action=ActivityLog.ACTION_UPDATE,
                content_object=obj,
                object_id=str(obj.pk),
                object_repr=str(obj),
                note=note,
                changes=changes or None,
            )
        else:
            ActivityLog.objects.create(
                user=request.user,
                action=ActivityLog.ACTION_CREATE,
                content_object=obj,
                object_id=str(obj.pk),
                object_repr=str(obj),
                note=note,
                changes={
                    "product": serialize_value(obj.product_id),
                    "qty_on_hand": serialize_value(obj.qty_on_hand),
                },
            )

        return result

    def delete_model(self, request, obj):
        note = (request.POST.get("activity_note") or "").strip()
        obj.soft_delete(user=request.user)
        ActivityLog.objects.create(
            user=request.user,
            action=ActivityLog.ACTION_SOFT_DELETE,
            content_object=obj,
            object_id=str(obj.pk),
            object_repr=str(obj),
            note=note,
        )

    def delete_queryset(self, request, queryset):
        raise forms.ValidationError("Gunakan hapus per item agar bisa mengisi catatan.")

    def get_actions(self, request):
        actions = super().get_actions(request)
        # Jangan izinkan hapus massal, soalnya harus ada catatan
        actions.pop("delete_selected", None)
        return actions

    def delete_view(self, request, object_id, extra_context=None):
        if request.method == "POST" and request.POST.get("post") == "yes":
            note = (request.POST.get("activity_note") or "").strip()
            if not note:
                original_post = request.POST
                request.POST = QueryDict("")
                try:
                    extra_context = {
                        **(extra_context or {}),
                        "activity_note_error": "Catatan wajib diisi.",
                        "activity_note_value": "",
                    }
                    return super().delete_view(request, object_id, extra_context=extra_context)
                finally:
                    request.POST = original_post

        return super().delete_view(request, object_id, extra_context=extra_context)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj=obj, **kwargs)
        wh = get_primary_warehouse()
        if wh is not None and "product" in form.base_fields:
            product_field = form.base_fields["product"]

            # Tampilkan aksi 'lihat terkait' saja untuk produk, sembunyikan ikon tambah/ubah/hapus
            widget = product_field.widget
            for attr, value in (
                ("can_add_related", False),
                ("can_change_related", False),
                ("can_delete_related", False),
                ("can_view_related", True),
            ):
                if hasattr(widget, attr):
                    setattr(widget, attr, value)

            qs = product_field.queryset
            qs = qs.exclude(stock_balances__warehouse=wh, stock_balances__is_deleted=False)
            if obj is not None and obj.product_id:
                qs = qs | product_field.queryset.filter(pk=obj.product_id)
            product_field.queryset = qs.distinct()

            def clean_product(self_):
                product = self_.cleaned_data.get("product")
                if not product:
                    return product
                exists = StockBalance.objects.filter(product=product, warehouse=wh)
                if obj is not None:
                    exists = exists.exclude(pk=obj.pk)
                if exists.exists():
                    raise forms.ValidationError("Stok untuk produk ini sudah ada.")
                return product

            # Pasang validasi dinamis biar tiap produk cuma punya 1 baris stok di gudang utama
            form.clean_product = clean_product
        return form