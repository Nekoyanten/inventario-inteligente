"""Bares y discotecas: la noche (cuentas, puerta, reservas), configuración y análisis."""

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.catalogo.models import Producto
from apps.clientes.models import Cliente
from apps.core.auditoria import auditar
from apps.core.negocio import del_negocio, negocio_requerido, obtener_del_negocio
from apps.usuarios.permisos import requiere_permiso

from . import analisis
from . import services as s
from .fidelizacion import recordatorios
from .forms import ConfiguracionNocturnaForm, MesaForm, PrecioEspecialForm, ReservaForm
from .models import BotellaGuardada, Cuenta, Ingreso, Invitado, ItemCuenta, Mesa, PrecioEspecial, Reserva, noche_de


def _dec(valor, defecto="0"):
    try:
        return Decimal(str(valor or defecto).replace(",", "."))
    except InvalidOperation:
        return Decimal(defecto)


def _cliente(request):
    cid = request.POST.get("cliente_id") or request.POST.get("cliente")
    return obtener_del_negocio(request.negocio, Cliente, pk=cid) if cid else None


# ---------------------------------------------------------------- la noche
@negocio_requerido
@requiere_permiso("registrar_venta")
def noche(request):
    n = request.negocio
    conf = s.configuracion(n)
    hoy = noche_de(timezone.now(), n)
    abiertas = list(del_negocio(n, Cuenta).filter(estado=Cuenta.Estado.ABIERTA).select_related("mesa", "cliente"))
    for c in abiertas:
        c.r = s.resumen(c)
    especiales = [p for p in del_negocio(n, PrecioEspecial).filter(activa=True) if p.vigente_en(timezone.now())]
    return render(request, "nocturno/noche.html", {
        "conf": conf, "hoy": hoy, "cuentas": abiertas, "presentes": s.presentes(n, hoy),
        "mesas_libres": del_negocio(n, Mesa).filter(activa=True).exclude(cuentas__estado=Cuenta.Estado.ABIERTA),
        "reservas": del_negocio(n, Reserva).filter(fecha=hoy).exclude(estado=Reserva.Estado.CANCELADA),
        "especiales": especiales, "abierto_total": sum(c.r["total"] for c in abiertas),
        "recordatorios": recordatorios(n) if request.user.puede("gestionar_clientes") else [],
        "ingresos": del_negocio(n, Ingreso).filter(noche=hoy)[:10],
    })


@negocio_requerido
@requiere_permiso("registrar_venta")
@require_POST
def abrir(request):
    mesa = obtener_del_negocio(request.negocio, Mesa, pk=request.POST["mesa"]) if request.POST.get("mesa") else None
    try:
        cuenta = s.abrir_cuenta(request.negocio, request.user, mesa=mesa, nombre=request.POST.get("nombre", ""),
                                cliente=_cliente(request), personas=int(request.POST.get("personas") or 1))
    except (s.ErrorNocturno, ValueError) as e:
        messages.error(request, str(e))
        return redirect("nocturno:noche")
    return redirect("nocturno:cuenta", pk=cuenta.pk)


@negocio_requerido
@requiere_permiso("registrar_venta")
def cuenta(request, pk):
    c = obtener_del_negocio(request.negocio, Cuenta.objects.select_related("mesa", "cliente", "reserva"), pk=pk)
    try:
        r = s.resumen(c, puntos=int(request.GET.get("puntos") or 0))
    except Exception as e:  # puntos inválidos: se muestra sin canje
        messages.error(request, str(e))
        r = s.resumen(c)
    return render(request, "nocturno/cuenta.html", {
        "c": c, "r": r, "cobrados": c.items.filter(venta__isnull=False).select_related("producto", "venta"),
        "conf": s.configuracion(request.negocio),
        "guardadas": c.cliente.botellas_guardadas.filter(estado=BotellaGuardada.Estado.GUARDADA) if c.cliente else [],
    })


