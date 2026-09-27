"""Lista de arranque de cada negocio: los pasos mínimos para que el sistema empiece a ser útil."""

from django.urls import reverse


def progreso_arranque(negocio) -> dict:
    from apps.catalogo.models import Producto
    from apps.inventario.models import ConteoFisico
    from apps.proveedores.models import Proveedor
    from apps.usuarios.models import Rol, Usuario
    from apps.ventas.models import Venta

    admin = Usuario.objects.filter(negocio=negocio, rol=Rol.ADMIN).order_by("date_joined").first()
    pasos = [
        {"texto": "Carga al menos 5 productos", "url": reverse("catalogo:lista"),
         "ok": Producto.objects.filter(negocio=negocio, es_agrupador=False).count() >= 5},
        {"texto": "Registra un proveedor con su tiempo de entrega", "url": reverse("proveedores:lista"),
         "ok": Proveedor.objects.filter(negocio=negocio).exists()},
        {"texto": "Haz un conteo físico para arrancar con el stock real", "url": reverse("inventario:conteos"),
         "ok": ConteoFisico.objects.filter(negocio=negocio, estado=ConteoFisico.Estado.APROBADO).exists()},
        {"texto": "Registra tu primera venta", "url": reverse("ventas:pos"),
         "ok": Venta.objects.filter(negocio=negocio).exists()},
        {"texto": "Crea usuarios para tu equipo (si trabajas con más personas)", "url": reverse("usuarios:lista"),
         "ok": Usuario.objects.filter(negocio=negocio).count() > 1},
        {"texto": "Agrega tu correo para recibir alertas y recuperar la contraseña",
         "url": reverse("usuarios:editar", args=[admin.pk]) if admin else reverse("usuarios:lista"),
         "ok": bool(admin and admin.email)},
    ]
    hechos = sum(p["ok"] for p in pasos)
    return {"pasos": pasos, "hechos": hechos, "total": len(pasos), "completo": hechos == len(pasos),
            "porcentaje": round(hechos / len(pasos) * 100)}
