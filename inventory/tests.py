from django.core.exceptions import ValidationError
from django.test import TestCase

from inventory.models import StockIn, StockInItem, StockMovement, StockOut, StockOutItem
from master.models import Product, ProductCategory, StockBalance, UnitOfMeasure, Warehouse


class InventoryStockFlowTests(TestCase):
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

    def test_stock_in_increases_on_hand_and_creates_movement(self):
        doc = StockIn.objects.create(note="in")
        item = StockInItem.objects.create(stock_in=doc, product=self.product, qty=5)

        wh = Warehouse.objects.order_by("id").first()
        self.assertIsNotNone(wh)
        bal = StockBalance.objects.get(product=self.product, warehouse=wh)
        self.assertEqual(bal.qty_on_hand, 5)

        m = StockMovement.objects.get(source_item_id=item.pk)
        self.assertEqual(m.movement_type, StockMovement.TYPE_IN)
        self.assertEqual(m.product_id, self.product.id)
        self.assertEqual(m.qty, 5)

    def test_stock_out_cannot_make_negative(self):
        in_doc = StockIn.objects.create(note="in")
        StockInItem.objects.create(stock_in=in_doc, product=self.product, qty=5)

        out_doc = StockOut.objects.create(note="out")
        with self.assertRaises(ValidationError):
            StockOutItem.objects.create(stock_out=out_doc, product=self.product, qty=10)

    def test_stock_out_decreases_on_hand_and_creates_movement(self):
        in_doc = StockIn.objects.create(note="in")
        StockInItem.objects.create(stock_in=in_doc, product=self.product, qty=5)

        out_doc = StockOut.objects.create(note="out")
        out_item = StockOutItem.objects.create(stock_out=out_doc, product=self.product, qty=3)

        wh = Warehouse.objects.order_by("id").first()
        self.assertIsNotNone(wh)
        bal = StockBalance.objects.get(product=self.product, warehouse=wh)
        self.assertEqual(bal.qty_on_hand, 2)

        m = StockMovement.objects.get(source_item_id=out_item.pk)
        self.assertEqual(m.movement_type, StockMovement.TYPE_OUT)
        self.assertEqual(m.product_id, self.product.id)
        self.assertEqual(m.qty, 3)
