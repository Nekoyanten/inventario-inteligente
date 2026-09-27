from django.urls import path

from . import views

app_name = "registro"
urlpatterns = [
    path("", views.registro_paso1, name="paso1"),
    path("tipo-de-negocio/", views.registro_paso2, name="paso2"),
    path("listo/", views.registro_listo, name="listo"),
]
