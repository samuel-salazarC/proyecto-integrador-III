"""Puente sobre el río María Aguilar: lo que muestran las fotos.

App de una página para la ciudadanía. De arriba abajo: franja con el nombre, la fuente y la
fecha de la última foto; portada («Seis meses de obra vistos por una cámara») con el estado de
la obra según las fotos, un comparador y tres cifras; qué pasó cada mes; recorrido por los cambios; lo que no se ve (calendario de
evidencia); un comparador libre («Explore por su cuenta») y el alcance del sitio.

Solo lee archivos de app/ (generados por src/06_fotos_app.py), así que funciona desplegada
sin las fotos originales. Nada depende de un número fijo de hitos: todo se calcula de
app/datos. El tema (tipografía y fondos) está en .streamlit/config.toml.

Uso local:
  streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import base64
import html
import re
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

APP = Path(__file__).resolve().parent
DATOS = APP / "datos"
REPO_URL = "https://github.com/samuel-salazarC/proyecto-integrador-III"
NOMBRE_OBRA = "Puente sobre el río María Aguilar"

UTIL = "hay foto útil"
NO_SE_VE = "hay foto pero no se ve la obra"
SIN_FOTO = "no hay foto"
ESTADOS = [UTIL, NO_SE_VE, SIN_FOTO]
# Nombre corto de cada estado en el calendario (clase CSS y leyenda)
CLAVE_ESTADO = {UTIL: "util", NO_SE_VE: "nose", SIN_FOTO: "sin"}
LEYENDA = {UTIL: "Con foto útil", NO_SE_VE: "Con foto, sin vista de la obra", SIN_FOTO: "Sin foto"}

# Dos colores con significado fijo en toda la página: azul = hay evidencia de la obra,
# bermellón = no hay evidencia (sólido: no hay foto; tenue: hay foto pero no se ve la obra).
# Azul/bermellón validados para daltonismo (Okabe-Ito); el resto son neutros del tema.
# En el calendario, además del color, cada estado tiene su forma: relleno, rayado o contorno.
COLORES = {
    "light": {"si": "#0072B2", "si_texto": "#FFFFFF", "no": "#D55E00", "no_suave": "#F0B48C", "tinta": "#1A1A19",
              "tenue": "#66635C", "fondo": "#FBFAF7", "borde": "#DEDBD3", "hueco": "rgba(213,94,0,0.13)"},
    "dark": {"si": "#3D9BE0", "si_texto": "#10100F", "no": "#E8743B", "no_suave": "#7E3A16", "tinta": "#EDEBE6",
             "tenue": "#A8A59D", "fondo": "#141413", "borde": "#3A3936", "hueco": "rgba(232,116,59,0.20)"},
}
COLOR_ESTADO = {UTIL: "si", NO_SE_VE: "no_suave", SIN_FOTO: "no"}
CLARIDAD = {"alta": "muy claro", "media": "claro", "baja": "poco claro"}  # según la confianza de hitos.csv
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
MESES_LARGO = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
               "septiembre", "octubre", "noviembre", "diciembre"]
DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
DIAS_LARGO = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
NUMEROS = ["cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez",
           "once", "doce", "trece", "catorce", "quince", "dieciséis", "diecisiete", "dieciocho",
           "diecinueve", "veinte"]
HORAS_LUZ = range(6, 18)  # el detalle por hora muestra de 6:00 a 17:59; de noche no se ve la obra
# Hito que marca el puente en uso (frase de estado y cifras de portada): se busca esta palabra
# en el título. Si ningún hito la tiene, la portada usa el último cambio visible.
PALABRA_PUENTE_EN_USO = "vehículos"
# Marco común de todas las fotos (comparadores y pares antes/después). Las fotos de app/fotos
# miden 960 × 768 px: el contenido de la página no pasa de 960 px para no ampliarlas.
FOTO_RADIO = "10px"
FOTO_PROPORCION = "5 / 4"
ANCHO_CONTENIDO = 960

st.set_page_config(page_title="Puente sobre el río María Aguilar: lo que muestran las fotos", page_icon="🌉",
                   layout="wide")


# ============================================================================
# Datos
# ============================================================================

@st.cache_data
def cargar() -> dict[str, pd.DataFrame]:
    dias = pd.read_csv(DATOS / "dias.csv", parse_dates=["fecha", "fecha_hora_foto"])
    horas = pd.read_csv(DATOS / "evidencia_dia_hora.csv", parse_dates=["fecha"])
    hitos = pd.read_csv(DATOS / "hitos.csv", parse_dates=["fecha_inicio", "fecha_fin", "fecha_hora_antes", "fecha_hora_despues"])
    vistas = pd.read_csv(DATOS / "vistas.csv", parse_dates=["fecha_inicio", "fecha_fin"])
    alineacion = pd.read_csv(DATOS / "alineacion.csv", parse_dates=["fecha"])
    for tabla in (dias, hitos, vistas, alineacion):
        tabla["vista"] = tabla["vista"].astype("Int64")
    hitos = hitos.sort_values(["fecha_inicio", "fecha_fin"]).reset_index(drop=True)
    hitos["numero"] = range(1, len(hitos) + 1)
    if "resumen" not in hitos:
        hitos["resumen"] = pd.NA
    return {"dias": dias, "horas": horas, "hitos": hitos, "vistas": vistas, "alineacion": alineacion}


@st.cache_data
def imagen_base64(ruta: str) -> str:
    return base64.b64encode((APP / ruta).read_bytes()).decode()


def tramos_sin_evidencia(dias: pd.DataFrame) -> pd.DataFrame:
    """Rachas de días consecutivos sin foto útil (inicio, fin, días), de la más larga a la más corta."""
    sin = dias["estado"].ne(UTIL)
    grupo = (sin != sin.shift()).cumsum()
    rachas = dias[sin].groupby(grupo[sin])["fecha"].agg(["min", "max", "size"])
    return rachas.rename(columns={"min": "inicio", "max": "fin", "size": "dias"}).sort_values("dias", ascending=False)


def cambios_de_vista(vistas: pd.DataFrame) -> pd.Series:
    return vistas.sort_values("fecha_inicio")["fecha_inicio"].iloc[1:]


def hito_en_uso(hitos: pd.DataFrame) -> pd.Series | None:
    en_uso = hitos[hitos["titulo"].str.contains(PALABRA_PUENTE_EN_USO, case=False, na=False)]
    return None if en_uso.empty else en_uso.iloc[0]


def ultima_foto(dias: pd.DataFrame) -> pd.Timestamp:
    return dias.loc[dias["fotos"].gt(0), "fecha"].max()


# ============================================================================
# Formato en lenguaje ciudadano
# ============================================================================

def fecha(f: pd.Timestamp, dia_semana: bool = False, anio: bool = True) -> str:
    """Fecha corta: '19 nov 2025' (con dia_semana: 'mié 19 nov 2025')."""
    texto = f"{f.day} {MESES[f.month - 1]}" + (f" {f.year}" if anio else "")
    return f"{DIAS[f.weekday()]} {texto}" if dia_semana else texto


def fecha_larga(f: pd.Timestamp, dia_semana: bool = False) -> str:
    """Fecha para leer en una frase: '19 de noviembre de 2025'."""
    texto = f"{f.day} de {MESES_LARGO[f.month - 1]} de {f.year}"
    return f"{DIAS_LARGO[f.weekday()]} {texto}" if dia_semana else texto


def rango(a: pd.Timestamp, b: pd.Timestamp) -> str:
    if a == b:
        return fecha(a)
    if a.year == b.year and a.month == b.month:
        return f"{a.day}–{b.day} {MESES[a.month - 1]} {a.year}"
    if a.year == b.year:
        return f"{fecha(a, anio=False)} – {fecha(b)}"
    return f"{fecha(a)} – {fecha(b)}"


def rango_largo(a: pd.Timestamp, b: pd.Timestamp) -> str:
    """'del 6 de febrero al 3 de marzo de 2026' (el año se repite solo si cambia)."""
    inicio = f"{a.day} de {MESES_LARGO[a.month - 1]}" + ("" if a.year == b.year else f" de {a.year}")
    return f"del {inicio} al {fecha_larga(b)}"


def hora(f: pd.Timestamp) -> str:
    return f"{f.hour}:{f.minute:02d}"


def plural(n: int, singular: str, plural_: str | None = None) -> str:
    return f"{n} {singular if n == 1 else (plural_ or singular + 's')}"


def palabra(n: int, mayus: bool = False) -> str:
    texto = NUMEROS[n] if 0 <= n < len(NUMEROS) else str(n)
    return mayuscula(texto) if mayus else texto


def mayuscula(texto: str) -> str:
    return texto[:1].upper() + texto[1:]


def enumerar(partes: list[str]) -> str:
    """['a', 'b', 'c'] -> 'a, b y c'."""
    return partes[0] if len(partes) == 1 else ", ".join(partes[:-1]) + " y " + partes[-1]


def primera_frase(texto: str) -> str:
    return re.split(r"(?<=\.)\s+(?=[A-ZÁÉÍÓÚÑ])", str(texto).strip(), maxsplit=1)[0]


def alt_foto(f: pd.Timestamp, extra: str = "") -> str:
    return (f"Foto de la cámara tomada el {fecha_larga(f, dia_semana=True)} a las {hora(f)}: "
            f"vista del puente sobre el río María Aguilar y la vía a su alrededor.{(' ' + extra) if extra else ''}")


def tema() -> str:
    try:
        return "dark" if st.context.theme.type == "dark" else "light"
    except Exception:
        return "light"


# ============================================================================
# Estilo
# ============================================================================

def estilos(c: dict) -> None:
    st.html(f"""<style>
