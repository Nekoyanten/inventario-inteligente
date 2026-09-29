"""Clientes habituales: panel de análisis, fichas, puntos, ofertas por WhatsApp y encuesta pública."""

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.auditoria import auditar
from apps.core.negocio import del_negocio, negocio_requerido, obtener_del_negocio
from apps.usuarios.permisos import requiere_permiso

from . import analisis
from .forms import ClienteForm, ConfiguracionFidelizacionForm, OfertaForm
from .models import Cliente, Encuesta, Nivel, Oferta
from .services import (
    ErrorClientes,
    ajustar_puntos,
    destinatarios,
    eliminar_cliente,
    mensaje_oferta,
    normalizar_telefono,
    registrar_envio,
    url_whatsapp,
)
from .sugerencias import crear_desde_sugerencia, sugerir


# ---------------------------------------------------------------- panel
@negocio_requerido
@requiere_permiso("gestionar_clientes")
def panel(request):
    return render(request, "clientes/panel.html", {
        "r": analisis.resumen(request.negocio),
        "sugerencias": sugerir(request.negocio),
        "ofertas": del_negocio(request.negocio, Oferta).filter(hasta__gte=timezone.localdate(), activa=True)[:5],
    })


@negocio_requerido
@requiere_permiso("gestionar_clientes")
def lista(request):
    segmento = request.GET.get("segmento", "")
    if segmento in analisis.SEGMENTOS:
        ids = [c.pk for c in analisis.clientes_por_segmento(request.negocio, (segmento,))]
        qs = del_negocio(request.negocio, Cliente).filter(pk__in=ids)
    else:
        qs = del_negocio(request.negocio, Cliente)
    if request.GET.get("nivel") in Nivel.values:
        qs = qs.filter(nivel=request.GET["nivel"])
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(nombre__icontains=q) | Q(telefono__contains=normalizar_telefono(q) or q) | Q(documento=q))
    orden = {"puntos": "-puntos", "compras": "-total_compras", "reciente": "-ultima_compra"}.get(
        request.GET.get("orden"), "nombre")
    return render(request, "clientes/lista.html", {
        "pagina": Paginator(qs.order_by(orden, "pk"), 40).get_page(request.GET.get("pagina")),
        "segmentos": analisis.SEGMENTOS, "niveles": Nivel.choices, "segmento": segmento,
    })


@negocio_requerido
@requiere_permiso("registrar_cliente")
def formulario(request, pk=None):
    cliente = obtener_del_negocio(request.negocio, Cliente, pk=pk) if pk else None
    if cliente and not request.user.puede("gestionar_clientes"):
        raise Http404
    form = ClienteForm(request.POST or None, instance=cliente, negocio=request.negocio)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        auditar(request.negocio, request.user, "editar_cliente" if pk else "crear_cliente", obj)
        messages.success(request, f"Cliente {obj.nombre} guardado.")
        return redirect("clientes:detalle", pk=obj.pk) if request.user.puede("gestionar_clientes") else redirect(
            "ventas:pos")
    return render(request, "clientes/formulario.html", {"form": form, "cliente": cliente})


@negocio_requerido
@requiere_permiso("gestionar_clientes")
def detalle(request, pk):
    from apps.ventas.models import Venta

    cliente = obtener_del_negocio(request.negocio, Cliente, pk=pk)
    whatsapp = url_whatsapp(cliente.telefono, f"Hola {cliente.primer_nombre}, te saluda {request.negocio.nombre}.") \
        if cliente.telefono else None
    return render(request, "clientes/detalle.html", {
        "cliente": cliente, "segmento": analisis.SEGMENTOS[analisis.segmento_rfm(cliente)],
        "favoritos": analisis.productos_favoritos(cliente),
        "ventas": Venta.objects.filter(cliente_ref=cliente).order_by("-fecha")[:15],
        "puntos": cliente.movimientos_puntos.select_related("venta", "usuario")[:20],
        "encuestas": cliente.encuestas.filter(respondida__isnull=False)[:10],
        "ofertas": cliente.ofertas_recibidas.select_related("oferta").order_by("-fecha")[:10],
        "whatsapp": whatsapp,
    })


@negocio_requerido
@requiere_permiso("gestionar_clientes")
@require_POST
def ajustar(request, pk):
    cliente = obtener_del_negocio(request.negocio, Cliente, pk=pk)
    try:
        ajustar_puntos(cliente, int(request.POST.get("puntos") or 0), request.user, request.POST.get("motivo", ""))
    except (ErrorClientes, ValueError) as e:
        messages.error(request, str(e) if isinstance(e, ErrorClientes) else "Escribe un número de puntos.")
    else:
        messages.success(request, "Puntos ajustados.")
    return redirect("clientes:detalle", pk=pk)


@negocio_requerido
@requiere_permiso("gestionar_clientes")
@require_POST
def eliminar(request, pk):
    cliente = obtener_del_negocio(request.negocio, Cliente, pk=pk)
    nombre = cliente.nombre
    eliminar_cliente(cliente, request.user)
    messages.success(request, f"Se borraron los datos de {nombre}. Sus compras quedaron sin nombre en el historial.")
    return redirect("clientes:lista")


# ---------------------------------------------------------------- punto de venta (JSON)
def _json_cliente(c: Cliente) -> dict:
    return {"id": c.pk, "nombre": c.nombre, "telefono": c.telefono, "puntos": c.puntos, "nivel": c.get_nivel_display(),
            "compras": c.n_compras}


