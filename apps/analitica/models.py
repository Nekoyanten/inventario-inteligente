from django.db import models


class DemandaDiaria(models.Model):
    """Agregado de unidades vendidas por producto y día (base de toda la analítica)."""

    producto = models.ForeignKey("catalogo.Producto", on_delete=models.CASCADE, related_name="demanda_diaria")
    fecha = models.DateField()
    cantidad = models.DecimalField(max_digits=12, decimal_places=3, default=0)

    class Meta:
        unique_together = ("producto", "fecha")
        ordering = ["fecha"]
        indexes = [models.Index(fields=["producto", "fecha"])]
