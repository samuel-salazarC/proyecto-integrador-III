# Proyecto Integrador III · Visualización de datos

Visualización de los cambios visibles en la obra del puente sobre el río María Aguilar (PROERI) a partir de las fotografías capturadas por el sistema dIAra de la Contraloría General de la República (CGR). El proyecto responde: **¿qué cambios se observan en la obra, cuándo ocurrieron y qué días no hay evidencia fotográfica?**

**Público.** El público principal es el perfil de auditor o consultor de la CGR, que necesita verificar cada afirmación contra las fotos y los datos; se mantiene una capa ciudadana, sin tecnicismos, en la primera pestaña de la app. No se usan datos externos a las fotografías.

Curso: Visualización de datos (BCD 8215), Lead University · III cuatrimestre 2026.

## Datos

- **Fuente:** carpeta `proeri_proyecto1` del proyecto dIAra (CGR).
- **Contenido:** ~21 600 fotografías originales, del 2 de octubre de 2025 al 17 de abril de 2026, organizadas en carpetas por fecha (`YYYYMMDD/YYYYMMDD-HHMMSS.jpg`).
- **Uso:** la CGR confirmó que las imágenes son de uso público y no contienen información sensible.
- Las fotografías originales **no se incluyen en el repositorio** por su tamaño. Para reproducir el proyecto, copie las carpetas por fecha y `control.csv` en `data/raw_data/`. No se utilizan las carpetas `imagenes_tratadas` ni `analisis_cambio_camara`.

## Estructura

```
app/
  streamlit_app.py # app web (solo lee archivos de app/)
  requirements.txt # dependencias mínimas para el despliegue
  static/fotos/    # fotos reducidas e índice (generadas por 06; se sirven por URL)
  datos/           # tablas livianas para la app (generadas por 06 y 07)
data/
  raw_data/        # fotografías originales (no versionadas)
  processed_data/  # tablas generadas por el procesamiento
reports/
  revision_tramos/ # hojas de contacto para revisión visual
  hitos/           # hojas semanales y diarias para identificar hitos de la obra
  indice_cambio/   # hoja de picos, zona analizada y registro diario del índice de cambio (07)
  app_v1/ … app_v4/ # capturas de la app en cada ronda de rediseño
src/               # scripts de procesamiento, en orden numérico
```

## Procesamiento

Ejecutar en orden (las fotografías originales solo se leen, nunca se modifican):

```bash
python src/01_inventario.py        # inventario y calidad de cada foto
python src/02_tramos_encuadre.py   # tramos de encuadre fijo y días que muestran la obra
python src/03_orientacion.py       # orientación detectada de cada foto (después de 02)
python src/04_fotos_utilizables.py # tabla final de fotos utilizables y resumen diario final
python src/05_hojas_semanales.py   # hojas semanales por encuadre para identificar hitos
python src/06_fotos_app.py         # fotos reducidas y tablas para la app (después de anotar hitos.csv)
python src/07_indice_cambio.py     # índice de cambio visual y alineación diaria (después de 06)
```

La tabla para usar en adelante es `data/processed_data/fotos_utilizables.csv` (una fila por fotografía, con `utilizable`, `motivo_exclusion`, `tipo_exclusion`, `tramo_id`, `encuadre_id` y `rotacion_desde_crudo`), junto con `resumen_diario_final.csv` (por día, con `fotos_utiles` y `foto_del_dia` calculados solo con fotos utilizables).

Las correcciones a mano van en `data/processed_data/revision_manual.csv` (columnas `fecha`, `ruta`, `obra_visible`, `tramo_id`, `rotacion`, `nota`); los scripts las aplican sobre el resultado automático y registran qué cambió. Las hojas de contacto para revisión visual quedan en `reports/revision_tramos/`.

- **Tramo y encuadre.** `tramo_id` agrupa periodos en que la imagen no cambia; `encuadre_id` agrupa tramos con la misma vista física de la cámara. Para comparar antes y después de la obra se usa `encuadre_id`.
- **Fotos utilizables.** Una foto es utilizable si es diurna, legible y con luz suficiente, su día muestra la obra, su orientación está resuelta y no está dañada, sobreexpuesta, empañada ni es nocturna con focos. El tipo de exclusión es una clasificación aproximada por reglas de imagen (umbrales al inicio de `04_fotos_utilizables.py`).

