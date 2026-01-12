from django.contrib.auth import get_user_model
from django.test import TestCase

from master.models import Product, ProductCategory, UnitOfMeasure


class AdminReportsTests(TestCase):
    def setUp(self):
        self.category = ProductCategory.objects.create(name="Default")
        self.uom = UnitOfMeasure.objects.create(name="PCS", symbol="pcs")
        self.product = Product.objects.create(
            sku="SKU-1",
            name="Product 1",
            category=self.category,
            uom=self.uom,
            min_stock=0,
            is_active=True,
        )

    def test_products_report_requires_admin_login(self):
        resp = self.client.get("/admin/reports/products/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/admin/login/", resp["Location"])
        self.assertIn("next=/admin/reports/products/", resp["Location"])

    def test_stock_card_report_requires_admin_login(self):
        resp = self.client.get("/admin/reports/stock-card/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/admin/login/", resp["Location"])
        self.assertIn("next=/admin/reports/stock-card/", resp["Location"])

    def test_staff_can_open_products_report(self):
        User = get_user_model()
        user = User.objects.create_user(username="staff", password="pass", is_staff=True)
        self.client.force_login(user)

        resp = self.client.get("/admin/reports/products/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Daftar Produk")
        self.assertContains(resp, self.product.sku)

    def test_staff_can_open_stock_card_report(self):
        User = get_user_model()
        user = User.objects.create_user(username="staff", password="pass", is_staff=True)
        self.client.force_login(user)

        resp = self.client.get("/admin/reports/stock-card/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Stock Card")
        self.assertContains(resp, "Filter")
