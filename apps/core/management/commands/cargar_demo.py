"""Crea un minimercado de demostración con 60 días de ventas simuladas.

python manage.py cargar_demo   → usuario: admin / clave: admin12345
"""

import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.alertas.motor import evaluar_negocio
from apps.catalogo.models import Categoria, Producto, UnidadMedida
from apps.core.models import Giro, Negocio
from apps.inventario.models import TipoMovimiento
from apps.inventario.services import registrar_movimiento
from apps.proveedores.models import ProductoProveedor, Proveedor
from apps.recomendaciones.services import generar_recomendaciones
from apps.usuarios.models import Rol, Usuario
from apps.ventas.services import registrar_venta

PRODUCTOS = [
    # sku, nombre, categoría, compra, venta, mínimo, ventas/día promedio, stock inicial
    ("ARR-1K", "Arroz 1 kg", "Abarrotes", 3200, 4500, 10, 3, 120),
    ("GAS-15", "Gaseosa 1.5 L", "Bebidas", 4200, 6000, 10, 4, 260),
    ("CAF-250", "Café 250 g", "Abarrotes", 8500, 12000, 8, 5, 300),
    ("LEC-1L", "Leche 1 L", "Lácteos", 2900, 3800, 15, 8, 500),
    ("JAB-3", "Jabón x3", "Aseo", 5000, 7500, 5, 0.1, 40),
]


class Command(BaseCommand):
    help = "Carga un negocio de demostración con historial de ventas."

    @transaction.atomic
    def handle(self, *args, **opts):
        random.seed(42)
        negocio = Negocio.objects.create(nombre="Minimercado Demo", giro=Giro.MINIMERCADO)
        negocio.suscripcion.plan = "NEGOCIO"
        negocio.suscripcion.pagado_hasta = timezone.localdate() + timedelta(days=365)
        negocio.suscripcion.prueba_hasta = None
        negocio.suscripcion.save()
        admin = Usuario.objects.create_superuser("admin", "admin@demo.co", "admin12345", negocio=negocio, rol=Rol.ADMIN)
        und, _ = UnidadMedida.objects.get_or_create(nombre="Unidad", defaults={"abreviatura": "und"})
        prov_a = Proveedor.objects.create(negocio=negocio, nombre="Distribuidora A", tiempo_entrega_dias=3)
        prov_b = Proveedor.objects.create(negocio=negocio, nombre="Mayorista B", tiempo_entrega_dias=7)

        inicio = timezone.now() - timedelta(days=60)
        productos = []
        for i, (sku, nombre, cat, pc, pv, minimo, vpd, stock) in enumerate(PRODUCTOS):
            prov = prov_a if i % 2 == 0 else prov_b
            p = Producto.objects.create(
                negocio=negocio,
                sku=sku,
                nombre=nombre,
                categoria=Categoria.objects.get(negocio=negocio, nombre=cat),
                unidad=und,
                precio_compra=pc,
                precio_venta=pv,
                stock_minimo=minimo,
                proveedor_principal=prov,
            )
            ProductoProveedor.objects.create(proveedor=prov, producto=p, precio_compra=pc)
            registrar_movimiento(
                producto=p,
                tipo=TipoMovimiento.ENTRADA_INICIAL,
                cantidad=stock,
                usuario=admin,
                fecha=inicio,
                fecha_vencimiento=(inicio + timedelta(days=75)).date(),
                evaluar_alertas=False,
            )
            productos.append((p, vpd))

        for dia in range(60):
            fecha = inicio + timedelta(days=dia, hours=12)
            for p, vpd in productos:
                cant = max(0, round(random.gauss(vpd, vpd * 0.3))) if vpd >= 1 else int(random.random() < vpd)
                p.refresh_from_db()
                cant = min(cant, int(p.stock_actual))
                if cant:
                    registrar_venta(
                        negocio=negocio, vendedor=admin, fecha=fecha, lineas=[{"producto": p, "cantidad": cant}]
                    )

        alertas = evaluar_negocio(negocio)
        recs = generar_recomendaciones(negocio)
        self.stdout.write(
            self.style.SUCCESS(
                f"Demo lista: {len(productos)} productos, {alertas} alertas, {len(recs)} recomendaciones. "
                "Ingresa con admin / admin12345"
            )
        )