### Hitos de la obra

Los hitos (cambios visibles en la obra) **se identifican a mano**; `05_hojas_semanales.py` solo prepara el material:

- **Foto semanal.** Por cada semana (lunes a domingo) y `encuadre_id`, entre los días con `estado_dia_final == CON_EVIDENCIA` se elige la `foto_del_dia` con mayor `nitidez`. Una semana repartida entre dos encuadres (2026-01-12 a 2026-01-18) aparece en la hoja de cada uno; una semana sin días con evidencia queda como celda «sin evidencia». Las semanas del periodo sin vista de la obra (2026-02-09 a 2026-03-01) no tienen encuadre y no aparecen. La selección queda en `data/processed_data/fotos_semanales.csv` (`semana_inicio`, `encuadre_id`, `ruta`, `fecha_hora`, `nitidez`).
- **Hojas.** `reports/hitos/semanas_encuadre_<id>.jpg` (miniaturas de 640 px en orden cronológico, con fecha y hora encima; se dividen en `_parte1`, `_parte2`... si no caben). Siguen la regla para mostrar de abajo.
- **Modo diario.** Para acotar la fecha de un cambio que se ve entre dos semanas: `python src/05_hojas_semanales.py --dias 2025-10-06 2025-10-12` genera `reports/hitos/dias_<inicio>_<fin>.jpg` con la foto del día de cada día del rango (celda «sin evidencia» con el estado del día donde no hay).
- **Anotación.** Los hitos se anotan en `data/processed_data/hitos.csv` (`fecha_inicio`, `fecha_fin`, `encuadre_id`, `titulo`, `descripcion`, `ruta_foto_antes`, `ruta_foto_despues`, `confianza` alta/media/baja, `identificado_por` y, opcional, `resumen`, que la app ya no usa). El script la crea solo si no existe, con el hito ya identificado (colocación de la losa del puente, 2025-10-08 a 2025-10-09); si existe, no la toca.

### Regla para mostrar las fotos

Para mostrar una foto (app, hojas de contacto, fotos reducidas), **abrirla ignorando la etiqueta EXIF y girarla `rotacion_desde_crudo` grados** (180 en todas las fotos):

```python
import cv2
imagen = cv2.imread(ruta, cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
imagen = cv2.rotate(imagen, cv2.ROTATE_180)   # rotacion_desde_crudo == 180
```

Con Pillow: `Image.open(ruta)` sin `ImageOps.exif_transpose`, y luego `imagen.rotate(180)`. Es la regla que siguen las hojas de contacto de 02, 03 y 04 y las hojas de hitos de 05.

### Por qué: la etiqueta EXIF Orientation

Los píxeles guardados en los JPG están **siempre al revés**; lo que cambia es la etiqueta EXIF *Orientation* (274). Hasta el 2025-10-09 a las 15:30 las fotos traen `Orientation = 3` («girar 180°») y desde las 15:35 no la traen. Además, dos fotos (2025-10-07 13:27:40 y 2025-10-08 17:04:42) traen por error `Orientation = 6` («girar 90°»), aunque sus píxeles están al revés como los demás. Por eso, según cómo se abra el archivo, la misma foto se ve derecha, al revés o de lado:

- `cv2.imread` / `cv2.imdecode` **aplican** la etiqueta (salvo con `IMREAD_IGNORE_ORIENTATION`).
- Pillow (`Image.open`) **no** la aplica, salvo que se use `ImageOps.exif_transpose(imagen)`.

Ignorar la etiqueta y girar siempre 180° da el mismo resultado en todas las fotos y no depende de una etiqueta que a veces viene mal. La columna `rotacion` de `orientacion_fotos.csv` (0 o 180) es la orientación que detecta 03 sobre la imagen **con la etiqueta ya aplicada**; se conserva como comprobación (coincide con la etiqueta en todas las fotos), pero para mostrar se usa `rotacion_desde_crudo`. Ese cambio de etiqueta es también la `ROTACION_180` del 2025-10-09 que separa los tramos 1 y 2: la cámara no se movió.

