"""
URL configuration for andalas_cell_test project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path

from master import views as master_views
from reports import views as report_views

urlpatterns = [
    path("i18n/", include("django.conf.urls.i18n")),
    path(
        "admin/master/stock/",
        admin.site.admin_view(master_views.StockMonitoringView.as_view()),
        name="admin_master_stock",
    ),
    path(
        "admin/reports/products/",
        admin.site.admin_view(report_views.ProductListView.as_view()),
        name="admin_reports_products",
    ),
    path(
        "admin/reports/stock-card/",
        admin.site.admin_view(report_views.StockCardListView.as_view()),
        name="admin_reports_stock_card",
    ),
    path(
        "admin/reports/stock-card/",
        admin.site.admin_view(report_views.StockCardListView.as_view()),
        name="reports_reportstockcardmovement_changelist",
    ),
    path(
        "admin/reports/product-autocomplete/",
        admin.site.admin_view(report_views.ProductAutocompleteView.as_view()),
        name="admin_reports_product_autocomplete",
    ),
    path('admin/', admin.site.urls),
]
