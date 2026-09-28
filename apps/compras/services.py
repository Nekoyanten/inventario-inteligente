from django.db import transaction
from django.utils import timezone

from apps.core.auditoria import auditar
from apps.inventario.models import TipoMovimiento
from apps.inventario.services import ErrorInventario, registrar_movimiento

from .models import OrdenCompra


def _bloquear(orden: OrdenCompra):
    """Bloquea la fila de la orden hasta el fin de la transacción y recarga su estado actual.

    Evita que dos solicitudes simultáneas (doble clic, dos pestañas) reciban la misma mercancía dos veces."""
    list(OrdenCompra.objects.select_for_update().filter(pk=orden.pk).values_list("pk", flat=True))
    orden.refresh_from_db()


def enviar_orden(orden: OrdenCompra, usuario, fecha=None):
    if orden.estado != OrdenCompra.Estado.BORRADOR:
        raise ErrorInventario("Solo se envían órdenes en borrador.")
    orden.estado = OrdenCompra.Estado.ENVIADA
    orden.fecha_envio = fecha or timezone.now()
    orden.save()
    auditar(orden.negocio, usuario, "enviar_orden", orden)
    return orden


@transaction.atomic
def recibir_orden(orden: OrdenCompra, usuario, recibido: dict, numero_factura="", vencimientos: dict | None = None,
                  fecha=None):
    """Registra la recepción (total o parcial) de una orden.

    recibido: {detalle_id: cantidad}; vencimientos: {detalle_id: date} (si el negocio usa vencimientos)
    """
    _bloquear(orden)
    if orden.estado not in (
        OrdenCompra.Estado.ENVIADA,
        OrdenCompra.Estado.CONFIRMADA,
        OrdenCompra.Estado.RECIBIDA_PARCIAL,
    ):
        raise ErrorInventario("La orden no está en un estado que permita recepción.")
    vencimientos = vencimientos or {}
    ahora = fecha or timezone.now()
    for detalle in orden.detalles.select_related("producto"):
        cant = recibido.get(detalle.pk, 0)
        if not cant:
            continue
        if cant > detalle.pendiente:
            raise ErrorInventario(f"Se recibe más de lo pedido en {detalle.producto.nombre}.")
        registrar_movimiento(
            producto=detalle.producto,
            tipo=TipoMovimiento.ENTRADA_COMPRA,
            cantidad=cant,
            usuario=usuario,
            costo_unitario=detalle.costo_unitario,
            fecha_vencimiento=vencimientos.get(detalle.pk),
            motivo=f"OC #{orden.pk} {numero_factura}".strip(),
            referencia_tipo="orden_compra",
            referencia_id=orden.pk,
            fecha=ahora,
        )
        detalle.cantidad_recibida += cant
        detalle.save(update_fields=["cantidad_recibida"])

    completa = all(d.pendiente <= 0 for d in orden.detalles.all())
    orden.estado = OrdenCompra.Estado.RECIBIDA if completa else OrdenCompra.Estado.RECIBIDA_PARCIAL
    orden.numero_factura = numero_factura or orden.numero_factura
    if completa:
        orden.fecha_recepcion = ahora
        if orden.fecha_envio:
            orden.dias_entrega = max(0, (ahora - orden.fecha_envio).days)
    orden.save()
    auditar(orden.negocio, usuario, "recibir_orden", orden, completa=completa)
    return orden


@transaction.atomic
def recibir_todo(orden: OrdenCompra, usuario, numero_factura="", fecha=None, factura_imagen=None):
    """«Llegó todo» en un toque: recibe lo pendiente de cada línea. Los vencimientos se calculan con la vida útil."""
    _bloquear(orden)  # un doble toque no debe ingresar la mercancía dos veces
    pendientes = {d.pk: d.pendiente for d in orden.detalles.all() if d.pendiente > 0}
    if not pendientes:
        raise ErrorInventario("Esta orden no tiene nada pendiente por recibir.")
    recibir_orden(orden, usuario, pendientes, numero_factura=numero_factura, fecha=fecha)
    if factura_imagen:
        guardar_foto_factura(orden, factura_imagen)
    return orden