[data-testid="stMainBlockContainer"] {{ max-width: {ANCHO_CONTENIDO + 40}px; padding: 2rem 1.25rem 5rem; }}
h1, h2, h3 {{ font-family: "Source Serif 4", Georgia, serif !important; }}
[data-testid="stHeadingWithActionElements"] h2, [data-testid="stHeadingWithActionElements"] h3 {{ padding-top: 0.2rem !important; }}
h1 {{ font-size: clamp(2.2rem, 1.3rem + 3.8vw, 3.6rem) !important; line-height: 1.05 !important;
      letter-spacing: -0.02em; padding-bottom: 0.3rem !important; }}
h2 {{ font-size: clamp(1.6rem, 1.15rem + 2vw, 2.4rem) !important; line-height: 1.1 !important; letter-spacing: -0.01em; }}
h3 {{ font-size: clamp(1.3rem, 1.05rem + 1vw, 1.7rem) !important; line-height: 1.2 !important; }}
[data-testid="stMarkdownContainer"] p, [data-testid="stCaptionContainer"] p {{ max-width: 68ch; }}

/* Franja superior */
.franja {{ display: flex; flex-wrap: wrap; justify-content: space-between; gap: 0.25rem 1.5rem; padding: 0 0 0.75rem;
           border-bottom: 1px solid {c['borde']}; font-size: 0.88rem; line-height: 1.4; color: {c['tenue']}; }}
.franja b {{ color: {c['tinta']}; font-weight: 700; }}
.franja .datos {{ display: flex; flex-wrap: wrap; gap: 0.25rem 1.25rem; }}
.franja .datos span {{ white-space: nowrap; }}

/* Textos */
.kicker {{ text-transform: uppercase; letter-spacing: 0.09em; font-size: 0.78rem; font-weight: 700;
           color: {c['tenue']}; margin: 0; }}
.bajada {{ font-size: clamp(1.08rem, 1rem + 0.4vw, 1.3rem); line-height: 1.45; color: {c['tenue']};
           max-width: 60ch; margin: 0; }}
.estado {{ font-size: clamp(1.15rem, 1.02rem + 0.55vw, 1.4rem); line-height: 1.4; color: {c['tinta']};
           max-width: 52ch; margin: 0; }}
.estado::before {{ content: ""; display: inline-block; width: 0.6em; height: 0.6em; border-radius: 50%;
                   background: {c['si']}; margin-right: 0.5em; vertical-align: 0.08em; }}
/* Espacio uniforme entre secciones: cada sección empieza con este separador */
.seccion {{ margin: 3.5rem 0 1rem; border-top: 1px solid {c['borde']}; }}

/* Cifras de portada */
.cifras {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.75rem 1.5rem; margin: 0.25rem 0 0; }}
.cifra {{ border-top: 3px solid {c['borde']}; padding-top: 0.6rem; }}
.cifra.si {{ border-top-color: {c['si']}; }} .cifra.no {{ border-top-color: {c['no']}; }}
.cifra .num {{ display: block; font-family: "Source Serif 4", serif; font-weight: 700; line-height: 1;
              font-size: clamp(2rem, 1.5rem + 1.8vw, 2.75rem); color: {c['tinta']}; }}
.cifra .num small {{ font-size: 0.5em; font-weight: 600; margin-left: 0.2em; }}
.cifra .txt {{ display: block; margin-top: 0.35rem; font-size: 0.95rem; line-height: 1.35; color: {c['tenue']}; }}
@media (max-width: 640px) {{
  .cifras {{ grid-template-columns: 1fr; gap: 1rem; }}
}}

/* Qué pasó cada mes */
.meses-resumen {{ margin: 0 !important; padding: 0 !important; }}
.meses-resumen > div {{ margin: 0; display: grid; grid-template-columns: 11rem 1fr; gap: 0.15rem 1.25rem;
                        padding: 0.6rem 0; border-top: 1px solid {c['borde']}; }}
.meses-resumen > div:last-child {{ border-bottom: 1px solid {c['borde']}; }}
.meses-resumen dt {{ font-weight: 700; }}
.meses-resumen dd {{ margin: 0; line-height: 1.45; max-width: 62ch; }}
.meses-resumen .falta {{ color: {c['tenue']}; }}
@media (max-width: 640px) {{ .meses-resumen > div {{ grid-template-columns: 1fr; }} }}

/* Recorrido por los cambios */
.claridad {{ display: inline-block; margin: 0; padding: 0.3rem 0.75rem; border: 1px solid {c['borde']};
             border-radius: 999px; font-size: 0.9rem; color: {c['tenue']}; }}
.claridad b {{ color: {c['tinta']}; }}
.paso {{ font-variant-numeric: tabular-nums; font-weight: 700; text-align: center; margin: 0; }}
.alcance {{ margin: 0; font-size: 0.95rem; color: {c['tinta']}; max-width: 68ch; }}
.leyenda {{ display: flex; flex-wrap: wrap; gap: 0.4rem 1.2rem; font-size: 0.9rem; color: {c['tenue']}; margin: 0.25rem 0; }}
.leyenda span::before {{ content: ""; display: inline-block; width: 0.85em; height: 0.85em; margin-right: 0.4em;
                        vertical-align: -0.05em; border-radius: 2px; background: var(--c); border: 1px solid {c['borde']}; }}

/* Un solo marco para todas las fotos: misma proporción, esquinas y borde; sin ampliar más
   allá de su tamaño real (también en pantalla completa). */
[data-testid="stImage"] img {{ aspect-ratio: {FOTO_PROPORCION}; object-fit: cover; border-radius: {FOTO_RADIO};
                               border: 1px solid {c['borde']}; box-sizing: border-box; max-width: {ANCHO_CONTENIDO}px; }}
