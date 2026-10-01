"""Usuarios con rol dentro de un negocio."""

from django.contrib.auth.models import AbstractUser
from django.db import models


class Rol(models.TextChoices):
    ADMIN = "ADMIN", "Administrador"
    CAJERO = "CAJERO", "Cajero"
    MESERO = "MESERO", "Mesero"
    VENDEDOR = "VENDEDOR", "Vendedor"
    INVENTARIO = "INVENTARIO", "Bodega / inventario"


class Usuario(AbstractUser):
    negocio = models.ForeignKey(
        "core.Negocio", null=True, blank=True, on_delete=models.CASCADE, related_name="usuarios"
    )
    rol = models.CharField(max_length=12, choices=Rol.choices, default=Rol.VENDEDOR)
    telefono = models.CharField(max_length=30, blank=True)
    areas = models.JSONField(null=True, blank=True, help_text="Qué partes del sistema ve. Vacío = las de su rol")
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

    @property
    def areas_efectivas(self) -> list[str]:
        if self.areas is not None:
            return list(self.areas)
        from .permisos import areas_por_defecto

        return areas_por_defecto(self.rol, getattr(self.negocio, "giro", "") if self.negocio_id else "")

    @property
    def permisos(self) -> set[str]:
        from .permisos import permisos_de

        return permisos_de(self)

    def puede(self, accion: str) -> bool:
        return self.is_superuser or accion in self.permisos
