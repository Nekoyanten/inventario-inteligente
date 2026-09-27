# 🧪 Piloto simulado: 18 negocios, 60 días

> **Aviso importante.** Estos 18 negocios y sus dueños **son ficticios**. Nadie real usó la aplicación.
> Lo que sí es real: cada venta, compra, conteo, alerta y recomendación pasó por el **código real** de la
> aplicación (servicios, reglas y algoritmos), y las métricas salen de esa base de datos.
> Las "opiniones" de cada empresario son una **interpretación de las métricas medidas** para su perfil,
> no testimonios. Sirven para priorizar la Fase 8. **No reemplazan un piloto con clientes reales** y no deben
> usarse como testimonios en la página comercial.

## Cómo se hizo

```bash
python manage.py simular_piloto --dias 60 --salida piloto.json          # los 18 (base de datos limpia)
python manage.py simular_piloto --giro FARMACIA --dias 20                # solo un tipo de negocio
```

- **6 tipos de negocio × 3 clientes**, cada uno con **100 a 500 productos** y **3 proveedores**:
  - *Distribuidora Andina* es el proveedor malo: promete 3 días, se demora de 5 a 9 y entrega el 82 % de lo pedido.
  - *Mayorista del Sur* promete 4 días y se demora de 3 a 5.
  - *Comercializadora Nariño* promete 2 días y se demora de 2 a 3.
- **Un cliente por tipo de negocio cambia de proveedor** a mitad del piloto: reemplaza a Distribuidora Andina por *Proveedor Confiable S.A.S.*
- El simulador lleva **dos inventarios**: el **físico** (lo que hay en la estantería) y el **del sistema**. Se separan igual que en la vida real cuando el dueño no registra una compra, un daño o un vencimiento.
- **Qué hace cada dueño lo deciden 7 rasgos** (ver `apps/core/simulacion/perfiles.py`):
  - disciplina para registrar;
  - si compra con «Qué comprar» o "a ojo";
  - si revisa las alertas;
  - si hace conteo mensual;
  - errores de digitación (escribir ×10);
  - mermas;
  - día del cambio de proveedor.
- **La demanda sigue un patrón realista:**
  - pocos productos venden mucho (Zipf);
  - los viernes y sábados se vende más;
  - un cliente que no encuentra el producto se va sin comprarlo (venta perdida).

## Resultados por negocio

