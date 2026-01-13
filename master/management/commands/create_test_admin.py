import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Create/update a superuser for local/dev usage. "
        "Defaults: admin@admin.com / admin123. "
        "Override with DJANGO_SUPERUSER_USERNAME, DJANGO_SUPERUSER_EMAIL, DJANGO_SUPERUSER_PASSWORD."
    )

    def handle(self, *args, **options):
        User = get_user_model()
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "administrator")
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "admin@admin.com")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "Andalas2025Test")

        user, _created = User.objects.get_or_create(
            username=username, defaults={"is_staff": True, "is_superuser": True}
        )
        if not user.is_staff or not user.is_superuser:
            user.is_staff = True
            user.is_superuser = True

        if hasattr(user, "email"):
            user.email = email

        user.set_password(password)
        user.save()

        self.stdout.write(
            self.style.SUCCESS(f"Superuser ready: {username} / {password}")
        )