@negocio_requerido
@requiere_permiso("registrar_venta")
@require_POST
def pedir(request, pk):
    c = obtener_del_negocio(request.negocio, Cuenta, pk=pk)
    producto = obtener_del_negocio(request.negocio, Producto, pk=request.POST.get("producto") or 0)
    cortesia = bool(request.POST.get("cortesia")) and request.user.puede("configurar_negocio")
    try:
        s.agregar_item(c, producto, _dec(request.POST.get("cantidad"), "1"), request.user, cortesia=cortesia,
                       nota=request.POST.get("nota", ""))
    except s.ErrorNocturno as e:
        messages.error(request, str(e))
    return redirect("nocturno:cuenta", pk=pk)


@negocio_requerido
@requiere_permiso("registrar_venta")
@require_POST
def quitar(request, pk, item_id):
    c = obtener_del_negocio(request.negocio, Cuenta, pk=pk)
    item = obtener_del_negocio(request.negocio, ItemCuenta.objects.filter(cuenta=c), pk=item_id)
    try:
        s.quitar_item(item, request.user, request.POST.get("motivo", ""))
    except s.ErrorNocturno as e:
        messages.error(request, str(e))
    return redirect("nocturno:cuenta", pk=pk)


@negocio_requerido
@requiere_permiso("registrar_venta")
@require_POST
def asignar_cliente(request, pk):
    c = obtener_del_negocio(request.negocio, Cuenta, pk=pk)
    s._validar_abierta(c)
    c.cliente = _cliente(request)
    if request.POST.get("personas"):
        c.personas = max(1, int(request.POST["personas"]))
    c.save(update_fields=["cliente", "personas", "actualizado"])
    return redirect("nocturno:cuenta", pk=pk)


@negocio_requerido
@requiere_permiso("registrar_venta")
@require_POST
def cobrar(request, pk):
    from apps.clientes.services import ErrorClientes
    from apps.inventario.services import ErrorInventario

    c = obtener_del_negocio(request.negocio, Cuenta, pk=pk)
    ids = [int(x) for x in request.POST.getlist("items") if x.isdigit()]
    try:
        venta = s.cobrar(c, request.user, items_ids=ids or None, medio_pago=request.POST.get("medio_pago", "EFECTIVO"),
                         propina=_dec(request.POST.get("propina")), puntos=int(request.POST.get("puntos") or 0))
    except (s.ErrorNocturno, ErrorClientes, ErrorInventario, ValueError) as e:
        messages.error(request, str(e))
        return redirect("nocturno:cuenta", pk=pk)
    c.refresh_from_db()
    if c.estado == Cuenta.Estado.ABIERTA:
        messages.success(request, f"Se cobró una parte (venta #{venta.pk}). La cuenta sigue abierta.")
        return redirect("nocturno:cuenta", pk=pk)
    return redirect("ventas:detalle", pk=venta.pk)


@negocio_requerido
@requiere_permiso("configurar_negocio")
@require_POST
def anular(request, pk):
    c = obtener_del_negocio(request.negocio, Cuenta, pk=pk)
    try:
        s.anular_cuenta(c, request.user, request.POST.get("motivo", ""))
    except s.ErrorNocturno as e:
        messages.error(request, str(e))
        return redirect("nocturno:cuenta", pk=pk)
    return redirect("nocturno:noche")


# ---------------------------------------------------------------- puerta
@negocio_requerido
@requiere_permiso("registrar_venta")
@require_POST
def entrada(request):
    reserva = obtener_del_negocio(request.negocio, Reserva, pk=request.POST["reserva"]) \
        if request.POST.get("reserva") else None
    try:
        ing = s.registrar_ingreso(request.negocio, request.user, personas=int(request.POST.get("personas") or 1),
                                  cliente=_cliente(request), reserva=reserva,
                                  medio_pago=request.POST.get("medio_pago", "EFECTIVO"))
    except (s.ErrorNocturno, ValueError) as e:
        messages.error(request, str(e))
        return redirect("nocturno:noche")
    if ing.motivo_gratis:
        messages.success(request, f"Entrada gratis: {ing.motivo_gratis}.")
    elif ing.total:
        messages.success(request, f"Cover cobrado: ${ing.total:,.0f}".replace(",", ".") +
                         (" (queda como saldo para consumir)." if ing.consumible else "."))
    else:
        messages.success(request, "Entrada registrada.")
    if ing.cuenta_id:
        return redirect("nocturno:cuenta", pk=ing.cuenta_id)
    return redirect("nocturno:noche")


