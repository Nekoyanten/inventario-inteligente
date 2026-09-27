"""Núcleo: negocio, configuración adaptativa (plantillas de giro) y auditoría."""

from django.conf import settings
from django.db import models


class ModeloBase(models.Model):
    """Campos de tiempo comunes a todas las entidades."""

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Giro(models.TextChoices):
    MINIMERCADO = "MINIMERCADO", "Tienda / minimercado"
    ROPA = "ROPA", "Ropa y calzado"
    BELLEZA = "BELLEZA", "Belleza y cosméticos"
    FARMACIA = "FARMACIA", "Farmacia / droguería"
    RESTAURANTE = "RESTAURANTE", "Restaurante / comidas"
    GENERICO = "GENERICO", "Otro (genérico)"


class Negocio(ModeloBase):
    nombre = models.CharField(max_length=150)
    nit = models.CharField("NIT / documento", max_length=30, blank=True)
    giro = models.CharField(max_length=20, choices=Giro.choices, default=Giro.GENERICO)
    moneda = models.CharField(max_length=3, default="COP")
    telefono = models.CharField(max_length=30, blank=True)
    direccion = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return self.nombre


class ConfiguracionNegocio(ModeloBase):
    """Banderas que hacen al sistema adaptativo. Se precargan desde la plantilla de giro."""

    negocio = models.OneToOneField(Negocio, on_delete=models.CASCADE, related_name="config")

    # Funciones activables
    usa_vencimientos = models.BooleanField(default=False)
    usa_lotes = models.BooleanField(default=False)
    usa_variantes = models.BooleanField(default=False, help_text="Talla, color, tono…")
    permite_fracciones = models.BooleanField(default=False, help_text="Vender 0,5 kg, 1,25 L…")
    usa_temporadas = models.BooleanField(default=False)

    # Umbrales (semáforo)
    dias_vencimiento_rojo = models.PositiveIntegerField(default=7)
    dias_vencimiento_amarillo = models.PositiveIntegerField(default=30)
    dias_sin_movimiento = models.PositiveIntegerField(default=45, help_text="Para baja rotación")
    dias_exceso = models.PositiveIntegerField(default=90, help_text="Cobertura que se considera exceso")
    horizonte_compra_dias = models.PositiveIntegerField(default=7, help_text="Días que debe cubrir un pedido")
    tiempo_entrega_defecto = models.PositiveIntegerField(default=3, help_text="Si el producto no tiene proveedor")

    # Notificaciones
    resumen_por_correo = models.BooleanField(
        default=True, help_text="Enviar cada mañana las alertas críticas a los administradores"
    )

    def __str__(self):
        return f"Configuración de {self.negocio}"


class RegistroAuditoria(models.Model):
    """¿Quién hizo qué y cuándo? Solo se inserta, nunca se edita."""

    negocio = models.ForeignKey(Negocio, on_delete=models.CASCADE, related_name="auditoria")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    fecha = models.DateTimeField(auto_now_add=True, db_index=True)
    accion = models.CharField(max_length=50)
    entidad = models.CharField(max_length=50)
    entidad_id = models.CharField(max_length=40)
    detalle = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-fecha"]

    def __str__(self):
        return f"{self.fecha:%Y-%m-%d %H:%M} {self.usuario} {self.accion} {self.entidad}#{self.entidad_id}"
