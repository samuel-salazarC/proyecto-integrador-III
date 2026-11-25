# Nota metodológica

Puente sobre el río María Aguilar · Proyecto Integrador III · Visualización de datos (BCD 8215), Lead University, III cuatrimestre 2026.

Esta nota describe de dónde provienen los datos, cómo se depuraron, cómo se identificaron los cambios de la obra y cómo cada visualización de la aplicación responde la pregunta del proyecto. Las cifras corresponden a las tablas de `data/processed_data/` y pueden reproducirse con los scripts de `src/`.

## 1. Objetivo y pregunta

El proyecto busca que una persona sin formación técnica pueda entender, a partir de las fotografías de una cámara instalada en la obra, qué ha cambiado en ella. La pregunta que responde es:

> ¿Qué cambios se observan en la obra, cuándo ocurrieron y qué días no hay evidencia fotográfica?

La aplicación no informa presupuesto, plazos ni porcentaje de avance. Tras la Fase II, la Contraloría General de la República (CGR) indicó que la propuesta debía limitarse a la información disponible hoy, las imágenes con fecha, y no depender de datos certificados por terceros que podrían no existir. También señaló que el público es la ciudadanía y no un perfil consultor.

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

Dentro de la primera vista, el 16 de enero de 2026 la cámara se corrió unos 31 píxeles. La escena es la misma, por lo que la aplicación la trata como una sola vista y, al comparar fechas a ambos lados de ese día, ajusta la segunda foto para que coincida con la primera. Las comparaciones con barra deslizante solo se permiten dentro de una misma vista; entre vistas distintas las fotos se muestran lado a lado con un aviso.

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

## 7. Cómo responde cada visualización

| Elemento de la aplicación | Parte de la pregunta | Principio aplicado |
|---|---|---|
| Portada: comparador entre la primera foto y el 5 de febrero, frase de estado y tres cifras | ¿Qué cambió? | Jerarquía y narrativa: el hallazgo principal va primero |
| Qué pasó cada mes | ¿Cuándo ocurrió? | Resumen por periodo, para no tener que recorrer todas las fotos |
| Línea de tiempo y recorrido de los cambios, con fotos de antes y después | ¿Qué cambió y cuándo? | Anotación e interacción; la etiqueta de claridad comunica la incertidumbre de cada cambio |
| Calendario de evidencia por día | ¿Qué días no hay evidencia? | Divulgación de incertidumbre; cada estado se distingue por color y por forma |
| Comparador libre entre dos fechas | Exploración propia | Interacción y control; solo se pueden elegir días con foto útil |
| Línea final sobre el alcance | Lo que el sitio no dice | Transparencia sobre los límites de los datos |

Dos colores mantienen un significado fijo en toda la página: azul para "hay evidencia" y bermellón para "no hay evidencia", una combinación distinguible para personas con daltonismo. El resto usa tonos neutros. Todas las fotos tienen texto alternativo, cada gráfico tiene una descripción en texto y los controles pueden usarse con teclado. El lenguaje evita términos técnicos y la redacción es impersonal.

## 8. Decisiones y descartes

Se evaluó y se dejó fuera el conteo de personas y maquinaria, la detección automática de equipo de seguridad y la detección de lluvia, por tres razones:

- No existe un dato de referencia contra el cual validar esos conteos.
- La resolución de la cámara es baja y la nitidez disminuye en la segunda vista.
- En la prueba exploratoria de sitios existentes realizada en el curso, la detección automática de cascos y chalecos fue el elemento que menos confianza generó.

Se prefirió mostrar menos información, pero toda comprobable por quien mira la fotografía. Por la misma razón no se muestran porcentajes de avance, plazos ni montos.

## 9. Limitaciones

- La cámara es de baja resolución; algunos cambios pequeños no pueden distinguirse.
- La aplicación muestra una foto por día, cercana al mediodía; lo que ocurre a otras horas no se ve.
- Los cambios se identificaron por observación y dependen del criterio del equipo.
- Hay 42 días sin evidencia, entre ellos 26 seguidos, en los que la obra pudo cambiar sin quedar registrada.
- Las fechas de cada cambio son un intervalo entre dos fotos, no el momento exacto en que ocurrió.
- En la segunda vista de la cámara el puente ya está en servicio y no se identificaron cambios claros.
- La aplicación incluye etiquetas para lectores de pantalla, pero todavía no se ha probado con uno.

## 10. Reproducibilidad

Con las fotografías originales en `data/raw_data/`, los scripts se ejecutan en orden:

```bash
python src/01_inventario.py
python src/02_tramos_encuadre.py
python src/03_orientacion.py
python src/04_fotos_utilizables.py
python src/05_hojas_semanales.py
python src/06_fotos_app.py
```

El 25 de noviembre de 2026 se ejecutó la cadena completa desde cero y los archivos resultantes fueron idénticos a los versionados. La aplicación solo lee la carpeta `app/` (156 fotos reducidas a 960 px y las tablas resumidas, 19,6 MB), por lo que puede ejecutarse y desplegarse sin las fotografías originales.

Herramientas: Python, OpenCV, pandas, Plotly y Streamlit; control de versiones con Git y GitHub.
