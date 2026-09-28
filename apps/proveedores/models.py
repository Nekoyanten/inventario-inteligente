"""Proveedores y su desempeño (módulo 6)."""

from django.db import models
from django.db.models import Avg

from apps.core.models import ModeloBase


class Proveedor(ModeloBase):
    negocio = models.ForeignKey("core.Negocio", on_delete=models.CASCADE, related_name="proveedores")
    nombre = models.CharField(max_length=150)
    nit = models.CharField(max_length=30, blank=True)
    contacto = models.CharField(max_length=100, blank=True)
    telefono = models.CharField(max_length=30, blank=True)
    whatsapp = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    tiempo_entrega_dias = models.PositiveIntegerField(
        default=3, help_text="Estimado inicial; se recalcula con las entregas reales"
    )
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre

    def entregas_registradas(self) -> int:
        from apps.compras.models import OrdenCompra

        return OrdenCompra.objects.filter(proveedor=self, estado=OrdenCompra.Estado.RECIBIDA,
                                          dias_entrega__isnull=False).count()

    def tiempo_entrega_real(self):
        """Promedio de días entre envío y recepción de órdenes recibidas."""
        from apps.compras.models import OrdenCompra

        promedio = (
            OrdenCompra.objects.filter(proveedor=self, estado=OrdenCompra.Estado.RECIBIDA)
            .exclude(dias_entrega__isnull=True)
            .aggregate(p=Avg("dias_entrega"))["p"]
        )
        return round(promedio, 1) if promedio is not None else self.tiempo_entrega_dias


class ProductoProveedor(models.Model):
    proveedor = models.ForeignKey(Proveedor, on_delete=models.CASCADE, related_name="productos")
    producto = models.ForeignKey("catalogo.Producto", on_delete=models.CASCADE, related_name="proveedores")
    precio_compra = models.DecimalField(max_digits=12, decimal_places=2)
    tiempo_entrega_dias = models.PositiveIntegerField(null=True, blank=True)
    multiplo_empaque = models.PositiveIntegerField(default=1, help_text="Ej: se compra por cajas de 12")
    codigo_proveedor = models.CharField(max_length=40, blank=True)

    class Meta:
        unique_together = ("proveedor", "producto")
