import pytest

from apps.core.models import Giro, Negocio, RegistroAuditoria
from apps.usuarios.models import Rol, Usuario

PASO1 = {
    "nombre_negocio": "Boutique Luna", "nit": "", "telefono": "3001234567", "nombre": "Luna",
    "username": "luna", "email": "luna@example.com", "password1": "ClaveSegura123!", "password2": "ClaveSegura123!",
}


@pytest.mark.django_db
def test_registro_completo_en_dos_pasos(client):
    assert client.post("/registro/", PASO1).status_code == 302
    assert "password1" not in client.session["registro_paso1"]  # la clave no queda en texto plano
    resp = client.post("/registro/tipo-de-negocio/", {"giro": Giro.ROPA})
    assert resp.status_code == 302 and resp["Location"] == "/registro/listo/"

    negocio = Negocio.objects.get(nombre="Boutique Luna")
    usuario = Usuario.objects.get(username="luna")
    assert usuario.negocio == negocio and usuario.rol == Rol.ADMIN
    assert usuario.check_password("ClaveSegura123!")
    assert negocio.config.usa_variantes                      # plantilla aplicada
    assert RegistroAuditoria.objects.filter(accion="registrar_negocio").exists()

    listo = client.get("/registro/listo/").content.decode()
    assert "Variantes" in listo and "Talla" in listo           # resumen de funciones activadas
    assert client.get("/").status_code == 200                   # quedó con sesión iniciada


@pytest.mark.django_db
def test_paso2_sin_paso1_redirige(client):
    assert client.get("/registro/tipo-de-negocio/")["Location"] == "/registro/"


@pytest.mark.django_db
def test_contrasenas_distintas(client):
    resp = client.post("/registro/", {**PASO1, "password2": "otra"})
    assert resp.status_code == 200 and "no coinciden" in resp.content.decode()


def test_usuario_repetido(client, admin):
    resp = client.post("/registro/", {**PASO1, "username": "ADMIN"})
    assert "ya existe" in resp.content.decode()