[data-testid="stImage"] [data-testid="stImageCaption"], [data-testid="stImage"] + div p {{ font-size: 0.88rem; }}
/* Un solo estilo de botones: el secundario del tema, con zona táctil de 44 px */
.stButton button {{ min-height: 44px; padding: 0.4rem 1rem; }}
</style>""")


def seccion(kicker: str, titular: str, frase: str | None = None) -> None:
    """Encabezado de sección: rótulo, titular con la conclusión y como máximo una frase."""
    st.html(f'<div class="seccion" aria-hidden="true"></div><p class="kicker">{html.escape(kicker)}</p>')
    st.header(titular, anchor=False)
    if frase:
        st.html(f'<p class="bajada">{html.escape(frase)}</p>')


# ============================================================================
# Comparador (portada y "Explore por su cuenta")
# ============================================================================

def corrimientos_entre(alineacion: pd.DataFrame, a: pd.Series, b: pd.Series) -> pd.DataFrame:
    """Corrimientos de la cámara (dentro de la misma vista) entre la fecha de a y la de b."""
    return alineacion[alineacion["vista"].eq(a["vista"]) & (alineacion["fecha"] > a["fecha"])
                      & (alineacion["fecha"] <= b["fecha"])].sort_values("fecha")


def ajuste_css(corrimientos: pd.DataFrame) -> dict | None:
    """Transformación CSS que lleva la segunda foto a la posición de la primera, y el recorte
    (zoom) que oculta los bordes que quedan sin imagen. None si no se puede alinear."""
    if corrimientos.empty or not corrimientos["alinear"].astype(bool).all():
        return None
    ancho, alto = float(corrimientos["ancho"].iloc[0]), float(corrimientos["alto"].iloc[0])
    total = np.eye(3)  # puntos de la primera foto -> segunda foto
    for c in corrimientos.itertuples():
        total = np.array([[c.m00, c.m01, c.m02], [c.m10, c.m11, c.m12], [0, 0, 1]]) @ total
    inversa = np.linalg.inv(total)  # segunda foto -> posición en la primera
    centro = np.array([ancho / 2, alto / 2, 1.0])
    desplazamiento = (inversa @ centro)[:2] - centro[:2]
    esquinas = inversa @ np.array([[0, ancho, 0, ancho], [0, 0, alto, alto], [1, 1, 1, 1]])
    izq = max(esquinas[0, 0], esquinas[0, 2], 0)
    der = min(esquinas[0, 1], esquinas[0, 3], ancho)
    arr = max(esquinas[1, 0], esquinas[1, 1], 0)
    aba = min(esquinas[1, 2], esquinas[1, 3], alto)
    zoom = max(ancho / (der - izq), alto / (aba - arr)) * 1.005
    ventana_x = min(max((izq + der) / 2 - ancho / zoom / 2, izq), der - ancho / zoom)
    ventana_y = min(max((arr + aba) / 2 - alto / zoom / 2, arr), aba - alto / zoom)
    return {"tx": desplazamiento[0] / ancho * 100, "ty": desplazamiento[1] / alto * 100,
            "rot": float(np.degrees(np.arctan2(inversa[1, 0], inversa[0, 0]))),
            "escala": float(np.hypot(inversa[0, 0], inversa[1, 0])),
            "zoom": zoom, "vx": ventana_x / ancho * 100, "vy": ventana_y / alto * 100}


def html_comparador(a: pd.Series, b: pd.Series, texto_a: str, texto_b: str, c: dict, ajuste: dict | None = None) -> str:
    """Comparador antes/después con barra deslizante, sin dependencias externas.

    La foto de después ocupa todo el cuadro y la de antes se recorta desde la izquierda
    hasta la posición de la barra. La barra es un <input type="range"> transparente sobre
    las fotos: se arrastra con el mouse o el dedo y se mueve con las flechas del teclado.
    Con `ajuste`, la foto de después se mueve para coincidir con la de antes y las dos se
    amplían un poco para ocultar los bordes sin imagen. El marco (proporción, esquinas y
    borde) es el mismo de las demás fotos de la página.
    """
    aj = ajuste or {"tx": 0, "ty": 0, "rot": 0, "escala": 1, "zoom": 1, "vx": 0, "vy": 0}
    alt_a = html.escape(alt_foto(a["fecha_hora_foto"], "Foto de la izquierda (antes)."))
    alt_b = html.escape(alt_foto(b["fecha_hora_foto"], "Foto de la derecha (después)."))
    etiqueta = html.escape(f"Barra de comparación: a la izquierda {texto_a}, a la derecha {texto_b}")
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><style>
html, body {{ margin:0; padding:0; background:transparent; font-family:system-ui, sans-serif; }}
.comp {{ position:relative; width:100%; max-width:{ANCHO_CONTENIDO}px; aspect-ratio:{FOTO_PROPORCION}; overflow:hidden;
        border-radius:{FOTO_RADIO}; border:1px solid {c['borde']}; box-sizing:border-box; line-height:0;
        user-select:none; touch-action:pan-y; }}
.comp .lienzo {{ position:relative; transform-origin:0 0; transform:scale({aj['zoom']:.5f}) translate({-aj['vx']:.4f}%, {-aj['vy']:.4f}%); }}
.comp img {{ width:100%; height:auto; display:block; }}
.comp .despues {{ transform-origin:50% 50%;
                 transform:translate({aj['tx']:.4f}%, {aj['ty']:.4f}%) rotate({aj['rot']:.4f}deg) scale({aj['escala']:.5f}); }}
.comp .antes {{ position:absolute; inset:0; clip-path:inset(0 50% 0 0); }}
.comp .linea {{ position:absolute; top:0; bottom:0; left:50%; width:3px; margin-left:-1.5px; background:#fff;
               box-shadow:0 0 4px rgba(0,0,0,.6); pointer-events:none; }}
.comp .asa {{ position:absolute; top:50%; left:50%; width:44px; height:44px; margin:-22px 0 0 -22px; border-radius:50%;
             background:#fff; box-shadow:0 1px 8px rgba(0,0,0,.55); pointer-events:none; display:flex; align-items:center;
             justify-content:center; font:700 18px/1 system-ui, sans-serif; color:#1a1a19; }}
.comp .rotulo {{ position:absolute; top:10px; padding:5px 9px; border-radius:4px; background:rgba(20,20,19,.8); color:#fff;
                font:600 13px/1.2 system-ui, sans-serif; pointer-events:none; }}
.comp .izq {{ left:10px; }} .comp .der {{ right:10px; }}
.comp input {{ position:absolute; inset:0; width:100%; height:100%; margin:0; opacity:0; cursor:ew-resize; }}
.comp:has(input:focus-visible) {{ outline:3px solid {c['tinta']}; outline-offset:-3px; }}
</style></head><body>
<div class="comp">
  <div class="lienzo">
    <img class="despues" src="data:image/jpeg;base64,{imagen_base64(b['foto'])}" alt="{alt_b}">
    <img class="antes" src="data:image/jpeg;base64,{imagen_base64(a['foto'])}" alt="{alt_a}">
  </div>
  <div class="linea"></div><div class="asa" aria-hidden="true">&#8596;</div>
  <span class="rotulo izq" aria-hidden="true">{html.escape(texto_a)}</span>
  <span class="rotulo der" aria-hidden="true">{html.escape(texto_b)}</span>
  <input type="range" min="0" max="100" step="1" value="50" aria-label="{etiqueta}">
</div>
<script>
const c = document.querySelector('.comp'), r = c.querySelector('input');
const zoom = {aj['zoom']:.5f}, vx = {aj['vx']:.4f};
function mover() {{
  const v = r.value, x = vx + v / zoom;  // posición de la barra en la foto (antes del zoom)
  c.querySelector('.antes').style.clipPath = 'inset(0 ' + (100 - x) + '% 0 0)';
  c.querySelector('.linea').style.left = v + '%';
  c.querySelector('.asa').style.left = v + '%';
  r.setAttribute('aria-valuetext', v + ' por ciento de la foto de la izquierda visible');
}}
r.addEventListener('input', mover); mover();
</script></body></html>"""


def mostrar_comparacion(d: dict, c: dict, a: pd.Series, b: pd.Series) -> None:
    """Deslizador si las dos fechas son de la misma vista; si no, las dos fotos lado a lado con aviso.
    Sin notas debajo: los rótulos de las fotos ya dicen las fechas."""
    texto_a, texto_b = fecha(a["fecha"]), fecha(b["fecha"])
    if a["vista"] == b["vista"]:
        ajuste = ajuste_css(corrimientos_entre(d["alineacion"], a, b))
        st.iframe(html_comparador(a, b, texto_a, texto_b, c, ajuste), height="content")
    else:
        st.warning("La cámara apuntaba a otro lugar en una de estas fechas: las fotos no se pueden superponer.",
                   icon="⚠️")
        for col, fila, texto in zip(st.columns(2, gap="medium"), [a, b], [texto_a, texto_b]):
            col.image(str(APP / fila["foto"]), width="stretch", alt=alt_foto(fila["fecha_hora_foto"]), caption=texto)


# ============================================================================
# Franja superior y portada
# ============================================================================

def franja(dias: pd.DataFrame) -> None:
    st.html(f"""<header class="franja">
  <b>{NOMBRE_OBRA}</b>
  <span class="datos"><span>Fotos: CGR, proyecto dIAra</span><span>Última foto: {fecha(ultima_foto(dias))}</span></span>
</header>""")


def titular_portada(dias: pd.DataFrame) -> str:
    """'Seis meses de obra vistos por una cámara': meses entre la primera y la última foto.
    El nombre del puente no se repite: ya está en la franja superior."""
    dias_con_foto = dias.loc[dias["fotos"].gt(0), "fecha"]
    meses = round((dias_con_foto.max() - dias_con_foto.min()).days / 30.44)
    if meses < 2:
        return "La obra vista por una cámara"
    return f"{palabra(meses, True)} meses de obra vistos por una cámara"


def frase_estado(hitos: pd.DataFrame) -> str | None:
    """Estado de la obra según lo que se ve en las fotos, calculado de hitos.csv."""
    uso = hito_en_uso(hitos)
    if uso is not None:
        return f"En las fotos circulan vehículos sobre el puente desde el {fecha_larga(uso['fecha_fin'])}."
    if len(hitos):
        ultimo = hitos.sort_values("fecha_fin").iloc[-1]
        return f"Último cambio visible en las fotos: {ultimo['titulo'][:1].lower() + ultimo['titulo'][1:]}, " \
               f"el {fecha_larga(ultimo['fecha_fin'])}."
    return None


def cifras_portada(dias: pd.DataFrame, hitos: pd.DataFrame) -> list[tuple[str, str, str, str]]:
    """(clase, número, unidad, texto) de cada cifra, calculadas de los datos. No repiten la
    franja (última foto) ni la frase de estado (fecha de los primeros vehículos)."""
    cifras = []
    uso = hito_en_uso(hitos)
    if uso is not None:
        primero = hitos.iloc[0]
        semanas = round((uso["fecha_fin"] - primero["fecha_inicio"]).days / 7)
        cifras.append(("si", str(semanas), "semanas" if semanas != 1 else "semana",
                       f"entre el primer cambio visible ({fecha(primero['fecha_inicio'], anio=False)}) "
                       "y los primeros vehículos"))
    if len(hitos):
        cifras.append(("si", str(len(hitos)), "cambios" if len(hitos) != 1 else "cambio",
                       f"visibles en las fotos, {rango(hitos['fecha_inicio'].min(), hitos['fecha_fin'].max())}"))
    tramos = tramos_sin_evidencia(dias)
    if len(tramos):
        hueco = tramos.iloc[0]
        cifras.append(("no", str(int(hueco["dias"])), "días" if hueco["dias"] != 1 else "día",
                       f"seguidos sin fotos de la obra, {rango(hueco['inicio'], hueco['fin'])}"))
    return cifras


