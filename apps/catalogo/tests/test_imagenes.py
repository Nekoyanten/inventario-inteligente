import io

import boto3
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.catalogo.models import Producto


def _foto(ancho=3000, alto=2000, formato="JPEG"):
    buf = io.BytesIO()
    Image.new("RGB", (ancho, alto), (200, 30, 30)).save(buf, format=formato)
    return SimpleUploadedFile("foto.jpg", buf.getvalue(), content_type="image/jpeg")


def _datos(**extra):
    return {"nombre": "Labial", "sku": "LAB-1", "precio_compra": "10000", "precio_venta": "18000", "stock_minimo": "2",
            "activo": "on", **extra}


def test_imagen_se_reduce_y_convierte_a_webp(client, admin, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    client.force_login(admin)
    client.post("/productos/nuevo/", {**_datos(), "imagen": _foto()})
    p = Producto.objects.get(sku="LAB-1")
    assert p.imagen.name.startswith(f"productos/{p.negocio_id}/") and p.imagen.name.endswith(".webp")
    with Image.open(p.imagen.path) as img:
        assert max(img.size) == 800


def test_archivo_que_no_es_imagen_se_rechaza(client, admin, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    client.force_login(admin)
    falso = SimpleUploadedFile("virus.jpg", b"no soy una imagen", content_type="image/jpeg")
    resp = client.post("/productos/nuevo/", {**_datos(), "imagen": falso})
    assert resp.status_code == 200 and not Producto.objects.filter(sku="LAB-1").exists()


@pytest.fixture
def bucket(settings):
    from moto import mock_aws

    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="imagenes-prueba")
        opciones = {"bucket_name": "imagenes-prueba", "access_key": "x", "secret_key": "x",
                    "region_name": "us-east-1", "signature_version": "s3v4"}
        settings.STORAGES = {**settings.STORAGES,
                             "default": {"BACKEND": "storages.backends.s3.S3Storage", "OPTIONS": opciones}}
        yield boto3.client("s3", region_name="us-east-1")


def test_imagen_se_guarda_en_el_bucket(client, admin, bucket):
    client.force_login(admin)
    client.post("/productos/nuevo/", {**_datos(), "imagen": _foto(1000, 1000)})
    p = Producto.objects.get(sku="LAB-1")
    claves = [o["Key"] for o in bucket.list_objects_v2(Bucket="imagenes-prueba")["Contents"]]
    assert claves == [p.imagen.name] and "X-Amz-Signature" in p.imagen.url  # URL firmada: bucket privado
