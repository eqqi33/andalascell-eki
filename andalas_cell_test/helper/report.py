from __future__ import annotations

from datetime import date, datetime, time

from django.db.models import Q, Sum
from django.utils import timezone

from inventory.models import StockMovement


def to_start_dt(d: date | None) -> datetime | None:
    if not d:
        return None
    dt = datetime.combine(d, time.min)
    return timezone.make_aware(dt, timezone.get_current_timezone())


def to_end_dt(d: date | None) -> datetime | None:
    if not d:
        return None
    dt = datetime.combine(d, time.max)
    return timezone.make_aware(dt, timezone.get_current_timezone())


def build_stockcard_movement_filter(
    *,
    warehouse_id: int | None,
    product_id: int | None,
    start_dt: datetime | None,
    end_dt: datetime | None,
) -> Q:
    q = Q()
    if warehouse_id is not None:
        q &= Q(warehouse_id=warehouse_id)
    if product_id is not None:
        q &= Q(product_id=product_id)
    if start_dt is not None:
        q &= Q(created_at__gte=start_dt)
    if end_dt is not None:
        q &= Q(created_at__lte=end_dt)
    return q


def compute_opening_balance(
    *,
    warehouse_id: int | None,
    product_id: int,
    start_dt: datetime | None,
) -> int:
    if start_dt is None:
        return 0

    base_q = Q(product_id=product_id) & Q(created_at__lt=start_dt)
    if warehouse_id is not None:
        base_q &= Q(warehouse_id=warehouse_id)

    qs = StockMovement.objects.filter(base_q)
    opening_in = qs.filter(movement_type=StockMovement.TYPE_IN).aggregate(s=Sum("qty"))["s"] or 0
    opening_out = qs.filter(movement_type=StockMovement.TYPE_OUT).aggregate(s=Sum("qty"))["s"] or 0
    return int(opening_in) - int(opening_out)