def portada(d: dict, c: dict) -> None:
    dias, hitos = d["dias"], d["hitos"]
    st.title(titular_portada(dias), anchor=False)
    estado = frase_estado(hitos)
    if estado:
        st.html(f'<p class="estado">{html.escape(estado)}</p>')

    # Comparador de portada: primer y último día con foto útil de la primera vista
    utiles = dias[dias["estado"].eq(UTIL)]
    primera_vista = utiles[utiles["vista"].eq(utiles["vista"].iloc[0])]
    mostrar_comparacion(d, c, primera_vista.iloc[0], primera_vista.iloc[-1])

    items = "".join(
        f'<div class="cifra {clase}" role="listitem"><span class="num">{html.escape(num)}<small>{html.escape(unidad)}</small>'
        f'</span><span class="txt">{html.escape(texto)}</span></div>'
        for clase, num, unidad, texto in cifras_portada(dias, hitos))
    st.html(f'<div class="cifras" role="list">{items}</div>')


# ============================================================================
# Qué pasó cada mes
# ============================================================================

def frase_hito(h) -> str:
    """Frase breve del hito ('se pintan las líneas'); si hitos.csv no la trae, el título."""
    if isinstance(h.resumen, str) and h.resumen.strip():
        return h.resumen.strip()
    return h.titulo[:1].lower() + h.titulo[1:]


def dias_sin_evidencia_mes(g: pd.DataFrame) -> str | None:
    """'Sin fotos de la obra del 11 al 13 y del 20 al 21.' para los días de un mes (g)."""
    sin = g["estado"].ne(UTIL).to_numpy()
    if not sin.any():
        return None
    if sin.all():
        return "Sin fotos de la obra en todo el mes."
    fechas = g["fecha"].tolist()
    primero, ultimo = fechas[0], fechas[-1]
    partes, k = [], 0
    while k < len(fechas):
        if not sin[k]:
            k += 1
            continue
        j = k
        while j + 1 < len(fechas) and sin[j + 1]:
            j += 1
        a, b = fechas[k], fechas[j]
        if a == b:
            partes.append(f"el día {a.day}")
        elif a == primero and a.day == 1:
            partes.append(f"hasta el día {b.day}")
        elif b == ultimo and b.day == b.days_in_month:
            partes.append(f"desde el día {a.day}")
        else:
            partes.append(f"del {a.day} al {b.day}")
        k = j + 1
    return f"Sin fotos de la obra {enumerar(partes)}."


def resumen_mensual(d: dict) -> list[tuple[str, str, str | None]]:
    """(mes, lo que cambió, días sin evidencia) por cada mes del periodo."""
    dias, hitos = d["dias"], d["hitos"]
    vistas = cambios_de_vista(d["vistas"])
    filas = []
    for periodo, g in dias.groupby(dias["fecha"].dt.to_period("M")):
        del_mes = hitos[hitos["fecha_fin"].dt.to_period("M").eq(periodo)]
        cambios = (mayuscula(enumerar([frase_hito(h) for h in del_mes.itertuples()])) + "."
                   if len(del_mes) else "Sin cambios visibles en las fotos.")
        for f in vistas[vistas.dt.to_period("M").eq(periodo)]:
            cambios += f" El día {f.day} la cámara empieza a mostrar otra vista."
        filas.append((f"{mayuscula(MESES_LARGO[periodo.month - 1])} de {periodo.year}", cambios,
                      dias_sin_evidencia_mes(g)))
    return filas


def cada_mes(d: dict) -> None:
    seccion("Mes a mes", "Qué pasó cada mes")
    filas = "".join(
        f'<div><dt>{html.escape(mes)}</dt><dd>{html.escape(cambios)}'
        + (f' <span class="falta">{html.escape(falta)}</span>' if falta else "") + "</dd></div>"
        for mes, cambios, falta in resumen_mensual(d))
    st.html(f'<dl class="meses-resumen">{filas}</dl>')


# ============================================================================
# Recorrido por los cambios
# ============================================================================

def titular_cambios(hitos: pd.DataFrame) -> str:
    n = len(hitos)
    if n == 0:
        return "Todavía no hay cambios identificados"
    por_mes = hitos.groupby(hitos["fecha_fin"].dt.to_period("M")).size()
    mes, k = por_mes.idxmax(), int(por_mes.max())
    if n >= 3 and k >= 2 and k > n / 3:
        return f"{palabra(n, True)} cambios visibles; {palabra(k)} de ellos en {MESES_LARGO[mes.month - 1]} de {mes.year}"
    return f"{palabra(n, True)} {'cambio visible' if n == 1 else 'cambios visibles'} entre {fecha(hitos['fecha_inicio'].min())} y {fecha(hitos['fecha_fin'].max())}"


def eje_meses(fig: go.Figure, inicio: pd.Timestamp, fin: pd.Timestamp) -> None:
    meses = pd.date_range(inicio.to_period("M").to_timestamp(), fin, freq="MS")
    fig.update_xaxes(tickvals=[m + pd.Timedelta(days=14) for m in meses],
                     ticktext=[MESES[m.month - 1] + (f"<br>{m.year}" if i == 0 or m.month == 1 else "")
                               for i, m in enumerate(meses)],
                     range=[inicio - pd.Timedelta(days=3), fin + pd.Timedelta(days=3)],
                     ticks="", title=None, showgrid=False, zeroline=False, fixedrange=True)


# Línea de tiempo de los cambios: componente propio (st.components.v2) con un botón real por
# cambio. Plotly no sirve aquí: en pantallas táctiles emite el clic pero no la selección, así
# que tocar un punto no llevaba al cambio. Con botones funciona igual con el dedo, el mouse y
# el teclado (Tab y Enter). Las filas se reparten en el navegador según el ancho real, para
# que los puntos no se toquen. En pantallas angostas (menos de ANGOSTO px) los puntos se
# apilarían: se muestra en cambio una fila de botones numerados de 44 px que salta de línea,
# con la misma etiqueta y la misma marca del cambio elegido. El cambio elegido se nombra
# debajo (titular).
LINEA_CSS = """
.linea { font-family: var(--st-font, sans-serif); color: var(--st-text-color); }
.linea .lienzo { position: relative; }
.linea .hueco { position: absolute; top: 0; bottom: 30px; border-radius: 4px; }
.linea .hueco span { position: absolute; top: 4px; left: 0; right: 0; text-align: center; font-size: 0.72rem;
  line-height: 1.15; font-weight: 600; }
.linea .vista { position: absolute; top: 0; bottom: 30px; border-left: 1.5px dotted var(--st-text-color); opacity: 0.75; }
.linea .vista span { position: absolute; bottom: 2px; left: 5px; font-size: 0.72rem; line-height: 1.15; white-space: nowrap; }
.linea .eje { position: absolute; left: 0; right: 0; bottom: 0; height: 30px; }
.linea .eje span { position: absolute; transform: translateX(-50%); font-size: 0.72rem; line-height: 1.1;
  text-align: center; opacity: 0.72; white-space: nowrap; }
.linea button { position: absolute; width: 32px; height: 32px; margin: -16px 0 0 -16px; padding: 0; border-radius: 50%;
  border: 2px solid var(--st-text-color); background: var(--st-background-color); color: var(--st-text-color);
  font: 700 0.8rem/1 var(--st-font, sans-serif); cursor: pointer; touch-action: manipulation; }
.linea button::after { content: ""; position: absolute; inset: -6px; border-radius: 50%; }
.linea button[aria-current="step"] { background: var(--st-text-color); color: var(--st-background-color);
  width: 36px; height: 36px; margin: -18px 0 0 -18px; }
.linea button:hover { box-shadow: 0 0 0 4px color-mix(in srgb, var(--st-text-color) 18%, transparent); }
.linea button:focus-visible { outline: 3px solid var(--st-text-color); outline-offset: 3px; }
.linea .botones { display: flex; flex-wrap: wrap; gap: 8px; }
.linea .botones button { position: static; width: 44px; height: 44px; margin: 0; font-size: 0.95rem; }
.linea .botones button[aria-current="step"] { width: 44px; height: 44px; margin: 0; }
.linea .botones button::after { display: none; }
"""

