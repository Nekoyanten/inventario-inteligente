"""Bares y discotecas: la noche (cuentas, puerta, reservas), configuración y análisis."""

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.catalogo.models import Producto
from apps.clientes.models import Cliente
from apps.core.auditoria import auditar
from apps.core.negocio import del_negocio, negocio_requerido, obtener_del_negocio
from apps.usuarios.permisos import requiere_alguno, requiere_permiso

from . import analisis
from . import services as s
from .fidelizacion import recordatorios
from .forms import ConfiguracionNocturnaForm, MesaForm, PrecioEspecialForm, ReservaForm
from .models import (
    AsignacionMesa,
    BotellaGuardada,
    Cuenta,
    EntregaMesero,
    Ingreso,
    Invitado,
    ItemCuenta,
    Mesa,
    PrecioEspecial,
    Reserva,
    noche_de,
)


def _dec(valor, defecto="0"):
    try:
        return Decimal(str(valor or defecto).replace(",", "."))
    except InvalidOperation:
        return Decimal(defecto)


def _cuenta_propia(request, pk, qs=Cuenta.objects):
    """La cuenta, si quien la pide puede atenderla (el mesero solo ve las de sus mesas)."""
    c = obtener_del_negocio(request.negocio, qs, pk=pk)
    if not s.puede_atender(request.user, c):
        raise PermissionDenied
    return c


def _volver(request):
    return "nocturno:noche" if request.user.puede("cobrar_cuentas") else "nocturno:mis_mesas"


def _fidelizacion(request) -> bool:
    from apps.core.modulos import activo

    config = getattr(request.negocio, "config", None)
    return bool(config and config.fidelizacion_activa) and activo(request.negocio, "clientes")


def _cliente(request):
    cid = request.POST.get("cliente_id") or request.POST.get("cliente")
    return obtener_del_negocio(request.negocio, Cliente, pk=cid) if cid else None


# ---------------------------------------------------------------- la noche
@negocio_requerido
@requiere_permiso("cobrar_cuentas")
def noche(request):
    n = request.negocio
    conf = s.configuracion(n)
    hoy = noche_de(timezone.now(), n)
    abiertas = list(del_negocio(n, Cuenta).filter(estado=Cuenta.Estado.ABIERTA).select_related("mesa", "cliente",
                                                                                               "mesero"))
    for c in abiertas:
        c.r = s.resumen(c)
    abiertas.sort(key=lambda c: (c.pide_cuenta is None, c.pide_cuenta or c.creado))  # primero las que piden pagar
    especiales = [p for p in del_negocio(n, PrecioEspecial).filter(activa=True) if p.vigente_en(timezone.now())]
    return render(request, "nocturno/noche.html", {
        "conf": conf, "hoy": hoy, "cuentas": abiertas, "presentes": s.presentes(n, hoy),
        "mesas_libres": del_negocio(n, Mesa).filter(activa=True).exclude(cuentas__estado=Cuenta.Estado.ABIERTA),
        "reservas": del_negocio(n, Reserva).filter(fecha=hoy).exclude(estado=Reserva.Estado.CANCELADA),
        "especiales": especiales, "abierto_total": sum(c.r["total"] for c in abiertas),
        "recordatorios": recordatorios(n) if request.user.puede("gestionar_clientes") else [],
        "ingresos": del_negocio(n, Ingreso).filter(noche=hoy)[:10],
        "por_cobrar": sum(1 for c in abiertas if c.pide_cuenta),
        "entregas": del_negocio(n, EntregaMesero).filter(recibida__isnull=True).select_related("mesero", "cuenta",
                                                                                             "cuenta__mesa"),
        "sin_asignar": del_negocio(n, Mesa).filter(activa=True).exists()
        and not del_negocio(n, AsignacionMesa).filter(noche=hoy).exists(),
    })


# ---------------------------------------------------------------- mesas y meseros
def _meseros(negocio):
    from apps.usuarios.models import Usuario

    return [u for u in Usuario.objects.filter(negocio=negocio, is_active=True).order_by("first_name", "username")
            if u.puede("atender_mesas") and not u.puede("cobrar_cuentas")]