## App web

`app/streamlit_app.py` es la app del proyecto: «Puente sobre el río María Aguilar: lo que muestran las fotos». Una franja fija con el nombre del puente, la fuente y la fecha de la última foto queda sobre tres pestañas. Las pestañas guardan su estado y se reflejan en la URL (`?pestana=Explorar+y+verificar`), así que un enlace puede abrir directamente una de ellas:

- **La historia** (capa ciudadana, sin tecnicismos). Arriba, lo esencial: estado de la obra según las fotos y tres cifras. Sobre el recorrido, una fila de botones «Ir a» salta a cualquier parte (Inicio, cada hito por su número, Hoy, Lo que no se ve). Luego un recorrido en tres partes y un cierre, con una barra que indica en qué parte va el lector, y al final una tarjeta de resumen con todos los hitos (número, título, fechas y claridad):
  1. *Al inicio*: la primera foto útil.
  2. *Qué cambió*: scrollytelling con un componente propio (`st.components.v2`). La foto queda fija y los bloques de texto avanzan al desplazarse; cada hito tiene un bloque «antes» y uno «después» que cambian la foto en el mismo lugar (la de después alineada a la de antes), y una línea de tiempo compacta marca el hito actual. Teclado: Tab recorre los bloques; un botón alterna antes y después.
  3. *Cómo está hoy*: time-lapse con la foto del día de cada día (la útil más cercana a las 12:00), reproducir/pausar, tres velocidades, barra para ir a cualquier día, fecha y hora visibles (resaltada si la foto se aleja más de 30 min del mediodía) y un cuadro «sin foto» en los días sin evidencia, para que la falta se vea como una pausa. Marca el cambio de vista del 4 de marzo. Las fotos se estabilizan con la alineación diaria de 07.
  4. *Lo que no se ve*: una fila por mes en la que cada punto es una foto (las 21 644), agrupadas por estado (útil, excluida por calidad, de noche, sin vista de la obra) en ese orden y con sus cifras en texto: el estado se lee por color y por posición.
- **Explorar y verificar** (auditoría), en este orden: calendario para elegir cualquier día; foto del día; datos del día (fotos tomadas, utilizables, excluidas por criterio, índice de cambio, fotos por hora y botón para compararlo con el día con evidencia anterior); comparador de dos fechas, con el calendario para cambiarlas debajo; lista completa de hitos con su claridad.
  - **Comparador** en tres modos: barra deslizante, lado a lado y parpadeo (alterna las fotos cada 0,8 s, con pausa). Dentro de una vista, la foto de después se alinea a la de antes. Si las dos fechas son días con evidencia consecutivos, «Mostrar dónde cambió» superpone en magenta el mapa de cambio de 07.
- **Datos y método** (auditoría): días por mes según evidencia, fotos por motivo de exclusión, índice de cambio visual con su validación contra los hitos, resumen del método, enlace a la nota metodológica y descarga de las tablas de `app/datos` en CSV. En celular, el gráfico del índice se desplaza en horizontal y un aviso recomienda revisarlo en computadora o con el teléfono en horizontal.

**Del dato a la evidencia.** «Ver en detalle» (en cada hito del recorrido, del resumen y de la lista; en cada pico del índice, como botón o tocando su barra; y en el día que muestra el time-lapse) deja elegido ese día o ese par de fechas en «Explorar y verificar», cambia a esa pestaña, desplaza la página hasta el comparador o el detalle del día y muestra un aviso con lo que se abrió. En el calendario de «Explorar y verificar» tocar un día ya muestra su detalle.

**Fotos ampliables.** Tocar cualquier foto (recorrido, time-lapse, comparador, detalle del día) o su botón «Ampliar» la abre a pantalla completa, con acercar/alejar (también + y −), paso entre antes y después y «Cerrar»; Escape cierra y el foco vuelve a donde estaba.

