from __future__ import annotations

from datetime import datetime, time, timedelta

from django.contrib import admin
from django.contrib.admin.options import ModelAdmin
from django.contrib.admin.views.main import ChangeList
from django.core.validators import EMPTY_VALUES
from django.db.models import Model, QuerySet
from django.db.models.fields import DateTimeField, Field
from django.forms import ValidationError
from django.http import HttpRequest
from django.utils import timezone

from unfold.contrib.filters.forms import RangeDateForm
from unfold.utils import parse_date_str


def _parse_flexible_date(value: str | None) -> datetime.date | None:
    """Bisa parsing tanggal dari berbagai format, misal 2024-01-01, 01-01-2024, 01/01/2024."""
    if not value:
        return None

    value = value.strip()
    if not value:
        return None

    parsed = parse_date_str(value)
    if parsed is not None:
        return parsed

    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue

    return None


class RangeDateTimeByDateFilter(admin.FieldListFilter):
    """Filter rentang tanggal (by date) di sidebar admin, input fleksibel."""
    request = None
    parameter_name = None
    form_class = RangeDateForm
    template = "unfold/filters/filters_date_range.html"

    def __init__(
        self,
        field: Field,
        request: HttpRequest,
        params: dict[str, str],
        model: type[Model],
        model_admin: ModelAdmin,
        field_path: str,
    ) -> None:
        super().__init__(field, request, params, model, model_admin, field_path)

        if not isinstance(field, DateTimeField):
            raise TypeError(
                f"Class {type(self.field)} is not supported for {self.__class__.__name__}."
            )

        self.request = request
        if self.parameter_name is None:
            self.parameter_name = self.field_path

        if self.parameter_name + "_from" in params:
            value = params.pop(self.field_path + "_from")
            value = value[0] if isinstance(value, list) else value
            if value not in EMPTY_VALUES:
                self.used_parameters[self.field_path + "_from"] = value

        if self.parameter_name + "_to" in params:
            value = params.pop(self.field_path + "_to")
            value = value[0] if isinstance(value, list) else value
            if value not in EMPTY_VALUES:
                self.used_parameters[self.field_path + "_to"] = value

    def expected_parameters(self) -> list[str | None]:
        return [
            f"{self.parameter_name}_from",
            f"{self.parameter_name}_to",
        ]

    def queryset(self, request: HttpRequest, queryset: QuerySet) -> QuerySet | None:
        """Filter queryset sesuai tanggal yang dipilih user."""
        filters: dict[str, object] = {}

        value_from = self.used_parameters.get(f"{self.parameter_name}_from")
        value_to = self.used_parameters.get(f"{self.parameter_name}_to")

        try:
            if value_from not in EMPTY_VALUES and isinstance(value_from, str):
                from_date = _parse_flexible_date(value_from)
                if from_date is not None:
                    from_dt = timezone.make_aware(
                        datetime.combine(from_date, time.min),
                        timezone.get_current_timezone(),
                    )
                    filters[f"{self.parameter_name}__gte"] = from_dt

            if value_to not in EMPTY_VALUES and isinstance(value_to, str):
                to_date = _parse_flexible_date(value_to)
                if to_date is not None:
                    next_day = to_date + timedelta(days=1)
                    next_day_dt = timezone.make_aware(
                        datetime.combine(next_day, time.min),
                        timezone.get_current_timezone(),
                    )
                    filters[f"{self.parameter_name}__lt"] = next_day_dt

            return queryset.filter(**filters)
        except (ValueError, ValidationError):
            return None

    def choices(self, changelist: ChangeList):
        """Bikin form filter di sidebar admin."""
        yield {
            "request": self.request,
            "parameter_name": self.parameter_name,
            "form": self.form_class(
                name=self.parameter_name,
                data={
                    f"{self.parameter_name}_from": self.used_parameters.get(
                        f"{self.parameter_name}_from", None
                    ),
                    f"{self.parameter_name}_to": self.used_parameters.get(
                        f"{self.parameter_name}_to", None
                    ),
                },
            ),
        }
