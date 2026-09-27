"""Adjunta el negocio del usuario autenticado a cada request (request.negocio)."""


class NegocioActualMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        usuario = getattr(request, "user", None)
        request.negocio = getattr(usuario, "negocio", None) if usuario and usuario.is_authenticated else None
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
