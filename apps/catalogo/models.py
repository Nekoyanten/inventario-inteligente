"""Catálogo de productos (módulo 1 del diseño)."""

from decimal import Decimal

from django.db import models

from apps.core.models import ModeloBase


class Categoria(ModeloBase):
    negocio = models.ForeignKey("core.Negocio", on_delete=models.CASCADE, related_name="categorias")
    nombre = models.CharField(max_length=80)

    class Meta:
        unique_together = ("negocio", "nombre")
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class AtributoPersonalizado(models.Model):
    """Atributo adaptativo por categoría: Talla, Color, Tono, Principio activo…"""

    class Tipo(models.TextChoices):
        TEXTO = "TEXTO", "Texto"
        NUMERO = "NUMERO", "Número"
        OPCION = "OPCION", "Lista de opciones"

    categoria = models.ForeignKey(Categoria, on_delete=models.CASCADE, related_name="atributos")
    nombre = models.CharField(max_length=60)
    tipo = models.CharField(max_length=10, choices=Tipo.choices, default=Tipo.TEXTO)
    opciones = models.JSONField(default=list, blank=True, help_text='Ej: ["S", "M", "L"]')
    obligatorio = models.BooleanField(default=False)

    class Meta:
        unique_together = ("categoria", "nombre")

    def __str__(self):
        return f"{self.categoria} · {self.nombre}"


class Marca(ModeloBase):
    negocio = models.ForeignKey("core.Negocio", on_delete=models.CASCADE, related_name="marcas")
    nombre = models.CharField(max_length=80)

    class Meta:
        unique_together = ("negocio", "nombre")

    def __str__(self):
        return self.nombre


class UnidadMedida(models.Model):
    nombre = models.CharField(max_length=30, unique=True)  # Unidad, Kilogramo, Litro, Caja…
    abreviatura = models.CharField(max_length=10)
    permite_decimales = models.BooleanField(default=False)

    def __str__(self):
        return self.abreviatura


class EstadoStock(models.TextChoices):
    AGOTADO = "AGOTADO", "⚫ Agotado"
    CRITICO = "CRITICO", "🔴 Crítico"
    BAJO = "BAJO", "🟡 Bajo"
    NORMAL = "NORMAL", "🟢 Normal"
    EXCESO = "EXCESO", "🔵 Exceso"


class Producto(ModeloBase):
    negocio = models.ForeignKey("core.Negocio", on_delete=models.CASCADE, related_name="productos")
    sku = models.CharField("Código / SKU", max_length=40)
    codigo_barras = models.CharField(max_length=40, blank=True, db_index=True)
    nombre = models.CharField(max_length=150)
    descripcion = models.TextField(blank=True)
    categoria = models.ForeignKey(Categoria, null=True, blank=True, on_delete=models.SET_NULL)
    marca = models.ForeignKey(Marca, null=True, blank=True, on_delete=models.SET_NULL)
    proveedor_principal = models.ForeignKey(
        "proveedores.Proveedor", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    unidad = models.ForeignKey(UnidadMedida, null=True, blank=True, on_delete=models.PROTECT)
    precio_compra = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    precio_venta = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # stock_actual es un valor en caché: SOLO lo modifica inventario.services.registrar_movimiento
    stock_actual = models.DecimalField(max_digits=12, decimal_places=3, default=0, editable=False)
    stock_minimo = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    stock_maximo = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)

    atributos = models.JSONField(default=dict, blank=True, help_text="Valores de atributos personalizados")
    imagen = models.ImageField(upload_to="productos/", null=True, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        unique_together = ("negocio", "sku")
        ordering = ["nombre"]
        indexes = [models.Index(fields=["negocio", "activo"])]

    def __str__(self):
        return f"{self.nombre} ({self.sku})"

    @property
    def valor_inventario(self) -> Decimal:
        return self.stock_actual * self.precio_compra

    @property
    def margen(self) -> Decimal:
        if not self.precio_venta:
            return Decimal("0")
        return (self.precio_venta - self.precio_compra) / self.precio_venta * 100

    def get_estado_display(self) -> str:
        return EstadoStock(self.estado_basico()).label

    def estado_basico(self) -> str:
        """Semáforo solo por stock mínimo. La versión inteligente está en analitica.services."""
        if self.stock_actual <= 0:
            return EstadoStock.AGOTADO
        if self.stock_actual <= self.stock_minimo / 2:
            return EstadoStock.CRITICO
        if self.stock_actual <= self.stock_minimo:
            return EstadoStock.BAJO
        return EstadoStock.NORMAL
