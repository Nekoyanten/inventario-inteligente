from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from apps.clientes.views import encuesta
from apps.usuarios.seguridad import Ingreso, entrar_equipo  # noqa: E402

admin.site.site_header = "Inventario Inteligente"

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("ingresar/", Ingreso.as_view(), name="login"),
    path("equipo/<str:token>/", entrar_equipo, name="equipo"),
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
    path("plataforma/", include("apps.core.urls_plataforma")),
    path("productos/", include("apps.catalogo.urls")),
    path("inventario/", include("apps.inventario.urls")),
    path("ventas/", include("apps.ventas.urls")),
    path("clientes/", include("apps.clientes.urls")),
    path("noche/", include("apps.nocturno.urls")),
    path("encuesta/<str:token>/", encuesta, name="encuesta"),
    path("proveedores/", include("apps.proveedores.urls")),
    path("compras/que-comprar/", include("apps.recomendaciones.urls")),
    path("compras/", include("apps.compras.urls")),
    path("alertas/", include("apps.alertas.urls")),
    path("api/", include("apps.api.urls")),
    path("", include("apps.core.urls_pwa")),
    path("", include("apps.core.urls_publico")),
    path("", include("apps.dashboard.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
elif settings.SERVIR_MEDIA_LOCAL and not settings.ALMACENAMIENTO_NUBE:
    # Solo para un servidor propio con disco persistente. En Render/Docker usa un bucket (AWS_STORAGE_BUCKET_NAME).
    from django.urls import re_path
    from django.views.static import serve

    urlpatterns += [re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT})]