LINEA_JS = """
export default function (component) {
  const { data, setTriggerValue, parentElement } = component;
  const SEPARACION = 44, FILA = 46, EJE = 30, ARRIBA = 30, ANGOSTO = 640;
  // Streamlit vuelve a llamar a esta función cuando cambian los datos: se quita lo anterior
  parentElement.querySelectorAll('.linea').forEach((e) => e.remove());
  const raiz = document.createElement('div');
  raiz.className = 'linea';
  raiz.setAttribute('role', 'group');
  raiz.setAttribute('aria-label', 'Línea de tiempo de los cambios');
  parentElement.appendChild(raiz);

  const boton = (p, estilo) => '<button type="button" data-n="' + p.n + '"' + (estilo ? ' style="' + estilo + '"' : '') +
    ' title="' + p.titulo + ' · ' + p.rango + '" aria-label="Cambio ' + p.n + ': ' + p.titulo + ', ' + p.rango + '"' +
    (p.elegido ? ' aria-current="step"' : '') + '>' + p.n + '</button>';

  function activar() {
    raiz.querySelectorAll('button').forEach((b) => {
      b.onclick = () => setTriggerValue('elegido', Number(b.dataset.n));
    });
  }

  function dibujar() {
    const ancho = raiz.clientWidth || 600;
    if (ancho < ANGOSTO) {  // pantalla angosta: fila de botones numerados
      raiz.innerHTML = '<div class="botones">' + data.puntos.map((p) => boton(p)).join('') + '</div>';
      activar();
      return;
    }
    // Filas: cada punto va en la primera fila donde queda a SEPARACION px del anterior
    const ultimo = [], filas = data.puntos.map((p) => {
      const x = p.x / 100 * ancho;
      let f = 0;
      while (ultimo[f] !== undefined && x - ultimo[f] < SEPARACION) f++;
      ultimo[f] = x;
      return f;
    });
    const nFilas = Math.max(1, ...filas.map((f) => f + 1));
    const alto = ARRIBA + nFilas * FILA + EJE;
    let h = '<div class="lienzo" style="height:' + alto + 'px">';
    if (data.hueco) {
      h += '<div class="hueco" style="left:' + data.hueco.x0 + '%;width:' + (data.hueco.x1 - data.hueco.x0) +
           '%;background:' + data.hueco.fondo + ';color:' + data.hueco.color + '"><span>' + data.hueco.texto + '</span></div>';
    }
    data.vistas.forEach((v) => {
      h += '<div class="vista" style="left:' + v.x + '%"><span>' + v.texto + '</span></div>';
    });
    h += '<div class="eje" aria-hidden="true">' + data.meses.map((m) =>
      '<span style="left:' + m.x + '%">' + m.texto + '</span>').join('') + '</div>';
    data.puntos.forEach((p, i) => {
      const y = alto - EJE - FILA / 2 - filas[i] * FILA;
      h += boton(p, 'left:' + p.x + '%;top:' + y + 'px');
    });
    h += '</div>';
    raiz.innerHTML = h;
    activar();
  }

  dibujar();
  const observador = new ResizeObserver(() => {
    if (!raiz.isConnected) { observador.disconnect(); return; }
    dibujar();
  });
  observador.observe(raiz);
  return () => { observador.disconnect(); raiz.remove(); };
}
"""

linea_componente = st.components.v2.component("linea_de_tiempo_cambios", css=LINEA_CSS, js=LINEA_JS)


def datos_linea(d: dict, c: dict, paso: int) -> dict:
    """Posiciones (en % del ancho) de los cambios, el hueco más largo, los cambios de vista y los meses."""
    hitos, dias = d["hitos"], d["dias"]
    inicio, fin = dias["fecha"].min(), dias["fecha"].max()
    margen = 4.0  # % a cada lado para que los puntos de los extremos no se corten

    def x(f: pd.Timestamp) -> float:
        return round(margen + (f - inicio) / (fin - inicio) * (100 - 2 * margen), 3)

    hueco = tramos_sin_evidencia(dias).iloc[0]
    meses = pd.date_range(inicio.to_period("M").to_timestamp(), fin, freq="MS")
    return {
        "puntos": [{"n": int(h.numero), "x": x(h.fecha_fin), "titulo": html.escape(h.titulo),
                    "rango": rango(h.fecha_inicio, h.fecha_fin), "elegido": i == paso}
                   for i, h in enumerate(hitos.itertuples())],
        "hueco": {"x0": x(hueco["inicio"] - pd.Timedelta(hours=12)), "x1": x(hueco["fin"] + pd.Timedelta(hours=12)),
                  "texto": f"{int(hueco['dias'])} días<br>sin fotos<br>de la obra", "fondo": c["hueco"], "color": c["no"]},
        "vistas": [{"x": x(f - pd.Timedelta(hours=12)), "texto": "cambió<br>la vista"} for f in cambios_de_vista(d["vistas"])],
        "meses": [{"x": x(max(m + pd.Timedelta(days=14), inicio)),
                   "texto": MESES[m.month - 1] + (f"<br>{m.year}" if i == 0 or m.month == 1 else "")}
                  for i, m in enumerate(meses)],
    }


def mover_paso(delta: int, total: int) -> None:
    st.session_state.paso = min(max(st.session_state.paso + delta, 0), total - 1)


def historia(d: dict, c: dict) -> None:
    hitos = d["hitos"]
    seccion("Los cambios", titular_cambios(hitos),
            "Toque un número o use los botones Anterior y Siguiente." if len(hitos) else None)
    if hitos.empty:
        return
    total = len(hitos)
    paso = min(st.session_state.setdefault("paso", 0), total - 1)

    resultado = linea_componente(data=datos_linea(d, c, paso), key="linea_de_tiempo", on_elegido_change=lambda: None)
    elegido = getattr(resultado, "elegido", None)
    if elegido is not None and int(elegido) - 1 != paso:
        st.session_state.paso = min(max(int(elegido) - 1, 0), total - 1)
        st.rerun()

    with st.container(horizontal=True, horizontal_alignment="distribute", vertical_alignment="center"):
        st.button("← Anterior", on_click=mover_paso, args=(-1, total), disabled=paso == 0, key="anterior")
        st.html(f'<p class="paso" aria-live="polite">Cambio {paso + 1} de {total}</p>')
        st.button("Siguiente →", on_click=mover_paso, args=(1, total), disabled=paso == total - 1, key="siguiente")

    h = hitos.iloc[paso]
    st.subheader(h["titulo"], anchor=False)
    st.markdown(primera_frase(h["descripcion"]))
    for col, (cuando, foto, momento) in zip(
            st.columns(2, gap="medium"),
            [("Antes", h["foto_antes"], h["fecha_hora_antes"]), ("Después", h["foto_despues"], h["fecha_hora_despues"])]):
        with col:
            if isinstance(foto, str) and (APP / foto).exists():
                st.image(str(APP / foto), width="stretch", alt=alt_foto(momento, f"{cuando} del cambio: {h['titulo']}."),
                         caption=f"{cuando} · {fecha(momento, dia_semana=True)}, {hora(momento)}")
            else:
                st.caption(f"{cuando}: foto no disponible")
    claridad = CLARIDAD.get(str(h["confianza"]).strip().lower())
    if claridad:
        st.html(f'<p class="claridad">Qué tan claro se ve en las fotos: <b>{claridad}</b></p>')

    hueco = tramos_sin_evidencia(d["dias"]).iloc[0]
    vista = cambios_de_vista(d["vistas"])
    with st.expander("Descripción de la gráfica"):
        st.markdown(
            f"Línea de tiempo con {plural(total, 'cambio')} entre el {fecha_larga(hitos['fecha_inicio'].min())} y el "
            f"{fecha_larga(hitos['fecha_fin'].max())}; cada punto numerado es un cambio, ubicado en la fecha en que ya se "
            f"ve. La zona sombreada, {rango_largo(hueco['inicio'], hueco['fin'])}, son días sin "
            "fotos de la obra."
            + (f" La línea punteada marca el {fecha_larga(vista.iloc[0])}, cuando cambió la vista de la cámara."
               if len(vista) else ""))


# ============================================================================
# Calendario de días (componente propio): "Lo que no se ve" y "Explore por su cuenta"
# ============================================================================

