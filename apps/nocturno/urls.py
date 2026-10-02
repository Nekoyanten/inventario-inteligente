from django.urls import path

from . import views

app_name = "nocturno"
urlpatterns = [
    path("", views.noche, name="noche"),
    path("mesas/", views.mesas, name="mesas"),
    path("mis-mesas/", views.mis_mesas, name="mis_mesas"),
    path("mesas/<int:mesa_id>/tomar/", views.tomar, name="tomar"),
    path("cuentas/<int:pk>/liberar/", views.liberar, name="liberar"),
    path("entregas/<int:pk>/recibir/", views.recibir_entrega, name="recibir_entrega"),
    path("cuentas/<int:pk>/pedir-cuenta/", views.pedir_cuenta, name="pedir_cuenta"),
    path("cuentas/abrir/", views.abrir, name="abrir"),
    path("cuentas/<int:pk>/", views.cuenta, name="cuenta"),
    path("cuentas/<int:pk>/pedir/", views.pedir, name="pedir"),
    path("cuentas/<int:pk>/menos/", views.menos, name="menos"),
    path("cuentas/<int:pk>/quitar/<int:item_id>/", views.quitar, name="quitar"),
    path("cuentas/<int:pk>/cliente/", views.asignar_cliente, name="asignar_cliente"),
    path("cuentas/<int:pk>/cobrar/", views.cobrar, name="cobrar"),
    path("cuentas/<int:pk>/anular/", views.anular, name="anular"),
    path("cuentas/<int:pk>/guardar-botella/", views.guardar_botella, name="guardar_botella"),
    path("entrada/", views.entrada, name="entrada"),
    path("reservas/", views.reservas, name="reservas"),
    path("reservas/<int:pk>/", views.reserva, name="reserva"),
    path("botellas/", views.botellas, name="botellas"),
    path("botellas/<int:pk>/retirar/", views.retirar_botella, name="retirar_botella"),
    path("tragos/<int:pk>/", views.crear_trago, name="crear_trago"),
    path("ajustes/", views.ajustes, name="ajustes"),
    path("precios/", views.precios, name="precios"),
    path("precios/<int:pk>/", views.precios, name="precio"),
    path("analisis/", views.analisis_view, name="analisis"),
]
