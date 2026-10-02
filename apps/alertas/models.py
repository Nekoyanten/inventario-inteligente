from django.db import models

from apps.core.models import ModeloBase


class Alerta(ModeloBase):
    class Tipo(models.TextChoices):
        AGOTADO = "AGOTADO", "Producto agotado"
        STOCK_CRITICO = "STOCK_CRITICO", "Stock crítico"
        STOCK_BAJO = "STOCK_BAJO", "Stock bajo"
        RIESGO_AGOTAMIENTO = "RIESGO_AGOTAMIENTO", "Riesgo de agotamiento"
        VENCIMIENTO = "VENCIMIENTO", "Próximo a vencer"
        VENCIDO = "VENCIDO", "Producto vencido"
        BAJA_ROTACION = "BAJA_ROTACION", "Baja rotación"
        EXCESO = "EXCESO", "Exceso de inventario"
        ANOMALIA = "ANOMALIA", "Movimiento inusual"
        VENTA_SIN_STOCK = "VENTA_SIN_STOCK", "Venta sin stock registrado"

    class Severidad(models.IntegerChoices):
        INFO = 1, "Información"
        REVISAR = 2, "Revisar"
        ACTUAR = 3, "Actuar"

    class Estado(models.TextChoices):
        ABIERTA = "ABIERTA", "Abierta"
        VISTA = "VISTA", "Vista"
        RESUELTA = "RESUELTA", "Resuelta"
        DESCARTADA = "DESCARTADA", "Descartada"

    negocio = models.ForeignKey("core.Negocio", on_delete=models.CASCADE, related_name="alertas")
    producto = models.ForeignKey(
        "catalogo.Producto", null=True, blank=True, on_delete=models.CASCADE, related_name="alertas"
    )
    tipo = models.CharField(max_length=25, choices=Tipo.choices)
    severidad = models.IntegerField(choices=Severidad.choices, default=Severidad.REVISAR)
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.ABIERTA)
    mensaje = models.CharField(max_length=300)
    accion_sugerida = models.CharField(max_length=200, blank=True)
    datos = models.JSONField(default=dict, blank=True)
    resuelta_por = models.ForeignKey("usuarios.Usuario", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    nota = models.CharField(max_length=255, blank=True, help_text="Justificación al resolver o descartar")

    class Meta:
        ordering = ["-severidad", "-creado"]
        indexes = [models.Index(fields=["negocio", "estado", "severidad"])]

    def __str__(self):
        return f"{self.get_severidad_display()} {self.mensaje}"

    @property
    def enlace_accion(self):
        """A dónde lleva el botón de acción sugerida."""
        from django.urls import reverse

        if self.tipo in (self.Tipo.STOCK_BAJO, self.Tipo.STOCK_CRITICO, self.Tipo.RIESGO_AGOTAMIENTO, self.Tipo.AGOTADO):
            return reverse("recomendaciones:lista") if _existe("recomendaciones:lista") else None
        if self.tipo in (self.Tipo.VENCIMIENTO, self.Tipo.VENCIDO):
            return reverse("inventario:lotes")
        if self.tipo in (self.Tipo.ANOMALIA, self.Tipo.VENTA_SIN_STOCK) and self.datos.get("movimiento") and self.producto_id:
            return reverse("inventario:kardex", args=[self.producto_id])
        if self.producto_id:
            return reverse("catalogo:detalle", args=[self.producto_id])
        return None


def _existe(nombre):
    from django.urls import NoReverseMatch, reverse

    try:
        reverse(nombre)
        return True
    except NoReverseMatch:
        return False
