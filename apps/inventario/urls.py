from django.urls import path

from . import views

app_name = "inventario"
urlpatterns = [
    path("", views.movimiento, name="movimiento"),
    path("historial/", views.historial, name="historial"),
    path("kardex/<int:pk>/", views.kardex_producto, name="kardex"),
    path("vencimientos/", views.lotes, name="lotes"),
    path("vencimientos/<int:pk>/retirar/", views.retirar_lote, name="retirar_lote"),
    path("conteos/", views.conteos, name="conteos"),
    path("conteos/<int:pk>/", views.conteo, name="conteo"),
]
