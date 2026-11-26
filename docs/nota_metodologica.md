# Nota metodológica

Puente sobre el río María Aguilar · Proyecto Integrador III · Visualización de datos (BCD 8215), Lead University, III cuatrimestre 2026.

Esta nota describe para quién es la aplicación, de dónde provienen los datos, cómo se depuraron, cómo se identificaron los cambios de la obra, cómo se calcula el índice de cambio visual y cómo cada visualización responde la pregunta del proyecto. Las cifras corresponden a las tablas de `data/processed_data/` y pueden reproducirse con los scripts de `src/`.

## 1. Objetivo, pregunta y público

El proyecto busca mostrar, a partir de las fotografías de una cámara instalada en la obra, qué ha cambiado en ella y qué parte del periodo no tiene evidencia. La pregunta que responde es:

> ¿Qué cambios se observan en la obra, cuándo ocurrieron y qué días no hay evidencia fotográfica?

**Público.** Para la Fase III el profesor del curso asignó como público principal el perfil de auditor o consultor de la CGR: una persona que necesita verificar cada afirmación contra las fotos, conocer los criterios con que se descartaron datos y descargar las tablas. Se mantiene una capa ciudadana, sin tecnicismos, porque así lo había pedido la CGR tras la Fase II. La aplicación separa ambas capas en pestañas (sección 8).

**Alcance.** La aplicación no informa presupuesto, plazos ni porcentaje de avance. Tras la Fase II, la Contraloría General de la República (CGR) indicó que la propuesta debía limitarse a la información disponible hoy, las imágenes con fecha, y no depender de datos certificados por terceros que podrían no existir. No se agregan datos externos.

## 2. Procedencia de los datos

| Aspecto | Detalle |
|---|---|
| Fuente | CGR, proyecto dIAra, carpeta `proeri_proyecto1` |
| Contenido | 21 644 fotografías originales en carpetas por fecha (`YYYYMMDD/YYYYMMDD-HHMMSS.jpg`) |
| Periodo | 2 de octubre de 2025 a 17 de abril de 2026 (198 días) |
| Uso | La CGR confirmó que las imágenes son de uso público y no contienen información sensible |
| Copia de trabajo | `data/raw_data/`, fuera del control de versiones por su tamaño; las fotografías solo se leen, nunca se modifican |

No se usaron las carpetas de imágenes tratadas de la CGR: no mejoran la nitidez y cubren menos tiempo que las originales.

## 3. Depuración: de 21 644 a 18 861 fotografías

Una fotografía se considera utilizable si es diurna, legible y con luz suficiente, si su día muestra la obra y si no está dañada, sobreexpuesta ni empañada.

| Motivo de exclusión | Fotografías | Criterio |
|---|---:|---|
| Nocturna | 1 799 | Tomada fuera del horario de 06:00 a 17:59 |
| Luz insuficiente | 578 | Brillo medio menor a 30 (de 255) o más del 80 % de la imagen subexpuesta |
| Día sin vista de la obra | 220 | La cámara no apuntaba a la obra ese día |
| Calidad | 92 | Dañada, sobreexpuesta, empañada o iluminada solo por focos al atardecer |
| Orientación dudosa | 91 | No fue posible determinar con confianza la orientación de la imagen (por ejemplo, fotos empañadas o fuera de encuadre) |
| Ilegible | 3 | El archivo no pudo abrirse |
| **Total excluidas** | **2 783** | |
| **Utilizables** | **18 861** | 87 % del total |

Los umbrales están al inicio de `src/01_inventario.py` y `src/04_fotos_utilizables.py`. Las correcciones manuales se registran en `data/processed_data/revision_manual.csv` y las hojas de contacto de `reports/revision_tramos/` documentan la revisión visual.

Para la figura de puntos de la aplicación, cada foto se clasifica en cuatro estados: útil; de noche (motivo «nocturna»); sin vista de la obra (motivo «día sin vista de la obra»); y excluida por calidad, que agrupa luz insuficiente, calidad, orientación dudosa e ilegible (764 fotos), porque todas son fotos diurnas de un día con vista de la obra que no se pueden leer bien.