# Una cuadrícula por mes con los días de la semana. Cada día se distingue por color y por
# forma: relleno azul (con foto útil), rayado (con foto, sin vista de la obra) y contorno
# punteado (sin foto). Dos modos:
#   ver     solo lectura, celdas pequeñas; todos los meses a la vista.
#   elegir  los días con foto útil son botones de 44 px; se eligen dos fechas para comparar.
#           Los meses van en una fila con desplazamiento horizontal. Teclado: Tab entra al
#           calendario, las flechas recorren los días elegibles, Inicio/Fin van al primero y
#           al último, Enter o Espacio eligen.
CALENDARIO_CSS = """
.cal { position: relative; font-family: var(--st-font, sans-serif); color: var(--tinta); }
.cal td, .cal .dia, .cal .meses { position: relative; }
.cal .sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
.cal button { font: inherit; color: inherit; -webkit-tap-highlight-color: transparent; touch-action: manipulation; }

/* Estados: color + forma (también en la leyenda) */
.cal .c { position: relative; display: flex; align-items: center; justify-content: center; box-sizing: border-box;
  width: 100%; height: 100%; border-radius: 5px; border: 1.5px solid transparent; font-variant-numeric: tabular-nums; }
.cal .c.util { background: var(--si); color: var(--si-texto); }
.cal .c.nose { border-color: var(--no); color: var(--tinta);
  background: repeating-linear-gradient(135deg, var(--no-suave) 0 2.5px, transparent 2.5px 6px); }
.cal .c.sin { border: 1.5px dashed var(--no); color: var(--tinta); }
.cal .c.fuera { color: var(--tenue); opacity: 0.5; }
.cal .c.sel { background: var(--tinta); color: var(--fondo); }

.cal .leyenda { list-style: none; display: flex; flex-wrap: wrap; gap: 0.4rem 1.25rem; padding: 0; margin: 0 0 0.9rem;
  font-size: 0.9rem; color: var(--tenue); }
.cal .leyenda li { display: flex; align-items: center; gap: 0.45rem; }
.cal .leyenda b { color: var(--tinta); font-variant-numeric: tabular-nums; }
.cal .leyenda .c { width: 1.15rem; height: 1.15rem; border-radius: 4px; }

.cal table { border-collapse: collapse; border-spacing: 0; table-layout: fixed; width: calc(7 * var(--celda)); }
.cal caption { text-align: left; font-weight: 700; font-size: 0.95rem; padding: 0 0 0.3rem; }
.cal th { font-size: 0.7rem; font-weight: 600; color: var(--tenue); height: 1.4rem; padding: 0; }
.cal td { width: var(--celda); height: var(--celda); padding: var(--hueco); box-sizing: border-box; }

/* ver: todos los meses en una cuadrícula que se acomoda al ancho */
.cal.ver { --celda: 28px; --hueco: 1.5px; }
.cal.ver .c { font-size: 0.7rem; }
.cal.ver .meses { display: grid; grid-template-columns: repeat(auto-fill, minmax(calc(7 * var(--celda)), 1fr));
  gap: 1.25rem 1.5rem; }
@media (max-width: 640px) {
  .cal.ver { --celda: 21px; --hueco: 1px; }
  .cal.ver .c { font-size: 0.6rem; border-radius: 3px; }
  .cal.ver .meses { gap: 1rem; }
}

/* elegir: botones de 44 px, meses en fila con desplazamiento horizontal */
.cal.elegir { --celda: 44px; --hueco: 3px; }
.cal.elegir td { padding: 0; }
.cal.elegir .dia { display: block; width: var(--celda); height: var(--celda); padding: var(--hueco); margin: 0;
  border: 0; background: none; box-sizing: border-box; }
.cal.elegir button.dia { cursor: pointer; border-radius: 8px; }
.cal.elegir button.dia:hover .c { box-shadow: 0 0 0 2px var(--tinta); }
.cal.elegir button.dia:focus-visible { outline: 3px solid var(--tinta); outline-offset: -1px; }
.cal.elegir .c { font-size: 0.85rem; }
.cal.elegir .c.util, .cal.elegir .c.sel { font-weight: 700; }
.cal .marca { display: inline-flex; align-items: center; justify-content: center; min-width: 18px; height: 18px;
  border-radius: 9px; box-sizing: border-box; border: 1.5px solid var(--tinta); background: var(--fondo);
  color: var(--tinta); font-size: 0.7rem; font-weight: 700; line-height: 1; }
.cal .c .marca { position: absolute; top: -6px; right: -6px; }
.cal.elegir .meses { display: flex; gap: 16px; overflow-x: auto; scroll-snap-type: x mandatory; overscroll-behavior-x: contain;
  padding: 2px 2px 10px; scrollbar-width: thin; }
.cal.elegir .mes { flex: 0 0 auto; scroll-snap-align: start; }

/* Controles (mismo estilo que los botones del resto de la página) */
.cal .controles { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem; margin: 0 0 0.6rem; }
.cal .boton { min-height: 44px; display: inline-flex; align-items: center; gap: 0.6rem; padding: 0.35rem 0.9rem;
  border: 1px solid var(--borde); border-radius: var(--radio); background: transparent; cursor: pointer; text-align: left; }
.cal .boton:hover { border-color: var(--tinta); }
.cal .boton:focus-visible { outline: 3px solid var(--tinta); outline-offset: 2px; }
.cal .boton:disabled { opacity: 0.4; cursor: default; border-color: var(--borde); }
.cal .ranura { padding-left: 0.6rem; }
.cal .ranura .rot { display: block; font-size: 0.78rem; color: var(--tenue); line-height: 1.2; }
.cal .ranura b { display: block; line-height: 1.25; }
.cal .ranura[aria-pressed="true"] { border-color: var(--tinta); box-shadow: inset 0 0 0 1px var(--tinta); }
.cal .nav { margin-left: auto; display: flex; gap: 0.5rem; }
.cal .nav .boton { width: 44px; justify-content: center; padding: 0; font-size: 1.2rem; }
.cal .aviso { margin: 0 0 0.6rem; font-size: 0.95rem; min-height: 1.4em; }
@media (max-width: 640px) { .cal .nav { margin-left: 0; } }
"""

