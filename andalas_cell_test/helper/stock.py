from django.db import transaction
from django.core.exceptions import ValidationError

def update_balance_and_movement(
    *,
    movement_type,
    product,
    warehouse,
    qty,
    delta,
    created_at,
    invoice_id,
    source_item_id,
    is_in,
    balance_model,
    movement_model,
):
    """
    Fungsi bantu buat update stok dan mutasi, dipakai StockInItem/StockOutItem.
    Kalau stok jadi minus, langsung error.
    """
    with transaction.atomic():
        balance, _ = balance_model.objects.select_for_update().get_or_create(
            product=product,
            warehouse=warehouse,
            defaults={"qty_on_hand": 0},
        )
        new_qty = int(balance.qty_on_hand) + delta if is_in else int(balance.qty_on_hand) - delta
        if new_qty < 0:
            raise ValidationError("Warehouse stock cannot go negative.")
        if delta != 0:
            balance.qty_on_hand = new_qty
            balance.save(update_fields=["qty_on_hand"])
        movement_model.objects.update_or_create(
            movement_type=movement_type,
            source_item_id=source_item_id,
            defaults={
                "created_at": created_at,
                "warehouse": warehouse,
                "product": product,
                "qty": qty,
                "invoice_id": invoice_id,
            },
        )
        return balance
