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
    path("", include("apps.dashboard.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
