from django.urls import path

from . import views

app_name = "alertas"
urlpatterns = [
    path("", views.lista, name="lista"),
    path("analizar/", views.analizar, name="analizar"),
    path("silenciar/", views.silenciar_alertas, name="silenciar"),
    path("reactivar/", views.reactivar_alertas, name="reactivar"),
    path("<int:pk>/estado/", views.cambiar_estado, name="cambiar_estado"),
]
