"""9 negocios nocturnos ficticios (3 bares, 3 discotecas, 3 bar-discotecas) para el piloto simulado.

Todos los nombres son inventados. Rasgos:
- dias: noches que abre (0 = lunes … 6 = domingo) y grupos que llegan en promedio cada una de esas noches
- pool: cuántas personas distintas podrían visitarlo (su "universo" de clientes) y qué tan fieles son de base
- adopcion: probabilidad de que el personal registre al cliente (y él acepte) cuando no está registrado
- disciplina: registrar compras y hacer el conteo semanal de botellas
- sobreservido: cuánto de más se sirve por trago (merma de barra); cortesias: tragos regalados sin registrar
- mezcla: qué pide la gente (cerveza, trago, cóctel, botella completa en grupos)
"""

PERFILES_NOCTURNOS = [
    # ------------------------------------------------------------------ Bares
    dict(clave="bar-la-pola", giro="BAR", negocio="Bar La Pola", dueno="Andrés Felipe Gómez",
         lugar="Centro, Pasto", dias={1: 8, 2: 12, 3: 20, 4: 34, 5: 40}, apertura=17, cierre=1, tam_grupo=3.2,
         pool=900, fieles=0.08, adopcion=0.55, disciplina=0.9, conteo_semanal=True, sobreservido=0.04,
         cortesias=0.01, mezcla={"cerveza": 0.65, "trago": 0.15, "coctel": 0.1, "otros": 0.1}, botella=0.10,
         reservas=0.04, grupo_grande=0.10, happy_hour=[(1, 2, 3), "17:00", "19:30", "DOS_POR_UNO", "Cervezas"],
         revisa=0.8, cover=0, aforo=0, promotores=[],
         rasgos="Cervecería artesanal, dueño joven y organizado; quiere que la gente vuelva entre semana."),
    dict(clave="bar-el-rincon", giro="BAR", negocio="El Rincón Paisa", dueno="Luis Alberto Villota",
         lugar="barrio Obrero, Pasto", dias={3: 10, 4: 22, 5: 28, 6: 12}, apertura=16, cierre=0, tam_grupo=3.6,
         pool=450, fieles=0.14, adopcion=0.2, disciplina=0.55, conteo_semanal=False, sobreservido=0.14,
         cortesias=0.06, mezcla={"cerveza": 0.45, "trago": 0.35, "coctel": 0.0, "otros": 0.2}, botella=0.35,
         reservas=0.01, grupo_grande=0.03, happy_hour=None, revisa=0.2, cover=0, aforo=0, promotores=[],
         rasgos="Bar de barrio de 20 años, clientela fija que pide media de aguardiente; invita tragos «de la casa»."),
    dict(clave="bar-alquimia", giro="BAR", negocio="Gastrobar Alquimia", dueno="Daniela Paz",
         lugar="Av. Panamericana, Pasto", dias={2: 12, 3: 18, 4: 30, 5: 34}, apertura=18, cierre=1, tam_grupo=3.8,
         pool=800, fieles=0.07, adopcion=0.65, disciplina=0.85, conteo_semanal=True, sobreservido=0.07,
         cortesias=0.02, mezcla={"cerveza": 0.25, "trago": 0.1, "coctel": 0.5, "otros": 0.15}, botella=0.08,
         reservas=0.15, grupo_grande=0.25, happy_hour=[(2, 3), "18:00", "20:00", "PORCENTAJE", "Tragos y cócteles"],
         revisa=0.8, cover=0, aforo=0, promotores=[],
         rasgos="Cócteles de autor y comida; muchas reservas de oficinas (grupos de 10 a 20) los viernes."),
    # ------------------------------------------------------------------ Discotecas
    dict(clave="disco-galeras", giro="DISCOTECA", negocio="Galeras Club", dueno="Juan Sebastián Chamorro",
         lugar="Zona rosa, Pasto", dias={4: 55, 5: 70}, apertura=21, cierre=3, tam_grupo=4.0,
         pool=2200, fieles=0.035, adopcion=0.45, disciplina=0.85, conteo_semanal=True, sobreservido=0.08,
         cortesias=0.02, mezcla={"cerveza": 0.3, "trago": 0.2, "coctel": 0.15, "otros": 0.05}, botella=0.45,
         reservas=0.18, grupo_grande=0.35, happy_hour=None, revisa=0.7, cover=20000, aforo=450, consumible=True,
         promotores=["Mafe RRPP", "Kevin RRPP", "Laura RRPP"],
         rasgos="Discoteca grande con mesas VIP (consumo mínimo), relacionistas públicos y cumpleaños cada semana."),
    dict(clave="disco-son-loma", giro="DISCOTECA", negocio="Son de la Loma", dueno="Gloria Estela Benavides",
         lugar="Centro, Pasto", dias={3: 18, 4: 30, 5: 38}, apertura=21, cierre=3, tam_grupo=3.4,
         pool=900, fieles=0.09, adopcion=0.5, disciplina=0.75, conteo_semanal=True, sobreservido=0.1,
         cortesias=0.03, mezcla={"cerveza": 0.25, "trago": 0.25, "coctel": 0.05, "otros": 0.05}, botella=0.5,
         reservas=0.06, grupo_grande=0.08, happy_hour=[(3,), "21:00", "22:30", "PORCENTAJE", "Botellas"],
         revisa=0.6, cover=10000, aforo=250, consumible=False, promotores=[],
         rasgos="Salsoteca con público fiel de 30 a 55 años; la botella de aguardiente o ron es la reina."),
    dict(clave="disco-neon", giro="DISCOTECA", negocio="Neón Urbano", dueno="Kevin Stiven Rosero",
         lugar="Av. de los Estudiantes, Pasto", dias={3: 30, 4: 48, 5: 60}, apertura=22, cierre=3, tam_grupo=4.4,
         pool=2600, fieles=0.03, adopcion=0.35, disciplina=0.6, conteo_semanal=False, sobreservido=0.12,
         cortesias=0.04, mezcla={"cerveza": 0.35, "trago": 0.3, "coctel": 0.2, "otros": 0.05}, botella=0.3,
         reservas=0.12, grupo_grande=0.2, happy_hour=[(3,), "22:00", "23:30", "DOS_POR_UNO", "Tragos y cócteles"],
         revisa=0.5, cover=15000, aforo=380, consumible=True, promotores=["Santi RRPP", "Valen RRPP"],
         rasgos="Reggaetón, público de 18 a 25 años; muchas reservas que no llegan y control de edad estricto."),
    # ------------------------------------------------------------------ Bar-discotecas
    dict(clave="bardisco-terraza", giro="BAR_DISCOTECA", negocio="La Terraza", dueno="María Camila Ortiz",
         lugar="Unicentro, Pasto", dias={2: 15, 3: 22, 4: 42, 5: 50}, apertura=18, cierre=2, tam_grupo=3.6,
         pool=1500, fieles=0.05, adopcion=0.55, disciplina=0.85, conteo_semanal=True, sobreservido=0.06,
         cortesias=0.02, mezcla={"cerveza": 0.4, "trago": 0.2, "coctel": 0.25, "otros": 0.1}, botella=0.25,
         reservas=0.1, grupo_grande=0.2, happy_hour=[(2, 3, 4), "18:00", "20:00", "DOS_POR_UNO", "Cervezas"],
         revisa=0.8, cover=10000, aforo=300, consumible=True, promotores=["Nico RRPP"],
         rasgos="Bar con happy hour después del trabajo que a las 11 p. m. se vuelve rumba."),
    dict(clave="bardisco-crossover", giro="BAR_DISCOTECA", negocio="Crossover Bar & Disco", dueno="Hernán Darío Paz",
         lugar="Ipiales", dias={4: 38, 5: 50, 6: 14}, apertura=19, cierre=3, tam_grupo=4.6,
         pool=1600, fieles=0.05, adopcion=0.4, disciplina=0.75, conteo_semanal=True, sobreservido=0.09,
         cortesias=0.03, mezcla={"cerveza": 0.4, "trago": 0.25, "coctel": 0.1, "otros": 0.05}, botella=0.45,
         reservas=0.12, grupo_grande=0.4, happy_hour=None, revisa=0.6, cover=15000, aforo=350, consumible=True,
         promotores=["Diego RRPP"],
         rasgos="Frontera: grupos grandes que vienen de Ecuador los fines de semana, pagan en efectivo."),
    dict(clave="bardisco-bodega", giro="BAR_DISCOTECA", negocio="La Bodega Rock Bar", dueno="Wilson Ordóñez",
         lugar="Túquerres", dias={4: 16, 5: 22}, apertura=20, cierre=2, tam_grupo=3.0,
         pool=500, fieles=0.1, adopcion=0.25, disciplina=0.5, conteo_semanal=False, sobreservido=0.18,
         cortesias=0.07, mezcla={"cerveza": 0.55, "trago": 0.3, "coctel": 0.0, "otros": 0.15}, botella=0.2,
         reservas=0.02, grupo_grande=0.05, happy_hour=None, revisa=0.2, cover=5000, aforo=120, consumible=False,
         promotores=[],
         rasgos="El dueño es también el bartender; sirve «a ojo» y los amigos no pagan la primera ronda."),
]