CALENDARIO_JS = """
const memoria = new Map();  // estado de cada calendario entre redibujos: ranura activa, foco, desplazamiento

export default function (component) {
  const { data, setTriggerValue, parentElement } = component;
  const m = memoria.get(data.id) || {};
  memoria.set(data.id, m);
  // Si el foco estaba dentro del calendario anterior, se recuerda para devolverlo
  const activoAntes = parentElement.getRootNode().activeElement;
  if (activoAntes && parentElement.contains(activoAntes)) m.enfocar = selector(activoAntes);
  const viejo = parentElement.querySelector('.cal');
  if (viejo) m.scroll = viejo.querySelector('.meses').scrollLeft;
  parentElement.querySelectorAll('.cal').forEach((e) => e.remove());

  const elegir = data.modo === 'elegir';
  const raiz = document.createElement('div');
  raiz.className = 'cal ' + data.modo;
  Object.entries(data.colores).forEach(([k, v]) => raiz.style.setProperty('--' + k, v));
  parentElement.appendChild(raiz);

  const SEMANA = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'];
  const TEXTO = { util: 'hay foto útil', nose: 'hay foto pero no se ve la obra', sin: 'no hay foto', fuera: 'fuera del periodo' };
  const NOMBRE = { primera: 'primera', segunda: 'segunda' };
  const esc = (s) => String(s).replace(/[&<>"]/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));
  const dia = {};
  const elegibles = [];
  data.meses.forEach((mes) => mes.dias.forEach((d) => { dia[d.f] = d; if (d.e === 'util') elegibles.push(d.f); }));
  let primera = data.primera, segunda = data.segunda;
  let activo = m.activo || 'primera';
  let foco = m.foco && dia[m.foco] && dia[m.foco].e === 'util' ? m.foco : (activo === 'primera' ? primera : segunda) || elegibles[0];
  let aviso = '', avisoSr = '';  // avisoSr: solo para lector de pantalla (las fechas ya se ven arriba)

  function selector(el) {
    if (el.dataset && el.dataset.f) return '[data-f="' + el.dataset.f + '"]';
    if (el.dataset && el.dataset.ranura) return '[data-ranura="' + el.dataset.ranura + '"]';
    if (el.dataset && el.dataset.nav) return '[data-nav="' + el.dataset.nav + '"]';
    return null;
  }

  function celda(d) {
    const estado = d.e || 'fuera';
    if (elegir && d.e === 'util') {
      const n = d.f === primera ? 1 : d.f === segunda ? 2 : 0;
      const etiqueta = d.t + ', ' + TEXTO.util + (n === 1 ? ', primera fecha' : n === 2 ? ', segunda fecha' : '');
      return '<td><button type="button" class="dia" data-f="' + d.f + '" tabindex="' + (d.f === foco ? 0 : -1) +
        '" aria-pressed="' + (n ? 'true' : 'false') + '" aria-label="' + esc(etiqueta) + '"><span class="c ' +
        (n ? 'sel' : 'util') + '" aria-hidden="true">' + d.d + (n ? '<span class="marca">' + n + '</span>' : '') +
        '</span></button></td>';
    }
    const extra = elegir && d.e ? '; no se puede elegir' : '';
    return '<td><span class="dia"><span class="c ' + estado + '" aria-hidden="true">' + d.d + '</span>' +
      '<span class="sr">' + esc(d.t + ', ' + TEXTO[estado] + extra) + '</span></span></td>';
  }

  function mesHtml(mes) {
    const celdas = [];
    for (let i = 0; i < mes.salto; i++) celdas.push('<td></td>');
    mes.dias.forEach((d) => celdas.push(celda(d)));
    while (celdas.length % 7) celdas.push('<td></td>');
    let filas = '';
    for (let i = 0; i < celdas.length; i += 7) filas += '<tr>' + celdas.slice(i, i + 7).join('') + '</tr>';
    return '<div class="mes"><table><caption>' + esc(mes.nombre) + '</caption><thead><tr>' +
      SEMANA.map((s) => '<th scope="col"><span aria-hidden="true">' + s[0].toUpperCase() + '</span><span class="sr">' +
        s + '</span></th>').join('') + '</tr></thead><tbody>' + filas + '</tbody></table></div>';
  }

  function ranura(nombre, n, f) {
    return '<button type="button" class="boton ranura" data-ranura="' + nombre + '" aria-pressed="' +
      (activo === nombre) + '" aria-label="' + esc((n === 1 ? 'Primera' : 'Segunda') + ' fecha: ' + dia[f].t +
      '. Pulse para cambiarla') + '"><span class="marca" aria-hidden="true">' + n + '</span><span aria-hidden="true">' +
      '<span class="rot">' + (n === 1 ? 'Primera' : 'Segunda') + ' fecha</span><b>' + esc(dia[f].c) + '</b></span></button>';
  }

  function dibujar(enfocar) {
    const scroll = raiz.querySelector('.meses') ? raiz.querySelector('.meses').scrollLeft : m.scroll;
    let h = '';
    if (elegir) {
      h += '<div class="controles"><div role="group" aria-label="Fechas a comparar" class="controles" style="margin:0">' +
        ranura('primera', 1, primera) + ranura('segunda', 2, segunda) + '</div>' +
        '<div class="nav"><button type="button" class="boton" data-nav="-1" aria-label="Ver meses anteriores">&#8249;</button>' +
        '<button type="button" class="boton" data-nav="1" aria-label="Ver meses siguientes">&#8250;</button></div></div>';
      h += '<p class="aviso" aria-live="polite">' + (avisoSr ? '<span class="sr">' + esc(avisoSr) + '</span>' : '') +
        esc(aviso || ('Toque un día con foto útil para elegir la ' + NOMBRE[activo] + ' fecha.')) + '</p>';
    }
    h += '<ul class="leyenda" aria-label="Leyenda del calendario">' + data.leyenda.map((l) =>
      '<li><span class="c ' + l.e + '" aria-hidden="true"></span>' + esc(l.texto) +
      (l.n !== null && l.n !== undefined ? ' <b>' + l.n + '</b>' : '') + '</li>').join('') + '</ul>';
    h += '<div class="meses">' + data.meses.map(mesHtml).join('') + '</div>';
    raiz.innerHTML = h;
    if (!elegir) return;

    const meses = raiz.querySelector('.meses');
    if (scroll !== undefined) meses.scrollLeft = scroll;
    else {  // primera vez: que se vea el mes de la segunda fecha
      const mes = raiz.querySelector('[data-f="' + segunda + '"]').closest('.mes');
      meses.scrollLeft = Math.max(0, mes.offsetLeft + mes.offsetWidth - meses.clientWidth + 2);
    }
    raiz.querySelectorAll('button.dia').forEach((b) => {
      b.addEventListener('click', () => elegirDia(b.dataset.f));
      b.addEventListener('keydown', (ev) => mover(ev, b.dataset.f));
      b.addEventListener('focus', () => { foco = m.foco = b.dataset.f; });
    });
    raiz.querySelectorAll('[data-ranura]').forEach((b) => b.addEventListener('click', () => {
      activo = m.activo = b.dataset.ranura;
      aviso = ''; avisoSr = '';
      foco = m.foco = activo === 'primera' ? primera : segunda;
      dibujar('[data-ranura="' + activo + '"]');
    }));
    const navs = raiz.querySelectorAll('[data-nav]');
    const paso = 7 * 44 + 16;
    navs.forEach((b) => b.addEventListener('click', () => {
      meses.scrollBy({ left: Number(b.dataset.nav) * paso, behavior: 'smooth' });
    }));
    const bordes = () => {
      navs[0].disabled = meses.scrollLeft <= 1;
      navs[1].disabled = meses.scrollLeft + meses.clientWidth >= meses.scrollWidth - 1;
      m.scroll = meses.scrollLeft;
    };
    meses.addEventListener('scroll', bordes, { passive: true });
    bordes();
    if (enfocar) {
      const el = raiz.querySelector(enfocar);
      if (el && !el.disabled) el.focus({ preventScroll: true });
      else if (el) raiz.querySelector('[data-f="' + foco + '"]')?.focus({ preventScroll: true });
    }
  }

  function elegirDia(f) {
    const otra = activo === 'primera' ? segunda : primera;
    if (f === otra) {
      avisoSr = '';
      aviso = 'Ese día ya es la ' + (activo === 'primera' ? 'segunda' : 'primera') + ' fecha; elija otro.';
      dibujar('[data-f="' + f + '"]');
      return;
    }
    let p = activo === 'primera' ? f : primera, s = activo === 'segunda' ? f : segunda;
    if (p > s) [p, s] = [s, p];  // la primera fecha es siempre la más antigua (va a la izquierda)
    primera = p; segunda = s;
    const siguiente = activo === 'primera' ? 'segunda' : 'primera';
    avisoSr = 'Primera fecha: ' + dia[primera].t + '. Segunda fecha: ' + dia[segunda].t + '. ';
    aviso = 'Toque otro día para cambiar la ' + NOMBRE[siguiente] + ' fecha.';
    activo = m.activo = siguiente;
    foco = m.foco = f;
    dibujar('[data-f="' + f + '"]');
    m.aviso = [aviso, avisoSr];
    setTriggerValue('fechas', { primera: primera, segunda: segunda });
  }

  function sumar(f, n) {
    const t = new Date(f + 'T12:00:00Z');
    t.setUTCDate(t.getUTCDate() + n);
    return t.toISOString().slice(0, 10);
  }

  function mover(ev, f) {
    const i = elegibles.indexOf(f);
    let destino = null;
    if (ev.key === 'ArrowRight') destino = elegibles[i + 1];
    else if (ev.key === 'ArrowLeft') destino = elegibles[i - 1];
    else if (ev.key === 'ArrowDown') { const t = sumar(f, 7); destino = elegibles.find((x) => x >= t); }
    else if (ev.key === 'ArrowUp') { const t = sumar(f, -7); destino = [...elegibles].reverse().find((x) => x <= t); }
    else if (ev.key === 'Home') destino = elegibles[0];
    else if (ev.key === 'End') destino = elegibles[elegibles.length - 1];
    else return;
    ev.preventDefault();
    if (!destino) return;
    raiz.querySelectorAll('button.dia').forEach((b) => { b.tabIndex = b.dataset.f === destino ? 0 : -1; });
    const b = raiz.querySelector('[data-f="' + destino + '"]');
    b.focus({ preventScroll: true });
    b.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  }

  if (m.aviso && elegir) { [aviso, avisoSr] = m.aviso; m.aviso = null; }
  dibujar(m.enfocar);
  m.enfocar = null;
  return () => raiz.remove();
}
"""

calendario_componente = st.components.v2.component("calendario_dias", css=CALENDARIO_CSS, js=CALENDARIO_JS)


def datos_calendario(dias: pd.DataFrame, c: dict, modo: str, primera: str | None = None,
                     segunda: str | None = None) -> dict:
    estado = dias.set_index("fecha")["estado"]
    cuenta = dias["estado"].value_counts()
    meses = []
    for periodo in pd.period_range(dias["fecha"].min(), dias["fecha"].max(), freq="M"):
        inicio = periodo.start_time.normalize()
        lista = []
        for k in range(periodo.days_in_month):
            f = inicio + pd.Timedelta(days=k)
            lista.append({"d": f.day, "f": f.strftime("%Y-%m-%d"), "e": CLAVE_ESTADO.get(estado.get(f)),
                          "t": fecha_larga(f, dia_semana=True), "c": fecha(f, dia_semana=True)})
        meses.append({"nombre": f"{mayuscula(MESES_LARGO[periodo.month - 1])} {periodo.year}",
                      "salto": inicio.weekday(), "dias": lista})
    colores = {"si": c["si"], "si-texto": c["si_texto"], "no": c["no"], "no-suave": c["no_suave"], "tinta": c["tinta"],
               "tenue": c["tenue"], "fondo": c["fondo"], "borde": c["borde"], "radio": "0.6rem"}
    leyenda = [{"e": CLAVE_ESTADO[e], "texto": LEYENDA[e], "n": int(cuenta.get(e, 0)) if modo == "ver" else None}
               for e in ESTADOS]
    return {"id": modo, "modo": modo, "meses": meses, "leyenda": leyenda, "colores": colores,
            "primera": primera, "segunda": segunda}


# ============================================================================
# Lo que no se ve
# ============================================================================

def titular_calendario(dias: pd.DataFrame) -> str:
    faltan = int(dias["estado"].ne(UTIL).sum())
    if faltan == 0:
        return "Todos los días hay evidencia de la obra"
    n = round(len(dias) / faltan)
    if n <= 1:
        return f"En {faltan} de {len(dias)} días no hay evidencia de la obra"
    return f"En uno de cada {palabra(n)} días no hay evidencia de la obra"


