import random
from datetime import datetime, timedelta, time

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from inventory.models import StockIn, StockInItem, StockOut, StockOutItem
from master.models import DEFAULT_WAREHOUSE_CODE, Product, ProductCategory, StockBalance, UnitOfMeasure, Warehouse



class Command(BaseCommand):
    help = "Seed a lot of demo data (categories, UoM, products, stock ins/outs) for testing reports."

    def handle(self, *args, **options):
        # Create admin test account
        from django.contrib.auth import get_user_model
        User = get_user_model()
        admin_username = "administrator"
        admin_password = "Andalas2025Test"
        admin_email = "administrator@andalas.local"
        admin_user, created = User.objects.get_or_create(username=admin_username, defaults={"email": admin_email})
        if created or not admin_user.is_superuser:
            admin_user.is_staff = True
            admin_user.is_superuser = True
            admin_user.set_password(admin_password)
            admin_user.save()
            self.stdout.write(self.style.SUCCESS(f"Akun admin uji dibuat: {admin_username} / {admin_password}"))

        rng = random.Random(options["seed"])
        theme = options["theme"]

        Warehouse.objects.get_or_create(
            code=DEFAULT_WAREHOUSE_CODE,
            defaults={"name": "Main Warehouse", "is_active": True},
        )

        categories_count = max(1, options["categories"])
        products_count = max(1, options["products"])
        days = max(1, options["days"])
        stock_in_docs = max(0, options["ins"])
        stock_out_docs = max(0, options["outs"])
        items_min = max(1, options["items_min"])
        items_max = max(items_min, options["items_max"])

        if options["purge"] and options["reset"]:
            raise SystemExit("Use only one of --reset or --purge")

        with transaction.atomic():
            if options["purge"]:
                self.stdout.write(self.style.WARNING("Purging inventory + master data..."))
                StockMovementDelete.delete_all()
                Product.objects.all().delete()
                ProductCategory.objects.all().delete()
                UnitOfMeasure.objects.all().delete()
            elif options["reset"]:
                self.stdout.write(self.style.WARNING("Resetting inventory data..."))
                StockMovementDelete.delete_all()
                StockBalance.objects.update(qty_on_hand=0)

            if theme == "phones":
                categories = self._ensure_phone_categories()
                uoms = self._ensure_phone_uoms()
                products = self._ensure_phone_products(products_count, categories, uoms, rng)
            else:
                categories = self._ensure_categories(categories_count)
                uoms = self._ensure_uoms()
                products = self._ensure_products(products_count, categories, uoms)

        def create_doc_with_items(doc_cls, item_cls, note, products, rng, items_min, items_max, days, created_items_counter, qty_max=120, warehouse=None):
            created_at = self._random_datetime_within_days(rng, days)
            doc = doc_cls.objects.create(note=note)
            doc_cls.objects.filter(pk=doc.pk).update(created_at=created_at)
            doc.refresh_from_db(fields=["created_at", "invoice_id"])
            k = rng.randint(items_min, items_max)
            picked = rng.sample(products, k=min(k, len(products)))
            for product in picked:
                qty = rng.randint(1, qty_max)
                kwargs = {"product": product, item_cls._meta.model_name.split("item")[0] + "": doc}
                if warehouse:
                    kwargs["warehouse"] = warehouse
                item_cls.objects.create(**kwargs, qty=qty)
                created_items_counter[0] += 1

        created_in_items = [0]
        created_out_items = [0]

        for _ in range(stock_in_docs):
            create_doc_with_items(StockIn, StockInItem, "Seeded stock in", products, rng, items_min, items_max, days, created_in_items)

        default_wh = Warehouse.objects.filter(code=DEFAULT_WAREHOUSE_CODE).only("id").first()
        for _ in range(stock_out_docs):
            available = list(
                Product.objects.filter(stock_balances__warehouse=default_wh, stock_balances__qty_on_hand__gt=0)
                .distinct()
                .order_by("?")[: items_max * 3]
            )
            if not available:
                continue
            def pick_qty(product):
                bal = StockBalance.objects.filter(product=product, warehouse=default_wh).only("qty_on_hand").first()
                return rng.randint(1, min(int(bal.qty_on_hand), 80)) if bal and int(bal.qty_on_hand) > 0 else None
            created_at = self._random_datetime_within_days(rng, days)
            stock_out = StockOut.objects.create(note="Seeded stock out")
            StockOut.objects.filter(pk=stock_out.pk).update(created_at=created_at)
            stock_out.refresh_from_db(fields=["created_at", "invoice_id"])
            k = rng.randint(items_min, items_max)
            picked = available[: min(k, len(available))]
            for product in picked:
                qty = pick_qty(product)
                if qty:
                    StockOutItem.objects.create(stock_out=stock_out, product=product, qty=qty)
                    created_out_items[0] += 1

        self.stdout.write(self.style.SUCCESS("Seed completed."))
        self.stdout.write(
            f"Created: categories={ProductCategory.objects.count()}, uoms={UnitOfMeasure.objects.count()}, products={Product.objects.count()}, stock_in_items={created_in_items[0]}, stock_out_items={created_out_items[0]}"
        )
        
    def add_arguments(self, parser):
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument(
            "--theme",
            type=str,
            default="phones",
            choices=["phones", "generic"],
            help="Which catalog to generate for categories/products.",
        )
        parser.add_argument("--categories", type=int, default=8)
        parser.add_argument("--products", type=int, default=120)
        parser.add_argument("--days", type=int, default=90)
        parser.add_argument("--ins", type=int, default=220)
        parser.add_argument("--outs", type=int, default=180)
        parser.add_argument("--items-min", type=int, default=2)
        parser.add_argument("--items-max", type=int, default=6)
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete inventory documents + movements, and reset stock balances to 0 (keeps master data).",
        )
        parser.add_argument(
            "--purge",
            action="store_true",
            help="Delete inventory data and master data (products/categories/uoms) before seeding.",
        )

    def handle(self, *args, **options):
        rng = random.Random(options["seed"])
        theme = options["theme"]

        Warehouse.objects.get_or_create(
            code=DEFAULT_WAREHOUSE_CODE,
            defaults={"name": "Main Warehouse", "is_active": True},
        )

        categories_count = max(1, options["categories"])
        products_count = max(1, options["products"])
        days = max(1, options["days"])
        stock_in_docs = max(0, options["ins"])
        stock_out_docs = max(0, options["outs"])
        items_min = max(1, options["items_min"])
        items_max = max(items_min, options["items_max"])

        if options["purge"] and options["reset"]:
            raise SystemExit("Use only one of --reset or --purge")

        with transaction.atomic():
            if options["purge"]:
                self.stdout.write(self.style.WARNING("Purging inventory + master data..."))
                StockMovementDelete.delete_all()
                Product.objects.all().delete()
                ProductCategory.objects.all().delete()
                UnitOfMeasure.objects.all().delete()
            elif options["reset"]:
                self.stdout.write(self.style.WARNING("Resetting inventory data..."))
                StockMovementDelete.delete_all()
                StockBalance.objects.update(qty_on_hand=0)

            if theme == "phones":
                categories = self._ensure_phone_categories()
                uoms = self._ensure_phone_uoms()
                products = self._ensure_phone_products(products_count, categories, uoms, rng)
            else:
                categories = self._ensure_categories(categories_count)
                uoms = self._ensure_uoms()
                products = self._ensure_products(products_count, categories, uoms)

        # Seed inventory docs outside the big transaction to reduce lock duration;
        # item save() uses its own atomic sections.
        created_in_items = 0
        created_out_items = 0

        for _ in range(stock_in_docs):
            created_at = self._random_datetime_within_days(rng, days)
            stock_in = StockIn.objects.create(note="Seeded stock in")
            StockIn.objects.filter(pk=stock_in.pk).update(created_at=created_at)
            stock_in.refresh_from_db(fields=["created_at", "invoice_id"])

            k = rng.randint(items_min, items_max)
            picked = rng.sample(products, k=min(k, len(products)))
            for product in picked:
                qty = rng.randint(1, 120)
                StockInItem.objects.create(stock_in=stock_in, product=product, qty=qty)
                created_in_items += 1

        # For stock out, only pick products with available stock in the default warehouse.
        for _ in range(stock_out_docs):
            created_at = self._random_datetime_within_days(rng, days)
            stock_out = StockOut.objects.create(note="Seeded stock out")
            StockOut.objects.filter(pk=stock_out.pk).update(created_at=created_at)
            stock_out.refresh_from_db(fields=["created_at", "invoice_id"])

            default_wh = Warehouse.objects.filter(code=DEFAULT_WAREHOUSE_CODE).only("id").first()
            if not default_wh:
                continue

            available = list(
                Product.objects.filter(stock_balances__warehouse=default_wh, stock_balances__qty_on_hand__gt=0)
                .distinct()
                .order_by("?")[: items_max * 3]
            )
            if not available:
                continue

            k = rng.randint(items_min, items_max)
            # Ensure uniqueness within a doc (unique_together)
            picked = available[: min(k, len(available))]
            for product in picked:
                bal = StockBalance.objects.filter(product=product, warehouse=default_wh).only("qty_on_hand").first()
                if not bal or int(bal.qty_on_hand) <= 0:
                    continue
                qty = rng.randint(1, min(int(bal.qty_on_hand), 80))
                StockOutItem.objects.create(stock_out=stock_out, product=product, qty=qty)
                created_out_items += 1

        self.stdout.write(self.style.SUCCESS("Seed completed."))
        self.stdout.write(
            "Created: "
            f"categories={ProductCategory.objects.count()}, "
            f"uoms={UnitOfMeasure.objects.count()}, "
            f"products={Product.objects.count()}, "
            f"stock_in_items={created_in_items}, "
            f"stock_out_items={created_out_items}"
        )

    def _ensure_categories(self, n: int):
        categories = []
        for i in range(1, n + 1):
            obj, _ = ProductCategory.objects.get_or_create(name=f"Category {i:02d}")
            categories.append(obj)
        return categories

    def _ensure_phone_categories(self):
        names = [
            "HP",
            "Sparepart - iPhone",
            "Service - iPhone",
            "Sparepart - Samsung",
            "Service - Samsung",
            "Sparepart - Xiaomi",
            "Service - Xiaomi",
            "Sparepart - Oppo",
            "Service - Oppo",
            "Sparepart - Vivo",
            "Service - Vivo",
            "Sparepart - Realme",
            "Service - Realme",
            "Aksesoris - Kabel",
            "Aksesoris - Charger",
            "Aksesoris - Case",
            "Aksesoris - Tempered Glass",
            "Aksesoris - Audio",
        ]
        categories = []
        for name in names:
            obj, _ = ProductCategory.objects.get_or_create(name=name)
            categories.append(obj)
        return categories

    def _ensure_uoms(self):
        base = [
            ("Pieces", "pcs"),
            ("Box", "box"),
            ("Pack", "pack"),
            ("Kilogram", "kg"),
            ("Liter", "l"),
            ("Meter", "m"),
        ]
        uoms = []
        for name, symbol in base:
            obj, _ = UnitOfMeasure.objects.get_or_create(name=name, defaults={"symbol": symbol})
            if obj.symbol != symbol and not obj.symbol:
                obj.symbol = symbol
                obj.save(update_fields=["symbol"])
            uoms.append(obj)
        return uoms

    def _ensure_phone_uoms(self):
        base = [
            ("Piece", "pcs"),
            ("Unit", "unit"),
            ("Set", "set"),
            ("Service", "svc"),
            ("Hour", "hour"),
        ]
        uoms = []
        for name, symbol in base:
            obj, _ = UnitOfMeasure.objects.get_or_create(name=name, defaults={"symbol": symbol})
            if obj.symbol != symbol and not obj.symbol:
                obj.symbol = symbol
                obj.save(update_fields=["symbol"])
            uoms.append(obj)
        return uoms

    def _ensure_products(self, n: int, categories, uoms):
        products = []
        for i in range(1, n + 1):
            sku = f"SKU-{i:05d}"
            name = f"Product {i:05d}"
            category = categories[(i - 1) % len(categories)]
            uom = uoms[(i - 1) % len(uoms)]
            min_stock = 5 + (i % 50)

            obj, created = Product.objects.get_or_create(
                sku=sku,
                defaults={
                    "name": name,
                    "category": category,
                    "uom": uom,
                    "min_stock": min_stock,
                    "is_active": True,
                },
            )
            if not created:
                # Keep existing data, but ensure relations exist.
                changed = False
                if obj.category_id != category.id:
                    obj.category = category
                    changed = True
                if obj.uom_id != uom.id:
                    obj.uom = uom
                    changed = True
                if changed:
                    obj.save(update_fields=["category", "uom"])
            products.append(obj)

        return products

    def _ensure_phone_products(self, n: int, categories, uoms, rng: random.Random):
        category_by_name = {c.name: c for c in categories}
        uom_by_symbol = {u.symbol: u for u in uoms}

        phones_cat = category_by_name["HP"]

        sp_iphone = category_by_name["Sparepart - iPhone"]
        svc_iphone = category_by_name["Service - iPhone"]
        sp_samsung = category_by_name["Sparepart - Samsung"]
        svc_samsung = category_by_name["Service - Samsung"]
        sp_xiaomi = category_by_name["Sparepart - Xiaomi"]
        svc_xiaomi = category_by_name["Service - Xiaomi"]
        sp_oppo = category_by_name["Sparepart - Oppo"]
        svc_oppo = category_by_name["Service - Oppo"]
        sp_vivo = category_by_name["Sparepart - Vivo"]
        svc_vivo = category_by_name["Service - Vivo"]
        sp_realme = category_by_name["Sparepart - Realme"]
        svc_realme = category_by_name["Service - Realme"]

        acc_kabel = category_by_name["Aksesoris - Kabel"]
        acc_charger = category_by_name["Aksesoris - Charger"]
        acc_case = category_by_name["Aksesoris - Case"]
        acc_tg = category_by_name["Aksesoris - Tempered Glass"]
        acc_audio = category_by_name["Aksesoris - Audio"]

        u_pcs = uom_by_symbol.get("pcs") or uoms[0]
        u_unit = uom_by_symbol.get("unit") or uoms[0]
        u_set = uom_by_symbol.get("set") or uoms[0]
        u_svc = uom_by_symbol.get("svc") or uoms[0]

        iphone_models = [
            "iPhone 11",
            "iPhone 12",
            "iPhone 13",
            "iPhone 14",
            "iPhone 15",
        ]
        samsung_models = [
            "Samsung Galaxy A12",
            "Samsung Galaxy A32",
            "Samsung Galaxy A52",
            "Samsung Galaxy S21",
            "Samsung Galaxy S22",
        ]
        xiaomi_models = [
            "Xiaomi Redmi Note 10",
            "Xiaomi Redmi Note 11",
            "Xiaomi Redmi Note 12",
            "Xiaomi Poco X3",
            "Xiaomi Poco X5",
        ]

        oppo_models = [
            "Oppo A16",
            "Oppo A54",
            "Oppo A76",
            "Oppo Reno 6",
            "Oppo Reno 8",
        ]
        vivo_models = [
            "Vivo Y12",
            "Vivo Y20",
            "Vivo Y21",
            "Vivo V21",
            "Vivo V25",
        ]
        realme_models = [
            "Realme C11",
            "Realme C25",
            "Realme 7",
            "Realme 8",
            "Realme 10",
        ]

        spare_parts = [
            ("LCD", u_unit, 10),
            ("Baterai", u_unit, 15),
            ("Port Charger", u_unit, 12),
            ("Tutup Belakang", u_unit, 8),
            ("Kamera", u_unit, 6),
            ("Speaker", u_unit, 10),
            ("Earpiece", u_unit, 10),
            ("Flex Power", u_unit, 10),
            ("Flex Volume", u_unit, 10),
            ("SIM Tray", u_unit, 5),
        ]

        accessories_kabel = [
            ("Kabel USB-C", u_pcs, 25),
            ("Kabel Lightning", u_pcs, 25),
            ("Kabel Data 1m", u_pcs, 25),
        ]
        accessories_charger = [
            ("Charger Adapter 20W", u_pcs, 15),
            ("Charger Adapter 33W", u_pcs, 15),
            ("Charger Adapter 45W", u_pcs, 10),
            ("Wireless Charger", u_pcs, 8),
        ]
        accessories_case = [
            ("Case HP", u_pcs, 25),
            ("Case Anti Shock", u_pcs, 18),
        ]
        accessories_tg = [
            ("Tempered Glass 2.5D", u_pcs, 30),
            ("Tempered Glass Full Cover", u_pcs, 25),
        ]
        accessories_audio = [
            ("Earphones", u_pcs, 12),
            ("Headset Bluetooth", u_pcs, 8),
        ]

        services = [
            ("Cek Kerusakan", u_svc, 0),
            ("Ganti LCD (Jasa)", u_svc, 0),
            ("Ganti Baterai (Jasa)", u_svc, 0),
            ("Servis Port Charger (Jasa)", u_svc, 0),
            ("Bersih-bersih Water Damage", u_svc, 0),
            ("Flash Software", u_svc, 0),
            ("Pindah Data", u_svc, 0),
        ]

        # Build a catalog and then take first N (shuffled deterministically)
        catalog: list[tuple[str, str, ProductCategory, UnitOfMeasure, int]] = []

        def add_phone(model: str):
            sku = f"PHN-{model.replace(' ', '').replace('-', '')}".upper()
            catalog.append((sku, model, phones_cat, u_unit, 3))

        def add_spare(model: str, brand_cat: ProductCategory):
            model_code = model.replace(" ", "").replace("-", "")
            for part_name, uom, min_stock in spare_parts:
                sku = f"SP-{model_code}-{part_name.replace(' ', '').replace('/', '')}".upper()
                name = f"{part_name} untuk {model}"
                catalog.append((sku, name, brand_cat, uom, min_stock))

        def add_accessory(acc_name: str, acc_cat: ProductCategory, uom: UnitOfMeasure, min_stock: int):
            sku = f"ACC-{acc_name.replace(' ', '').replace('.', '')}".upper()
            catalog.append((sku, acc_name, acc_cat, uom, min_stock))

        def add_service(svc_name: str, svc_cat: ProductCategory, uom: UnitOfMeasure, min_stock: int):
            sku = f"SVC-{svc_name.replace(' ', '').replace('(', '').replace(')', '').replace('-', '')}".upper()
            catalog.append((sku, svc_name, svc_cat, uom, min_stock))

        for model in iphone_models + samsung_models + xiaomi_models + oppo_models + vivo_models + realme_models:
            add_phone(model)

        for model in iphone_models:
            add_spare(model, sp_iphone)
            for svc_name, uom, min_stock in services:
                add_service(f"{svc_name} - {model}", svc_iphone, uom, min_stock)
        for model in samsung_models:
            add_spare(model, sp_samsung)
            for svc_name, uom, min_stock in services:
                add_service(f"{svc_name} - {model}", svc_samsung, uom, min_stock)
        for model in xiaomi_models:
            add_spare(model, sp_xiaomi)
            for svc_name, uom, min_stock in services:
                add_service(f"{svc_name} - {model}", svc_xiaomi, uom, min_stock)
        for model in oppo_models:
            add_spare(model, sp_oppo)
            for svc_name, uom, min_stock in services:
                add_service(f"{svc_name} - {model}", svc_oppo, uom, min_stock)
        for model in vivo_models:
            add_spare(model, sp_vivo)
            for svc_name, uom, min_stock in services:
                add_service(f"{svc_name} - {model}", svc_vivo, uom, min_stock)
        for model in realme_models:
            add_spare(model, sp_realme)
            for svc_name, uom, min_stock in services:
                add_service(f"{svc_name} - {model}", svc_realme, uom, min_stock)

        for acc_name, uom, min_stock in accessories_kabel:
            add_accessory(acc_name, acc_kabel, uom, min_stock)
        for acc_name, uom, min_stock in accessories_charger:
            add_accessory(acc_name, acc_charger, uom, min_stock)
        for acc_name, uom, min_stock in accessories_case:
            add_accessory(acc_name, acc_case, uom, min_stock)
        for acc_name, uom, min_stock in accessories_tg:
            add_accessory(acc_name, acc_tg, uom, min_stock)
        for acc_name, uom, min_stock in accessories_audio:
            add_accessory(acc_name, acc_audio, uom, min_stock)

        rng.shuffle(catalog)
        catalog = catalog[:n]

        products: list[Product] = []
        for idx, (base_sku, name, category, uom, min_stock) in enumerate(catalog, start=1):
            # Ensure max_length=50 and uniqueness
            sku = base_sku[:40]
            if Product.objects.filter(sku=sku).exists():
                sku = f"{sku[:44]}-{idx:03d}"[:50]

            obj, created = Product.objects.get_or_create(
                sku=sku,
                defaults={
                    "name": name[:200],
                    "category": category,
                    "uom": uom,
                    "min_stock": min_stock,
                    "is_active": True,
                },
            )

            if not created:
                changed = False
                if obj.name != name[:200]:
                    obj.name = name[:200]
                    changed = True
                if obj.category_id != category.id:
                    obj.category = category
                    changed = True
                if obj.uom_id != uom.id:
                    obj.uom = uom
                    changed = True
                if obj.min_stock != min_stock:
                    obj.min_stock = min_stock
                    changed = True
                if changed:
                    obj.save(update_fields=["name", "category", "uom", "min_stock"])

            products.append(obj)

        # Make sure we always return at least 1 product
        if not products:
            obj, _ = Product.objects.get_or_create(
                sku="SKU-00001",
                defaults={"name": "Aksesoris HP", "category": acc_case, "uom": u_set, "min_stock": 10},
            )
            products.append(obj)

        return products

    def _random_datetime_within_days(self, rng: random.Random, days: int):
        now = timezone.now()
        delta_days = rng.randint(0, days - 1)
        day = (now - timedelta(days=delta_days)).date()
        hour = rng.randint(8, 18)
        minute = rng.choice([0, 5, 10, 15, 20, 30, 40, 45, 50, 55])
        dt = datetime.combine(day, time(hour=hour, minute=minute))
        return timezone.make_aware(dt)


class StockMovementDelete:
    """Encapsulate deletion order for inventory tables."""

    @staticmethod
    def delete_all():
        # Import here to avoid circular imports at module import time.
        from inventory.models import StockMovement

        StockMovement.objects.all().delete()
        StockInItem.objects.all().delete()
        StockOutItem.objects.all().delete()
        StockIn.objects.all().delete()
        StockOut.objects.all().delete()
