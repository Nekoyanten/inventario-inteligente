from django.urls import path

from . import views_plataforma as v

app_name = "plataforma"
urlpatterns = [
    path("", v.panel, name="panel"),
    path("negocios/nuevo/", v.crear_negocio, name="crear_negocio"),
    path("negocios/<int:pk>/", v.negocio, name="negocio"),
    path("negocios/<int:pk>/mesas/", v.mesas, name="mesas"),
    path("negocios/<int:pk>/entrar/", v.entrar, name="entrar"),
    path("negocios/<int:pk>/plan/", v.cambiar_plan, name="plan"),
    path("salir-del-negocio/", v.salir, name="salir"),
]
