from django import forms
from unfold.widgets import UnfoldAdminTextareaWidget
from .models import StockBalance

class StockBalanceAdminForm(forms.ModelForm):
    activity_note = forms.CharField(
        label="Catatan",
        required=True,
        widget=UnfoldAdminTextareaWidget(attrs={"rows": 3}),
        help_text="Wajib diisi.",
    )

    class Meta:
        model = StockBalance
        fields = ("product", "qty_on_hand")
