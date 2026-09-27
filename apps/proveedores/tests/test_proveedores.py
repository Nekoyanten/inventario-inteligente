def test_crear_proveedor_y_asociar_producto(client, admin, producto):
    from apps.proveedores.models import Proveedor

    client.force_login(admin)
    client.post("/proveedores/nuevo/", {"nombre": "Distribuidora Sur", "tiempo_entrega_dias": 2, "activo": "on"})
    prov = Proveedor.objects.get(nombre="Distribuidora Sur")
    client.post(f"/proveedores/{prov.pk}/", {"producto": producto.pk, "precio_compra": "8000", "multiplo_empaque": 12})
    assert prov.productos.get().multiplo_empaque == 12
    assert client.get("/proveedores/").status_code == 200