@negocio_requerido
@requiere_permiso("asignar_mesas")
def mesas(request):
    """Mapa de mesas de esta noche: quién atiende cada una y cómo va."""
    n = request.negocio
    hoy = noche_de(timezone.now(), n)
    meseros = _meseros(n)
    todas = s.orden_natural(del_negocio(n, Mesa).filter(activa=True))
    if request.method == "POST":
        accion = request.POST.get("accion")
        try:
            if accion == "copiar":
                total = s.copiar_asignacion(n, hoy, request.user)
                messages.success(request, f"Listo: se repitió la asignación de la noche anterior ({total} mesas).")
            elif accion == "repartir":
                total = s.repartir_mesas(n, hoy, meseros, request.user)
                messages.success(request, f"Listo: {total} mesas repartidas entre {len(meseros)} meseros.")
            else:
                por_id = {str(u.pk): u for u in meseros}
                s.asignar_mesas(n, hoy, {m.pk: por_id.get(request.POST.get(f"mesa-{m.pk}", "")) for m in todas},
                                request.user)
                messages.success(request, "Asignación guardada. Cada mesero ya ve sus mesas.")
        except s.ErrorNocturno as e:
            messages.error(request, str(e))
        return redirect("nocturno:mesas")
    asignadas = {a.mesa_id: a.mesero for a in del_negocio(n, AsignacionMesa).filter(noche=hoy).select_related("mesero")}
    abiertas = {c.mesa_id: c for c in del_negocio(n, Cuenta).filter(estado=Cuenta.Estado.ABIERTA, mesa__isnull=False)}
    zonas = {}
    for m in todas:
        m.mesero = asignadas.get(m.pk)
        m.cuenta = abiertas.get(m.pk)
        if m.cuenta:
            m.cuenta.r = s.resumen(m.cuenta)
        zonas.setdefault(m.get_zona_display(), []).append(m)
    carga = {u.pk: sum(1 for m in todas if m.mesero and m.mesero.pk == u.pk) for u in meseros}
    for u in meseros:
        u.num_mesas = carga[u.pk]
    return render(request, "nocturno/mesas.html", {"hoy": hoy, "zonas": zonas, "meseros": meseros,
                                                   "hay_mesas": bool(todas), "asignadas": len(asignadas)})


@negocio_requerido
@requiere_permiso("atender_mesas")
def mis_mesas(request):
    """Tablero del mesero: todas las mesas. Toca una libre y queda a su cargo; las de otros se ven ocupadas."""
    n = request.negocio
    hoy = noche_de(timezone.now(), n)
    todas = s.orden_natural(del_negocio(n, Mesa).filter(activa=True))
    abiertas = {c.mesa_id: c for c in del_negocio(n, Cuenta).filter(estado=Cuenta.Estado.ABIERTA, mesa__isnull=False)
                .select_related("mesero")}
    asignadas = {a.mesa_id: a.mesero for a in del_negocio(n, AsignacionMesa).filter(noche=hoy).select_related("mesero")}
    yo = request.user
    zonas, mias = {}, 0
    for m in todas:
        m.cuenta, m.asignado = abiertas.get(m.pk), asignadas.get(m.pk)
        if m.cuenta:
            m.cuenta.r = s.resumen(m.cuenta)
            m.mia = s.puede_atender(yo, m.cuenta)
            m.estado = "pide" if m.cuenta.pide_cuenta else ("mia" if m.mia else "otro")
            mias += m.mia
        else:
            m.mia = False
            m.estado = "reservada" if m.asignado and m.asignado.pk != yo.pk else "libre"
        zonas.setdefault(m.get_zona_display(), []).append(m)
    barra = del_negocio(n, Cuenta).filter(estado=Cuenta.Estado.ABIERTA, mesa__isnull=True, mesero=yo)
    return render(request, "nocturno/mis_mesas.html", {"hoy": hoy, "zonas": zonas, "barra": barra, "mias": mias,
                                                       "hay_mesas": bool(todas)})


@negocio_requerido
@requiere_permiso("atender_mesas")
@require_POST
def tomar(request, mesa_id):
    mesa = obtener_del_negocio(request.negocio, Mesa, pk=mesa_id)
    try:
        cuenta = s.tomar_mesa(request.negocio, request.user, mesa, personas=int(request.POST.get("personas") or 2))
    except (s.ErrorNocturno, ValueError) as e:
        messages.error(request, str(e))
        return redirect("nocturno:mis_mesas")
    return redirect("nocturno:cuenta", pk=cuenta.pk)