def mapa_por_hora(d: dict, c: dict) -> go.Figure:
    """Detalle por día y hora de luz (mapa de calor)."""
    horas = d["horas"][d["horas"]["hora"].isin(HORAS_LUZ)]
    codigo = {e: k for k, e in enumerate(ESTADOS)}
    tabla = horas.pivot(index="hora", columns="fecha", values="estado")
    fotos = horas.pivot(index="hora", columns="fecha", values="fotos")
    z = tabla.apply(lambda col: col.map(codigo)).astype(float).values
    texto = [[f"{fecha(col, dia_semana=True)}, {h}:00–{h}:59<br><b>{tabla.at[h, col]}</b>"
              + (f" ({plural(int(fotos.at[h, col]), 'foto')})" if fotos.at[h, col] else "")
              for col in tabla.columns] for h in tabla.index]
    escala = []
    for k, e in enumerate(ESTADOS):
        escala += [[k / len(ESTADOS), c[COLOR_ESTADO[e]]], [(k + 1) / len(ESTADOS), c[COLOR_ESTADO[e]]]]
    fig = go.Figure(go.Heatmap(z=z, x=tabla.columns, y=tabla.index, zmin=-0.5, zmax=len(ESTADOS) - 0.5,
                               colorscale=escala, showscale=False, text=texto, hovertemplate="%{text}<extra></extra>",
                               xgap=0, ygap=1))
    arriba = HORAS_LUZ[0] - 0.5
    for f in cambios_de_vista(d["vistas"]):
        x = f - pd.Timedelta(hours=12)
        fig.add_shape(type="line", x0=x, x1=x, y0=arriba - 1.0, y1=HORAS_LUZ[-1] + 0.5,
                      line=dict(color=c["tinta"], width=1.5, dash="dot"))
        fig.add_annotation(x=x, y=arriba - 1.0, yanchor="bottom", xanchor="left", xshift=5, showarrow=False,
                           text=f"cambió la vista, {fecha(f, anio=False)}", font=dict(size=11, color=c["tinta"]))
    marcas = list(range(HORAS_LUZ[0], HORAS_LUZ[-1] + 1, 3)) + [HORAS_LUZ[-1]]
    fig.update_yaxes(autorange=False, range=[HORAS_LUZ[-1] + 0.5, arriba - 2.2], tickvals=marcas,
                     ticktext=[f"{h} h" for h in marcas], title=None, showgrid=False, zeroline=False, fixedrange=True)
    eje_meses(fig, tabla.columns.min(), tabla.columns.max())
    fig.update_layout(height=360, margin=dict(l=40, r=8, t=8, b=8), plot_bgcolor="rgba(0,0,0,0)",
                      paper_bgcolor="rgba(0,0,0,0)", hoverlabel=dict(align="left"), separators=", ")
    return fig


def lo_que_no_se_ve(d: dict, c: dict) -> None:
    dias = d["dias"]
    hueco = tramos_sin_evidencia(dias).iloc[0]
    seccion("Lo que no se ve", titular_calendario(dias),
            f"El tramo más largo sin fotos de la obra va {rango_largo(hueco['inicio'], hueco['fin'])}: "
            f"{int(hueco['dias'])} días seguidos.")
    calendario_componente(data=datos_calendario(dias, c, "ver"), key="calendario_evidencia")

    n = dias["estado"].value_counts()
    vista = cambios_de_vista(d["vistas"])
    with st.expander("Descripción de la gráfica"):
        st.markdown(
            f"Calendario de {len(dias)} días, {rango_largo(dias['fecha'].min(), dias['fecha'].max())}, "
            f"un cuadro por día. {n.get(UTIL, 0)} días tienen fotos útiles de la obra (cuadro azul relleno); en "
            f"{n.get(SIN_FOTO, 0)} no hay ninguna foto (contorno punteado) y en {n.get(NO_SE_VE, 0)} hay fotos pero no se "
            "ve la obra (cuadro rayado)."
            + (f" El {fecha_larga(vista.iloc[0])} cambió la vista de la cámara." if len(vista) == 1
               else f" La vista de la cámara cambió {len(vista)} veces." if len(vista) else ""))
    with st.expander("Detalle por hora"):
        leyenda = "".join(f'<span style="--c:{c[COLOR_ESTADO[e]]}">{mayuscula(e)}</span>' for e in ESTADOS)
        st.html(f'<div class="leyenda" role="list" aria-label="Leyenda del detalle por hora">{leyenda}</div>')
        st.plotly_chart(mapa_por_hora(d, c), width="stretch", config={"displayModeBar": False, "scrollZoom": False})
        st.caption(f"Cada columna es un día y cada fila una hora de luz, de {HORAS_LUZ[0]} a {HORAS_LUZ[-1]} h. "
                   "De noche la cámara también toma fotos, pero no sirven para ver la obra.")
    with st.expander("¿Por qué faltan datos?"):
        st.markdown(
            f"- **No hay foto:** en {plural(int(n.get(SIN_FOTO, 0)), 'día')} la cámara no envió ninguna foto. "
            "Desde aquí no se puede saber por qué (corte de energía, de conexión u otra causa).\n"
            f"- **Hay foto pero no se ve la obra:** en {plural(int(n.get(NO_SE_VE, 0)), 'día')} la cámara apuntaba a "
            "otra cosa (el cielo, una superficie lisa o un techo) o las fotos estaban demasiado oscuras.\n"
            "- **Fotos que no sirven:** algunas salen empañadas, borrosas, quemadas por el sol o con franjas; casi "
            "siempre hay otras útiles el mismo día.\n"
            + (f"- **La cámara se movió:** el {' y el '.join(fecha_larga(f) for f in vista)} cambió de posición, así "
               "que las fotos de antes y después de esa fecha no se pueden superponer." if len(vista)
               else "- **La cámara no cambió de posición** en todo el periodo.")
        )


# ============================================================================
# Explore por su cuenta y pie
# ============================================================================

def explora(d: dict, c: dict) -> None:
    dias = d["dias"]
    seccion("Explore por su cuenta", "Compare dos días cualquiera",
            "Toque dos días con foto útil en el calendario y deslice la barra sobre la foto.")
    utiles = dias[dias["estado"].eq(UTIL)].set_index("fecha", drop=False)
    validas = set(utiles.index.strftime("%Y-%m-%d"))
    # Por defecto, la última vista de la cámara (la portada ya muestra la primera)
    ultima = utiles[utiles["vista"].eq(utiles["vista"].iloc[-1])]
    por_defecto = (ultima.index[0].strftime("%Y-%m-%d"), ultima.index[-1].strftime("%Y-%m-%d"))
    actual = st.session_state.get("fechas_explora", por_defecto)
    if not (set(actual) <= validas and actual[0] < actual[1]):
        actual = por_defecto
    st.session_state.fechas_explora = actual

    resultado = calendario_componente(data=datos_calendario(dias, c, "elegir", *actual), key="calendario_explora",
                                      on_fechas_change=lambda: None)
    nuevas = getattr(resultado, "fechas", None)
    if nuevas:
        par = tuple(sorted((str(nuevas.get("primera")), str(nuevas.get("segunda")))))
        if par != actual and set(par) <= validas and par[0] != par[1]:
            st.session_state.fechas_explora = par
            st.rerun()

    a, b = utiles.loc[pd.Timestamp(actual[0])], utiles.loc[pd.Timestamp(actual[1])]
    mostrar_comparacion(d, c, a, b)
    entre = d["hitos"][(d["hitos"]["fecha_fin"] > a["fecha"]) & (d["hitos"]["fecha_inicio"] < b["fecha"])]
    if len(entre):
        st.markdown("Cambios entre estas fechas: " + "; ".join(f"{h.numero}. {h.titulo.lower()}" for h in entre.itertuples()) + ".")


def pie() -> None:
    st.html('<div class="seccion" aria-hidden="true"></div>')
    with st.expander("Cómo se hizo"):
        st.markdown(
            "Las fotos son de la cámara instalada en la obra por la Contraloría General de la República (CGR), proyecto "
            "dIAra, y son de uso público. Se revisaron todas y se descartaron las de noche, las demasiado oscuras, "
            "borrosas o dañadas y las de los días en que la cámara no apuntaba a la obra. De cada día con fotos útiles se "
            "eligió una cercana al mediodía. Los cambios se identificaron a mano, comparando una foto por semana y, para "
            "precisar la fecha, una foto por día. Cuando la cámara se corrió ligeramente, el comparador alinea las fotos "
            "para que coincidan. "
            f"El procedimiento completo está en la [nota metodológica]({REPO_URL}/blob/main/docs/nota_metodologica.md)."
        )
    st.html('<p class="alcance">Este sitio muestra únicamente lo que se observa en las fotos de la cámara; no informa '
            'presupuesto, plazos ni porcentaje de avance de la obra.</p>')
    st.caption(f"Proyecto Integrador III · Visualización de datos, Lead University, 2026 · [Código y datos]({REPO_URL})")


def main() -> None:
    d = cargar()
    c = COLORES[tema()]
    estilos(c)
    franja(d["dias"])
    portada(d, c)
    cada_mes(d)
    historia(d, c)
    lo_que_no_se_ve(d, c)
    explora(d, c)
    pie()


main()