@transaction.atomic
def cerrar_recepcion(orden: OrdenCompra, usuario, fecha=None):
    """El proveedor no enviará lo que falta: se cierra la orden con lo que llegó (deja de contarse en camino)."""
    _bloquear(orden)
    if orden.estado != OrdenCompra.Estado.RECIBIDA_PARCIAL:
        raise ErrorInventario("Solo se cierran órdenes recibidas parcialmente.")
    ahora = fecha or timezone.now()
    orden.estado = OrdenCompra.Estado.RECIBIDA
    orden.fecha_recepcion = ahora
    if orden.fecha_envio:
        orden.dias_entrega = max(0, (ahora - orden.fecha_envio).days)
    faltantes = ", ".join(f"{d.pendiente:g} {d.producto.nombre}" for d in orden.detalles.select_related("producto")
                          if d.pendiente > 0)
    orden.observaciones = (orden.observaciones + f"\nCerrada sin recibir: {faltantes}").strip()
    orden.save()
    auditar(orden.negocio, usuario, "cerrar_recepcion", orden, faltantes=faltantes)
    return orden


def guardar_foto_factura(orden: OrdenCompra, archivo):
    """Guarda la foto de la factura (optimizada: legible pero liviana)."""
    from django.conf import settings

    from apps.core.imagenes import optimizar_imagen

    if archivo.size > settings.TAMANO_MAX_ARCHIVO_MB * 1024 * 1024:
        raise ErrorInventario(f"La foto supera {settings.TAMANO_MAX_ARCHIVO_MB} MB.")
    try:
        contenido = optimizar_imagen(archivo, lado_max=1800, calidad=75)
    except Exception as e:  # formato no soportado o archivo dañado
        raise ErrorInventario("No pudimos leer la foto de la factura. Prueba con JPG o PNG.") from e
    if orden.factura_imagen:
        orden.factura_imagen.delete(save=False)
    orden.factura_imagen.save(contenido.name, contenido, save=True)


def _fecha(texto):
    from datetime import date

    try:
        return date.fromisoformat(texto) if texto else None
    except ValueError as e:
        raise ErrorInventario(f"Fecha inválida: {texto}") from e


def _lineas_desde_post(post, negocio):
    """Lee filas enviadas como lineas-producto / lineas-cantidad / lineas-costo (listas paralelas)."""
    from decimal import Decimal, InvalidOperation

    from apps.catalogo.models import Producto
    from apps.core.negocio import del_negocio

    productos = del_negocio(negocio, Producto).filter(activo=True, es_agrupador=False)
    lineas = []
    for pid, cant, costo, venc in zip(post.getlist("lineas-producto"), post.getlist("lineas-cantidad"),
                                      post.getlist("lineas-costo"), post.getlist("lineas-vencimiento") or
                                      [""] * len(post.getlist("lineas-producto")), strict=False):
        try:
            cantidad = Decimal(cant)
            costo_d = Decimal(costo or "0")
        except InvalidOperation as e:
            raise ErrorInventario("Revisa las cantidades y costos.") from e
        if cantidad <= 0:
            continue
        producto = productos.filter(pk=pid).first()
        if producto is None:
            raise ErrorInventario("Uno de los productos no es válido.")
        lineas.append({"producto": producto, "cantidad": cantidad, "costo": costo_d, "vencimiento": _fecha(venc)})
    if not lineas:
        raise ErrorInventario("Agrega al menos un producto con cantidad mayor que cero.")
    return lineas


@transaction.atomic
def crear_orden(*, negocio, proveedor, usuario, lineas, observaciones="", fecha_esperada=None) -> OrdenCompra:
    from .models import DetalleOrdenCompra

    orden = OrdenCompra.objects.create(negocio=negocio, proveedor=proveedor, creada_por=usuario,
                                       observaciones=observaciones, fecha_esperada=fecha_esperada)
    for linea in lineas:
        DetalleOrdenCompra.objects.create(orden=orden, producto=linea["producto"], cantidad_pedida=linea["cantidad"],
                                          costo_unitario=linea["costo"] or linea["producto"].precio_compra)
    auditar(negocio, usuario, "crear_orden", orden, lineas=len(lineas))
    return orden


def confirmar_orden(orden: OrdenCompra, usuario):
    if orden.estado != OrdenCompra.Estado.ENVIADA:
        raise ErrorInventario("Solo se confirman órdenes enviadas.")
    orden.estado = OrdenCompra.Estado.CONFIRMADA
    orden.save(update_fields=["estado", "actualizado"])
    auditar(orden.negocio, usuario, "confirmar_orden", orden)


