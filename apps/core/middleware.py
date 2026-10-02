"""Adjunta el negocio del usuario autenticado a cada request (request.negocio)."""

SESION_SOPORTE = "negocio_soporte"


class NegocioActualMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        usuario = getattr(request, "user", None)
        request.negocio = getattr(usuario, "negocio", None) if usuario and usuario.is_authenticated else None
        request.soporte = False
        if usuario is not None and usuario.is_authenticated and usuario.is_superuser:
            request.negocio = None  # el superusuario es de la plataforma, no de una tienda: solo entra en modo soporte
        # El administrador de la plataforma puede entrar a cualquier negocio para dar soporte (queda en la bitácora)
        if usuario is not None and usuario.is_authenticated and usuario.is_superuser:
            pk = request.session.get(SESION_SOPORTE)
            if pk:
                from .models import Negocio

                request.negocio = Negocio.objects.filter(pk=pk).first()
                request.soporte = request.negocio is not None
                if not request.soporte:
                    request.session.pop(SESION_SOPORTE, None)
        return self.get_response(request)


class SuscripcionMiddleware:
    """Adjunta la suscripción del negocio (request.suscripcion) para mostrar avisos y aplicar límites."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.suscripcion = None
        if getattr(request, "negocio", None) is not None:
            from .limites import suscripcion

            request.suscripcion = suscripcion(request.negocio)
        return self.get_response(request)


class ModulosMiddleware:
    """Si el negocio no tiene un módulo en su plan, sus páginas muestran cómo pedirlo en vez de abrirse."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        s = getattr(request, "suscripcion", None)
        if s is not None:
            from .modulos import MODULOS, modulo_de_ruta

            clave = modulo_de_ruta(request.path)
            if clave and not s.tiene_modulo(clave):
                from django.conf import settings
                from django.shortcuts import render

                from .modulos import datos_guardados

                return render(request, "negocio/modulo_apagado.html", {
                    "modulo": MODULOS[clave][0], "contacto": settings.CONTACTO_VENTAS,
                    "guardados": datos_guardados(s.negocio, clave)}, status=403)
        return self.get_response(request)
