from __future__ import annotations


def can_view_activity_log(request) -> bool:
    user = getattr(request, "user", None)
    return bool(getattr(user, "is_active", False) and getattr(user, "is_superuser", False))
