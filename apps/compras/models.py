"""Órdenes de compra: de la recomendación al inventario (flujo 9.3 del diseño)."""

from django.conf import settings
from django.db import models

from apps.core.models import ModeloBase


class OrdenCompra(ModeloBase):
    class Estado(models.TextChoices):
        BORRADOR = "BORRADOR", "Borrador"
        ENVIADA = "ENVIADA", "Enviada al proveedor"
        CONFIRMADA = "CONFIRMADA", "Confirmada por el proveedor"
        RECIBIDA_PARCIAL = "PARCIAL", "Recibida parcialmente"
        RECIBIDA = "RECIBIDA", "Recibida"
        CANCELADA = "CANCELADA", "Cancelada"

    negocio = models.ForeignKey("core.Negocio", on_delete=models.CASCADE, related_name="ordenes_compra")
    proveedor = models.ForeignKey("proveedores.Proveedor", on_delete=models.PROTECT, related_name="ordenes")
    creada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.BORRADOR)
    fecha_envio = models.DateTimeField(null=True, blank=True)
    fecha_recepcion = models.DateTimeField(null=True, blank=True)
    dias_entrega = models.PositiveIntegerField(null=True, blank=True, help_text="Calculado al recibir")
    numero_factura = models.CharField(max_length=40, blank=True)
    observaciones = models.TextField(blank=True)

    class Meta:
        ordering = ["-creado"]

    def __str__(self):
        return f"OC #{self.pk} · {self.proveedor} · {self.get_estado_display()}"

    @property
    def total(self):
        return sum(d.cantidad_pedida * d.costo_unitario for d in self.detalles.all())


class DetalleOrdenCompra(models.Model):
    orden = models.ForeignKey(OrdenCompra, on_delete=models.CASCADE, related_name="detalles")
    producto = models.ForeignKey("catalogo.Producto", on_delete=models.PROTECT)
    cantidad_pedida = models.DecimalField(max_digits=12, decimal_places=3)
    cantidad_recibida = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    costo_unitario = models.DecimalField(max_digits=12, decimal_places=2)
    recomendacion = models.ForeignKey(
        "recomendaciones.RecomendacionCompra", null=True, blank=True, on_delete=models.SET_NULL
    )

    @property
    def pendiente(self):
        return self.cantidad_pedida - self.cantidad_recibida