**Orientación.** Los píxeles de todos los archivos están guardados al revés. Hasta el 9 de octubre de 2025 una etiqueta del archivo lo corregía; después dejó de venir. Para mostrar las fotos se ignora esa etiqueta y se giran siempre 180°, lo que da el mismo resultado en todas.

## 4. Cobertura por día

| Estado del día | Días |
|---|---:|
| Con fotos útiles de la obra | 156 |
| Sin ninguna foto | 34 |
| Con fotos, pero sin vista de la obra | 6 |
| Solo con fotos nocturnas | 2 |
| **Total** | **198** |

En 42 de los 198 días (21 %) no hay evidencia de la obra. Los tramos sin evidencia son: 11–13 de noviembre de 2025 (3 días), 20–21 de noviembre (2), 10–15 de enero de 2026 (6), 6 de febrero a 3 de marzo (26) y 31 de marzo a 4 de abril (5). De las 2 376 horas de luz del periodo, 1 804 (76 %) tienen al menos una foto útil.

Para cada día con evidencia se eligió una "foto del día": la utilizable más cercana a las 12:00.

## 5. Posición de la cámara

La cámara tuvo dos vistas distintas. La primera va del 2 de octubre de 2025 al 5 de febrero de 2026; la segunda, del 4 de marzo al 17 de abril de 2026. Entre ambas están los 26 días sin vista de la obra.

Dentro de la primera vista, el 16 de enero de 2026 la cámara se corrió unos 31 píxeles. La escena es la misma, por lo que la aplicación la trata como una sola vista.

Al calcular el índice de cambio (sección 7) se encontró que ese no es el único movimiento: dentro de cada vista la cámara se desplaza unos píxeles casi todos los días. Entre el 2 de octubre y el 5 de febrero el desplazamiento acumulado llega a ~74 píxeles (de 960) y 1,7° de giro; en la segunda vista, a ~25 píxeles. Por eso `src/07_indice_cambio.py` registra cada día contra el anterior y guarda la transformación de cada día al marco del primer día de su vista (`app/datos/alineacion_dia.csv`). La aplicación la usa para alinear el comparador, el antes y después del recorrido y el time-lapse. El corrimiento del 16-17 de enero medido así coincide con el que mide `06` (diferencia menor a 2 píxeles). Las comparaciones con barra deslizante solo se permiten dentro de una misma vista; entre vistas distintas las fotos se muestran lado a lado con un aviso.

## 6. Identificación de los cambios

Los cambios se identificaron por observación, no de forma automática:

1. Se generó una hoja con una foto por semana para cada vista (`reports/hitos/`) y se buscó entre qué semanas cambiaba algo.
2. Para cada cambio se generó una hoja con una foto por día y se ubicó la fecha.
3. El equipo revisó cada cambio con sus dos fotografías a tamaño completo y le asignó un nivel de claridad.

| Claridad | Criterio |
|---|---|
| Muy claro | Cualquier persona ve el cambio sin que se le indique dónde mirar |
| Claro | Se ve, pero hay que señalar la zona |
| Poco claro | Requiere interpretación; otra persona podría no estar de acuerdo |

La descripción de cada cambio se limita a lo que muestran sus dos fotografías.

| N.º | Cambio | Fechas | Claridad |
|---:|---|---|---|
| 1 | Colocación de la losa del puente | 8–9 oct 2025 | Muy claro |
| 2 | Instalación de las barandas azules | 26–28 oct 2025 | Muy claro |
| 3 | Trabajos de concreto en el acceso al puente | 30 oct – 6 nov 2025 | Claro |
| 4 | Superficie del puente pavimentada | 7–8 nov 2025 | Claro |
| 5 | Líneas pintadas sobre el puente | 14–15 nov 2025 | Claro |
| 6 | Primeros vehículos sobre el puente | 16–19 nov 2025 | Muy claro |
| 7 | Llega maquinaria de perforación al otro lado de la vía | 19–22 nov 2025 | Claro |
| 8 | Se retira la máquina perforadora | 7–8 dic 2025 | Muy claro |
| 9 | Movimiento de tierra al otro lado de la vía | 20–24 ene 2026 | Poco claro |