@negocio_requerido
@requiere_alguno("cobrar_cuentas", "atender_mesas")
@require_POST
def liberar(request, pk):
    c = _cuenta_propia(request, pk)
    try:
        s.liberar_mesa(c, request.user)
        messages.success(request, f"{c} quedó libre.")
    except s.ErrorNocturno as e:
        messages.error(request, str(e))
        return redirect("nocturno:cuenta", pk=pk)
    return redirect(_volver(request))


@negocio_requerido
@requiere_permiso("cobrar_cuentas")
@require_POST
def recibir_entrega(request, pk):
    e = obtener_del_negocio(request.negocio, EntregaMesero.objects.select_related("mesero", "cuenta"), pk=pk)
    s.recibir_entrega(e, request.user)
    messages.success(request, f"Recibido: {_pesos(e.valor)} de {e.mesero.get_full_name() or e.mesero.username}.")
    return redirect("nocturno:noche")


def _pesos(valor) -> str:
    return "$" + f"{valor:,.0f}".replace(",", ".")


@negocio_requerido
@requiere_alguno("cobrar_cuentas", "atender_mesas")
@require_POST
def pedir_cuenta(request, pk):
    c = _cuenta_propia(request, pk)
    try:
        s.pedir_la_cuenta(c, request.user)
        messages.success(request, f"Listo: la caja ya sabe que {c} quiere pagar.")
    except s.ErrorNocturno as e:
        messages.error(request, str(e))
        return redirect("nocturno:cuenta", pk=pk)
    return redirect(_volver(request))


@negocio_requerido
@requiere_alguno("cobrar_cuentas", "atender_mesas")
@require_POST
def abrir(request):
    mesa = obtener_del_negocio(request.negocio, Mesa, pk=request.POST["mesa"]) if request.POST.get("mesa") else None
    if not request.user.puede("cobrar_cuentas"):  # mesero: solo sus mesas
        hoy = noche_de(timezone.now(), request.negocio)
        if mesa is None or not s.mesas_de(request.negocio, request.user, hoy).filter(pk=mesa.pk).exists():
            messages.error(request, "Esa mesa no está asignada a ti esta noche.")
            return redirect("nocturno:mis_mesas")
    try:
        cuenta = s.abrir_cuenta(request.negocio, request.user, mesa=mesa, nombre=request.POST.get("nombre", ""),
                                cliente=_cliente(request), personas=int(request.POST.get("personas") or 1))
    except (s.ErrorNocturno, ValueError) as e:
        messages.error(request, str(e))
        return redirect(_volver(request))
    return redirect("nocturno:cuenta", pk=cuenta.pk)


@negocio_requerido
@requiere_alguno("cobrar_cuentas", "atender_mesas")
def cuenta(request, pk):
    c = _cuenta_propia(request, pk, Cuenta.objects.select_related("mesa", "cliente", "reserva", "mesero"))
    try:
        r = s.resumen(c, puntos=int(request.GET.get("puntos") or 0))
    except Exception as e:  # puntos inválidos: se muestra sin canje
        messages.error(request, str(e))
        r = s.resumen(c)
    return render(request, "nocturno/cuenta.html", {
        "c": c, "r": r, "cobra": True, "es_caja": request.user.puede("cobrar_cuentas"), "volver": _volver(request),
        "fidelizacion": _fidelizacion(request),
        "cobrados": c.items.filter(venta__isnull=False).select_related("producto", "venta"),
        "conf": s.configuracion(request.negocio),
        "guardadas": c.cliente.botellas_guardadas.filter(estado=BotellaGuardada.Estado.GUARDADA) if c.cliente else [],
        "rapidos": _mas_pedidos(request.negocio) if c.estado == Cuenta.Estado.ABIERTA else [],
    })


def _mas_pedidos(negocio, limite=8):
    """Botones de un toque para lo que más se pide (últimos 30 días): el mesero no tiene que escribir."""
    from datetime import timedelta

    from django.db.models import Sum

    desde = timezone.now() - timedelta(days=30)
    ids = list(ItemCuenta.objects.filter(cuenta__negocio=negocio, agregado__gte=desde, cortesia=False)
               .values("producto").annotate(n=Sum("cantidad")).order_by("-n").values_list("producto", flat=True)[:limite])
    por_id = {p.pk: p for p in Producto.objects.filter(pk__in=ids, activo=True)}
    return [por_id[i] for i in ids if i in por_id]