def cancelar_orden(orden: OrdenCompra, usuario, motivo=""):
    if orden.estado in (OrdenCompra.Estado.RECIBIDA, OrdenCompra.Estado.CANCELADA):
        raise ErrorInventario("Esta orden ya no se puede cancelar.")
    orden.estado = OrdenCompra.Estado.CANCELADA
    orden.observaciones = (orden.observaciones + f"\nCancelada: {motivo}").strip()
    orden.save(update_fields=["estado", "observaciones", "actualizado"])
    # Las recomendaciones asociadas vuelven a estar disponibles
    from apps.recomendaciones.models import RecomendacionCompra

    RecomendacionCompra.objects.filter(detalleordencompra__orden=orden).update(
        estado=RecomendacionCompra.Estado.DESCARTADA
    )
    auditar(orden.negocio, usuario, "cancelar_orden", orden, motivo=motivo)


@transaction.atomic
def registrar_compra_directa(*, negocio, proveedor, usuario, lineas, numero_factura="", factura_imagen=None,
                             fecha=None) -> OrdenCompra:
    """Factura del proveedor sin orden previa (p. ej. facturas a mano): entra directo al inventario."""
    orden = crear_orden(negocio=negocio, proveedor=proveedor, usuario=usuario, lineas=lineas)
    orden.es_compra_directa = True
    orden.estado = OrdenCompra.Estado.ENVIADA
    orden.save(update_fields=["es_compra_directa", "estado"])
    detalles = list(orden.detalles.all())
    recibir_orden(
        orden, usuario, {d.pk: d.cantidad_pedida for d in detalles}, numero_factura=numero_factura,
        vencimientos={d.pk: linea.get("vencimiento") for d, linea in zip(detalles, lineas, strict=True)}, fecha=fecha,
    )
    orden.dias_entrega = None  # no aplica a desempeño del proveedor
    orden.save(update_fields=["dias_entrega"])
    if factura_imagen:
        guardar_foto_factura(orden, factura_imagen)
    return orden


def mensaje_whatsapp(orden: OrdenCompra) -> str:
    lineas = "\n".join(f"• {d.cantidad_pedida:g} × {d.producto.nombre}" for d in orden.detalles.select_related("producto"))
    return (f"Hola {orden.proveedor.contacto or orden.proveedor.nombre}, le escribe {orden.negocio.nombre}.\n"
            f"Queremos hacer el siguiente pedido (orden #{orden.pk}):\n{lineas}\n"
            "¿Nos confirma disponibilidad y fecha de entrega? Gracias.")


def pdf_orden(orden: OrdenCompra) -> bytes:
    import io

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm)
    est = getSampleStyleSheet()
    n = orden.negocio
    elementos = [
        Paragraph(f"<b>{n.nombre}</b>", est["Title"]),
        Paragraph(f"NIT {n.nit or '—'} · {n.telefono or ''} · {n.direccion or ''}", est["Normal"]),
        Spacer(1, 12),
        Paragraph(f"<b>Orden de compra #{orden.pk}</b> — {orden.creado:%d/%m/%Y}", est["Heading2"]),
        Paragraph(f"Proveedor: <b>{orden.proveedor.nombre}</b> {orden.proveedor.nit or ''}", est["Normal"]),
    ]
    if orden.fecha_esperada:
        elementos.append(Paragraph(f"Entrega esperada: {orden.fecha_esperada:%d/%m/%Y}", est["Normal"]))
    elementos.append(Spacer(1, 12))
    filas = [["Producto", "Código", "Cantidad", "Costo unit.", "Subtotal"]]
    total = 0
    for d in orden.detalles.select_related("producto"):
        sub = d.cantidad_pedida * d.costo_unitario
        total += sub
        filas.append([d.producto.nombre, d.producto.sku, f"{d.cantidad_pedida:g}", f"${d.costo_unitario:,.0f}",
                      f"${sub:,.0f}"])
    filas.append(["", "", "", "Total", f"${total:,.0f}"])
    tabla = Table(filas, colWidths=[6.5 * cm, 2.8 * cm, 2 * cm, 2.6 * cm, 2.8 * cm])
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f7a4d")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"), ("GRID", (0, 0), (-1, -2), 0.25, colors.HexColor("#cccccc")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
    ]))
    elementos += [tabla, Spacer(1, 16)]
    if orden.observaciones:
        elementos.append(Paragraph(f"Observaciones: {orden.observaciones}", est["Normal"]))
    doc.build(elementos)
    return buf.getvalue()
