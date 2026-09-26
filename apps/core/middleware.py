"""Adjunta el negocio del usuario autenticado a cada request (request.negocio)."""


class NegocioActualMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        usuario = getattr(request, "user", None)
        request.negocio = getattr(usuario, "negocio", None) if usuario and usuario.is_authenticated else None
        return self.get_response(request)
