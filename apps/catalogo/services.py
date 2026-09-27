from django.db import transaction
from django.utils.text import slugify

from apps.core.auditoria import auditar
from apps.inventario.models import TipoMovimiento
from apps.inventario.services import registrar_movimiento

from .models import Producto


@transaction.atomic
def crear_producto(form, usuario, stock_inicial=None, vencimiento=None) -> Producto:
    producto = form.save()
    if stock_inicial:
        registrar_movimiento(
            producto=producto, tipo=TipoMovimiento.ENTRADA_INICIAL, cantidad=stock_inicial, usuario=usuario,
            motivo="Inventario inicial", fecha_vencimiento=vencimiento,
        )
    auditar(producto.negocio, usuario, "crear_producto", producto, sku=producto.sku)
    return producto


@transaction.atomic
def generar_variantes(padre: Producto, combinaciones: list[dict], usuario) -> list[Producto]:
    """Convierte `padre` en agrupador y crea una variante por combinación (omite las existentes)."""
    if padre.stock_actual:
        raise ValueError("El producto tiene stock; regístrelo en las variantes antes de convertirlo en agrupador.")
    padre.es_agrupador = True
    padre.save(update_fields=["es_agrupador"])
    creadas = []
    for combo in combinaciones:
        sufijo = "-".join(slugify(v)[:6].upper() for v in combo.values())
        sku = f"{padre.sku}-{sufijo}"[:40]
        if Producto.objects.filter(negocio=padre.negocio, sku=sku).exists():
            continue
        creadas.append(Producto.objects.create(
            negocio=padre.negocio, padre=padre, sku=sku,
            nombre=f"{padre.nombre} · " + " · ".join(combo.values()),
            categoria=padre.categoria, marca=padre.marca, unidad=padre.unidad,
            proveedor_principal=padre.proveedor_principal, precio_compra=padre.precio_compra,
            precio_venta=padre.precio_venta, stock_minimo=padre.stock_minimo, atributos={**padre.atributos, **combo},
            descripcion=padre.descripcion,
        ))
    auditar(padre.negocio, usuario, "generar_variantes", padre, cantidad=len(creadas))
    return creadas
