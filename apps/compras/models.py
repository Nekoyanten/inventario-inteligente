"""Órdenes de compra: de la recomendación al inventario (flujo 9.3 del diseño)."""

from django.conf import settings
from django.db import models

from apps.core.models import ModeloBase


def ruta_factura(instancia, nombre):
    return f"facturas/{instancia.negocio_id}/{nombre}"


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
    fecha_esperada = models.DateField(null=True, blank=True)
    es_compra_directa = models.BooleanField(default=False, help_text="Factura registrada sin orden previa")
    numero_factura = models.CharField(max_length=40, blank=True)
    factura_imagen = models.ImageField("Foto de la factura", upload_to=ruta_factura, null=True, blank=True)
    observaciones = models.TextField(blank=True)

    class Meta:
        ordering = ["-creado"]

    def __str__(self):
        return f"OC #{self.pk} · {self.proveedor} · {self.get_estado_display()}"

    @property
    def total(self):
        return sum(d.cantidad_pedida * d.costo_unitario for d in self.detalles.all())

    @property
    def a_tiempo(self):
        if self.dias_entrega is None:
            return None
        return self.dias_entrega <= self.proveedor.tiempo_entrega_dias

    @property
    def editable(self):
        return self.estado == self.Estado.BORRADOR


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
    def subtotal(self):
        return self.cantidad_pedida * self.costo_unitario

    @property
    def pendiente(self):
        return self.cantidad_pedida - self.cantidad_recibida