@negocio_requerido
@requiere_alguno("cobrar_cuentas", "atender_mesas")
@require_POST
def pedir(request, pk):
    c = _cuenta_propia(request, pk)
    if not str(request.POST.get("producto", "")).isdigit():
        messages.error(request, "Elige el producto de la lista (escribe y toca el que quieres).")
        return redirect("nocturno:cuenta", pk=pk)
    producto = obtener_del_negocio(request.negocio, Producto, pk=request.POST["producto"])
    cortesia = bool(request.POST.get("cortesia")) and request.user.puede("configurar_negocio")
    try:
        s.agregar_item(c, producto, _dec(request.POST.get("cantidad"), "1"), request.user, cortesia=cortesia,
                       nota=request.POST.get("nota", ""))
    except s.ErrorNocturno as e:
        messages.error(request, str(e))
    return redirect("nocturno:cuenta", pk=pk)


@negocio_requerido
@requiere_alguno("cobrar_cuentas", "atender_mesas")
@require_POST
def quitar(request, pk, item_id):
    c = _cuenta_propia(request, pk)
    item = obtener_del_negocio(request.negocio, ItemCuenta.objects.filter(cuenta=c), pk=item_id)
    if not request.user.puede("cobrar_cuentas") and item.agregado_por_id != request.user.pk:
        messages.error(request, "Solo puedes quitar lo que tú agregaste. Pídeselo al cajero.")
        return redirect("nocturno:cuenta", pk=pk)
    try:
        s.quitar_item(item, request.user, request.POST.get("motivo", ""))
    except s.ErrorNocturno as e:
        messages.error(request, str(e))
    return redirect("nocturno:cuenta", pk=pk)


@negocio_requerido
@requiere_alguno("cobrar_cuentas", "atender_mesas")
@require_POST
def asignar_cliente(request, pk):
    c = _cuenta_propia(request, pk)
    s._validar_abierta(c)
    c.cliente = _cliente(request)
    if request.POST.get("personas"):
        c.personas = max(1, int(request.POST["personas"]))
    c.save(update_fields=["cliente", "personas", "actualizado"])
    return redirect("nocturno:cuenta", pk=pk)


@negocio_requerido
@requiere_alguno("cobrar_cuentas", "atender_mesas")
@require_POST
def cobrar(request, pk):
    from apps.clientes.services import ErrorClientes
    from apps.inventario.services import ErrorInventario

    c = _cuenta_propia(request, pk)
    ids = [int(x) for x in request.POST.getlist("items") if x.isdigit()]
    try:
        venta = s.cobrar(c, request.user, items_ids=ids or None, medio_pago=request.POST.get("medio_pago", "EFECTIVO"),
                         propina=_dec(request.POST.get("propina")), puntos=int(request.POST.get("puntos") or 0))
    except (s.ErrorNocturno, ErrorClientes, ErrorInventario, ValueError) as e:
        messages.error(request, str(e))
        return redirect("nocturno:cuenta", pk=pk)
    c.refresh_from_db()
    paga_con = _dec(request.POST.get("paga_con"))
    cobrado = venta.total - venta.pagado_con_credito + venta.propina
    vueltas = max(Decimal("0"), paga_con - cobrado) if paga_con else Decimal("0")
    texto = f"Cobrado {_pesos(cobrado)}" + (f" · vueltas {_pesos(vueltas)}" if vueltas else "")
    if not request.user.puede("cobrar_cuentas"):  # mesero: la caja queda esperando la plata
        if s.registrar_entrega(c, venta, request.user, paga_con):
            texto += f". Entrega {_pesos(cobrado)} en la caja"
    if c.estado == Cuenta.Estado.ABIERTA:
        messages.success(request, f"{texto}. La cuenta sigue abierta con lo que falta.")
        return redirect("nocturno:cuenta", pk=pk)
    messages.success(request, f"{texto}. {c} quedó libre.")
    if not request.user.puede("cobrar_cuentas"):
        return redirect("nocturno:mis_mesas")
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
@requiere_permiso("cobrar_cuentas")
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
@requiere_permiso("cobrar_cuentas")
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
@requiere_permiso("cobrar_cuentas")
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
@requiere_permiso("cobrar_cuentas")
def botellas(request):
    s.vencer_botellas(request.negocio)
    return render(request, "nocturno/botellas.html", {
        "botellas": del_negocio(request.negocio, BotellaGuardada).select_related("cliente", "producto").order_by(
            "estado", "vence")[:200]})


@negocio_requerido
@requiere_permiso("cobrar_cuentas")
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
@requiere_permiso("cobrar_cuentas")
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
