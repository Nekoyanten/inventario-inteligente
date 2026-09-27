from django.urls import path

from . import views

app_name = "inventario"
urlpatterns = [
    path("", views.movimiento, name="movimiento"),
    path("historial/", views.historial, name="historial"),
    path("kardex/<int:pk>/", views.kardex_producto, name="kardex"),
]
