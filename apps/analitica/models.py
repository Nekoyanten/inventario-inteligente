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


class Temporada(models.Model):
    """Época en la que la demanda cambia (Navidad, regreso a clases, Día de la Madre…).

    Se repite cada año entre dos fechas (día/mes). El factor multiplica la demanda estimada:
    1.5 = se vende 50 % más; 0.7 = se vende 30 % menos.
    """

    negocio = models.ForeignKey("core.Negocio", on_delete=models.CASCADE, related_name="temporadas")
    nombre = models.CharField(max_length=80)
    inicio_mes = models.PositiveSmallIntegerField()
    inicio_dia = models.PositiveSmallIntegerField()
    fin_mes = models.PositiveSmallIntegerField()
    fin_dia = models.PositiveSmallIntegerField()
    factor = models.DecimalField(max_digits=4, decimal_places=2, default=1.5)
    categoria = models.ForeignKey("catalogo.Categoria", null=True, blank=True, on_delete=models.CASCADE,
                                  help_text="Vacío = aplica a todos los productos")

    class Meta:
        ordering = ["inicio_mes", "inicio_dia"]

    def __str__(self):
        return f"{self.nombre} ({self.inicio_dia}/{self.inicio_mes} – {self.fin_dia}/{self.fin_mes}, ×{self.factor})"

    def contiene(self, fecha) -> bool:
        md = (fecha.month, fecha.day)
        ini, fin = (self.inicio_mes, self.inicio_dia), (self.fin_mes, self.fin_dia)
        return ini <= md <= fin if ini <= fin else (md >= ini or md <= fin)  # cruza fin de año


class RegistroPronostico(models.Model):
    """Guarda lo que se pronosticó para luego compararlo con lo que realmente se vendió."""

    producto = models.ForeignKey("catalogo.Producto", on_delete=models.CASCADE, related_name="pronosticos")
    desde = models.DateField()
    hasta = models.DateField()
    pronosticado = models.DecimalField(max_digits=12, decimal_places=3)
    real = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)

    class Meta:
        ordering = ["-desde"]
        unique_together = ("producto", "desde")

    @property
    def error_pct(self):
        if self.real is None or not self.real:
            return None
        return abs(float(self.pronosticado) - float(self.real)) / float(self.real) * 100
