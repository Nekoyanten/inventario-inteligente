# 🧪 Demo: 5 negocios con clientes, proveedores de marca real y su plan

```bash
python manage.py cargar_demo_negocios              # 60 días de historial (~11 min en un computador normal)
python manage.py cargar_demo_negocios --dias 30    # más rápido
python manage.py cargar_demo_negocios --borrar     # elimina los 5 negocios de demostración
```

> **Aviso.** Los negocios, dueños y clientes son **inventados**. Las marcas y los productos existen, pero los precios son **aproximados** (Colombia, 2026) y **no** son cotizaciones de esas marcas. Cada venta, compra, oferta y punto pasó por el código real de la aplicación. **Cómo reaccionan los clientes es un supuesto del simulador** (ver al final). No uses estos datos como testimonios ni en la página comercial.

## Usuarios (clave de todos: `Demo2026!`)

| Usuario | Negocio | Tipo | Plan | Proveedor (marca real) | Productos | Usuarios |
|---|---|---|---|---|---|---|
| `bar.lacuadra` | Bar La Cuadra (Centro, Pasto) | Bar | **Emprendedor** | Bavaria (Águila, Poker, Club Colombia, Costeña, Corona, Stella Artois, BBC…) | 43 / 500 | 3 / 3 |
| `disco.kalima` | Kalima Club (Zona rosa) | Discoteca | **Negocio** | Diageo (Buchanan's, Old Parr, Johnnie Walker, Black & White, Smirnoff, Tanqueray, Baileys, Don Julio) | 57 / 5.000 | 4 / 10 |
| `bardisco.mirador` | Mirador 360 Bar & Disco | Bar-discoteca | **Negocio** | Industria Licorera de Caldas (Aguardiente Cristal, Cristal sin azúcar, Tapa Azul, Amarillo de Manzanares, Ron Viejo de Caldas 5, 8 y 15 años) | 52 / 5.000 | 4 / 10 |
| `ropa.denim` | Denim Store Pasto (Unicentro) | Ropa | **Emprendedor** | Levi's (501, 505, 511, 541, 721, 724, Ribcage, Trucker, Housemark, Batwing…) por talla y color | 101 / 500 | 3 / 3 |
| `vape.nube` | Nube Vape Shop | Vapeadores (nuevo) | **Gratis** | Vaporesso (XROS 4, XROS 4 Mini, XROS 5 Mini, XROS Pro, LUXE XR Max, cartuchos XROS, resistencias GTX) y líquidos Nasty Juice | 28 / 50 | 1 / 1 |

Los meseros y vendedores de cada negocio también entran con `Demo2026!` (por ejemplo `bar.lacuadra-mesero1`, `ropa.denim-vendedor1`). Los meseros tienen el rol **Mesero**: solo ven *Mis mesas* (el dueño se las asigna en *La noche → Mesas y meseros*).

## Cómo se ve cada plan (entra a *Mi plan* en cada usuario)

- **Gratis** — Nube Vape Shop. Usa 28 de 50 productos y 1 de 1 usuario, así que no puede invitar a un vendedor. Los reportes solo salen en CSV (Excel y PDF están bloqueados) y no tiene API.
- **Emprendedor** — Bar La Cuadra y Denim Store. Tienen reportes en Excel y PDF. Ya usan los 3 usuarios, así que para un cuarto mesero o vendedor deben subir de plan. La tienda de ropa ocupa 101 de 500 productos porque cada talla y color cuenta como uno.
- **Negocio** — Kalima Club y Mirador 360. Todo habilitado: API, 10 usuarios y 5.000 productos.

Hoy **la fidelización, el módulo nocturno y las alertas están en todos los planes**. Lo único que cambia entre planes es cuántos productos y usuarios hay, los reportes en Excel o PDF y la API.

## Qué ver en cada negocio (resultados de 60 días, semilla 7; cambian un poco según la fecha en que se corra)

| Negocio | Clientes | Ventas | Ventas con cliente | Vuelven | Satisfacción | Lo que más vende |
|---|---|---|---|---|---|---|
| Bar La Cuadra | 364 | $90,4 M | 79 % | 59 % | 4,3 ★ | Cócteles (Margarita, Cuba libre, Aguardiente sour) y Club Colombia / Águila Light |
| Kalima Club | 509 | $224,4 M | 56 % | 46 % | 4,1 ★ | Buchanan's Master y Deluxe, Johnnie Walker Black, Old Parr |
| Mirador 360 | 412 | $112,3 M | 57 % | 52 % | 4,2 ★ | Cover no consumido, Buchanan's, Corona, Ron Viejo de Caldas 5 años |
| Denim Store | 138 | $139,3 M | 40 % | 25 % | 4,3 ★ | Billetera Levi's y chaqueta Trucker |
| Nube Vape Shop | 162 | $69,3 M | 72 % | 81 % | 4,2 ★ | Cartuchos XROS 0,8 y 1,0 Ω, resistencias GTX |

*«Vuelven»: de los clientes activos, cuántos compraron dos o más veces.*

**¿Funcionan las técnicas de fidelización?** Se ve en *Clientes → Ofertas* (enviadas, cuántos volvieron y ventas con la oferta) y en *Clientes → Resumen* (segmentos, quién se está yendo, cumpleaños y encuestas).

| Negocio | Técnicas que usa | Qué muestra la app |
|---|---|---|
| Bar La Cuadra | Puntos, bono cada 5 visitas, botella guardada, 2×1 de cerveza martes a jueves, ofertas sugeridas | 83 bonos por visitas y 68 canjes de puntos. «Tu segunda visita»: volvió 1 de cada 3. «Gracias por preferirnos» (campeones): 73 %. |
| Kalima Club | Cover consumible, VIP con un acompañante gratis, promotores, botella guardada, recordatorios | El cliente identificado gasta **$151.527** por compra frente a $113.506 del anónimo. «Segunda visita»: 17–41 %. |
| Mirador 360 | Grupos con descuento y puntos al organizador, referidos, happy hour de cócteles, ofertas | 50 bonos (visitas, referidos y grupos). Identificado $91.922 frente a $62.147. «Segunda visita»: ~30 %. |
| Denim Store | Puntos, ofertas de cumpleaños, segunda compra, «te extrañamos» | **Aquí funciona poco**: la gente compra ropa cada varios meses. «Segunda visita» 10–18 %, cumpleaños 1 de 6 y solo 25 % vuelve en 60 días. La encuesta muestra 4,3 ★, así que el problema no es la atención. |
| Nube Vape Shop | Puntos (117 canjes) y ofertas solo a mayores de edad verificados | **Aquí funciona mucho**: el cartucho se acaba cada ~2 semanas. 81 % vuelve y «Segunda visita» 65–79 %. |

> **Cuidado al leer el «volvieron»**: cuenta a todos los que compraron después de recibir la oferta, incluso los que habrían vuelto sin ella (por eso «Gracias por preferirnos», enviada a los mejores clientes, da 70–90 %). Para saber si la oferta *causó* la visita hay que comparar con clientes parecidos a los que no se les envió.

## Lo que la demo encontró (corregido en este parche)

1. **«Cumpleaños de September»**: el título de la oferta de cumpleaños salía con el mes en inglés si el servidor no está en español. Ahora sale «Cumpleaños de septiembre».
2. **El nivel VIP llegaba demasiado fácil**: con $500.000 en 90 días, una persona que compraba dos jeans o una botella de whisky ya era VIP. Por eso Kalima tenía 88 VIP que entraban gratis. Ahora el umbral depende del tipo de negocio (se puede cambiar en *Programa de puntos*):
   - ropa: $1.500.000 y 3 compras para ser frecuente;
   - bar: $800.000;
   - bar-discoteca: $1.200.000;
   - discoteca: $1.500.000.
3. **Nuevo tipo de negocio «Vapeadores»** con la [Ley 2354 de 2024](https://lasalle.edu.co/es/noticias/regulacion-del-vapeo-en-colombia-ley-2354-de-2024):
   - no se registra un cliente sin verificar con cédula que es mayor de edad;
   - una fecha de nacimiento de menor se rechaza;
   - las ofertas solo llegan a mayores de edad verificados;
   - aparece un aviso legal en *Ofertas*: la publicidad de vapeadores está prohibida en medios masivos y redes sociales.

## Supuestos del simulador

- **Ropa y vapeadores.** Cada cliente tiene una *lealtad* (qué parte de sus compras hace aquí y no en la competencia) y una *sensibilidad* a la fidelización:
  - al 30–35 % no le mueve nada;
  - al 40–45 % le mueve un poco;
  - al 25 % le mueve bastante.

  Una oferta recibida aumenta la probabilidad de comprar aquí hasta en un 40 %, y los puntos y el nivel hasta en un 18 %. En vapeadores, la persona vuelve cuando se le acaba el cartucho o el líquido (cada 7 a 18 días). En ropa, compra de vez en cuando y más en quincena.
- **Bares y discotecas.** Usan el mismo simulador del piloto nocturno (docs/PILOTO_NOCTURNO.md).
- **Nombres y encuestas.** Los nombres y cumpleaños de los clientes son inventados. Las encuestas se entregan en ~40 % de las compras con cliente y responde ~1 de cada 3.