Todo se calcula de `app/datos`, sin depender de un número fijo de hitos. Cada gráfico tiene una descripción en texto; las fotos, texto alternativo; los controles funcionan con teclado y la app se adapta a modo claro y oscuro (tema en `.streamlit/config.toml`). Azul significa «hay evidencia» y bermellón «no la hay»; para el estado de cada foto se suman ocre (calidad) y violeta (noche), paleta validada para daltonismo en ambos modos.

La app **solo lee archivos de `app/`**, así que funciona sin `data/raw_data`:

- `app/static/fotos/` (de 06): la foto del día de cada día con evidencia y las fotos de `hitos.csv`, reducidas a 960 px de ancho (JPEG calidad 80, sin EXIF, con la regla para mostrar ya aplicada), e `indice.csv`. Están en `static/` porque el recorrido y el time-lapse las piden por URL (`server.enableStaticServing = true` en `.streamlit/config.toml`).
- `app/datos/` (de 06): `dias.csv` (estado, vista, fotos, fotos útiles, foto del día y fotos excluidas por motivo), `fotos.csv` (una fila por foto: fecha, hora y estado, sin rutas ni columnas técnicas), `hitos.csv` y `vistas.csv`. De 07: `indice_cambio.csv`, `alineacion_dia.csv` (transformación de cada día al marco del primer día de su vista; la usan el comparador, el recorrido y el time-lapse) y `app/static/cambio/<fecha>.png` (mapa de cambio de cada día con índice, PNG con transparencia de 320 px, ~0,7 MB en total). Las rutas de fotos son relativas a `app/` (`static/fotos/<archivo>.jpg`).
- **Vista.** La app agrupa los encuadres 1 y 2 como una sola vista (el 2026-01-17 la cámara solo se corrió ~31 px) y usa `vista` en vez de `encuadre_id`; el único cambio de vista es el del 2026-03-04. Dentro de una vista la cámara además se desplaza unos píxeles casi a diario (hasta ~74 px y 1,7° en la primera vista); 07 lo mide y la app lo corrige.

### Índice de cambio visual (07)

`src/07_indice_cambio.py` compara, para cada día con evidencia, su imagen con la del día con evidencia anterior de la misma vista: mediana de hasta 5 fotos utilizables cercanas a la foto del día (borra vehículos y personas que pasan), registro contra el día anterior (ORB + RANSAC o, si no alcanza, ECC, partiendo del corrimiento medido por 06), diferencia de estructura (término de contraste y estructura del SSIM, poco sensible a la luz), exclusión del 30 % de la imagen que más cambia siempre (vegetación, ramas, nubes) y atenuación del tráfico habitual. El índice es el % de la zona analizada que cambió; un día es pico si está en el 10 % más alto de su vista. Con los 9 hitos actuales coincide con un pico en 5 (por azar se esperarían ~2) y 6 de 16 picos caen dentro de un hito: sirve como alerta, no para identificar cambios por sí solo. Detalle y limitaciones en la nota metodológica; hoja de revisión en `reports/indice_cambio/`.

Cada vez que se agregan o corrigen hitos en `data/processed_data/hitos.csv` hay que volver a correr `python src/06_fotos_app.py` (agrega las fotos nuevas y borra las que ya no se usan) y `python src/07_indice_cambio.py` (la validación usa los hitos). `app/` pesa unos 20 MB y se versiona.

Para correrla localmente:

```bash
streamlit run app/streamlit_app.py
```

Para desplegarla en [Streamlit Community Cloud](https://share.streamlit.io): *Create app* → elegir este repositorio y la rama `main`, **archivo principal `app/streamlit_app.py`**, y en *Advanced settings* la **versión de Python igual a la local** (3.13). Community Cloud instala `app/requirements.txt` (el de la carpeta del archivo principal), que tiene solo lo que usa la app; el `requirements.txt` de la raíz es el entorno completo de análisis.

## Instalación

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Documentación

La [nota metodológica](docs/nota_metodologica.md) describe el público, la procedencia de los datos, la depuración, la identificación de los cambios, el índice de cambio visual, la estructura de la app, las decisiones de diseño y las limitaciones.

## Equipo

- José Ignacio Sánchez Víquez
- Samuel Salazar Calvo
- Roselind Vargas
- Honwi Zhen Feng