from django.db import models

from apps.core.models import ModeloBase


class RecomendacionCompra(ModeloBase):
    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        ACEPTADA = "ACEPTADA", "Convertida en orden"
        DESCARTADA = "DESCARTADA", "Descartada"

    negocio = models.ForeignKey("core.Negocio", on_delete=models.CASCADE, related_name="recomendaciones")
    producto = models.ForeignKey("catalogo.Producto", on_delete=models.CASCADE, related_name="recomendaciones")
    proveedor = models.ForeignKey("proveedores.Proveedor", null=True, blank=True, on_delete=models.SET_NULL)
    cantidad_sugerida = models.PositiveIntegerField()
    demanda_diaria = models.DecimalField(max_digits=12, decimal_places=3)
    stock_seguridad = models.DecimalField(max_digits=12, decimal_places=3)
    tiempo_entrega = models.DecimalField(max_digits=6, decimal_places=1)
    stock_al_calcular = models.DecimalField(max_digits=12, decimal_places=3)
    explicacion = models.TextField()
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.PENDIENTE)

    class Meta:
        ordering = ["-creado"]

    def __str__(self):
        return f"Pedir {self.cantidad_sugerida} de {self.producto.nombre}"