# ---------------------------------------------------------------- reservas
@negocio_requerido
@requiere_permiso("registrar_venta")
def reservas(request):
    n = request.negocio
    hoy = noche_de(timezone.now(), n)
    s.reservas_vencidas(n, hoy)
    form = ReservaForm(request.POST or None, negocio=n, initial={"fecha": hoy})
    if request.method == "POST" and form.is_valid():
        r = form.save(commit=False)
        r.creada_por = request.user
        if r.es_grupo and r.tipo == Reserva.Tipo.MESA:
            r.tipo = Reserva.Tipo.GRUPO
        r.save()
        auditar(n, request.user, "crear_reserva", r, personas=r.personas)
        messages.success(request, "Reserva creada." + (" Es un grupo: tendrá el beneficio de grupos." if r.es_grupo
                                                      else ""))
        return redirect("nocturno:reserva", pk=r.pk)
    return render(request, "nocturno/reservas.html", {
        "form": form, "proximas": del_negocio(n, Reserva).filter(fecha__gte=hoy).select_related("mesa"),
        "conf": s.configuracion(n)})


@negocio_requerido
@requiere_permiso("registrar_venta")
def reserva(request, pk):
    r = obtener_del_negocio(request.negocio, Reserva.objects.select_related("cliente", "mesa"), pk=pk)
    if request.method == "POST":
        accion = request.POST.get("accion")
        try:
            if accion == "llego":
                mesa = obtener_del_negocio(request.negocio, Mesa, pk=request.POST["mesa"]) \
                    if request.POST.get("mesa") else None
                c = s.marcar_llegada(r, request.user, mesa=mesa)
                return redirect("nocturno:cuenta", pk=c.pk)
            if accion == "invitado":
                Invitado.objects.create(reserva=r, nombre=request.POST.get("nombre", "")[:120] or "Invitado",
                                        telefono=request.POST.get("telefono", "")[:20])
            elif accion == "llego_invitado":
                inv = obtener_del_negocio(request.negocio, Invitado.objects.filter(reserva=r), pk=request.POST["invitado"])
                s.llegada_invitado(inv, request.user, registrar_cliente=bool(request.POST.get("registrar")),
                                   acepta_ofertas=bool(request.POST.get("ofertas")),
                                   mayor_edad=bool(request.POST.get("mayor_edad")))
            elif accion in ("CONFIRMADA", "CANCELADA", "NO_LLEGO"):
                r.estado = accion
                r.save(update_fields=["estado", "actualizado"])
        except s.ErrorNocturno as e:
            messages.error(request, str(e))
        return redirect("nocturno:reserva", pk=pk)
    return render(request, "nocturno/reserva.html", {
        "r": r, "invitados": r.invitados.all(), "conf": s.configuracion(request.negocio),
        "mesas": del_negocio(request.negocio, Mesa).filter(activa=True), "cuentas": r.cuentas.all()})


# ---------------------------------------------------------------- botellas
@negocio_requerido
@requiere_permiso("registrar_venta")
def botellas(request):
    s.vencer_botellas(request.negocio)
    return render(request, "nocturno/botellas.html", {
        "botellas": del_negocio(request.negocio, BotellaGuardada).select_related("cliente", "producto").order_by(
            "estado", "vence")[:200]})


@negocio_requerido
@requiere_permiso("registrar_venta")
@require_POST
def guardar_botella(request, pk):
    c = obtener_del_negocio(request.negocio, Cuenta, pk=pk)
    producto = obtener_del_negocio(request.negocio, Producto, pk=request.POST.get("producto") or 0)
    if not c.cliente:
        messages.error(request, "Para guardar la botella, asigna el cliente a la cuenta.")
    else:
        try:
            s.guardar_botella(c.cliente, producto, int(request.POST.get("restante") or 0), request.user,
                              request.POST.get("ubicacion", ""))
            messages.success(request, f"Botella guardada a nombre de {c.cliente}.")
        except (s.ErrorNocturno, ValueError) as e:
            messages.error(request, str(e))
    return redirect("nocturno:cuenta", pk=pk)


