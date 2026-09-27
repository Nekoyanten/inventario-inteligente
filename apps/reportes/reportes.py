"""Catálogo de reportes. Cada reporte = función que devuelve (encabezados, filas)."""

from apps.catalogo.models import Producto
from apps.core.negocio import del_negocio
from apps.inventario.models import Movimiento, TipoMovimiento


def inventario_actual(negocio):
    enc = ["SKU", "Producto", "Categoría", "Stock", "Mínimo", "Estado", "Precio compra", "Precio venta", "Valor"]
    filas = [
        [
            p.sku,
            p.nombre,
            str(p.categoria or ""),
            p.stock_actual,
            p.stock_minimo,
            p.get_estado_display(),
            p.precio_compra,
            p.precio_venta,
            p.valor_inventario,
        ]
        for p in del_negocio(negocio, Producto).filter(activo=True).select_related("categoria")
    ]
    return enc, filas


def historial_ajustes(negocio):
    enc = ["Fecha", "Producto", "Tipo", "Cantidad", "Usuario", "Motivo"]
    qs = del_negocio(negocio, Movimiento).filter(
        tipo__in=[TipoMovimiento.ENTRADA_AJUSTE, TipoMovimiento.SALIDA_AJUSTE]
    ).select_related("producto", "usuario")
    return enc, [
        [
            m.fecha.strftime("%Y-%m-%d %H:%M"),
            m.producto.nombre,
            m.get_tipo_display(),
            m.cantidad,
            str(m.usuario or ""),
            m.motivo,
        ]
        for m in qs
    ]


REPORTES = {
    "inventario-actual": ("Inventario actual", inventario_actual),
    "historial-ajustes": ("Historial de ajustes", historial_ajustes),
    # TODO (issues fase 5): movimientos, ventas, compras, más/menos vendidos, por vencer, agotados, utilidad
}
