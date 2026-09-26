"""Ventas (módulo VENTAS). Cada línea genera un Movimiento SALIDA_VENTA."""

from django.conf import settings
from django.db import models

from apps.core.models import ModeloBase


class Venta(ModeloBase):
    class Estado(models.TextChoices):
        COMPLETADA = "COMPLETADA", "Completada"
        ANULADA = "ANULADA", "Anulada"

    class MedioPago(models.TextChoices):
        EFECTIVO = "EFECTIVO", "Efectivo"
        TRANSFERENCIA = "TRANSFERENCIA", "Transferencia / Nequi / Daviplata"
        TARJETA = "TARJETA", "Tarjeta"
        CREDITO = "CREDITO", "Fiado / crédito"

    negocio = models.ForeignKey("core.Negocio", on_delete=models.CASCADE, related_name="ventas")
    vendedor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha = models.DateTimeField(db_index=True)
    cliente = models.CharField(max_length=120, blank=True)
    medio_pago = models.CharField(max_length=15, choices=MedioPago.choices, default=MedioPago.EFECTIVO)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.COMPLETADA)

    class Meta:
        ordering = ["-fecha"]

    def __str__(self):
        return f"Venta #{self.pk} {self.fecha:%Y-%m-%d} ${self.total:,.0f}"


class DetalleVenta(models.Model):
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name="detalles")
    producto = models.ForeignKey("catalogo.Producto", on_delete=models.PROTECT)
    cantidad = models.DecimalField(max_digits=12, decimal_places=3)
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2)
    costo_unitario = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    descuento = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    @property
    def subtotal(self):
        return self.cantidad * self.precio_unitario - self.descuento

    @property
    def utilidad(self):
        return self.subtotal - self.cantidad * self.costo_unitario
