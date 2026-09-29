"""Panel de la plataforma (solo superusuario): salud del sistema y métricas del piloto por negocio."""

from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Avg, Count, Max, Q
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.reportes.exportadores import a_csv

from .arranque import progreso_arranque
from .auditoria import auditar
from .middleware import SESION_SOPORTE
from .models import Comentario, EjecucionTarea, Negocio, Suscripcion
from .salud import configuracion, revisar

solo_superusuario = user_passes_test(lambda u: u.is_active and u.is_superuser)


def metricas_negocios(dias_piloto=21):
    from apps.ventas.models import Venta

    hoy = timezone.localdate()
    desde = hoy - timedelta(days=dias_piloto - 1)
    hace7 = timezone.now() - timedelta(days=7)
    filas = []
    negocios = Negocio.objects.select_related("suscripcion").annotate(
        n_productos=Count("productos", filter=Q(productos__es_agrupador=False), distinct=True),
        n_usuarios=Count("usuarios", filter=Q(usuarios__is_active=True), distinct=True),
        ultimo_ingreso=Max("usuarios__last_login"),
    ).order_by("-creado")
    for n in negocios:
        ventas = Venta.objects.filter(negocio=n, estado=Venta.Estado.COMPLETADA)
        dias_activos = (ventas.filter(fecha__date__gte=desde).annotate(dia=TruncDate("fecha"))
                        .values("dia").distinct().count())
        comentarios = Comentario.objects.filter(negocio=n)
        s = n.suscripcion
        filas.append({
            "negocio": n, "giro": n.get_giro_display(), "creado": n.creado,
            "plan": "Prueba" if s.en_prueba else s.limites["nombre"] + (" (vencido)" if s.vencido else ""),
            "dias_restantes": s.dias_restantes, "productos": n.n_productos, "usuarios": n.n_usuarios,
            "ultimo_ingreso": n.ultimo_ingreso, "ventas_7d": ventas.filter(fecha__gte=hace7).count(),
            "dias_activos": dias_activos, "dias_piloto": dias_piloto,
            "arranque": progreso_arranque(n)["porcentaje"],
            "comentarios_pendientes": comentarios.filter(atendido=False).count(),
            "calificacion": comentarios.aggregate(p=Avg("calificacion"))["p"],
        })
    return filas


@staff_member_required
@solo_superusuario
def panel(request):
    filas = metricas_negocios()
    if request.GET.get("formato") == "csv":
        enc = ["Negocio", "Tipo", "Plan", "Creado", "Productos", "Usuarios", "Último ingreso", "Ventas 7 días",
               "Días con ventas (21)", "Arranque %", "Comentarios pendientes", "Calificación"]
        return a_csv("piloto", enc, [[f["negocio"].nombre, f["giro"], f["plan"], f["creado"], f["productos"],
                                      f["usuarios"], f["ultimo_ingreso"], f["ventas_7d"], f["dias_activos"],
                                      f["arranque"], f["comentarios_pendientes"], f["calificacion"]] for f in filas])
    return render(request, "plataforma/panel.html", {
        "salud": revisar(completo=True), "config": configuracion(), "filas": filas,
        "tareas": EjecucionTarea.objects.all()[:10],
        "comentarios": Comentario.objects.filter(atendido=False).select_related("negocio", "usuario")[:20],
        "activos": sum(1 for f in filas if f["dias_activos"] >= 15),
        "admin_url": settings.ADMIN_URL,
        "planes": [(k, v["nombre"]) for k, v in settings.PLANES.items()],
    })


@require_POST
@staff_member_required
@solo_superusuario
def entrar(request, pk):
    """Entrar a un negocio como administrador de la plataforma (soporte): ve y hace todo lo que su administrador."""
    negocio = get_object_or_404(Negocio, pk=pk)
    request.session[SESION_SOPORTE] = negocio.pk
    auditar(negocio, request.user, "soporte_entrar", negocio)
    messages.info(request, f"Estás dentro de «{negocio.nombre}» como administrador de la plataforma.")
    return redirect("dashboard:inicio")


@require_POST
@staff_member_required
@solo_superusuario
def salir(request):
    pk = request.session.pop(SESION_SOPORTE, None)
    negocio = Negocio.objects.filter(pk=pk).first() if pk else None
    if negocio:
        auditar(negocio, request.user, "soporte_salir", negocio)
    return redirect("plataforma:panel")


