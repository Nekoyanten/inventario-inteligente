"""Entradas y salidas, historial de movimientos y kárdex por producto."""

from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import redirect, render

from apps.catalogo.models import Producto
from apps.core.negocio import del_negocio, negocio_requerido, obtener_del_negocio
from apps.reportes.exportadores import a_csv
from apps.usuarios.permisos import requiere_permiso

from .forms import FiltroMovimientosForm, MovimientoForm
from .models import Movimiento, TipoMovimiento
from .services import ErrorInventario, kardex, registrar_movimiento


def _filtrar(qs, form):
    if form.is_valid():
        d = form.cleaned_data
        if d.get("tipo"):
            qs = qs.filter(tipo=d["tipo"])
        if d.get("desde"):
            qs = qs.filter(fecha__date__gte=d["desde"])
        if d.get("hasta"):
            qs = qs.filter(fecha__date__lte=d["hasta"])
    return qs


@negocio_requerido
@requiere_permiso("registrar_movimiento")
def movimiento(request):
    inicial = {}
    producto_previo = None
    if request.GET.get("producto"):
        producto_previo = obtener_del_negocio(request.negocio, Producto, pk=request.GET["producto"])
        inicial["producto"] = producto_previo.pk
    if request.GET.get("tipo"):
        inicial["tipo"] = request.GET["tipo"]
    form = MovimientoForm(request.POST or None, initial=inicial, negocio=request.negocio,
                          puede_ver_costos=request.user.puede("ver_precios_compra"))
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            registrar_movimiento(
                producto=d["producto"], tipo=d["tipo"], cantidad=d["cantidad"], usuario=request.user,
                motivo=d["motivo"], costo_unitario=d.get("costo_unitario"),
                fecha_vencimiento=d.get("fecha_vencimiento"),
            )
        except ErrorInventario as e:
            form.add_error(None, str(e))
        else:
            d["producto"].refresh_from_db()
            messages.success(request, f"Registrado. {d['producto'].nombre} queda con {d['producto'].stock_actual:g}.")
            return redirect(f"{request.path}?producto={d['producto'].pk}")
    if form.is_bound and form.data.get("producto"):
        producto_previo = del_negocio(request.negocio, Producto).filter(pk=form.data["producto"]).first()
    recientes = del_negocio(request.negocio, Movimiento).select_related("producto", "usuario")[:10]
    return render(request, "inventario/movimiento.html", {"form": form, "producto": producto_previo,
                                                          "recientes": recientes})


@negocio_requerido
@requiere_permiso("registrar_movimiento")
def historial(request):
    form = FiltroMovimientosForm(request.GET or None)
    qs = _filtrar(del_negocio(request.negocio, Movimiento).select_related("producto", "usuario"), form)
    if request.GET.get("anomalos"):
        qs = qs.filter(marcado_anomalo=True)
    pagina = Paginator(qs, 40).get_page(request.GET.get("pagina"))
    return render(request, "inventario/historial.html", {"form": form, "pagina": pagina})


@negocio_requerido
@requiere_permiso("consultar_productos")
def kardex_producto(request, pk):
    producto = obtener_del_negocio(request.negocio, Producto, pk=pk)
    form = FiltroMovimientosForm(request.GET or None)
    qs = _filtrar(kardex(producto), form)
    if request.GET.get("formato") == "csv":
        filas = [[m.fecha.strftime("%Y-%m-%d %H:%M"), m.get_tipo_display(),
                  m.cantidad if m.es_entrada else -m.cantidad, m.stock_resultante, str(m.usuario or ""), m.motivo]
                 for m in qs]
        return a_csv(f"kardex-{producto.sku}", ["Fecha", "Qué pasó", "Cantidad", "Quedan", "Quién", "Por qué"], filas)
    pagina = Paginator(qs.order_by("-fecha", "-id"), 50).get_page(request.GET.get("pagina"))
    detalles = que_se_preparo(producto, pagina.object_list)
    for m in pagina.object_list:
        m.detalle_claro = detalles.get(m.pk, "")
    return render(request, "inventario/kardex.html", {"producto": producto, "form": form, "pagina": pagina})


def que_se_preparo(insumo, movimientos) -> dict:
    """Para cada salida de un insumo por una venta: qué se preparó con él («8 × Trago de Aguardiente (30 ml)»)."""
    from apps.catalogo.models import RecetaItem
    from apps.core.formato import numero
    from apps.ventas.models import DetalleVenta

    ventas = {m.referencia_id: m.pk for m in movimientos
              if m.tipo == TipoMovimiento.SALIDA_INSUMO and m.referencia_tipo == "venta" and m.referencia_id}
    if not ventas:
        return {}
    usan = set(RecetaItem.objects.filter(insumo=insumo).values_list("producto_id", flat=True))
    from django.db.models import Sum

    textos: dict = {}
    for d in (DetalleVenta.objects.filter(venta_id__in=ventas, producto_id__in=usan)
              .values("venta_id", "producto__nombre").annotate(n=Sum("cantidad")).order_by("venta_id", "producto__nombre")):
        textos.setdefault(ventas[d["venta_id"]], []).append(f"{numero(d['n'])} × {d['producto__nombre']}")
    return {pk: "Se preparó: " + ", ".join(t) for pk, t in textos.items()}


