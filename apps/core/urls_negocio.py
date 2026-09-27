from django.urls import path

from . import views_negocio as v

app_name = "negocio"
urlpatterns = [
    path("configuracion/", v.configuracion, name="configuracion"),
    path("configuracion/restaurar/", v.restaurar_plantilla, name="restaurar_plantilla"),
    path("auditoria/", v.auditoria, name="auditoria"),
    path("temporadas/", v.temporadas, name="temporadas"),
    path("api/", v.api_token, name="api"),
    path("plan/", v.plan, name="plan"),
]
