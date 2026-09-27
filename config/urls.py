from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

admin.site.site_header = "Inventario Inteligente"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("ingresar/", auth_views.LoginView.as_view(), name="login"),
    path("salir/", auth_views.LogoutView.as_view(), name="logout"),
    path("reportes/", include("apps.reportes.urls")),
    path("usuarios/", include("apps.usuarios.urls")),
    path("registro/", include("apps.core.urls")),
    path("negocio/", include("apps.core.urls_negocio")),
    path("productos/", include("apps.catalogo.urls")),
    path("inventario/", include("apps.inventario.urls")),
    path("ventas/", include("apps.ventas.urls")),
    path("proveedores/", include("apps.proveedores.urls")),
    path("compras/que-comprar/", include("apps.recomendaciones.urls")),
    path("compras/", include("apps.compras.urls")),
    path("alertas/", include("apps.alertas.urls")),
    path("api/", include("apps.api.urls")),
    path("", include("apps.core.urls_pwa")),
    path("", include("apps.dashboard.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
