"""Stock, movimientos (kárdex), lotes y conteos físicos (módulos 2, 7 y 12)."""

from datetime import date

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import ModeloBase


class TipoMovimiento(models.TextChoices):
    # Entradas (+)
    ENTRADA_INICIAL = "ENTRADA_INICIAL", "Inventario inicial"
    ENTRADA_COMPRA = "ENTRADA_COMPRA", "Compra a proveedor"
    ENTRADA_DEVOLUCION_CLIENTE = "ENTRADA_DEVOLUCION_CLIENTE", "Devolución de cliente"
    ENTRADA_AJUSTE = "ENTRADA_AJUSTE", "Ajuste positivo"
    # Salidas (−)
    SALIDA_VENTA = "SALIDA_VENTA", "Venta"
    SALIDA_DANADO = "SALIDA_DANADO", "Producto dañado"
    SALIDA_VENCIDO = "SALIDA_VENCIDO", "Producto vencido"
    SALIDA_DEVOLUCION_PROVEEDOR = "SALIDA_DEVOLUCION_PROVEEDOR", "Devolución al proveedor"
    SALIDA_AJUSTE = "SALIDA_AJUSTE", "Ajuste negativo"
    SALIDA_CONSUMO_INTERNO = "SALIDA_CONSUMO_INTERNO", "Consumo interno (uso en servicios o cocina)"

    @classmethod
    def es_entrada(cls, tipo: str) -> bool:
        return tipo.startswith("ENTRADA_")


# Tipos que exigen un motivo escrito (evita "cambiar el número sin explicación").
TIPOS_CON_MOTIVO_OBLIGATORIO = {
    TipoMovimiento.ENTRADA_AJUSTE,
    TipoMovimiento.SALIDA_AJUSTE,
    TipoMovimiento.SALIDA_DANADO,
    TipoMovimiento.SALIDA_DEVOLUCION_PROVEEDOR,
    TipoMovimiento.ENTRADA_DEVOLUCION_CLIENTE,
}


class Lote(ModeloBase):
    producto = models.ForeignKey("catalogo.Producto", on_delete=models.CASCADE, related_name="lotes")
    codigo = models.CharField(max_length=40, blank=True)
    fecha_vencimiento = models.DateField(null=True, blank=True, db_index=True)
    cantidad = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    costo_unitario = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ["fecha_vencimiento", "creado"]  # FEFO

    def __str__(self):
        return f"{self.producto.nombre} lote {self.codigo or self.pk} vence {self.fecha_vencimiento}"

    def dias_para_vencer(self, hoy: date | None = None):
        if not self.fecha_vencimiento:
            return None
        return (self.fecha_vencimiento - (hoy or timezone.localdate())).days


class Movimiento(models.Model):
    """Registro inmutable de cada cambio de stock. Un error se corrige con otro movimiento."""

    negocio = models.ForeignKey("core.Negocio", on_delete=models.CASCADE, related_name="movimientos")
    producto = models.ForeignKey("catalogo.Producto", on_delete=models.PROTECT, related_name="movimientos")
    lote = models.ForeignKey(Lote, null=True, blank=True, on_delete=models.SET_NULL)
    tipo = models.CharField(max_length=30, choices=TipoMovimiento.choices)
    cantidad = models.DecimalField(max_digits=12, decimal_places=3, help_text="Siempre positiva")
    costo_unitario = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    stock_resultante = models.DecimalField(max_digits=12, decimal_places=3)
    fecha = models.DateTimeField(db_index=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    motivo = models.CharField(max_length=255, blank=True)
    # Referencia al documento de origen (venta, orden de compra, conteo)
    referencia_tipo = models.CharField(max_length=30, blank=True)
    referencia_id = models.PositiveIntegerField(null=True, blank=True)
    marcado_anomalo = models.BooleanField(default=False)

    class Meta:
        ordering = ["-fecha", "-id"]
        indexes = [models.Index(fields=["producto", "fecha"]), models.Index(fields=["negocio", "tipo", "fecha"])]

    def __str__(self):
        signo = "+" if self.es_entrada else "−"
        return f"{self.fecha:%Y-%m-%d} {self.producto.nombre} {signo}{self.cantidad} ({self.get_tipo_display()})"

    @property
    def es_entrada(self) -> bool:
        return TipoMovimiento.es_entrada(self.tipo)

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("Los movimientos son inmutables; registre un movimiento inverso.")
        super().save(*args, **kwargs)


class ConteoFisico(ModeloBase):
    class Estado(models.TextChoices):
        EN_PROCESO = "EN_PROCESO", "En proceso"
        PENDIENTE_APROBACION = "PENDIENTE", "Pendiente de aprobación"
        APROBADO = "APROBADO", "Aprobado"
        ANULADO = "ANULADO", "Anulado"

    negocio = models.ForeignKey("core.Negocio", on_delete=models.CASCADE)
    responsable = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    aprobado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.EN_PROCESO)
    observaciones = models.TextField(blank=True)


class DetalleConteo(models.Model):
    conteo = models.ForeignKey(ConteoFisico, on_delete=models.CASCADE, related_name="detalles")
    producto = models.ForeignKey("catalogo.Producto", on_delete=models.PROTECT)
    stock_sistema = models.DecimalField(max_digits=12, decimal_places=3)
    stock_contado = models.DecimalField(max_digits=12, decimal_places=3)
    motivo = models.CharField(max_length=255, blank=True)

    @property
    def diferencia(self):
        return self.stock_contado - self.stock_sistema
