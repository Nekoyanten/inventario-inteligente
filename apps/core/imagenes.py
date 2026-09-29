"""Optimización de imágenes subidas: más livianas para celulares con datos móviles."""

import io
import uuid

from django.conf import settings
from django.core.files.base import ContentFile
from PIL import Image, ImageOps


def optimizar_imagen(archivo, lado_max: int | None = None, calidad: int = 80) -> ContentFile:
    """Corrige la orientación de la foto, la reduce a `lado_max` px y la convierte a WebP."""
    lado_max = lado_max or settings.IMAGEN_LADO_MAX
    archivo.seek(0)
    with Image.open(archivo) as img:
        img = ImageOps.exif_transpose(img)  # fotos de celular giradas
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA" if "transparency" in img.info else "RGB")
        img.thumbnail((lado_max, lado_max), Image.Resampling.LANCZOS)
        salida = io.BytesIO()
        img.save(salida, format="WEBP", quality=calidad, method=4)
    return ContentFile(salida.getvalue(), name=f"{uuid.uuid4().hex}.webp")


def ruta_imagen_producto(instancia, nombre):
    """productos/<negocio>/<archivo>: ordena el bucket por negocio (facilita exportar o borrar sus datos)."""
    return f"productos/{instancia.negocio_id or 'sin-negocio'}/{nombre}"


def ruta_logo(instancia, nombre):
    return f"logos/{instancia.negocio_id or 'sin-negocio'}/{nombre}"
