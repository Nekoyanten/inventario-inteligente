"""18 empresarios ficticios (3 por tipo de negocio) para el piloto simulado.

Todos los nombres de personas y negocios son inventados. Los rasgos de comportamiento controlan
cómo usa cada uno el sistema durante la simulación:

- disciplina: probabilidad de registrar cada compra, daño o vencimiento (el resto queda "por fuera")
- sigue_sistema: probabilidad de comprar con «Qué comprar» en lugar de pedir "a ojo"
- revisa_alertas: probabilidad de mirar y atender las alertas cada semana
- conteo: si hace conteo físico mensual
- error_digitacion: probabilidad por venta de escribir una cantidad equivocada (×10)
- cambia_proveedor: día en que reemplaza a su peor proveedor (None = no cambia)
"""

PERFILES = [
    # ------------------------------------------------------------------ Minimercados
    dict(clave="mini-rosita", giro="MINIMERCADO", negocio="Tienda Doña Rosita", dueno="Rosa Elvira Burbano",
         lugar="barrio Las Cuadras, Pasto", productos=320, tickets=70, empleados=1, disciplina=0.92, sigue_sistema=0.85,
         revisa_alertas=0.8, conteo=True, error_digitacion=0.002, merma=0.004, cambia_proveedor=None,
         rasgos="Metódica, 30 años con la tienda, usa el celular pero prefiere que su hija le configure todo."),
    dict(clave="mini-el-vecino", giro="MINIMERCADO", negocio="Minimercado El Vecino", dueno="Jairo Andrés Enríquez",
         lugar="Avenida Panamericana, Pasto", productos=480, tickets=110, empleados=3, disciplina=0.75, sigue_sistema=0.6,
         revisa_alertas=0.5, conteo=True, error_digitacion=0.004, merma=0.006, cambia_proveedor=35,
         rasgos="Negocio grande y ocupado, 3 cajeros por turnos; le importa no quedarse sin productos de alta rotación."),
    dict(clave="mini-la-esquina", giro="MINIMERCADO", negocio="Autoservicio La Esquina", dueno="Mónica Guerrero",
         lugar="Ipiales", productos=150, tickets=45, empleados=0, disciplina=0.55, sigue_sistema=0.35,
         revisa_alertas=0.3, conteo=False, error_digitacion=0.006, merma=0.008, cambia_proveedor=None,
         rasgos="Atiende sola, compra 'a ojo' desde hace años, desconfía de la tecnología, internet inestable."),
    # ------------------------------------------------------------------ Ropa
    dict(clave="ropa-moda-sur", giro="ROPA", negocio="Moda Sur Boutique", dueno="Valentina Rosero",
         lugar="Centro Comercial Unicentro, Pasto", productos=420, tickets=18, empleados=2, disciplina=0.9,
         sigue_sistema=0.7, revisa_alertas=0.8, conteo=True, error_digitacion=0.002, merma=0.001, cambia_proveedor=None,
         rasgos="Joven, vende también por Instagram y WhatsApp; necesita saber qué tallas se agotan."),
    dict(clave="ropa-jeans-galeras", giro="ROPA", negocio="Jeans Galeras", dueno="Carlos Mauricio Chamorro",
         lugar="Calle 18, Pasto", productos=300, tickets=14, empleados=1, disciplina=0.8, sigue_sistema=0.5,
         revisa_alertas=0.6, conteo=True, error_digitacion=0.003, merma=0.001, cambia_proveedor=30,
         rasgos="Compra a confeccionistas locales que a veces incumplen; quiere medir qué proveedor le falla."),
    dict(clave="ropa-kids", giro="ROPA", negocio="Pequeños Pasos Kids", dueno="Lucía Fernanda Díaz",
         lugar="Tumaco", productos=180, tickets=10, empleados=0, disciplina=0.65, sigue_sistema=0.4,
         revisa_alertas=0.4, conteo=False, error_digitacion=0.004, merma=0.001, cambia_proveedor=None,
         rasgos="Ropa y calzado infantil; poco tiempo, internet de datos móviles, maneja todo desde el celular."),
    # ------------------------------------------------------------------ Belleza
    dict(clave="bella-glamour", giro="BELLEZA", negocio="Glamour Cosméticos", dueno="Daniela Martínez",
         lugar="Centro, Pasto", productos=380, tickets=30, empleados=2, disciplina=0.88, sigue_sistema=0.75,
         revisa_alertas=0.75, conteo=True, error_digitacion=0.002, merma=0.002, cambia_proveedor=None,
         rasgos="Distribuidora de catálogo y tienda física; los vencimientos y los tonos agotados son su dolor."),
    dict(clave="bella-sala-luna", giro="BELLEZA", negocio="Sala de Belleza Luna", dueno="Paola Andrea Ortiz",
         lugar="barrio Palermo, Pasto", productos=120, tickets=12, empleados=3, disciplina=0.6, sigue_sistema=0.45,
         revisa_alertas=0.4, conteo=False, error_digitacion=0.004, merma=0.004, cambia_proveedor=40,
         rasgos="Peluquería que vende productos y también los gasta en servicios; mezcla consumo interno con ventas."),
    dict(clave="bella-natural", giro="BELLEZA", negocio="Natural Skin Nariño", dueno="Andrés Felipe Pantoja",
         lugar="Pasto (tienda en línea)", productos=200, tickets=22, empleados=1, disciplina=0.95, sigue_sistema=0.85,
         revisa_alertas=0.9, conteo=True, error_digitacion=0.001, merma=0.001, cambia_proveedor=None,
         rasgos="Emprendedor digital, vende por su página web; quiere conectar la tienda en línea con el inventario."),
    # ------------------------------------------------------------------ Farmacias
    dict(clave="farma-san-rafael", giro="FARMACIA", negocio="Droguería San Rafael", dueno="Luis Eduardo Benavides",
         lugar="barrio Obrero, Pasto", productos=460, tickets=85, empleados=2, disciplina=0.9, sigue_sistema=0.8,
         revisa_alertas=0.85, conteo=True, error_digitacion=0.002, merma=0.002, cambia_proveedor=None,
         rasgos="Regente de farmacia, muy estricto con lotes y vencimientos; le preocupa la normativa."),
    dict(clave="farma-salud-total", giro="FARMACIA", negocio="Farmacia Salud Total", dueno="Ana María Villota",
         lugar="Ipiales", productos=350, tickets=60, empleados=2, disciplina=0.7, sigue_sistema=0.55,
         revisa_alertas=0.5, conteo=True, error_digitacion=0.003, merma=0.003, cambia_proveedor=28,
         rasgos="Su distribuidor principal entrega tarde y cambió a uno nuevo durante la prueba."),
    dict(clave="farma-express", giro="FARMACIA", negocio="Droguería Express 24h", dueno="Jhon Jairo Muñoz",
         lugar="Tumaco", productos=220, tickets=50, empleados=3, disciplina=0.6, sigue_sistema=0.4,
         revisa_alertas=0.35, conteo=False, error_digitacion=0.005, merma=0.004, cambia_proveedor=None,
         rasgos="Abre 24 horas con turnos rotativos; varios empleados comparten un mismo celular."),
    # ------------------------------------------------------------------ Restaurantes
    dict(clave="resta-el-cuy", giro="RESTAURANTE", negocio="Asadero El Cuy Dorado", dueno="Segundo Arturo Jojoa",
         lugar="Catambuco, Pasto", productos=110, tickets=40, empleados=4, disciplina=0.7, sigue_sistema=0.6,
         revisa_alertas=0.55, conteo=True, error_digitacion=0.003, merma=0.02, cambia_proveedor=None,
         rasgos="Compra en la plaza cada 2 días; las mermas de carne y verdura son grandes."),
    dict(clave="resta-sazon", giro="RESTAURANTE", negocio="Sazón Pastuso", dueno="Gloria Inés Ceballos",
         lugar="Centro, Pasto", productos=140, tickets=60, empleados=5, disciplina=0.8, sigue_sistema=0.7,
         revisa_alertas=0.7, conteo=True, error_digitacion=0.002, merma=0.015, cambia_proveedor=33,
         rasgos="Almuerzos ejecutivos; el proveedor de carnes le falla y quiere cambiarlo con datos."),
    dict(clave="resta-comidas-rapidas", giro="RESTAURANTE", negocio="Comidas Rápidas La 27", dueno="Kevin Stiven Rosero",
         lugar="Calle 27, Pasto", productos=100, tickets=55, empleados=2, disciplina=0.5, sigue_sistema=0.3,
         revisa_alertas=0.3, conteo=False, error_digitacion=0.006, merma=0.012, cambia_proveedor=None,
         rasgos="Joven, todo por domicilios; no tiene tiempo de registrar compras, compra con efectivo en el momento."),
    # ------------------------------------------------------------------ Otros (genérico)
    dict(clave="gen-ferreteria", giro="GENERICO", negocio="Ferretería El Tornillo Feliz", dueno="Hernando Paz",
         lugar="Avenida Boyacá, Pasto", productos=500, tickets=35, empleados=2, disciplina=0.85, sigue_sistema=0.65,
         revisa_alertas=0.6, conteo=True, error_digitacion=0.003, merma=0.001, cambia_proveedor=None,
         rasgos="Miles de referencias pequeñas; vende tornillos por unidad y cables por metro."),
    dict(clave="gen-papeleria", giro="GENERICO", negocio="Papelería Arcoíris", dueno="Sandra Milena Cabrera",
         lugar="frente a colegio, Pasto", productos=260, tickets=45, empleados=1, disciplina=0.75, sigue_sistema=0.55,
         revisa_alertas=0.5, conteo=True, error_digitacion=0.003, merma=0.002, cambia_proveedor=38,
         rasgos="Temporada escolar fuerte en enero y agosto; su mayorista le cumple poco."),
    dict(clave="gen-miscelanea", giro="GENERICO", negocio="Miscelánea Todo a Mil", dueno="Wilson Ordóñez",
         lugar="La Unión, Nariño", productos=140, tickets=30, empleados=0, disciplina=0.5, sigue_sistema=0.3,
         revisa_alertas=0.25, conteo=False, error_digitacion=0.006, merma=0.003, cambia_proveedor=None,
         rasgos="Municipio pequeño, señal débil, está aprendiendo a usar el celular para el negocio."),
]
