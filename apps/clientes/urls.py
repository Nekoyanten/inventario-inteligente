from django.urls import path

from . import views

app_name = "clientes"
urlpatterns = [
    path("", views.panel, name="panel"),
    path("lista/", views.lista, name="lista"),
    path("nuevo/", views.formulario, name="crear"),
    path("buscar.json", views.buscar_json, name="buscar_json"),
    path("nuevo.json", views.crear_json, name="crear_json"),
    path("programa/", views.configuracion, name="configuracion"),
    path("ofertas/", views.ofertas, name="ofertas"),
    path("ofertas/nueva/", views.oferta_formulario, name="oferta_crear"),
    path("ofertas/sugerida/", views.crear_sugerida, name="crear_sugerida"),
    path("ofertas/<int:pk>/", views.oferta, name="oferta"),
    path("ofertas/<int:pk>/editar/", views.oferta_formulario, name="oferta_editar"),
    path("ofertas/<int:pk>/enviar/<int:cliente_id>/", views.enviar, name="enviar"),
    path("<int:pk>/", views.detalle, name="detalle"),
    path("<int:pk>/editar/", views.formulario, name="editar"),
    path("<int:pk>/puntos/", views.ajustar, name="ajustar"),
    path("<int:pk>/eliminar/", views.eliminar, name="eliminar"),
]
