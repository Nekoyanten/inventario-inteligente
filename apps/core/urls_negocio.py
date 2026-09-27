from django.urls import path

from . import views_negocio as v

app_name = "negocio"
urlpatterns = [
    path("configuracion/", v.configuracion, name="configuracion"),
    path("configuracion/restaurar/", v.restaurar_plantilla, name="restaurar_plantilla"),
    path("auditoria/", v.auditoria, name="auditoria"),
]
