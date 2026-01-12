from __future__ import annotations

from django.apps import apps


def get_primary_warehouse():
    """Ambil gudang pertama (berdasarkan id), kalau nggak ada ya None."""

    Warehouse = apps.get_model("master", "Warehouse")
    return Warehouse.objects.order_by("id").first()


def get_primary_warehouse_id():
    """Ambil id gudang pertama, kalau nggak ada ya None."""

    Warehouse = apps.get_model("master", "Warehouse")
    wh = Warehouse.objects.order_by("id").only("id").first()
    return int(wh.id) if wh else None
