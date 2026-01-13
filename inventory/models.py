import uuid
from django.conf import settings

from django.core.exceptions import ValidationError
from django.db import models, transaction

from master.models import Product, StockBalance, Warehouse, get_default_warehouse_id


class ItemMovementMixin:
    movement_type: str
    is_in: bool
    stock_relation: str

    def _get_product_and_warehouse(self):
        product = Product.objects.get(pk=self.product_id)
        stock_obj = getattr(self, self.stock_relation)
        warehouse = Warehouse.objects.select_for_update().get(pk=stock_obj.warehouse_id)
        return product, warehouse, stock_obj

    def _update_balance_and_movement(self, qty, delta, created_at, invoice_id, source_item_id):
        from andalas_cell_test.andalas_cell_test.helper.stock import update_balance_and_movement
        update_balance_and_movement(
            movement_type=self.movement_type,
            product=self._product,
            warehouse=self._warehouse,
            qty=qty,
            delta=delta,
            created_at=created_at,
            invoice_id=invoice_id,
            source_item_id=source_item_id,
            is_in=self.is_in,
            balance_model=StockBalance,
            movement_model=StockMovement,
        )

    def save(self, *args, **kwargs) -> None:
        with transaction.atomic():
            old_qty = 0
            if self.pk:
                old_qty = (
                    self.__class__.objects.select_for_update()
                    .only("qty")
                    .get(pk=self.pk)
                    .qty
                )
            delta = int(self.qty) - int(old_qty)
            self._product, self._warehouse, stock_obj = self._get_product_and_warehouse()
            self._update_balance_and_movement(
                qty=self.qty,
                delta=delta,
                created_at=stock_obj.created_at,
                invoice_id=stock_obj.invoice_id,
                source_item_id=self.pk,
            )
            super().save(*args, **kwargs)

    def delete(self, *args, **kwargs) -> None:
        with transaction.atomic():
            self._product, self._warehouse, stock_obj = self._get_product_and_warehouse()
            self._update_balance_and_movement(
                qty=-self.qty,
                delta=-self.qty,
                created_at=stock_obj.created_at,
                invoice_id=stock_obj.invoice_id,
                source_item_id=self.pk,
            )
            StockMovement.objects.filter(movement_type=self.movement_type, source_item_id=self.pk).delete()
            super().delete(*args, **kwargs)

class StockDocument(models.Model):
    invoice_id = models.CharField(max_length=32, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    note = models.TextField(blank=True)

    class Meta:
        abstract = True
        ordering = ["-created_at", "-id"]


class StockIn(StockDocument):
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="stock_ins",
        default=get_default_warehouse_id,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_stock_ins",
        editable=False,
    )

    def save(self, *args, **kwargs) -> None:
        user = kwargs.pop('user', None)
        if user and not self.pk:
            self.created_by = user
        if not self.invoice_id:
            self.invoice_id = f"INV-IN-{uuid.uuid4().hex[:10].upper()}"
        result = super().save(*args, **kwargs)
        # Catat siapa yang bikin dokumen ini
        if user and not self.pk:
            from master.models import ActivityLog
            from django.contrib.contenttypes.models import ContentType
            ActivityLog.objects.create(
                user=user,
                content_type=ContentType.objects.get_for_model(self),
                object_id=self.pk,
                action=ActivityLog.ACTION_CREATE,
                object_repr=str(self),
                note="StockIn created",
            )
        return result

    def __str__(self) -> str:
        return self.invoice_id


class StockOut(StockDocument):
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="stock_outs",
        default=get_default_warehouse_id,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_stock_outs",
        editable=False,
    )

    def save(self, *args, **kwargs) -> None:
        user = kwargs.pop('user', None)
        if user and not self.pk:
            self.created_by = user
        if not self.invoice_id:
            self.invoice_id = f"INV-OUT-{uuid.uuid4().hex[:10].upper()}"
        result = super().save(*args, **kwargs)
        # Log creation
        if user and not self.pk:
            from master.models import ActivityLog
            from django.contrib.contenttypes.models import ContentType
            ActivityLog.objects.create(
                user=user,
                content_type=ContentType.objects.get_for_model(self),
                object_id=self.pk,
                action=ActivityLog.ACTION_CREATE,
                object_repr=str(self),
                note="StockOut created",
            )
        return result

    def __str__(self) -> str:
        return self.invoice_id


class StockMovement(models.Model):
    TYPE_IN = "IN"
    TYPE_OUT = "OUT"

    movement_type = models.CharField(max_length=3, choices=[(TYPE_IN, "Stock In"), (TYPE_OUT, "Stock Out")])
    created_at = models.DateTimeField()

    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="movements", default=get_default_warehouse_id)

    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="movements")
    qty = models.PositiveIntegerField()

    invoice_id = models.CharField(max_length=32)
    source_item_id = models.PositiveIntegerField()

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["movement_type", "source_item_id"],
                name="uniq_stockmovement_source_item_per_type",
            )
        ]
        indexes = [
            models.Index(fields=["product", "created_at"], name="inventory_s_product_92fcf9_idx"),
            models.Index(fields=["movement_type", "created_at"], name="inventory_s_movemen_605463_idx"),
        ]

    def __str__(self) -> str:
        sign = "+" if self.movement_type == self.TYPE_IN else "-"
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.product.sku} {sign}{self.qty}"


class StockInItem(ItemMovementMixin, models.Model):
    stock_in = models.ForeignKey(StockIn, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="stock_in_items")
    qty = models.PositiveIntegerField()

    class Meta:
        unique_together = ("stock_in", "product")

    def __str__(self) -> str:
        return f"{self.stock_in.invoice_id} {self.product.sku} +{self.qty}"

    movement_type = StockMovement.TYPE_IN
    is_in = True
    stock_relation = "stock_in"


class StockOutItem(ItemMovementMixin, models.Model):
    stock_out = models.ForeignKey(StockOut, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="stock_out_items")
    qty = models.PositiveIntegerField()

    class Meta:
        unique_together = ("stock_out", "product")

    def __str__(self) -> str:
        return f"{self.stock_out.invoice_id} {self.product.sku} -{self.qty}"

    movement_type = StockMovement.TYPE_OUT
    is_in = False
    stock_relation = "stock_out"
