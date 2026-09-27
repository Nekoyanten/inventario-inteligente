from apps.analitica.models import Temporada
from apps.core.models import Giro, Negocio


def test_restaurar_plantilla(client, admin, negocio):
    negocio.categorias.all().delete()
    client.force_login(admin)
    client.post("/negocio/configuracion/restaurar/")
    assert negocio.categorias.filter(nombre="Abarrotes").exists()


def test_temporadas_crear_validar_y_eliminar(client, admin, negocio):
    client.force_login(admin)
    assert client.get("/negocio/temporadas/").status_code == 200
    resp = client.post("/negocio/temporadas/", {"nombre": "Mala", "inicio_dia": 40, "inicio_mes": 13, "fin_dia": 1,
                                                "fin_mes": 1, "factor": "1.5"})
    assert "Debe estar entre" in resp.content.decode()
    client.post("/negocio/temporadas/", {"nombre": "Navidad", "inicio_dia": 15, "inicio_mes": 12, "fin_dia": 6,
                                         "fin_mes": 1, "factor": "1.8"})
    t = Temporada.objects.get(negocio=negocio)
    client.post("/negocio/temporadas/", {"eliminar": t.pk})
    assert not Temporada.objects.exists()


def test_temporada_de_otro_negocio_no_se_puede_eliminar(client, admin):
    otro = Negocio.objects.create(nombre="Otro", giro=Giro.GENERICO)
    ajena = Temporada.objects.create(negocio=otro, nombre="Ajena", inicio_mes=1, inicio_dia=1, fin_mes=1, fin_dia=2)
    client.force_login(admin)
    client.post("/negocio/temporadas/", {"eliminar": ajena.pk})
    assert Temporada.objects.filter(pk=ajena.pk).exists()


def test_token_api_y_regenerar(client, admin):
    from rest_framework.authtoken.models import Token

    client.force_login(admin)
    assert client.get("/negocio/api/").status_code == 200
    client.post("/negocio/api/")
    primero = Token.objects.get(user=admin).key
    client.post("/negocio/api/")
    assert Token.objects.get(user=admin).key != primero


def test_pagina_mi_plan(client, admin):
    client.force_login(admin)
    html = client.get("/negocio/plan/").content.decode()
    assert "período de prueba" in html and "Emprendedor" in html
