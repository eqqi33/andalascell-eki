# Gudang Tunggal (Django 5.2 + Unfold + PostgreSQL)

## Kebutuhan
- Python 3.10+
- PostgreSQL
- Virtualenv bisa dibuat di `.venv/`

## File Environment
- `.env` : untuk jalankan manual lokal (development)
- `.env.docker` : untuk docker compose
- `.env.production` : untuk server/produksi

File provisioning Docker (pgAdmin servers.json/pgpassfile) ada di folder `docker/`.

> Catatan: Django ambil credential DB dan secret dari environment variable. File env cuma buat memudahkan, dan sudah di-ignore git.
> File .env yang asli tetap sediakan dengan nama .env.example, jadi kalau mau dipakai harus di-rename dulu jadi .env

## Setup Lokal (Manual Python)
```bash
cd /home/eqqi33/Projects/Playground/python/Django/andalas_cell_test
source .venv/bin/activate
export $(grep -v '^#' .env | xargs)
python manage.py makemigrations
python manage.py migrate
python manage.py create_test_admin
python manage.py runserver
```

Buka:
- Admin: http://127.0.0.1:8000/admin/
- Laporan produk: http://127.0.0.1:8000/admin/reports/products/
- Laporan kartu stok: http://127.0.0.1:8000/admin/reports/stock-card/

Akun admin uji:
- Username: `administrator`
- Password: `Andalas2025Test`

## Docker
```bash
docker compose up --build
```

Setelah build dan migrasi, jalankan:
```bash
docker compose exec web python manage.py migrate
docker compose exec web python manage.py create_test_admin
```

pgAdmin:
- URL: http://127.0.0.1:5050/
- Login: `admin@local.com` / `admin`
- Server sudah otomatis terdaftar: "Andalas Postgres" (host: `db`, db: `andalas_db`)

## Seeder Data Demo & Produk

Saat build Docker, semua seeder (user, produk, data demo) dijalankan otomatis.

### Docker
Setelah build dan migrasi, jalankan:
```bash
docker compose run --rm web python manage.py seed_demo_data --reset
```
Seeder ini akan membuat data user, produk, dan data demo lain yang diperlukan.

### Manual Lokal
Untuk jalankan seeder manual di lokal:
```bash
python manage.py seed_demo_data --reset
```
Seeder ini akan membuat data user, produk, dan data demo lain yang diperlukan.

## Membuat Virtualenv (Lokal)

Kalau folder `.venv/` belum ada, bikin virtual environment dengan:
```bash
python3 -m venv .venv
```
Aktifkan dengan:
```bash
source .venv/bin/activate
```

## ERD (Mermaid)
Lihat [ERD.md](ERD.md).

## Saran Jalankan Project

Lebih cepat dan praktis jalankan project pakai Docker, karena tidak perlu konfigurasi manual. Cukup jalankan perintah Docker dari folder root project ini.

Contoh:
```bash
docker compose up --build
```

Setelah itu, migrasi dan seeder bisa langsung dijalankan di container.
```bash
docker compose exec web python manage.py migrate
docker compose exec web python manage.py seed_demo_data --reset
```
