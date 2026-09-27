"""Límites de cada plan comercial."""

from django.contrib.auth import get_user_model


class LimiteDelPlan(Exception):
    pass


def suscripcion(negocio):
    from .models import Suscripcion

    s, _ = Suscripcion.objects.get_or_create(negocio=negocio)
    return s


def verificar_productos(negocio, nuevos: int = 1):
    from apps.catalogo.models import Producto

    lim = suscripcion(negocio).limites
    actuales = Producto.objects.filter(negocio=negocio, es_agrupador=False).count()
    if actuales + nuevos > lim["productos"]:
        raise LimiteDelPlan(f"Tu plan {lim['nombre']} permite {lim['productos']} productos (tienes {actuales}). "
                            "Mejora tu plan para agregar más.")


def verificar_usuarios(negocio):
    lim = suscripcion(negocio).limites
    actuales = get_user_model().objects.filter(negocio=negocio, is_active=True).count()
    if actuales >= lim["usuarios"]:
        raise LimiteDelPlan(f"Tu plan {lim['nombre']} permite {lim['usuarios']} usuario(s). Mejora tu plan para agregar más.")


def permite(negocio, funcion: str) -> bool:
    return bool(suscripcion(negocio).limites.get(funcion))