Entre el primer cambio visible (8 de octubre) y los primeros vehículos sobre el puente (19 de noviembre) pasaron seis semanas. En la segunda vista de la cámara no se identificó ningún cambio claro.

## 7. Índice de cambio visual

El índice es el algoritmo de análisis de imágenes de la aplicación. Para cada día con evidencia mide qué parte de la imagen cambió respecto del día con evidencia anterior de la misma vista. Se calcula localmente con las fotografías originales (`src/07_indice_cambio.py`) y se guarda en `app/datos/indice_cambio.csv`, de modo que la aplicación no necesita las fotos originales.

**Pasos.**

1. *Imagen del día.* Mediana, píxel a píxel, de hasta 5 fotos utilizables tomadas a menos de 60 minutos de la foto del día. Un vehículo o una persona que pasa aparece en una o dos fotos y la mediana lo borra; lo que permanece (la obra, la maquinaria estacionada) queda.
2. *Registro.* Cada día se alinea con el día con evidencia anterior por puntos característicos (ORB + RANSAC, el mismo método de `02` y `06`) y, si no hay suficientes coincidencias, por intensidad (ECC, con correlación mínima de 0,6). De 154 días, 146 se registraron por puntos, 4 por intensidad y 4 no se pudieron alinear; estos últimos quedan sin índice, porque el desalineo contaría como cambio.
3. *Diferencia de estructura.* Sobre la imagen en gris reducida a 320 píxeles de ancho se calcula el término de contraste y estructura del índice SSIM. Un día nublado y uno soleado difieren en brillo, pero poco en estructura.
4. *Lo que no es obra.* Para cada píxel se calcula su diferencia típica (la mediana de todos los pares de días de la vista). Se excluye el 30 % de la imagen que más cambia siempre: hojas del árbol y vegetación del primer plano movidas por el viento, nubes. En el resto, un píxel cuenta como cambio solo si su diferencia es al menos 2,5 veces la típica, lo que atenúa además el tráfico habitual de la carretera. No se usó una máscara fija del cielo porque la grúa y la perforadora de noviembre, que son hitos, se recortan contra el cielo y una máscara las ocultaría. La zona analizada de cada vista está en `reports/indice_cambio/zona_analizada_vista_<n>.jpg`.
5. *Índice y picos.* El índice es el porcentaje de la zona analizada que cambió. Un día es pico si su índice está en el 10 % más alto de su vista (16 picos en total).

**Validación contra los hitos.** Un hito coincide con un pico si algún día con índice entre la foto de antes (excluida) y la de después (incluida) es pico.

| N.º | Hito | Días con índice en la ventana | Índice máximo | ¿Coincide con un pico? |
|---:|---|---:|---:|---|
| 1 | Colocación de la losa del puente | 1 | 26,2 % | Sí |
| 2 | Instalación de las barandas azules | 2 | 7,2 % | No |
| 3 | Trabajos de concreto en el acceso al puente | 7 | 21,9 % | Sí |
| 4 | Superficie del puente pavimentada | 1 | 20,6 % | Sí |
| 5 | Líneas pintadas sobre el puente | 1 | 7,2 % | No |
| 6 | Primeros vehículos sobre el puente | 3 | 22,7 % | Sí |
| 7 | Llega maquinaria de perforación al otro lado de la vía | 1 | 19,5 % | Sí |
| 8 | Se retira la máquina perforadora | 1 | 4,7 % | No |
| 9 | Movimiento de tierra al otro lado de la vía | 4 | 5,6 % | No |