| Negocio | Giro | Prod. | Tickets | Ventas (M$) | Margen | Demanda perdida | Días agotado (top 20 %) | Ventas bloqueadas / sin registrar | Compras sin registrar | Descuadre al cierre | Vencido (M$) | Error pronóstico (WAPE) | Alertas abiertas |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Tienda Doña Rosita | Minimercado | 320 | 3,948 | 71.1 | 28.1 % | 10.3 % | 7.9 % | 42 / 11 | 3 | 0 prod · $0.0 M | 3.0 | 52.4 % | 384 |
| Minimercado El Vecino | Minimercado | 480 | 6,103 | 114.1 | 26.7 % | 14.8 % | 14.0 % | 185 / 80 | 4 | 19 prod · $0.5 M | 3.6 | 55.8 % | 543 |
| Autoservicio La Esquina | Minimercado | 150 | 2,357 | 41.0 | 27.8 % | 19.4 % | 17.6 % | 531 / 303 | 18 | 118 prod · $3.3 M | 1.1 | 72.2 % | 225 |
| Moda Sur Boutique | Ropa | 427 | 812 | 124.7 | 28.4 % | 39.2 % | 24.3 % | 103 / 30 | 2 | 0 prod · $0.0 M | 0.0 | 182.6 % | 547 |
| Jeans Galeras | Ropa | 301 | 559 | 64.4 | 25.4 % | 49.7 % | 36.8 % | 86 / 29 | 4 | 1 prod · $0.4 M | 0.0 | 317.3 % | 360 |
| Pequeños Pasos Kids | Ropa | 177 | 429 | 47.4 | 23.2 % | 38.1 % | 31.7 % | 135 / 65 | 6 | 70 prod · $9.7 M | 0.0 | 238.8 % | 227 |
| Glamour Cosméticos | Belleza | 380 | 1,661 | 186.6 | 26.9 % | 17.8 % | 13.7 % | 184 / 50 | 1 | 0 prod · $0.0 M | 0.0 | 102.4 % | 488 |
| Sala de Belleza Luna | Belleza | 120 | 597 | 74.4 | 26.0 % | 28.8 % | 20.7 % | 69 / 36 | 7 | 64 prod · $15.8 M | 0.0 | 156.1 % | 169 |
| Natural Skin Nariño | Belleza | 200 | 1,310 | 162.9 | 28.5 % | 15.7 % | 10.8 % | 0 / 0 | 0 | 0 prod · $0.0 M | 0.0 | 59.3 % | 264 |
| Droguería San Rafael | Farmacia | 460 | 4,902 | 240.6 | 30.5 % | 10.4 % | 5.2 % | 221 / 73 | 6 | 1 prod · $0.2 M | 0.0 | 54.4 % | 546 |
| Farmacia Salud Total | Farmacia | 350 | 3,478 | 138.9 | 28.5 % | 15.2 % | 12.3 % | 715 / 289 | 15 | 0 prod · $0.0 M | 0.0 | 54.6 % | 453 |
| Droguería Express 24h | Farmacia | 220 | 2,741 | 91.1 | 28.7 % | 19.4 % | 16.8 % | 676 / 346 | 19 | 153 prod · $8.6 M | 0.0 | 75.4 % | 259 |
| Asadero El Cuy Dorado | Restaurante | 110 | 1,884 | 70.4 | 28.3 % | 31.1 % | 14.3 % | 389 / 157 | 20 | 8 prod · $0.2 M | 15.7 | 52.5 % | 168 |
| Sazón Pastuso | Restaurante | 140 | 3,016 | 98.0 | 27.2 % | 30.0 % | 10.9 % | 156 / 62 | 5 | 1 prod · $0.0 M | 19.7 | 39.9 % | 208 |
| Comidas Rápidas La 27 | Restaurante | 100 | 2,781 | 56.6 | 27.0 % | 27.3 % | 13.4 % | 605 / 355 | 26 | 75 prod · $2.1 M | 14.2 | 54.5 % | 149 |
| Ferretería El Tornillo Feliz | Otros | 500 | 1,819 | 79.0 | 26.4 % | 25.9 % | 19.7 % | 110 / 40 | 4 | 23 prod · $0.3 M | 0.0 | 105.4 % | 656 |
| Papelería Arcoíris | Otros | 260 | 2,323 | 104.7 | 29.2 % | 24.6 % | 19.1 % | 339 / 132 | 6 | 1 prod · $0.1 M | 0.0 | 87.4 % | 314 |
| Miscelánea Todo a Mil | Otros | 140 | 1,339 | 49.1 | 28.9 % | 44.2 % | 41.1 % | 443 / 248 | 11 | 84 prod · $3.1 M | 0.0 | 166.7 % | 157 |

**Cómo leer la tabla**

- **Demanda perdida:** de cada 100 productos que pidieron los clientes, cuántos no había en la estantería.
- **Días agotado (top 20 %):** qué tan seguido faltó uno de los productos que más se venden.
- **Ventas bloqueadas:** en la estantería había producto, pero el sistema decía que no (porque no se registró una compra) y no dejó vender.
- **Descuadre:** diferencia entre el sistema y la estantería el último día.
- **WAPE:** error del pronóstico a 30 días, ponderado por volumen.

## Lo que dice cada empresario (simulado)

### Minimercados

**Rosa Elvira Burbano — Tienda Doña Rosita (320 productos) ⭐⭐⭐⭐⭐**
> "Mi hija me lo dejó listo y yo solo vendo y le hago caso a «Qué comprar». Casi nunca me quedo sin lo que más se vende. En el conteo del mes el sistema cuadró casi exacto. Lo que sí me molesta es entrar y ver 384 alertas: yo no tengo tiempo de leer tanto. Díganme las 10 importantes y ya."

*Datos:* 7,9 % de días agotado en el top 20 %, descuadre final $0 y 8 de 10 errores de digitación detectados. Los dos conteos mensuales tuvieron diferencias menores a $400 mil. Aun así terminó con 384 alertas abiertas.

