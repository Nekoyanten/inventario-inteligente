from django.urls import path

from . import views_publico as v

app_name = "publico"
urlpatterns = [
    path("ayuda/", v.ayuda, name="ayuda"),
    path("terminos/", v.terminos, name="terminos"),
    path("privacidad/", v.privacidad, name="privacidad"),
    path("comentarios/", v.comentario, name="comentario"),
    path("salud/", v.salud, name="salud"),
    path("negocio/exportar-datos/", v.exportar_datos, name="exportar_datos"),
]
