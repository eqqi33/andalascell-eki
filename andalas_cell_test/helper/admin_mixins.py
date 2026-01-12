def serialize_value(value):
    """Bantu konversi value ke bentuk string, None tetap None."""
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


class StaffReadOnlyAdminMixin:
    """Staff yang aktif bisa lihat modul ini, tapi tidak bisa ubah data apapun."""

    def has_module_permission(self, request):
        return bool(getattr(request, "user", None) and request.user.is_active and request.user.is_staff)

    def has_view_permission(self, request, obj=None):
        return bool(getattr(request, "user", None) and request.user.is_active and request.user.is_staff)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class SuperuserReadOnlyAdminMixin:
    """Superuser aktif bisa akses modul ini, tapi nggak bisa edit data sama sekali."""

    def has_module_permission(self, request):
        return bool(getattr(request, "user", None) and request.user.is_active and request.user.is_superuser)

    def has_view_permission(self, request, obj=None):
        return bool(getattr(request, "user", None) and request.user.is_active and request.user.is_superuser)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class GatedAdminAccessMixin:
    """Akses admin bisa digate pakai fungsi khusus, tinggal override aja user_can_access(request)."""

    def user_can_access(self, request) -> bool:
        return True

    def has_module_permission(self, request):
        if not self.user_can_access(request):
            return False
        return super().has_module_permission(request)

    def has_view_permission(self, request, obj=None):
        if not self.user_can_access(request):
            return False
        return super().has_view_permission(request, obj=obj)