El índice coincide con un pico en 5 de 9 hitos; con ventanas del mismo largo, por azar se esperarían unos 2. De los 16 picos, 6 caen dentro de un hito. Los otros 10 (12-13 de octubre, 26-27 de noviembre, 15-16 de diciembre, 5-7 y 14 de marzo) corresponden, al revisar sus fotos, a tráfico detenido en la segunda vista (camiones en fila que la mediana no borra), maquinaria que cambia de lugar sin que sea un hito y ramas cercanas a la cámara.

**Utilidad.** El índice detecta cambios grandes de estructura (la losa, el pavimento, maquinaria que llega) y no detecta cambios finos o lejanos (barandas, líneas pintadas, la perforadora que se retira al fondo, tierra removida). Sirve como alerta para decidir qué días revisar, no para identificar cambios por sí solo. La validación es optimista: los parámetros (constante del término de estructura, porcentaje de zona excluida) se ajustaron revisando a ojo los picos falsos de una primera versión, que eran sobre todo desalineos y cambios de luz, con estos mismos hitos a la vista. En la segunda vista, donde la cámara muestra casi solo la vía, el índice mide sobre todo tráfico.

## 8. Estructura de la aplicación y cómo responde cada visualización

La aplicación tiene una franja fija con el nombre del puente, la fuente y la fecha de la última foto, y tres pestañas. La primera es para la ciudadanía y evita términos técnicos; las otras dos son para auditoría y usan los términos del procesamiento (vista de la cámara, corrimiento, criterio de exclusión).

| Pestaña y elemento | Parte de la pregunta | Principio aplicado |
|---|---|---|
| **La historia** · frase de estado y tres cifras | ¿Qué cambió? | Jerarquía: lo esencial primero, siempre visible al abrir |
| · Partes 1 y 2: recorrido con foto fija (scrollytelling) con antes y después de cada hito y línea de tiempo compacta | ¿Qué cambió y cuándo? | Narrativa y anotación; el cambio se ve en el mismo lugar de la foto; la claridad comunica la incertidumbre |
| · Parte 3: time-lapse con un cuadro por día y pausas «sin foto» | ¿Cómo está hoy? ¿Qué días faltan? | Animación con control del lector; la falta de evidencia se muestra en lugar de saltarse |
| · Cierre: un punto por foto, por mes | ¿Qué días no hay evidencia? | Visualización de unidades; el estado se lee por color y por posición, con cifras en texto |
| **Explorar y verificar** · detalle de cualquier día, comparador libre, lista de hitos | Verificación | Detalles a pedido; cada cifra se puede rastrear hasta el día y la foto |
| **Datos y método** · días por mes, motivos de exclusión, índice de cambio, método y descargas | Verificación y método | Transparencia: criterios, validación del algoritmo y datos descargables |

Para que el lector no dependa de su memoria, la historia tiene botones para saltar a cualquier parte y cierra con un resumen de todos los hitos. Para que el auditor pase de una alerta a la evidencia en un paso, cada hito, cada pico del índice y el día que muestra el time-lapse tienen «Ver en detalle», que abre ese día o ese par de fechas en «Explorar y verificar». El comparador tiene tres modos (barra, lado a lado y parpadeo) y, para dos días con evidencia consecutivos, superpone el mapa de cambio del índice (`app/static/cambio/`), de modo que cada pico se puede contrastar con las zonas que lo produjeron. Todas las fotos se pueden ampliar a pantalla completa.

El recorrido usa un componente propio de Streamlit (`st.components.v2`): la foto queda fija con `position: sticky` y, con cada desplazamiento, se calcula qué bloque de texto pasó la línea de lectura. Funcionó de forma estable dentro de las pestañas en escritorio y en celular (390 píxeles de ancho), por lo que no fue necesario recurrir a pasos con botones Anterior/Siguiente.