@negocio_requerido
@requiere_permiso("registrar_cliente")
def buscar_json(request):
    q = (request.GET.get("q") or "").strip()
    if len(q) < 2:
        return JsonResponse({"resultados": []})
    tel = normalizar_telefono(q)
    filtro = Q(nombre__icontains=q) | Q(documento=q)
    if len(tel) >= 3:
        filtro |= Q(telefono__contains=tel)
    qs = del_negocio(request.negocio, Cliente).filter(activo=True).filter(filtro).order_by("-ultima_compra", "nombre")
    return JsonResponse({"resultados": [_json_cliente(c) for c in qs[:10]]})


@negocio_requerido
@requiere_permiso("registrar_cliente")
@require_POST
def crear_json(request):
    form = ClienteForm(request.POST, negocio=request.negocio)
    if not form.is_valid():
        errores = "; ".join(f"{form.fields[k].label if k in form.fields else ''}: {' '.join(v)}".strip(": ")
                            for k, v in form.errors.items())
        return JsonResponse({"error": errores}, status=400)
    cliente = form.save()
    auditar(request.negocio, request.user, "crear_cliente", cliente)
    return JsonResponse({"cliente": _json_cliente(cliente)})


# ---------------------------------------------------------------- ofertas
@negocio_requerido
@requiere_permiso("gestionar_clientes")
def ofertas(request):
    hoy = timezone.localdate()
    qs = del_negocio(request.negocio, Oferta).select_related("producto", "categoria")
    filas = [(o, analisis.efectividad(o)) for o in qs[:50]]
    return render(request, "clientes/ofertas.html", {"filas": filas, "hoy": hoy, "sugerencias": sugerir(request.negocio)})


@negocio_requerido
@requiere_permiso("gestionar_clientes")
def oferta_formulario(request, pk=None):
    oferta = obtener_del_negocio(request.negocio, Oferta, pk=pk) if pk else None
    form = OfertaForm(request.POST or None, instance=oferta, negocio=request.negocio)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        if not pk:
            obj.creada_por = request.user
        obj.save()
        auditar(request.negocio, request.user, "editar_oferta" if pk else "crear_oferta", obj)
        messages.success(request, "Oferta guardada.")
        return redirect("clientes:oferta", pk=obj.pk)
    return render(request, "clientes/oferta_formulario.html", {"form": form, "oferta": oferta})


@negocio_requerido
@requiere_permiso("gestionar_clientes")
def oferta(request, pk):
    oferta = obtener_del_negocio(request.negocio, Oferta.objects.select_related("producto", "categoria"), pk=pk)
    enviados = set(oferta.envios.values_list("cliente_id", flat=True))
    lista_dest = list(destinatarios(oferta)[:300])
    return render(request, "clientes/oferta.html", {
        "oferta": oferta, "efectividad": analisis.efectividad(oferta),
        "destinatarios": [(c, c.pk in enviados) for c in lista_dest],
        "ejemplo": mensaje_oferta(oferta, lista_dest[0]) if lista_dest else None,
        "vigente": oferta.vigente(timezone.localdate()),
    })


@negocio_requerido
@requiere_permiso("gestionar_clientes")
@require_POST
def enviar(request, pk, cliente_id):
    """Anota el envío y abre WhatsApp con el mensaje personalizado (un toque por cliente)."""
    oferta = obtener_del_negocio(request.negocio, Oferta, pk=pk)
    cliente = obtener_del_negocio(request.negocio, Cliente, pk=cliente_id)
    try:
        url = registrar_envio(oferta, cliente, request.user)
    except ErrorClientes as e:
        messages.error(request, str(e))
        return redirect("clientes:oferta", pk=pk)
    return redirect(url)


@negocio_requerido
@requiere_permiso("gestionar_clientes")
@require_POST
def crear_sugerida(request):
    oferta = crear_desde_sugerencia(request.negocio, request.POST.get("clave", ""), request.user)
    if oferta is None:
        messages.error(request, "Esa sugerencia ya no está disponible.")
        return redirect("clientes:ofertas")
    auditar(request.negocio, request.user, "crear_oferta", oferta, origen="sugerida")
    messages.success(request, "Oferta creada. Revísala y envíala a tus clientes.")
    return redirect("clientes:oferta", pk=oferta.pk)


@negocio_requerido
@requiere_permiso("gestionar_clientes")
def configuracion(request):
    form = ConfiguracionFidelizacionForm(request.POST or None, instance=request.negocio.config)
    if request.method == "POST" and form.is_valid():
        form.save()
        auditar(request.negocio, request.user, "configurar_fidelizacion", request.negocio.config,
                cambios=form.changed_data)
        messages.success(request, "Programa de fidelización actualizado.")
        return redirect("clientes:panel")
    return render(request, "clientes/configuracion.html", {"form": form})


# ---------------------------------------------------------------- encuesta pública (sin iniciar sesión)
def encuesta(request, token):
    enc = get_object_or_404(Encuesta.objects.select_related("negocio", "venta"), token=token)
    gracias = enc.respondida is not None
    error = ""
    if request.method == "POST" and not gracias:
        try:
            calificacion = int(request.POST.get("calificacion", 0))
        except ValueError:
            calificacion = 0
        if 1 <= calificacion <= 5:
            enc.calificacion = calificacion
            enc.comentario = request.POST.get("comentario", "")[:1000]
            enc.respondida = timezone.now()
            enc.save(update_fields=["calificacion", "comentario", "respondida"])
            gracias = True
        else:
            error = "Elige de 1 a 5 estrellas."
    return render(request, "clientes/encuesta.html", {"enc": enc, "gracias": gracias, "error": error})