@require_POST
@staff_member_required
@solo_superusuario
def cambiar_plan(request, pk):
    """Asigna el plan de un negocio: Gratis, o uno de pago por N días (sin prueba gratis)."""
    negocio = get_object_or_404(Negocio, pk=pk)
    plan = request.POST.get("plan", "")
    if plan not in settings.PLANES:
        messages.error(request, "Plan no válido.")
        return redirect("plataforma:panel")
    try:
        dias = max(1, min(3660, int(request.POST.get("dias") or 30)))
    except ValueError:
        dias = 30
    s = Suscripcion.objects.get_or_create(negocio=negocio)[0]
    anterior = s.plan_efectivo
    s.plan, s.prueba_hasta = plan, None
    s.pagado_hasta = None if plan == "GRATIS" else timezone.localdate() + timedelta(days=dias)
    s.save()
    auditar(negocio, request.user, "cambiar_plan", s, anterior=anterior, nuevo=plan, dias=dias)
    detalle = "" if plan == "GRATIS" else f" hasta el {s.pagado_hasta:%d/%m/%Y}"
    messages.success(request, f"{negocio.nombre}: plan {settings.PLANES[plan]['nombre']}{detalle}.")
    return redirect("plataforma:panel")



@staff_member_required
@solo_superusuario
def negocio(request, pk):
    """Administrar un negocio: su plan a la medida, sus usuarios y entrar a verlo."""
    from apps.catalogo.models import Producto
    from apps.usuarios.models import Usuario

    from .forms_plataforma import PlanNegocioForm

    n = get_object_or_404(Negocio.objects.select_related("suscripcion"), pk=pk)
    s = n.suscripcion
    form = PlanNegocioForm.desde(s, request.POST or None)
    if request.method == "POST" and form.is_valid():
        antes = {"plan": s.plan, "limites": dict(s.limites), "apagados": list(s.modulos_apagados)}
        form.aplicar(s)
        auditar(n, request.user, "ajustar_plan", s, antes=antes,
                despues={"plan": s.plan, "limites": dict(s.limites), "apagados": list(s.modulos_apagados)})
        messages.success(request, f"Plan de {n.nombre} guardado.")
        return redirect("plataforma:negocio", pk=n.pk)
    uso = {"productos": Producto.objects.filter(negocio=n, es_agrupador=False).count(),
           "usuarios": Usuario.objects.filter(negocio=n, is_active=True).count()}
    return render(request, "plataforma/negocio.html", {
        "n": n, "s": s, "form": form, "uso": uso,
        "usuarios": Usuario.objects.filter(negocio=n).order_by("-is_active", "rol", "username"),
        "admin_url": settings.ADMIN_URL,
    })


@staff_member_required
@solo_superusuario
def crear_negocio(request):
    """Alta de un negocio con su dueño y una clave temporal que se le envía por WhatsApp."""
    from django.db import transaction

    from apps.usuarios.models import Rol, Usuario

    from .forms_plataforma import NuevoNegocioForm, clave_temporal

    form = NuevoNegocioForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        clave = clave_temporal()
        with transaction.atomic():
            n = Negocio.objects.create(nombre=d["nombre"], giro=d["giro"], nit=d["nit"], telefono=d["telefono"],
                                       direccion=d["direccion"])  # la señal aplica la plantilla del giro
            nombre, *apellidos = d["dueno"].split()
            dueno = Usuario.objects.create_user(d["usuario"], email=d["correo"], password=clave, first_name=nombre,
                                                last_name=" ".join(apellidos), negocio=n, rol=Rol.ADMIN,
                                                telefono=d["telefono"])
            s = n.suscripcion
            s.plan, s.prueba_hasta = d["plan"], None
            s.pagado_hasta = None if d["plan"] == "GRATIS" else timezone.localdate() + timedelta(days=d["dias"])
            s.save()
            auditar(n, request.user, "crear_negocio", n, giro=n.giro, plan=s.plan, dueno=dueno.username)
        url = request.build_absolute_uri("/ingresar/")
        mensaje = (f"Hola {nombre}, ya está listo {n.nombre} en {settings.EMPRESA['nombre']}.\n"
                   f"Entra en {url}\nUsuario: {dueno.username}\nClave temporal: {clave}\n"
                   "Cámbiala al entrar: Ajustes → Cambiar mi contraseña.")
        return render(request, "plataforma/negocio_creado.html", {
            "n": n, "dueno": dueno, "clave": clave, "url": url, "mensaje": mensaje,
            "telefono": "".join(c for c in (d["telefono"] or "") if c.isdigit())})
    return render(request, "plataforma/crear_negocio.html", {"form": form})