@negocio_requerido
@requiere_permiso("registrar_venta")
@require_POST
def retirar_botella(request, pk):
    b = obtener_del_negocio(request.negocio, BotellaGuardada, pk=pk)
    try:
        s.retirar_botella(b, request.user)
        messages.success(request, f"{b.producto} entregada a {b.cliente}.")
    except s.ErrorNocturno as e:
        messages.error(request, str(e))
    return redirect(request.POST.get("volver") if request.POST.get("volver", "").startswith("/noche/")
                    else "nocturno:botellas")


@negocio_requerido
@requiere_permiso("gestionar_productos")
@require_POST
def crear_trago(request, pk):
    botella = obtener_del_negocio(request.negocio, Producto, pk=pk)
    try:
        trago = s.crear_trago(botella, ml_botella=int(request.POST.get("ml_botella") or 0),
                              ml_trago=int(request.POST.get("ml_trago") or 0), precio=_dec(request.POST.get("precio")),
                              usuario=request.user)
    except (s.ErrorNocturno, ValueError) as e:
        messages.error(request, str(e))
        return redirect("catalogo:detalle", pk=pk)
    messages.success(request, f"Listo: «{trago.nombre}» descuenta {trago.receta.first().cantidad} de botella por trago.")
    return redirect("catalogo:detalle", pk=trago.pk)


# ---------------------------------------------------------------- configuración
@negocio_requerido
@requiere_permiso("configurar_negocio")
def ajustes(request):
    n = request.negocio
    form = ConfiguracionNocturnaForm(request.POST or None, instance=s.configuracion(n), prefix="c")
    mesa_form = MesaForm(prefix="m")
    if request.method == "POST":
        if request.POST.get("tipo") == "mesa":
            mesa_form = MesaForm(request.POST, prefix="m")
            if mesa_form.is_valid():
                m = mesa_form.save(commit=False)
                m.negocio = n
                if Mesa.objects.filter(negocio=n, nombre=m.nombre).exists():
                    messages.error(request, "Ya hay una mesa con ese nombre.")
                else:
                    m.save()
                    messages.success(request, f"Mesa {m} creada.")
                    return redirect("nocturno:ajustes")
        elif form.is_valid():
            form.save()
            auditar(n, request.user, "configurar_noche", n, cambios=form.changed_data)
            messages.success(request, "Configuración guardada.")
            return redirect("nocturno:ajustes")
    return render(request, "nocturno/ajustes.html", {"form": form, "mesa_form": mesa_form,
                                                     "mesas": del_negocio(n, Mesa)})


@negocio_requerido
@requiere_permiso("configurar_negocio")
def precios(request, pk=None):
    n = request.negocio
    obj = obtener_del_negocio(n, PrecioEspecial, pk=pk) if pk else None
    inicial = {}
    if not obj and request.GET.get("dia", "").isdigit():
        inicial = {"nombre": "Happy hour", "tipo": "DOS_POR_UNO", "dias": [int(request.GET["dia"])],
                   "hora_inicio": "19:00", "hora_fin": "21:00"}
    form = PrecioEspecialForm(request.POST or None, instance=obj, negocio=n, initial=inicial)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Precio especial guardado.")
        return redirect("nocturno:precios")
    return render(request, "nocturno/precios.html", {"form": form, "obj": obj,
                                                     "reglas": del_negocio(n, PrecioEspecial).select_related(
                                                         "producto", "categoria")})


@negocio_requerido
@requiere_permiso("ver_reportes")
def analisis_view(request):
    n = request.negocio
    return render(request, "nocturno/analisis.html", {
        "dias": analisis.por_dia_semana(n), "horas": analisis.por_hora(n), "pc": analisis.pour_cost(n),
        "botellas": analisis.rendimiento_botellas(n)[:15], "reservas": analisis.reservas(n),
        "promotores": analisis.promotores(n), "puerta": analisis.puerta(n), "fid": analisis.fidelizacion(n),
        "sugerencias": analisis.sugerencias(n),
    })
