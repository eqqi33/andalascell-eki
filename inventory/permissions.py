from __future__ import annotations

from django.conf import settings


def user_can_access_stock_movement(user) -> bool:
    if user is None:
        return False

    if not getattr(user, "is_active", False) or not getattr(user, "is_staff", False):
        return False

    if getattr(user, "is_superuser", False):
        return True

    group_name = getattr(settings, "STOCK_MOVEMENT_AUDIT_GROUP", "Auditor Persediaan")
    return user.groups.filter(name=group_name).exists()


def can_view_stock_movement(request) -> bool:
    user = getattr(request, "user", None)
    return user_can_access_stock_movement(user)
