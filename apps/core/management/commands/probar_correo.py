"""Verifica la configuración de correo:  python manage.py probar_correo tu@correo.com"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.core.correo import enviar


class Command(BaseCommand):
    help = "Envía un correo de prueba para confirmar que EMAIL_URL funciona."

    def add_arguments(self, parser):
        parser.add_argument("destino")

    def handle(self, destino, **opts):
        if not settings.CORREO_CONFIGURADO:
            self.stdout.write(self.style.WARNING("EMAIL_URL no está configurado: el correo se imprimirá en la consola."))
        self.stdout.write(f"Servidor: {settings.EMAIL_HOST or '(consola)'}:{settings.EMAIL_PORT} · remitente: "
                          f"{settings.DEFAULT_FROM_EMAIL}")
        if not enviar("prueba", "Correo de prueba", [destino]):
            raise CommandError("No se pudo enviar. Revisa usuario, contraseña de aplicación, puerto y TLS en EMAIL_URL.")
        self.stdout.write(self.style.SUCCESS(f"Correo enviado a {destino}. Revisa también la carpeta de spam."))
