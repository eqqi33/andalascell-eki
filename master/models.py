from __future__ import annotations

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from andalas_cell_test.helper.warehouses import get_primary_warehouse_id


DEFAULT_WAREHOUSE_CODE = "MAIN"


def get_default_warehouse_id() -> int:
    warehouse_id = Warehouse.objects.order_by("id").values_list("id", flat=True).first()
    if warehouse_id:
        return int(warehouse_id)

    # Kalau baru install dan belum ada data, bikin gudang utama dulu
    warehouse, _ = Warehouse.objects.get_or_create(
        code=DEFAULT_WAREHOUSE_CODE,
        defaults={"name": "Main Warehouse", "is_active": True},
    )
    return int(warehouse.pk)


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SoftDeleteQuerySet(models.QuerySet):
    def alive(self) -> models.QuerySet:
        return self.filter(is_deleted=False)

    def dead(self) -> models.QuerySet:
        return self.filter(is_deleted=True)

    def delete(self) -> int:
        return super().update(is_deleted=True, deleted_at=timezone.now())

    def hard_delete(self) -> int:
        return super().delete()


class SoftDeleteManager(models.Manager):
    def get_queryset(self) -> models.QuerySet:
        return SoftDeleteQuerySet(self.model, using=self._db).filter(is_deleted=False)


class SoftDeleteModel(TimeStampedModel):
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_%(app_label)s_%(class)s_set",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_%(app_label)s_%(class)s_set",
    )
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="deleted_%(app_label)s_%(class)s_set",
    )

    objects = SoftDeleteManager()
    all_objects = SoftDeleteQuerySet.as_manager()

    class Meta:
        abstract = True

    def soft_delete(self, user=None) -> None:
        if self.is_deleted:
            return
        self.is_deleted = True
        self.deleted_at = timezone.now()
        if user is not None:
            self.deleted_by = user
        self.save(update_fields=["is_deleted", "deleted_at", "deleted_by", "updated_at"])

    def restore(self) -> None:
        if not self.is_deleted:
            return
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None
        self.save(update_fields=["is_deleted", "deleted_at", "deleted_by", "updated_at"])

    def delete(self, using=None, keep_parents=False, hard: bool = False) -> None:
        if hard:
            return super().delete(using=using, keep_parents=keep_parents)
        self.soft_delete()

    def hard_delete(self, using=None, keep_parents=False) -> int:
        return super().delete(using=using, keep_parents=keep_parents)


class ActivityLog(models.Model):
    ACTION_CREATE = "CREATE"
    ACTION_UPDATE = "UPDATE"
    ACTION_DELETE = "DELETE"
    ACTION_SOFT_DELETE = "SOFT_DELETE"
    ACTION_RESTORE = "RESTORE"

    ACTION_CHOICES = [
        (ACTION_CREATE, "Create"),
        (ACTION_UPDATE, "Update"),
        (ACTION_DELETE, "Delete"),
        (ACTION_SOFT_DELETE, "Soft delete"),
        (ACTION_RESTORE, "Restore"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="activity_logs",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.CharField(max_length=64)
    content_object = GenericForeignKey("content_type", "object_id")

    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    object_repr = models.CharField(max_length=255, blank=True)
    note = models.TextField(blank=True)
    changes = models.JSONField(null=True, blank=True)

    class Meta:
        verbose_name = _("Aktivitas")
        verbose_name_plural = _("Aktivitas")
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["content_type", "object_id", "created_at"], name="master_acti_content_c38c2e_idx"),
        ]

    def __str__(self) -> str:
        who = getattr(self.user, "username", None) or "(system)"
        return f"{self.created_at:%Y-%m-%d %H:%M:%S} {who} {self.action} {self.object_repr}"


class ProductCategory(TimeStampedModel):
    name = models.CharField(_("Nama"), max_length=120, unique=True)
    is_active = models.BooleanField(_("Aktif"), default=True)

    class Meta:
        verbose_name = _("Kategori")
        verbose_name_plural = _("Kategori")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class UnitOfMeasure(TimeStampedModel):
    name = models.CharField(_("Nama"), max_length=80, unique=True)
    symbol = models.CharField(_("Simbol"), max_length=20, blank=True)
    is_active = models.BooleanField(_("Aktif"), default=True)

    class Meta:
        verbose_name = _("Satuan")
        verbose_name_plural = _("Satuan")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.symbol or self.name


class Product(TimeStampedModel):
    sku = models.CharField(_("SKU"), max_length=50, unique=True)
    name = models.CharField(_("Nama"), max_length=200)
    category = models.ForeignKey(ProductCategory, verbose_name=_("Kategori"), on_delete=models.PROTECT, related_name="products")
    uom = models.ForeignKey(UnitOfMeasure, verbose_name=_("Satuan"), on_delete=models.PROTECT, related_name="products")
    min_stock = models.PositiveIntegerField(_("Stok minimum"), default=0)
    is_active = models.BooleanField(_("Aktif"), default=True)

    class Meta:
        verbose_name = _("Produk")
        verbose_name_plural = _("Produk")
        ordering = ["sku"]

    def __str__(self) -> str:
        return f"{self.sku} - {self.name}"

    @property
    def is_low_stock(self) -> bool:
        wh_id = get_primary_warehouse_id()
        if not wh_id:
            return 0 < int(self.min_stock)
        qty = (
            StockBalance.objects.filter(product_id=self.pk, warehouse_id=wh_id)
            .values_list("qty_on_hand", flat=True)
            .first()
        )
        return int(qty or 0) < int(self.min_stock)


class Warehouse(TimeStampedModel):
    code = models.CharField(_("Kode"), max_length=30, unique=True)
    name = models.CharField(_("Nama"), max_length=120)
    is_active = models.BooleanField(_("Aktif"), default=True)

    class Meta:
        verbose_name = _("Gudang")
        verbose_name_plural = _("Gudang")
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class StockBalance(SoftDeleteModel):
    product = models.ForeignKey(Product, verbose_name=_("Produk"), on_delete=models.PROTECT, related_name="stock_balances")
    warehouse = models.ForeignKey(Warehouse, verbose_name=_("Gudang"), on_delete=models.PROTECT, related_name="stock_balances")
    qty_on_hand = models.PositiveIntegerField(_("Stok"), default=0)

    class Meta:
        verbose_name = _("Stok")
        verbose_name_plural = _("Stok")
        constraints = [
            models.UniqueConstraint(
                fields=["product", "warehouse"],
                condition=Q(is_deleted=False),
                name="uniq_stockbalance_product_warehouse",
            ),
        ]
        indexes = [
            models.Index(fields=["warehouse", "product"]),
        ]

    def __str__(self) -> str:
        return f"{self.warehouse.code} {self.product.sku} = {self.qty_on_hand}"