# ---------------------------------------------------------------- Vencimientos

@negocio_requerido
@requiere_permiso("registrar_movimiento")
def lotes(request):
    from django.utils import timezone

    from .models import Lote

    config = request.negocio.config
    hoy = timezone.localdate()
    qs = del_negocio(request.negocio, Lote).filter(cantidad__gt=0, fecha_vencimiento__isnull=False).select_related(
        "producto").order_by("fecha_vencimiento")
    filas = []
    for lote in qs:
        dias = lote.dias_para_vencer(hoy)
        if dias < 0:
            estado = ("gris", "Vencido")
        elif dias <= config.dias_vencimiento_rojo:
            estado = ("rojo", "Vence pronto")
        elif dias <= config.dias_vencimiento_amarillo:
            estado = ("amarillo", "Próximo a vencer")
        else:
            estado = ("verde", "Vigente")
        filas.append({"lote": lote, "dias": dias, "dias_abs": abs(dias), "color": estado[0], "estado": estado[1],
                      "valor": lote.cantidad * lote.producto.precio_compra})
    if request.GET.get("filtro") == "riesgo":
        filas = [f for f in filas if f["color"] != "verde"]
    return render(request, "inventario/lotes.html", {"filas": filas})


@negocio_requerido
@requiere_permiso("registrar_movimiento")
def retirar_lote(request, pk):
    from .models import Lote
    from .services import retirar_lote_vencido

    if request.method == "POST":
        lote = obtener_del_negocio(request.negocio, Lote, pk=pk)
        retirar_lote_vencido(lote, request.user)
        messages.success(request, f"Se registró la salida por vencimiento de {lote.producto.nombre}.")
    return redirect("inventario:lotes")


# ---------------------------------------------------------------- Conteo físico

@negocio_requerido
@requiere_permiso("registrar_conteo")
def conteos(request):
    from apps.catalogo.models import Categoria

    from .models import ConteoFisico
    from .services import crear_conteo

    if request.method == "POST" and request.POST.get("tipo") == "ciclico":
        from .services import crear_conteo_ciclico

        try:
            conteo = crear_conteo_ciclico(request.negocio, request.user)
        except ErrorInventario as e:
            messages.error(request, str(e))
            return redirect("inventario:conteos")
        return redirect("inventario:conteo", pk=conteo.pk)
    if request.method == "POST":
        categoria = None
        if request.POST.get("categoria"):
            categoria = obtener_del_negocio(request.negocio, Categoria, pk=request.POST["categoria"])
        conteo = crear_conteo(request.negocio, request.user, categoria)
        return redirect("inventario:conteo", pk=conteo.pk)
    return render(request, "inventario/conteos.html", {
        "conteos": del_negocio(request.negocio, ConteoFisico).select_related("responsable").order_by("-creado")[:30],
        "categorias": del_negocio(request.negocio, Categoria),
    })


@negocio_requerido
@requiere_permiso("registrar_conteo")
def conteo(request, pk):
    from decimal import Decimal, InvalidOperation

    from .models import ConteoFisico
    from .services import aprobar_conteo, enviar_conteo

    conteo = obtener_del_negocio(request.negocio, ConteoFisico, pk=pk)
    detalles = list(conteo.detalles.select_related("producto", "producto__categoria").order_by(
        "producto__categoria__nombre", "producto__nombre"))
    if request.method == "POST":
        accion = request.POST.get("accion", "guardar")
        try:
            if conteo.estado == ConteoFisico.Estado.EN_PROCESO:
                for d in detalles:
                    valor = request.POST.get(f"contado-{d.pk}")
                    if valor not in (None, ""):
                        try:
                            d.stock_contado = Decimal(valor)
                        except InvalidOperation:
                            continue
                    d.motivo = request.POST.get(f"motivo-{d.pk}", d.motivo)[:255]
                    d.save(update_fields=["stock_contado", "motivo"])
            if accion == "enviar":
                enviar_conteo(conteo, request.user)
                messages.success(request, "Conteo enviado para aprobación.")
            elif accion == "aprobar":
                if not request.user.puede("aprobar_ajuste"):
                    messages.error(request, "Solo el administrador aprueba ajustes.")
                else:
                    movs = aprobar_conteo(conteo, request.user)
                    messages.success(request, f"Conteo aprobado: {len(movs)} ajustes registrados.")
            elif accion == "anular" and request.user.puede("aprobar_ajuste"):
                conteo.estado = ConteoFisico.Estado.ANULADO
                conteo.save(update_fields=["estado"])
                messages.success(request, "Conteo anulado.")
            else:
                messages.success(request, "Avance guardado.")
        except ErrorInventario as e:
            messages.error(request, str(e))
        return redirect("inventario:conteo", pk=pk)
    diferencias = [d for d in detalles if d.diferencia]
    valor_dif = sum(d.diferencia * d.producto.precio_compra for d in diferencias)
    return render(request, "inventario/conteo.html", {
        "conteo": conteo, "detalles": detalles, "diferencias": diferencias, "valor_diferencia": valor_dif,
        "editable": conteo.estado == ConteoFisico.Estado.EN_PROCESO,
    })