**Jairo Andrés Enríquez — Minimercado El Vecino (480 productos, cambió de proveedor el día 35) ⭐⭐⭐⭐**
> "Lo mejor fue ver en números que Andina me estaba robando días: prometía 3 y llegaba a los 6. Cambié y el nuevo cumple. Pero para cambiarlo tuve que ir producto por producto: ¡259 productos! Y con tres cajeros, a veces uno digita 20 en vez de 2 y el sistema no siempre avisa."

*Datos:* registró 29 errores de digitación, de los que se detectaron 16 y se corrigieron 9. Ver también la sección [Cambio de proveedor](#cambio-de-proveedor-qué-pasó).

**Mónica Guerrero — Autoservicio La Esquina (150 productos) ⭐⭐½**
> "El sistema me dice que no tengo gaseosas y yo las estoy viendo en la nevera. Me bloquea la venta, el cliente esperando… entonces vendo sin registrar. Al final ya no le creo a los números."

*Datos:*
- El sistema le bloqueó 531 ventas y 303 terminaron sin registrar.
- No registró 18 compras.
- Terminó con 118 productos descuadrados ($3,3 M), porque no hace conteo.
- Es el caso típico de abandono: el sistema pierde exactitud y la dueña deja de confiar en él.

### Ropa

**Valentina Rosero — Moda Sur Boutique (427 variantes) ⭐⭐⭐½**
> "Me encanta ver qué talla se agota, pero el pronóstico por cada talla y color no sirve: vendo 1 o 2 de cada una al mes. Yo pienso en 'jean skinny', no en 'jean skinny talla 8 azul'. Lo que necesito es que me diga la curva: de 12 jeans, cuántos de cada talla."

*Datos:* WAPE de 183 % a nivel de variante, 39 % de demanda perdida y 547 alertas abiertas, casi todas de «baja rotación» en variantes.

**Carlos Mauricio Chamorro — Jeans Galeras (301 variantes, cambió de proveedor el día 30) ⭐⭐⭐**
> "Cambié de confeccionista porque sabía que me fallaba, pero el sistema me mostraba que cumplía en 3 días. ¡Claro, nunca había recibido un pedido de él en el sistema! Debería decirme 'todavía no tengo datos' en vez de mostrar lo que el proveedor prometió."

*Datos:* al cambiar, `tiempo_entrega_real()` devolvió 3,0 días, que es lo **prometido**, porque no había órdenes recibidas. WAPE de 317 % y 37 % de días agotado en el top 20 %.

**Lucía Fernanda Díaz — Pequeños Pasos Kids (177 variantes) ⭐⭐½**
> "Lo manejo todo desde el celular y a veces no alcanzo a registrar la mercancía que llega. Después el sistema no me deja vender lo que sí tengo."

*Datos:* 135 ventas bloqueadas y 65 sin registrar. Sin conteo, terminó con 70 variantes descuadradas por $9,7 M.

### Belleza

**Daniela Martínez — Glamour Cosméticos (380 productos) ⭐⭐⭐⭐**
> "«Qué comprar» me ahorra la tarde del lunes: casi siempre lo uso tal cual. Lo que no aguanto es que los tonos que casi no se venden me llenen la bandeja de alertas; lo importante se me pierde."

*Datos:*
- 13,7 % de días agotado en el top 20 %.
- Hizo 23 órdenes con «Qué comprar» y 3 a ojo.
- Descuadre final $0.
- 488 alertas abiertas.

**Paola Andrea Ortiz — Sala de Belleza Luna (120 productos, cambió de proveedor el día 40) ⭐⭐½**
> "En la peluquería gastamos shampoo y tintes en los servicios, no solo los vendemos. No sé cómo registrar eso: si lo saco como 'dañado' me daña los reportes, y si no lo saco el inventario nunca cuadra."

*Datos:* 64 productos descuadrados por $15,8 M, el mayor descuadre del piloto. No existe un movimiento de **consumo interno**.

**Andrés Felipe Pantoja — Natural Skin Nariño (200 productos) ⭐⭐⭐⭐½**
> "Es el primer sistema que uso que me explica por qué pedir. Lo que me falta es que se conecte con mi tienda en línea: hoy paso los pedidos a mano."

*Datos:*
- 0 ventas bloqueadas.
- 0 descuadre.
- WAPE de 59 %.
- Integración con tienda en línea: no existe. Es una hipótesis, porque el simulador no la mide.

### Farmacias

**Luis Eduardo Benavides — Droguería San Rafael (460 productos) ⭐⭐⭐⭐½**
> "Lotes, vencimientos y FEFO: justo lo que exige la norma. El mejor resultado del piloto. Me falta que el sistema me recuerde revisar los lotes que vencen en 3 meses para devolverlos al laboratorio a tiempo, y la factura electrónica."

*Datos:* 5,2 % de días agotado en el top 20 %, el mejor del piloto, y descuadre final de $0,2 M. Le detectaron 6 de 11 errores de digitación.

**Ana María Villota — Farmacia Salud Total (350 productos, cambió de proveedor el día 28) ⭐⭐⭐⭐**
> "El reporte de proveedores me dio la razón: Andina se demoraba 7 días. El nuevo llega en menos de 3 y ya no me quedo sin acetaminofén. Pero ese día tenía 4 órdenes abiertas con Andina y no sabía qué hacer con ellas."

*Datos:* 715 ventas bloqueadas por compras sin registrar. Los conteos mensuales lo corrigieron: terminó con **0 de descuadre**.

**Jhon Jairo Muñoz — Droguería Express 24h (220 productos) ⭐⭐½**
> "Somos 4 en turnos con un solo celular. Nadie sabe quién vendió qué, porque todos entran con el mismo usuario. Y si el sistema dice que no hay, el de la noche vende igual sin registrar."

*Datos:* 676 ventas bloqueadas, 346 sin registrar y 153 productos descuadrados ($8,6 M).

### Restaurantes

**Segundo Arturo Jojoa — Asadero El Cuy Dorado (110 productos) ⭐⭐⭐**
> "Me dice cuánto pedir, pero me pide carne para 10 días cuando la carne dura 4. Se me dañaron más de 15 millones en dos meses. Eso no puede ser."

*Datos:* **$15,7 M vencidos (22 % de las ventas)**. El pedido sugerido cubre *tiempo de entrega + horizonte* y **no tiene en cuenta la vida útil**.

**Gloria Inés Ceballos — Sazón Pastuso (140 productos, cambió de proveedor el día 33) ⭐⭐⭐½**
> "Con los datos cambié al proveedor de carnes que me fallaba. Ya llega en 3 días en vez de 7. Pero sigo botando comida: el sistema debería saber que lo fresco se pide poquito y seguido."

*Datos:* $19,7 M vencidos. Con el proveedor malo, el sistema calculaba 7 días de tiempo de entrega y por eso pedía más carne de la que alcanzaba a usar.

**Kevin Stiven Rosero — Comidas Rápidas La 27 (100 productos) ⭐⭐**
> "Compro en la plaza con efectivo y no tengo tiempo de registrar. Si pudiera tomarle foto a la factura y listo…"

*Datos:* 26 compras sin registrar, 605 ventas bloqueadas y 75 productos descuadrados.

### Otros (ferretería, papelería, miscelánea)

**Hernando Paz — Ferretería El Tornillo Feliz (500 productos) ⭐⭐⭐½**
> "Tengo 500 referencias y el 80 % se vende poco: es normal en una ferretería. El sistema me pone 656 alertas de 'baja rotación' y 'exceso'. Aprendí a no mirarlas, y ahí está el peligro."

*Datos:* 656 alertas abiertas, el récord del piloto, y WAPE de 105 % en la cola larga.

**Sandra Milena Cabrera — Papelería Arcoíris (260 productos, cambió de proveedor el día 38) ⭐⭐⭐½**
> "El cambio de mayorista fue buena decisión y el sistema me ayudó a verlo. Pero lo que más me preocupa es enero y agosto: ¿el sistema va a saber que en temporada escolar se vende 5 veces más?"

*Datos:* existen las temporadas, pero hay que crearlas a mano. El piloto de 60 días no alcanza a medirlo.

**Wilson Ordóñez — Miscelánea Todo a Mil (140 productos) ⭐⭐**
> "Todavía me enredo. Cuando no hay señal no sé si la venta quedó guardada. Y el sistema me dice que no hay cosas que sí tengo."

*Datos:* 44 % de demanda perdida y 41 % de días agotado en el top 20 %, los peores del piloto. Compra a ojo en 21 de 27 pedidos y no hace conteo.

## Cambio de proveedor: qué pasó

| Negocio | Día | Productos reasignados | Entrega real de Andina | Entrega real del nuevo | A tiempo: Andina → nuevo | Órdenes abiertas con Andina |
|---|--:|--:|--:|--:|--:|--:|
| Minimercado El Vecino | 35 | 259 | 6,3 días | 3,0 días | 0 % → 83 % | 2 |
| Jeans Galeras | 30 | 68 | **sin datos** (mostró 3,0) | 3,0 días | — → 100 % | 0 |
| Sala de Belleza Luna | 40 | 62 | 8,3 días | 2,0 días | 0 % → 100 % (1 orden) | 1 |
| Farmacia Salud Total | 28 | 57 | 7,0 días | 2,6 días | 0 % → 80 % | 4 |
| Sazón Pastuso | 33 | 42 | 6,9 días | 2,9 días | 0 % → 75 % | 2 |
| Papelería Arcoíris | 38 | 89 | 6,8 días | 3,3 días | 0 % → 33 % | 0 |

**Lo que funcionó**

- El sistema **sí aprende** el tiempo real de entrega: pasó de los 3 días prometidos a 6–8 días reales.
- Al cambiar, **las recomendaciones se ajustaron solas**: ninguna quedó apuntando al proveedor viejo, porque se regeneran.
- En 5 de los 6 casos, el reporte de proveedores justificaba el cambio con datos.

**Lo que dolió**

1. **No hay cambio masivo de proveedor.** Reasignar entre 42 y 259 productos uno por uno no es realista.
2. **Sin datos, el sistema muestra lo prometido** como si fuera real (caso Jeans Galeras). Debe decir "aún no hay entregas registradas".
3. **Órdenes abiertas con el proveedor que se desactiva:** de 1 a 4 por negocio. El sistema no pregunta si se cancelan o se esperan.
4. **Tiempos de entrega largos inflan los pedidos de perecederos.** Con Andina (7 días), el restaurante pedía carne para 10 días. El problema no es el cambio de proveedor: es la falta de un tope por vida útil (ver P1).

## Consolidado

| Señal | Evidencia en el piloto |
|---|---|
| **Los disciplinados ganan** | Doña Rosita, Natural Skin y San Rafael tuvieron de 5 % a 11 % de días agotado en el top 20 % y descuadre ≈ $0 |
| **Sin conteo, el sistema se descuadra** | Los 6 negocios sin conteo terminaron con 64 a 153 productos descuadrados. Los que cuentan quedaron cerca de 0 |
| **El bloqueo de venta empuja a no registrar** | Entre todos: 4.989 ventas bloqueadas, de las cuales 2.306 (46 %) nunca se registraron |
| **Registrar compras es el eslabón débil** | 157 compras sin registrar son el origen de casi todos los bloqueos |
| **Perecederos: el mayor costo** | Los 3 restaurantes botaron entre $14 M y $20 M, alrededor del 20–25 % de sus ventas |
| **Fatiga de alertas** | Entre 149 y 656 alertas abiertas por negocio; la mayoría son «baja rotación» y «exceso» de la cola larga |
| **Errores de digitación** | 83 errores ×10: se detectaron 47 (57 %) y se corrigieron 28 (34 %) |
| **Pronóstico por variante en ropa no sirve** | WAPE de 183 % a 317 % en ropa, frente a 40–75 % en farmacia, restaurante y minimercado |

## Fase 8 recomendada (priorizada)

| # | Mejora | Por qué (evidencia) | Esfuerzo |
|---|---|---|---|
| **P1** | **Vida útil por producto** y tope del pedido sugerido (`demanda × vida útil`). Aviso cuando el tiempo de entrega es mayor que la vida útil | $14–20 M vencidos en cada restaurante | M |
| **P2** | **"Vender de todas formas"** cuando el sistema dice 0 (configurable), con un ajuste pendiente que el administrador revisa | 4.989 bloqueos; el 46 % de esas ventas nunca se registró | S |
| **P3** | **Recepción rápida de compras:** "llegó todo" en un toque, recepción desde el WhatsApp del pedido y factura sin orden con foto adjunta | 157 compras sin registrar | M |
| **P4** | **Conteo cíclico diario** (10 productos al día, priorizados por ABC y por riesgo de descuadre) en lugar de solo el conteo mensual completo | Descuadres de 64 a 153 productos en quienes no cuentan | M |
| **P5** | **Bandeja "Hoy":** las 10 alertas más importantes; baja rotación y exceso agrupados en un resumen semanal, silenciables por categoría | 149–656 alertas abiertas | S |
| **P6** | **Cambio masivo de proveedor** (por proveedor o categoría), con decisión sobre las órdenes abiertas y "sin datos suficientes" en el desempeño | 42–259 productos a mano; Jeans Galeras decidió sin datos | S |
| **P7** | **Confirmación en el punto de venta** cuando la cantidad supera 5 veces lo habitual | Solo se detectó el 57 % de los errores ×10 | S |
| **P8** | **Ropa por familia:** pronóstico y compra a nivel de agrupador con **curva de tallas** | WAPE de 183–317 % por variante | M |
| **P9** | **Movimiento "consumo interno"** (peluquerías y restaurantes), separado de daños | Sala Luna: $15,8 M descuadrados | S |
| **P10** | **Usuario por empleado con PIN rápido** en un dispositivo compartido | Droguería 24h: nadie sabe quién vendió qué | S |
| **P11** | **Horizonte de compra = ciclo real:** detectar cada cuánto compra el negocio y sugerir el ajuste | Las tiendas de ropa compran cada 14 días con un horizonte de 7: el pedido se acaba antes de la siguiente compra (24–37 % de días agotado en el top 20 %) | S |
| **P12** | **Precisión en lenguaje simple** usando WAPE y excluyendo los días agotados (hoy se usa MAPE, que castiga la cola larga) | MAPE mediano de 56–215 % no le dice nada al dueño | S |
| **P13** | **Eliminar la cuenta de un negocio** (derecho de supresión, Ley 1581) | El simulador no pudo borrar negocios: las llaves protegidas lo impiden y no hay flujo de cierre de cuenta | S |

**Para validar con clientes reales, porque el simulador no puede medirlo:**

- factura electrónica DIAN (farmacias, ferretería);
- integración con tienda en línea;
- temporadas escolares automáticas;
- confianza en el modo sin conexión con señal débil.

**Recomendación:**

- **Fase 8a (2 semanas):** P2, P5, P6, P7, P9, P10, P13. Son cambios pequeños que atacan la causa del abandono.
- **Fase 8b (3–4 semanas):** P1, P3, P4, P8, P11, P12.
- Después, **piloto real con 3–5 negocios** (ver [PILOTO.md](PILOTO.md)), comparando sus métricas con estas.

## Errores de la aplicación que encontró la simulación (ya corregidos en esta rama)

- **Los productos agrupadores de variantes** (p. ej. "Jean skinny", el padre de las tallas) generaban alertas y recomendaciones de compra. Ahora se excluyen en el motor de alertas y en «Qué comprar». Prueba: `test_agrupador_de_variantes_no_genera_alertas_ni_compras`.
- **Fechas en los servicios.** Compras, ventas, conteos y retiro de vencidos no aceptaban una fecha explícita, así que no se podía reconstruir el historial ni cargar datos pasados. Ahora aceptan `fecha=` (opcional).
- **Evaluación de alertas en cada movimiento.** Nuevo `sin_evaluacion_automatica()` para cargas masivas: importar 6.000 ventas ya no evalúa alertas 6.000 veces.

## Limitaciones

- 60 días no alcanzan para medir estacionalidad ni el pronóstico mensual con varios ciclos: solo se cerró un período de pronóstico.
- **El comportamiento humano es una aproximación.** En particular, los rasgos se fijaron a mano y no se calibraron con datos reales.
- **Las opiniones son interpretaciones de las métricas.** Un cliente real puede valorar cosas que aquí no aparecen, como la facilidad de uso, el soporte o el precio.
