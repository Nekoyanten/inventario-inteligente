# 🍸 Fase 10: bares, discotecas y bar-discotecas — piloto simulado de 60 noches

> **Aviso importante.** Los 9 negocios, sus dueños y sus clientes **son ficticios**: nadie real usó la aplicación.
> Lo que sí es real: cada cuenta, cover, reserva, trago, botella guardada, bono, conteo y compra pasó por el
> **código real** de la aplicación, y las métricas salen de esa base de datos (PostgreSQL).
> Lo que **no** es real: **cómo reaccionan los clientes a la fidelización**. Eso es un **supuesto** del simulador
> (ver [Supuestos](#supuestos-de-conducta-lo-más-importante-de-leer)). Por eso el efecto de la fidelización que
> se muestra aquí es **ilustrativo**: indica el orden de magnitud y dónde se gana o se pierde, no una promesa.
> Las "voces" de los dueños son una **interpretación de las métricas** de su perfil, no testimonios.
> No reemplaza un piloto con bares reales y no debe usarse en la página comercial.

## 1. Formas de fidelización para la noche: qué dice la investigación

| Forma | Cómo funciona | Qué dice la evidencia | En la app |
|---|---|---|---|
| **Puntos y niveles** | Cada compra suma puntos canjeables; el cliente sube a Frecuente o VIP | Los programas por niveles logran ~48 % de participación frente a ~35 % de los planos, y los miembros compran más seguido ([Paytronix](https://www.paytronix.com/blog/effectiveness-of-loyalty-programs)) | Ya existía (Fase 9); ahora los niveles también dan **cover gratis** |
| **Bono por visitas** | "Cada 5 noches, 100 puntos": premia volver, no gastar más | Es la mecánica clásica de frecuencia para bares y cervecerías ([Kangaroo](https://loyalty.kangaroorewards.com/customer-loyalty-for-restaurants-and-bars-how-to-keep-guests-coming-back/), [Brewlytics](https://brewlytics.ai/blog/brewery-loyalty-program-ideas-that-actually-drive-repeat-visits)) | `visitas_para_bono`, `puntos_bono_visita` |
| **Botella guardada** (*bottle keep*) | Lo que sobra de la botella queda marcado a nombre del cliente hasta su próxima visita | Nace en Japón; el cliente vuelve porque le sale más barato que comprar tragos sueltos ([Wikipedia](https://en.wikipedia.org/wiki/Bottle_keep), [Imbibe](https://imbibemagazine.com/bottle-keep-programs-on-the-rise/)) | Guardar, retirar, vencimiento (60 días) y recordatorio |
| **Entrada preferente / cover gratis VIP** | Los mejores clientes no pagan cover o no hacen fila | Es un beneficio típico de discotecas junto a cumpleaños, referidos y botellas ([Loyalty Gator](https://www.loyaltygator.com/bar)) | `cover_gratis_desde` (VIP o Frecuente) |
| **Cumpleaños** | Reserva de cumpleaños: el cumpleañero entra gratis | Mismo origen ([Loyalty Gator](https://www.loyaltygator.com/bar)) | Tipo de reserva `CUMPLEAÑOS` |
| **Referidos y organizador del grupo** | Quien trae amigos gana puntos cuando el amigo compra por primera vez; el organizador de un grupo gana puntos por asistente | Mismo origen ([Loyalty Gator](https://www.loyaltygator.com/bar)) | `puntos_por_referido`, `grupo_puntos_por_asistente` |
| **Happy hour y noches temáticas** | Precio especial o 2×1 en la franja floja | Sirve para las noches flojas, pero el descuento profundo y permanente erosiona la ganancia: mejor ofertas puntuales tipo "sorpresa" ([PepperHQ](https://www.pepperhq.com/blog/growing-customer-loyalty)) | Precios por franja (incluso pasada la medianoche); el análisis sugiere la noche floja |
| **Anticipo en reservas** | Se cobra una parte al reservar y se descuenta de la cuenta | Los depósitos reducen el *no-show* en 57 % en promedio ([OpenTable](https://www.opentable.com/restaurant-solutions/resources/3-proven-payment-strategies-reduce-no-shows/)) | Campo `anticipo` = crédito en la cuenta |
| **Recordatorios por WhatsApp** | "Tu botella vence el viernes", "te falta una visita para el bono" | WhatsApp llega a más del 75 % de los usuarios en Colombia y la mensajería empresarial creció 84 % en un año ([Infobae](https://www.infobae.com/tecno/2026/04/27/whatsapp-lidera-el-crecimiento-del-84-en-la-mensajeria-empresarial-en-colombia/)) | Lista de recordatorios con un toque (sin envío masivo automático) |

**Reglas colombianas que la app respeta:**

- **Mayoría de edad** ([Ley 124 de 1994](https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=291)): prohíbe vender bebidas embriagantes a menores. En giros nocturnos no se registra un cliente sin verificar que es mayor de edad, y una fecha de nacimiento de menor se rechaza.
- **Propina voluntaria** ([Ley 1935 de 2018](https://www.siigo.com/blog/obligaciones-fiscales/propina-colombia-ley-1935/)): es voluntaria, la sugerida no puede pasar del **10 %** antes de impuestos y hay que preguntarle al cliente si la acepta. La app la sugiere, no la suma sola, la limita al 10 % y redondea hacia abajo.
- **Datos personales** (Ley 1581): autorización al registrar y autorización aparte para ofertas (desde la Fase 9).

**Costo de lo servido (*pour cost*).** Las referencias internacionales son 18–20 % en destilados por trago y 24–28 % en cerveza ([Sculpture Hospitality](https://www.sculpturehospitality.com/blog/what-is-the-average-liquor-cost-for-a-bar), con datos de Restaurants Canada).

## 2. Qué se construyó (módulo «La noche»)

Aparece solo en los giros **Bar / gastrobar**, **Discoteca** y **Bar-discoteca**.

- **Cuentas abiertas por mesa o a nombre**: una cuenta abierta por mesa; pedidos con la hora (para el happy hour); quitar un pedido exige motivo y queda en la bitácora; las cortesías solo las da el administrador; cobro parcial ("yo pago lo mío") y total; propina voluntaria.
- **Botellas y tragos**: la unidad *botella* admite décimos. "Vender por tragos" crea el trago como preparado cuya receta es la fracción de la botella (30 ml de 750 = 0,04). El conteo semanal de botellas abiertas en décimos revela lo que se pierde en la barra.
- **Cover y reservas VIP**: cover consumible (queda como crédito en la cuenta) o no consumible (venta); aforo; VIP o Frecuente entran gratis. Las reservas de mesa, grupo, cumpleaños o lista de un promotor pueden llevar anticipo, consumo mínimo e invitados. Si no se alcanza el consumo mínimo, se cobra la diferencia.
- **Happy hour y noches**: porcentaje, 2×1 o precio fijo por días y horas, incluso pasada la medianoche. El 2×1 **junta rondas distintas** de la misma cuenta.
- **Grupos de más de 10 personas**: descuento automático en la cuenta (nunca bajo el costo) y puntos para el organizador por cada asistente.
- **Fidelización**: todo lo de la tabla anterior, además de los puntos y ofertas de la Fase 9.
- **Análisis de la noche**:
  - venta por día de la semana y por hora;
  - pour cost teórico y **real** (con lo que faltó en los conteos), por categoría;
  - rendimiento de cada botella;
  - reservas: *no-show*, grupos, consumo por persona;
  - promotores y puerta;
  - fidelización;
  - sugerencias automáticas.

## 3. Cómo se hizo el piloto simulado

```bash
python manage.py simular_nocturno --dias 60 --semilla 7 --salida noche.json                     # con fidelización
python manage.py simular_nocturno --dias 60 --semilla 7 --sin-fidelizacion --salida control.json  # grupo de control
```

- **9 negocios ficticios** (3 bares, 3 discotecas, 3 bar-discotecas) en Pasto, Ipiales y Túquerres, **60 noches** cada uno, sobre **PostgreSQL**, con el código de esta fase montado sobre el parche 9.
- Cada negocio tiene 16 botellas (aguardiente, ron, whisky, tequila, vodka, ginebra), sus tragos creados con «Vender por tragos», 10 cervezas, 8 cócteles con receta (limón, hielo, hierbabuena…), bebidas sin alcohol y comida. Las discotecas y bar-discotecas tienen mesas VIP con consumo mínimo de $400.000.
- **Un "universo" de personas** por negocio (450 a 2.600): pocas vienen casi cada semana y muchas vienen una vez. Llegan en grupos (promedio 3 a 4,6 personas); hay reservas de mesa, cumpleaños, listas de promotores y grupos de 10 a 22 personas; algunas reservas no llegan (menos si dejaron anticipo).
- **Qué hace cada dueño lo deciden sus rasgos** (ver `apps/core/simulacion/perfiles_nocturnos.py`):
  - cuántos clientes registra el personal;
  - si hace el conteo semanal de botellas y registra las compras;
  - cuánto de más sirve el bartender;
  - cuántos tragos regala sin registrar;
  - si revisa los recordatorios de WhatsApp.
- El simulador lleva **dos inventarios**: lo que hay en la barra (con el sobreservido y las cortesías) y lo que cree el sistema. El conteo semanal los vuelve a juntar.
- **Comparación A/B justa**: cada negocio se corrió **con y sin fidelización**, con **2 semillas** (7 y 11), 36 corridas en total. Se usaron *números aleatorios comunes*: las mismas personas, las mismas reservas y, si alguien viene la misma noche en los dos casos, pide exactamente lo mismo. **Lo único que cambia es la fidelización.** Sin esto, la diferencia entre corridas era puro ruido: en una primera versión una bar-discoteca daba +18 % solo por el azar de las botellas pedidas.

### Supuestos de conducta (lo más importante de leer)

La app mide lo que pasa, pero **cuánto más vuelve un cliente por la fidelización no se puede saber sin clientes reales**. Se supuso, para un cliente registrado, este aumento en la probabilidad de volver en una noche dada:

| Situación del cliente | Aumento supuesto |
|---|---|
| Solo estar registrado (puntos, niveles) | +5 % |
| Tiene una botella guardada | +30 % |
| Recibió un recordatorio u oferta por WhatsApp en los últimos 7–10 días | +15 % |
| Su próxima visita le da el bono | +10 % |

- Son supuestos **moderados**. Por ejemplo, Paytronix reporta que el 81 % de los miembros de programas de fidelización compran con más frecuencia ([Paytronix](https://www.paytronix.com/blog/effectiveness-of-loyalty-programs)), pero eso no dice *cuánto* más.
- Si los clientes reales reaccionan el doble, el efecto se acerca al doble. Si no reaccionan, la fidelización solo cuesta.
- Por eso el piloto real debe medir, antes que nada, **"vuelven"** y **"visitas por cliente"** (ya salen en *Análisis*).

## 4. Resultados de las 60 noches (con fidelización, promedio de 2 semillas) — SIMULADOS

| Negocio | Giro | Personas | Ventas | Venta por persona | Costo de lo servido (teórico → real) | Merma de barra | Vuelven | Visitas por persona | Clientes registrados | Ventas con cliente |
|---|---|---|---|---|---|---|---|---|---|---|
| Bar La Pola | Bar | 3.444 | $89,8 M | $26.078 | 34,4 → 34,6 % | $250.204 | 52 % | 2,69 | 352 | 80 % |
| El Rincón Paisa | Bar | 2.360 | $63,0 M | $26.690 | 34,8 → 34,8 %* | $488.646 | 54 % | 3,24 | 94 | 55 % |
| Gastrobar Alquimia | Bar | 3.260 | $123,3 M | $37.818 | 28,5 → 29,7 % | $1.412.413 | 48 % | 2,52 | 310 | 82 % |
| Galeras Club | Discoteca | 4.610 | $147,6 M | $32.014 | 33,2 → 34,0 % | $1.179.738 | 36 % | 1,73 | 432 | 48 % |
| Son de la Loma | Discoteca | 2.642 | $95,4 M | $36.111 | 34,6 → 35,1 % | $431.243 | 48 % | 2,37 | 255 | 72 % |
| Neón Urbano | Discoteca | 5.804 | $149,0 M | $25.684 | 32,4 → 32,4 %* | $769.951 | 35 % | 1,73 | 392 | 38 % |
| La Terraza | Bar-discoteca | 4.432 | $133,1 M | $30.020 | 32,0 → 32,7 % | $917.376 | 40 % | 2,09 | 455 | 66 % |
| Crossover Bar & Disco | Bar-discoteca | 4.572 | $124,1 M | $27.117 | 34,2 → 34,9 % | $880.984 | 40 % | 1,98 | 329 | 50 % |
| La Bodega Rock Bar | Bar-discoteca | 978 | $27,8 M | $28.497 | 34,5 → 34,5 %* | $370.366 | 45 % | 2,07 | 66 | 40 % |

\* Sin conteo semanal de botellas: la merma existe (columna "merma de barra", medida por el simulador) pero **el sistema no la ve**, así que el costo "real" queda igual al teórico.

**Lo que muestran los números:**

- **El costo de lo servido por categoría** fue muy parecido en los 9: tragos y cócteles ~25 %, cerveza ~40 %, botella entera ~40 %.
  - La cerveza nacional deja mucho menos margen que la referencia internacional (24–28 %).
  - En una primera versión la app alertaba "cerveza cara" en los 9 negocios: era ruido. Ahora solo alerta en tragos y cócteles, que es donde el dueño controla medida, receta y precio. La cerveza y la botella se muestran con su referencia.
- **La merma de barra solo se ve con conteo.**
  - En Alquimia el conteo semanal mostró 1,2 puntos entre el costo teórico y el real ($1,4 M en 60 noches), y la app sugirió "botellas que rinden menos".
  - El Rincón, Neón y La Bodega no cuentan: pierden $0,4–0,8 M sin enterarse.
- **Agotados.** Parte de los pedidos no se pudo atender porque se acabó la cerveza o la botella:
  - Neón: 17 % de los pedidos;
  - La Pola: 9 %;
  - Alquimia: 8 %;
  - El Rincón, La Terraza y Crossover: 7 %;
  - las demás: 0–3 %.

  Hay dos causas. La primera: el pronóstico empieza bajo mientras aprende (para la cerveza más vendida de La Pola pasó de ~6 a ~14 unidades diarias). La segunda: la demanda se concentra de jueves a sábado. En Neón, además, no se hacen conteos y hay compras sin registrar, así que el sistema cree que hay más de lo que hay.
- **Reservas.** El *no-show* fue de 20 % a 32 % en casi todos, y la app sugirió pedir anticipo.
  - Los grupos grandes consumieron **más** por persona que los clientes sin reserva en las discotecas: Neón $33.361 frente a $23.567, Galeras $33.284 frente a $30.097, Crossover $29.006 frente a $25.466.
  - En los bares consumieron **menos** por persona (llegan tarde y alcanzan menos rondas). La muestra es chica (2 a 10 grupos por negocio).

## 5. ¿La fidelización paga? Con vs. sin (A/B, 2 semillas) — SIMULADO

| Negocio | Personas | Ventas | Utilidad (neta de merma) | Visitas por persona | Utilidad: semilla 7 / 11 | Lo que costó la fidelización |
|---|---|---|---|---|---|---|
| Bar La Pola | +3,9 % | +3,2 % | **+3,1 %** | +3,7 % | +3,5 / +2,6 % | $0,41 M (puntos) |
| El Rincón Paisa | +2,8 % | +1,7 % | **+1,4 %** | +2,4 % | +0,7 / +2,1 % | $0,23 M |
| Gastrobar Alquimia | +3,9 % | +3,0 % | **+2,7 %** | +3,9 % | +0,5 / +5,2 % | $0,59 M |
| Galeras Club | +1,3 % | +1,0 % | **+0,7 %** | +1,5 % | +0,4 / +1,0 % | $2,58 M (cover VIP $2,34 M) |
| Son de la Loma | +4,9 % | +2,3 % | **+1,4 %** | +4,6 % | +3,0 / −0,2 % | $2,38 M (cover VIP $2,05 M) |
| Neón Urbano | +1,6 % | +1,5 % | **+1,3 %** | +1,5 % | +0,5 / +1,9 % | $1,75 M |
| La Terraza | +2,7 % | +1,4 % | **+1,2 %** | +2,5 % | +2,4 / 0,0 % | $2,70 M |
| Crossover Bar & Disco | +3,5 % | +3,5 % | **+3,5 %** | +3,1 % | +4,5 / +2,4 % | $2,63 M |
| La Bodega Rock Bar | +0,5 % | −0,1 % | **−0,3 %** | +1,0 % | −0,6 / −0,1 % | $0,16 M |
| **Los 9** | | | **+1,8 %** | | | |

**Cómo leerlo:**

- Con los supuestos de la sección 3, la fidelización suma **entre 0,7 % y 3,5 % de utilidad en 8 de los 9 negocios en solo 60 noches**. Es poco pero positivo, y crece con el tiempo, porque el bono y la botella guardada se acumulan.
- **La botella guardada** es la mecánica que más mueve a la gente. Hubo 56 a 101 botellas guardadas en las discotecas, y la mitad o más se retiró en una visita posterior.
- **Donde más paga**: negocios con buena adopción (el personal registra al cliente) y grupos que vuelven (La Pola, Alquimia, Crossover).
- **Donde menos**: discotecas con público muy rotativo (Galeras: 1,73 visitas por persona). Ahí el cover gratis VIP se lleva casi todo lo que la fidelización trae.
- **Donde no paga**: La Bodega. Es chica, registra a pocos clientes (25 %) y sus clientes ya vienen por el dueño. Ahí basta la botella guardada; no hace falta un programa completo.
- **Lo que costó** la fidelización se mide ahora en *Análisis → Fidelización*: puntos canjeados, ofertas y cover regalado. Así el dueño lo compara con lo que trae.

### El error que la simulación destapó: el cover gratis del VIP

En la primera corrida, **Son de la Loma perdía utilidad con la fidelización (−1,8 %)**, aunque le llegaba más gente (+4,4 %). La causa era un error de diseño: cuando un cliente VIP llegaba con 5 amigos, **entraban gratis los 6**.

Ahora entran gratis el VIP y un acompañante (configurable), y el cumpleañero solo; el resto del grupo paga. Con esa corrección Son de la Loma pasó a **+1,4 %**, y la app avisa cuando el cover regalado por nivel supera el 10 % de la puerta.

## 6. La voz de cada dueño (ficticia, interpretando sus métricas)

### Bares

- **Andrés Felipe Gómez — Bar La Pola (Centro, Pasto).**
  - «Registramos al 80 % de las cuentas y 66 veces alguien ganó el bono de la quinta visita: la gente vuelve entre semana, que era lo que yo quería (+3,1 % de utilidad).
  - El 2×1 de cerveza de martes a jueves se usó 84 veces; menos mal que ahora cuenta las rondas por separado.
  - Lo que me dolió fue quedarme sin Poker y Corona los viernes: 9 % de los pedidos. Voy a pedir el lunes pensando en el fin de semana, no en el promedio.»
- **Luis Alberto Villota — El Rincón Paisa (barrio Obrero, Pasto).**
  - «Mi gente viene 3 veces en dos meses sin que yo haga nada, y la media de aguardiente guardada con el nombre les encantó (28 botellas).
  - Los puntos no me cambian mucho (+1,4 %).
  - Lo que no sabía es que entre los tragos "de la casa" y el pulso generoso se me van casi $500.000 cada dos meses. La app no los ve porque no cuento las botellas. Voy a contar las abiertas cada lunes.»
- **Daniela Paz — Gastrobar Alquimia (Av. Panamericana, Pasto).**
  - «Tengo el ticket más alto ($37.818 por persona) y 36 reservas, 10 de oficinas con más de 10 personas.
  - Un tercio de las reservas no llegó; ahora pido anticipo, que queda como saldo en la cuenta.
  - El conteo semanal me mostró que los cócteles me cuestan 1,2 puntos más de lo que dice la receta: $1,4 M. Jigger para todos.»

### Discotecas

- **Juan Sebastián Chamorro — Galeras Club (Zona rosa, Pasto).**
  - «Por la puerta pasaron 4.610 personas y el cover consumible funciona: pagan en la entrada y lo gastan adentro.
  - La mayoría viene una sola vez, así que la fidelización me suma poco (+0,7 %) y el cover gratis de los VIP se lleva $2,3 M.
  - Lo que sí sirvió: 101 botellas guardadas. La mitad volvió por su botella.»
- **Gloria Estela Benavides — Son de la Loma (Centro, Pasto).**
  - «Mi público es fiel y muchos son VIP. Cuando el VIP entraba con toda su mesa gratis, perdía plata con la fidelización.
  - Con "el VIP y uno más", gano 1,4 % y llega 5 % más gente.
  - Las botellas de aguardiente guardadas (71) son lo que más me pide la clientela.»
- **Kevin Stiven Rosero — Neón Urbano (Av. de los Estudiantes, Pasto).**
  - «El que más gente mueve: 5.804 personas.
  - El problema no es la fidelización (+1,3 %). Es que el 17 % de los pedidos se perdió por agotados, porque no cuento botellas y a veces no registro lo que llega.
  - El control de edad al registrar me da tranquilidad con la Ley 124.»

### Bar-discotecas

- **María Camila Ortiz — La Terraza (Unicentro, Pasto).**
  - «El 2×1 después del trabajo llena la terraza temprano y a las 11 cambia a rumba.
  - Registramos 455 clientes y tuvimos 30 reservas, 8 de grupos.
  - Los grupos consumen un poco menos por persona que el resto ($26.834 frente a $29.465) por el descuento de grupo, pero llegan en noches que sin ellos serían flojas.»
- **Hernán Darío Paz — Crossover Bar & Disco (Ipiales).**
  - «Los grupos grandes que vienen de Ecuador consumen más por persona ($29.006 frente a $25.466). Los puntos al organizador por cada asistente hacen que vuelvan a reservar aquí: +3,5 %, el que más.
  - Tres de cada diez reservas no llegan, así que voy a pedir anticipo.
  - El domingo es flojo y la app me sugiere happy hour ese día.»
- **Wilson Ordóñez — La Bodega Rock Bar (Túquerres).**
  - «Soy dueño y bartender. Con 978 personas en dos meses, los puntos no me pagan (−0,3 %).
  - Lo que me sirve es la cuenta por mesa, la botella guardada y ver cuánto se va en "la primera ronda de los amigos".
  - Sin contar botellas no lo veo, así que voy a empezar por ahí.»

## 7. Errores que encontró la simulación (corregidos en este parche)

1. **Receta con fracción de un insumo que se maneja en unidades enteras** (0,2 de "hierbabuena" en unidades): se guardaba y **después fallaba cada venta del cóctel**. Ahora la receta no lo permite y pide cambiar la unidad (kg, L, botella…).
2. **El 2×1 no juntaba rondas**: si alguien pedía una cerveza y otra 20 minutos después, cada una era una línea y el 2×1 nunca aplicaba. Ahora se juntan las unidades de toda la cuenta dentro de la franja.
3. **Propina sugerida**:
   - se redondeaba hacia arriba y podía pasar del 10 %;
   - además, el redondeo "a centenas" no redondeaba;
   - el porcentaje configurable no tenía tope.

   Ahora son máximo 10 % (Ley 1935), a centenas y hacia abajo.
4. **Cover gratis para todo el grupo del VIP y del cumpleañero** (sección 5).
5. **Alerta de costo de cerveza en todos los negocios** (falsa alarma por usar la referencia internacional).
6. **Texto**: "Happy hour los domingo" pasó a "los domingos".

## 8. Recomendaciones consolidadas

**Para los dueños (se pueden hacer hoy con la app):**

1. **Contar las botellas abiertas cada semana** (en décimos). Es lo que convierte la merma de barra en un número y activa las alertas de rendimiento. Los tres negocios que no contaban perdían $0,4–0,8 M sin verlo.
2. **Botella guardada y bono por visitas primero**; el resto de la fidelización después. Son las que mueven más visitas por peso regalado.
3. **Cover gratis solo para el VIP y un acompañante**, o mejor, **beneficio en consumo** (cover consumible, trago de bienvenida). La app muestra cuánto cover se regala.
4. **Anticipo en las reservas de mesa VIP y de grupo** (el *no-show* simulado fue 20–32 %; OpenTable reporta 57 % menos *no-show* con depósito).
5. **Premiar al organizador del grupo** (puntos por asistente): los grupos grandes consumieron más por persona en discotecas y bar-discotecas.
6. **Happy hour solo en la noche floja** que muestra *Análisis*, nunca todos los días.
7. **Registrar al cliente en la puerta o al abrir la cuenta**. Donde se registró a pocos (La Bodega: 66 clientes), la fidelización no se notó.

**Para la aplicación (propuesta de Fase 11):**

1. **Compras pensando en el fin de semana**: para giros nocturnos, que "Qué comprar" del lunes cubra hasta el domingo siguiente con un stock de seguridad de un fin de semana, y que avise el miércoles si no alcanza para jueves a sábado. Es la mayor pérdida medida (7–17 % de pedidos agotados en 6 de los 9).
2. **Aprender la demanda más rápido en las primeras semanas** (el pronóstico arrancó en la mitad de la demanda real).
3. **Confirmación de reservas por WhatsApp** con un toque la tarde anterior, y registro de quién confirmó.
4. **Beneficios VIP configurables por noche** (por ejemplo, cover gratis solo de miércoles a jueves).
5. **Validar los supuestos con un piloto real** de 2 bares y 1 discoteca durante 8 semanas, midiendo "vuelven" y "visitas por cliente" con y sin fidelización (por noches alternas o por sede).

## 9. Limitaciones

- *Nota posterior (Fase 11):* los umbrales VIP de los giros nocturnos subieron (bar $800.000, bar-discoteca $1.200.000, discoteca $1.500.000 en 90 días). Este piloto se midió con el umbral anterior de $500.000, así que en él había más VIP y más cover regalado.

- **Los supuestos de conducta de la sección 3 determinan el efecto de la fidelización.** Con otros supuestos, otro resultado. Lo que **no** depende de supuestos es cuánto cuesta cada beneficio y que el sistema lo registre bien.
- 60 noches es poco para ver el efecto completo de niveles y botellas guardadas.
- Precios y costos de licor aproximados para Nariño en 2026; no son una cotización.
- No se simularon peleas, cierres por autoridades, pagos con tarjeta fallidos, cortes de luz ni *Internet* intermitente en la puerta.
- Los "dueños" son ficticios y sus voces son una lectura de sus métricas.
