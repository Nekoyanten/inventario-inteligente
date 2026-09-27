from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from apps.usuarios.seguridad import Ingreso  # noqa: E402

admin.site.site_header = "Inventario Inteligente"

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("ingresar/", Ingreso.as_view(), name="login"),
    path("clave/recuperar/", auth_views.PasswordResetView.as_view(), name="password_reset"),
    path("clave/recuperar/enviado/", auth_views.PasswordResetDoneView.as_view(), name="password_reset_done"),
    path("clave/nueva/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("clave/lista/", auth_views.PasswordResetCompleteView.as_view(), name="password_reset_complete"),
    path("clave/cambiar/", auth_views.PasswordChangeView.as_view(), name="password_change"),
    path("clave/cambiada/", auth_views.PasswordChangeDoneView.as_view(), name="password_change_done"),
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
    path("", include("apps.core.urls_publico")),
    path("", include("apps.dashboard.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