Azul significa «hay evidencia» y bermellón «no hay evidencia» en toda la aplicación, una combinación distinguible con daltonismo. Para el estado de cada foto se suman ocre (excluida por calidad) y violeta (de noche); la paleta de cuatro colores se validó en modo claro y oscuro (separación para los tres tipos de daltonismo y contraste mínimo de 3:1 con el fondo). Ningún elemento depende solo del color: el calendario usa relleno, rayado y contorno; la figura de puntos, la posición de cada grupo; el índice, la intensidad de la barra y una línea de umbral. Todas las fotos tienen texto alternativo, cada gráfico tiene una descripción en texto y los controles (pasos del recorrido, time-lapse, calendarios y comparadores) pueden usarse con teclado. La redacción es impersonal.

## 9. Decisiones y descartes

Se evaluó y se dejó fuera el conteo de personas y maquinaria, la detección automática de equipo de seguridad y la detección de lluvia, por tres razones:

- No existe un dato de referencia contra el cual validar esos conteos.
- La resolución de la cámara es baja y la nitidez disminuye en la segunda vista.
- En la prueba exploratoria de sitios existentes realizada en el curso, la detección automática de cascos y chalecos fue el elemento que menos confianza generó.

Se prefirió mostrar menos información, pero toda comprobable por quien mira la fotografía. Por la misma razón no se muestran porcentajes de avance, plazos ni montos. El índice de cambio sí se incluye porque se puede verificar: cada pico se contrasta con las fotos del día en «Explorar y verificar» y con los hitos identificados a mano, y la aplicación muestra cuántos acierta y cuántos no.

En la reestructuración para el público auditor se eliminó el resumen «Qué pasó cada mes» y el mapa de calor por hora de la versión anterior: lo primero queda cubierto por el recorrido y la lista de hitos, y lo segundo por el detalle de fotos por hora de cada día y por la figura de puntos.

## 10. Limitaciones

- La cámara es de baja resolución; algunos cambios pequeños no pueden distinguirse.
- La aplicación muestra una foto por día, cercana al mediodía; lo que ocurre a otras horas no se ve.
- Los cambios se identificaron por observación y dependen del criterio del equipo.
- Hay 42 días sin evidencia, entre ellos 26 seguidos, en los que la obra pudo cambiar sin quedar registrada.
- Las fechas de cada cambio son un intervalo entre dos fotos, no el momento exacto en que ocurrió.
- En la segunda vista de la cámara el puente ya está en servicio y no se identificaron cambios claros.
- El índice de cambio no detecta cambios finos o lejanos y marca como cambio el tráfico detenido y la maquinaria que se mueve; sus parámetros se ajustaron con los mismos hitos con que se valida (sección 7).
- La cámara se desplaza casi a diario; en 4 días no se pudo alinear con el anterior y la alineación de esos días es aproximada en el comparador y el time-lapse.
- El time-lapse muestra la foto útil más cercana al mediodía; en 5 días esa foto se aleja más de 30 minutos (la hora se resalta en pantalla). Reproducirlo completo descarga unos 18 MB de fotos.
- La aplicación incluye etiquetas para lectores de pantalla, pero todavía no se ha probado con uno.

## 11. Reproducibilidad

Con las fotografías originales en `data/raw_data/`, los scripts se ejecutan en orden:

```bash
python src/01_inventario.py
python src/02_tramos_encuadre.py
python src/03_orientacion.py
python src/04_fotos_utilizables.py
python src/05_hojas_semanales.py
python src/06_fotos_app.py
python src/07_indice_cambio.py
```

El 25 de noviembre de 2026 se ejecutó la cadena de `01` a `06` desde cero y los archivos resultantes fueron idénticos a los versionados; `07` se agregó el 26 de noviembre. La aplicación solo lee la carpeta `app/` (156 fotos reducidas a 960 px en `app/static/fotos/` y las tablas resumidas en `app/datos/`, 19,4 MB), por lo que puede ejecutarse y desplegarse sin las fotografías originales.

Herramientas: Python, OpenCV, pandas, Plotly y Streamlit; control de versiones con Git y GitHub.
