from crispy_forms.helper import FormHelper
from crispy_forms.layout import Column, Layout, Row
from django.utils.translation import gettext_lazy as _

from django import forms

from unfold.fields import UnfoldAdminAutocompleteModelChoiceField
from unfold.layout import Submit
from unfold.widgets import UnfoldAdminSingleDateWidget

from master.models import Product


class StockCardForm(forms.Form):
    product = UnfoldAdminAutocompleteModelChoiceField(
        "admin_reports_product_autocomplete",
        queryset=Product.objects.none(),
        required=False,
    )
    date_from = forms.DateField(required=False, widget=UnfoldAdminSingleDateWidget())
    date_to = forms.DateField(required=False, widget=UnfoldAdminSingleDateWidget())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_method = "get"
        self.helper.attrs = {
            "class": "max-w-6xl",
        }
        self.helper.layout = Layout(
            Row(
                Column("product"),
                Column("date_from"),
                Column("date_to"),
                css_class="gap-6",
            ),
            Submit("submit", _("Filter")),
        )

        # Pilihan <select> dibuat minimal (hanya yang dipilih), tapi tetap bisa
        # validasi produk yang dipilih
        raw_value = None
        if self.is_bound:
            raw_value = self.data.get(self.add_prefix("product"))
        elif self.initial.get("product") is not None:
            raw_value = self.initial.get("product")

        if raw_value:
            self.fields["product"].queryset = Product.objects.filter(pk=raw_value)
