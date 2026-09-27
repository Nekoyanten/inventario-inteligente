"""Entradas y salidas, historial de movimientos y kárdex por producto."""

from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import redirect, render

from apps.catalogo.models import Producto
from apps.core.negocio import del_negocio, negocio_requerido, obtener_del_negocio
from apps.reportes.exportadores import a_csv
from apps.usuarios.permisos import requiere_permiso

from .forms import FiltroMovimientosForm, MovimientoForm
from .models import Movimiento
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
        return a_csv(f"kardex-{producto.sku}", ["Fecha", "Tipo", "Cantidad", "Saldo", "Usuario", "Motivo"], filas)
    pagina = Paginator(qs.order_by("-fecha", "-id"), 50).get_page(request.GET.get("pagina"))
    return render(request, "inventario/kardex.html", {"producto": producto, "form": form, "pagina": pagina})
