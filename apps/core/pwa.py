"""App instalable (PWA): manifiesto, service worker y página sin conexión."""

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.views.decorators.cache import cache_control

VERSION_CACHE = "inventario-v1"


@cache_control(max_age=86400)
def manifest(request):
    return JsonResponse({
        "name": "Inventario Inteligente", "short_name": "Inventario", "lang": "es-CO",
        "start_url": "/", "scope": "/", "display": "standalone",
        "background_color": "#f4f6f5", "theme_color": "#1f7a4d",
        "description": "Inventario que te dice qué comprar, qué se vence y qué no se vende.",
        "icons": [
            {"src": static("img/icono.svg"), "sizes": "any", "type": "image/svg+xml", "purpose": "any"},
            {"src": static("img/icono-192.png"), "sizes": "192x192", "type": "image/png"},
            {"src": static("img/icono-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
        ],
        "shortcuts": [
            {"name": "Vender", "url": "/ventas/vender/"},
            {"name": "Productos", "url": "/productos/"},
            {"name": "Alertas", "url": "/alertas/"},
        ],
    }, content_type="application/manifest+json")




def service_worker(request):
    js = render_to_string("pwa/sw.js", {"version": VERSION_CACHE, "css": static("css/app.css"),
                                        "js": static("js/app.js"), "icono": static("img/icono.svg")})
    resp = HttpResponse(js, content_type="application/javascript")
    resp["Service-Worker-Allowed"] = "/"
    resp["Cache-Control"] = "no-cache"
    return resp


def sin_conexion(request):
    return render(request, "sin_conexion.html")
