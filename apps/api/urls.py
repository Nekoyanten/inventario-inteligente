from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("productos", views.ProductoViewSet, basename="producto")
router.register("movimientos", views.MovimientoViewSet, basename="movimiento")
router.register("ventas", views.VentaViewSet, basename="venta")
router.register("alertas", views.AlertaViewSet, basename="alerta")

urlpatterns = [
    path("v1/", include(router.urls)),
    path("v1/resumen/", views.resumen, name="api-resumen"),
    path("v1/token/", obtain_auth_token, name="api-token"),
    path("esquema/", SpectacularAPIView.as_view(), name="api-esquema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="api-esquema"), name="api-docs"),
]
