from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

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
        url = reverse("admin:reports_reportstockcardmovement_changelist")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/admin/login/", resp["Location"])
        self.assertIn(f"next={url}", resp["Location"])

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

        resp = self.client.get(reverse("admin:reports_reportstockcardmovement_changelist"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Kartu Stok Produk")
        self.assertContains(resp, "Filter")

    def test_staff_can_export_stock_card_pdf(self):
        User = get_user_model()
        user = User.objects.create_user(username="staff", password="pass", is_staff=True)
        self.client.force_login(user)

        url = reverse("admin:reports_reportstockcardmovement_changelist")
        resp = self.client.get(f"{url}?export=pdf")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertTrue(resp.content.startswith(b"%PDF"))
