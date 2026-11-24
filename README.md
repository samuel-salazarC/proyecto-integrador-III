# Proyecto Integrador III · Visualización de datos

Visualización del avance del Puente María Aguilar (PROERI) a partir de las fotografías capturadas por el sistema dIAra de la Contraloría General de la República (CGR). El proyecto responde una pregunta ciudadana: **¿qué cambios se observan en la obra, cuándo ocurrieron y qué días no hay evidencia fotográfica?**

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
  fotos/           # fotos reducidas e índice (generadas por 06)
  datos/           # tablas livianas para la app (generadas por 06)
data/
  raw_data/        # fotografías originales (no versionadas)
  processed_data/  # tablas generadas por el procesamiento
reports/
  revision_tramos/ # hojas de contacto para revisión visual
  hitos/           # hojas semanales y diarias para identificar hitos de la obra
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
- **Anotación.** Los hitos se anotan en `data/processed_data/hitos.csv` (`fecha_inicio`, `fecha_fin`, `encuadre_id`, `titulo`, `descripcion`, `ruta_foto_antes`, `ruta_foto_despues`, `confianza` alta/media/baja, `identificado_por`). El script la crea solo si no existe, con el hito ya identificado (colocación de la losa del puente, 2025-10-08 a 2025-10-09); si existe, no la toca.

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

`app/streamlit_app.py` es la app del proyecto, para la ciudadanía: cifras clave, la obra y la cámara, lo que se ve (una foto por semana con los cambios identificados, antes y después de cada cambio y un comparador con barra deslizante entre dos fechas) y lo que no se ve (calendario de evidencia por día y hora, resumen por mes y por qué faltan datos).

La app **solo lee archivos de `app/`**, así que funciona sin `data/raw_data`. Esos archivos los genera `06_fotos_app.py`:

- `app/fotos/`: la foto del día de cada día con evidencia y las fotos de `hitos.csv` y `fotos_semanales.csv`, reducidas a 960 px de ancho (JPEG calidad 80, sin EXIF, con la regla para mostrar ya aplicada); `miniaturas/` con las fotos semanales a 400 px; índice en `indice.csv` (`fecha`, `encuadre_id`, `vista`, `archivo`, `fecha_hora`).
- `app/datos/`: `dias.csv`, `evidencia_dia_hora.csv` (por día y hora 0–23: «hay foto útil», «hay foto pero no se ve la obra» o «no hay foto»), `hitos.csv`, `fotos_semanales.csv` (una foto por semana y vista), `vistas.csv` y `alineacion.csv` (corrimiento de la cámara dentro de una vista, para alinear el comparador), con las rutas de fotos relativas a `app/` (`fotos/<archivo>.jpg`).
- **Vista.** La app agrupa los encuadres 1 y 2 como una sola vista (el 2026-01-17 la cámara solo se corrió ~31 px) y usa `vista` en vez de `encuadre_id`; el único cambio de vista es el del 2026-03-04. `encuadre_id` no cambia en `data/processed_data`.

Cada vez que se agregan o corrigen hitos en `data/processed_data/hitos.csv` hay que volver a correr `python src/06_fotos_app.py`: agrega las fotos nuevas y borra las que ya no se usan. La app no depende de un número fijo de hitos. `app/` pesa unos 20 MB y se versiona.

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

## Equipo

- José Ignacio Sánchez Víquez
- Samuel Salazar Calvo
- Roselind Vargas
- Honwi Zhen Feng