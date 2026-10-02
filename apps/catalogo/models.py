"""Catálogo de productos (módulo 1 del diseño)."""

from decimal import Decimal

from django.db import models

from apps.core.imagenes import ruta_imagen_producto
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
    AGOTADO = "AGOTADO", "Agotado"
    CRITICO = "CRITICO", "Crítico"
    BAJO = "BAJO", "Bajo"
    NORMAL = "NORMAL", "Normal"
    EXCESO = "EXCESO", "Exceso"


class TipoProducto(models.TextChoices):
    PRODUCTO = "PRODUCTO", "Producto (se vende y tiene stock)"
    INSUMO = "INSUMO", "Insumo (se compra y se gasta; no se vende)"
    PREPARADO = "PREPARADO", "Preparado o servicio (se vende; gasta insumos de su receta)"


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
    vida_util_dias = models.PositiveIntegerField(
        "Vida útil (días)", null=True, blank=True,
        help_text="Cuántos días dura el producto desde que llega. Limita el pedido sugerido y fecha los lotes solo")

    atributos = models.JSONField(default=dict, blank=True, help_text="Valores de atributos personalizados")
    # Variantes: 'Camisa básica' (padre, agrupador sin stock) → 'Camisa básica · M · Azul' (hijo con stock propio)
    padre = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="variantes"
    )
    es_agrupador = models.BooleanField(default=False, help_text="Producto padre de variantes; no se vende ni maneja stock")
    tipo = models.CharField(max_length=10, choices=TipoProducto.choices, default=TipoProducto.PRODUCTO, db_index=True)
    imagen = models.ImageField(upload_to=ruta_imagen_producto, null=True, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        unique_together = ("negocio", "sku")
        ordering = ["nombre"]
        indexes = [models.Index(fields=["negocio", "activo"])]

    def __str__(self):
        return f"{self.nombre} ({self.sku})"

    @property
    def nombre_corto(self):
        return self.nombre

    @property
    def vendible(self) -> bool:
        return self.activo and not self.es_agrupador and self.tipo != TipoProducto.INSUMO

    @property
    def maneja_stock(self) -> bool:
        """Los preparados (un almuerzo, un corte de cabello) no tienen stock propio: su stock son sus insumos."""
        return not self.es_agrupador and self.tipo != TipoProducto.PREPARADO

    @property
    def es_preparado(self) -> bool:
        return self.tipo == TipoProducto.PREPARADO

    @property
    def es_insumo(self) -> bool:
        return self.tipo == TipoProducto.INSUMO

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


class RecetaItem(models.Model):
    """Cuánto de cada insumo lleva un producto: «Almuerzo ejecutivo» → 0,15 kg de arroz, 0,2 kg de pollo…

    Sirve para dos cosas: al vender un preparado se descuentan sus insumos, y al registrar la producción de un
    producto elaborado (pan, jabones) se gastan los insumos y entra el producto terminado."""

    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name="receta")
    insumo = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name="usado_en")
    cantidad = models.DecimalField(max_digits=12, decimal_places=3, help_text="Por cada unidad del producto")
    merma_pct = models.DecimalField("Merma %", max_digits=5, decimal_places=2, default=0,
                                    help_text="Lo que se pierde al preparar (cáscaras, recortes…)")

    class Meta:
        unique_together = ("producto", "insumo")
        ordering = ["insumo__nombre"]

    def __str__(self):
        return f"{self.producto.nombre}: {self.cantidad} {self.insumo.nombre}"

    @property
    def cantidad_total(self) -> Decimal:
        """Cantidad a descontar por unidad, incluida la merma."""
        return (self.cantidad * (1 + self.merma_pct / 100)).quantize(Decimal("0.001"))

    @property
    def costo(self) -> Decimal:
        return self.cantidad_total * self.insumo.precio_compra
