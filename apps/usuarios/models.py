"""Usuarios con rol dentro de un negocio."""

from django.contrib.auth.models import AbstractUser
from django.db import models


class Rol(models.TextChoices):
    ADMIN = "ADMIN", "Administrador"
    VENDEDOR = "VENDEDOR", "Vendedor"
    INVENTARIO = "INVENTARIO", "Encargado de inventario"


class Usuario(AbstractUser):
    negocio = models.ForeignKey(
        "core.Negocio", null=True, blank=True, on_delete=models.CASCADE, related_name="usuarios"
    )
    rol = models.CharField(max_length=12, choices=Rol.choices, default=Rol.VENDEDOR)
    telefono = models.CharField(max_length=30, blank=True)
    pin = models.CharField(max_length=128, blank=True, help_text="PIN cifrado para cambiar de usuario en un equipo compartido")

    def fijar_pin(self, pin: str | None):
        from django.contrib.auth.hashers import make_password

        self.pin = make_password(pin) if pin else ""

    def verificar_pin(self, pin: str) -> bool:
        from django.contrib.auth.hashers import check_password

        return bool(self.pin and pin and check_password(pin, self.pin))

    @property
    def es_admin(self):
        return self.rol == Rol.ADMIN or self.is_superuser

    def puede(self, accion: str) -> bool:
        from .permisos import PERMISOS_POR_ROL

        return self.is_superuser or accion in PERMISOS_POR_ROL.get(self.rol, set())
