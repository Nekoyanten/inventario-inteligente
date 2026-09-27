from django.utils.http import url_has_allowed_host_and_scheme


def url_segura(request, url):
    """Devuelve la URL solo si apunta a este mismo sitio (evita redirecciones abiertas a sitios externos)."""
    if url and url_has_allowed_host_and_scheme(url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return url
    return None
