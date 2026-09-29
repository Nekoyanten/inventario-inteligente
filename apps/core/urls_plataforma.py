from django.urls import path

from . import views_plataforma as v

app_name = "plataforma"
urlpatterns = [
    path("", v.panel, name="panel"),
    path("negocios/<int:pk>/entrar/", v.entrar, name="entrar"),
    path("negocios/<int:pk>/plan/", v.cambiar_plan, name="plan"),
    path("salir-del-negocio/", v.salir, name="salir"),
]
