"""Panel de la plataforma (solo superusuario): salud del sistema y métricas del piloto por negocio."""

from datetime import timedelta

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Avg, Count, Max, Q
from django.db.models.functions import TruncDate
from django.shortcuts import render
from django.utils import timezone

from apps.reportes.exportadores import a_csv

from .arranque import progreso_arranque
from .models import Comentario, EjecucionTarea, Negocio
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
            "plan": "Prueba" if s.en_prueba else s.get_plan_display() + ("" if s.al_dia or s.plan == "GRATIS" else " (vencido)"),
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
        "admin_url": __import__("django.conf", fromlist=["settings"]).settings.ADMIN_URL,
    })
