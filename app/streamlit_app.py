"""Puente María Aguilar: lo que muestran las fotos.

App de una página para la ciudadanía, con estructura de pieza de periodismo de datos:
portada con el hallazgo y un comparador, recorrido paso a paso por los cambios, lo que no
se ve (calendario de evidencia) y un comparador libre al final («Explore por su cuenta»). Solo lee archivos de app/
(generados por src/06_fotos_app.py), así que funciona desplegada sin las fotos originales.
El tema (tipografía y fondos) está en .streamlit/config.toml.

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

UTIL = "hay foto útil"
NO_SE_VE = "hay foto pero no se ve la obra"
SIN_FOTO = "no hay foto"
ESTADOS = [UTIL, NO_SE_VE, SIN_FOTO]

# Dos colores con significado fijo en toda la página: azul = hay evidencia de la obra,
# bermellón = no hay evidencia (sólido: no hay foto; tenue: hay foto pero no se ve la obra).
# Azul/bermellón validados para daltonismo (Okabe-Ito); el resto son neutros del tema.
COLORES = {
    "light": {"si": "#0072B2", "no": "#D55E00", "no_suave": "#F0B48C", "tinta": "#1A1A19",
              "tenue": "#66635C", "fondo": "#FBFAF7", "borde": "#DEDBD3", "hueco": "rgba(213,94,0,0.13)"},
    "dark": {"si": "#3D9BE0", "no": "#E8743B", "no_suave": "#7E3A16", "tinta": "#EDEBE6",
             "tenue": "#A8A59D", "fondo": "#141413", "borde": "#3A3936", "hueco": "rgba(232,116,59,0.20)"},
}
COLOR_ESTADO = {UTIL: "si", NO_SE_VE: "no_suave", SIN_FOTO: "no"}
CLARIDAD = {"alta": "muy claro", "media": "claro", "baja": "poco claro"}  # según la confianza de hitos.csv
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
MESES_LARGO = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
               "septiembre", "octubre", "noviembre", "diciembre"]
DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
NUMEROS = ["cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez",
           "once", "doce", "trece", "catorce", "quince", "dieciséis", "diecisiete", "dieciocho",
           "diecinueve", "veinte"]
HORAS_LUZ = range(6, 18)  # el calendario muestra de 6:00 a 17:59; de noche no se ve la obra
# Hito que marca el puente en uso, para el titular de portada ("En N semanas, un hueco se
# convirtió en un puente"): se busca esta palabra en el título. Si no está, titular genérico.
PALABRA_PUENTE_EN_USO = "vehículos"

st.set_page_config(page_title="Puente María Aguilar: lo que muestran las fotos", page_icon="🌉", layout="wide")


# ============================================================================
# Datos
# ============================================================================

@st.cache_data
def cargar() -> dict[str, pd.DataFrame]:
    dias = pd.read_csv(DATOS / "dias.csv", parse_dates=["fecha", "fecha_hora_foto"])
    horas = pd.read_csv(DATOS / "evidencia_dia_hora.csv", parse_dates=["fecha"])
    hitos = pd.read_csv(DATOS / "hitos.csv", parse_dates=["fecha_inicio", "fecha_fin", "fecha_hora_antes", "fecha_hora_despues"])
    semanas = pd.read_csv(DATOS / "fotos_semanales.csv", parse_dates=["semana_inicio", "fecha_hora"])
    vistas = pd.read_csv(DATOS / "vistas.csv", parse_dates=["fecha_inicio", "fecha_fin"])
    alineacion = pd.read_csv(DATOS / "alineacion.csv", parse_dates=["fecha"])
    for tabla in (dias, hitos, semanas, vistas, alineacion):
        tabla["vista"] = tabla["vista"].astype("Int64")
    hitos = hitos.sort_values(["fecha_inicio", "fecha_fin"]).reset_index(drop=True)
    hitos["numero"] = range(1, len(hitos) + 1)
    return {"dias": dias, "horas": horas, "hitos": hitos, "semanas": semanas, "vistas": vistas,
            "alineacion": alineacion}


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


# ============================================================================
# Formato en lenguaje ciudadano
# ============================================================================

def fecha(f: pd.Timestamp, dia_semana: bool = False, anio: bool = True) -> str:
    texto = f"{f.day} {MESES[f.month - 1]}" + (f" {f.year}" if anio else "")
    return f"{DIAS[f.weekday()]} {texto}" if dia_semana else texto


def rango(a: pd.Timestamp, b: pd.Timestamp) -> str:
    if a == b:
        return fecha(a)
    if a.year == b.year and a.month == b.month:
        return f"{a.day}–{b.day} {MESES[a.month - 1]} {a.year}"
    if a.year == b.year:
        return f"{fecha(a, anio=False)} – {fecha(b)}"
    return f"{fecha(a)} – {fecha(b)}"


def hora(f: pd.Timestamp) -> str:
    return f"{f.hour}:{f.minute:02d}"


def miles(n: int) -> str:
    """1804 -> '1 804' (separador de miles con espacio)."""
    return f"{n:,}".replace(",", " ")


def plural(n: int, singular: str, plural_: str | None = None) -> str:
    return f"{n} {singular if n == 1 else (plural_ or singular + 's')}"


def palabra(n: int, mayuscula: bool = False) -> str:
    texto = NUMEROS[n] if 0 <= n < len(NUMEROS) else str(n)
    return texto[:1].upper() + texto[1:] if mayuscula else texto


def primera_frase(texto: str) -> str:
    return re.split(r"(?<=\.)\s+(?=[A-ZÁÉÍÓÚÑ])", str(texto).strip(), maxsplit=1)[0]


def alt_foto(f: pd.Timestamp, extra: str = "") -> str:
    return (f"Foto de la cámara tomada el {fecha(f, dia_semana=True)} a las {hora(f)}: "
            f"vista del Puente María Aguilar y la vía a su alrededor.{(' ' + extra) if extra else ''}")


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
[data-testid="stMainBlockContainer"] {{ max-width: 1000px; padding: 2.5rem 1.25rem 5rem; }}
h1, h2, h3 {{ font-family: "Source Serif 4", Georgia, serif !important; }}
[data-testid="stHeadingWithActionElements"] h2, [data-testid="stHeadingWithActionElements"] h3 {{ padding-top: 0.2rem !important; }}
h1 {{ font-size: clamp(2.2rem, 1.3rem + 3.8vw, 3.75rem) !important; line-height: 1.05 !important;
      letter-spacing: -0.02em; padding-bottom: 0.4rem !important; }}
h2 {{ font-size: clamp(1.65rem, 1.15rem + 2.1vw, 2.5rem) !important; line-height: 1.1 !important;
      letter-spacing: -0.01em; }}
h3 {{ font-size: clamp(1.3rem, 1.05rem + 1vw, 1.7rem) !important; line-height: 1.2 !important; }}
[data-testid="stMarkdownContainer"] p, [data-testid="stCaptionContainer"] p {{ max-width: 68ch; }}
.kicker {{ text-transform: uppercase; letter-spacing: 0.09em; font-size: 0.78rem; font-weight: 700;
           color: {c['tenue']}; margin: 0; }}
.bajada {{ font-size: clamp(1.08rem, 1rem + 0.4vw, 1.3rem); line-height: 1.45; color: {c['tenue']};
           max-width: 60ch; margin: 0 0 0.5rem; }}
.seccion {{ margin: 3.5rem 0 1.25rem; border-top: 1px solid {c['borde']}; }}
.cifras {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.75rem 1.5rem; margin: 0.5rem 0; }}
.cifra {{ border-top: 3px solid {c['borde']}; padding-top: 0.6rem; }}
.cifra.si {{ border-top-color: {c['si']}; }} .cifra.no {{ border-top-color: {c['no']}; }}
.cifra .num {{ display: block; font-family: "Source Serif 4", serif; font-weight: 700; line-height: 1;
              font-size: clamp(2.2rem, 1.6rem + 2vw, 3rem); color: {c['tinta']}; }}
.cifra.si .num {{ color: {c['si']}; }} .cifra.no .num {{ color: {c['no']}; }}
.cifra .txt {{ display: block; margin-top: 0.3rem; font-size: 0.95rem; line-height: 1.35; color: {c['tenue']}; }}
@media (max-width: 640px) {{
  .cifras {{ grid-template-columns: 1fr; }}
  .cifra {{ display: grid; grid-template-columns: 5.5rem 1fr; align-items: baseline; gap: 0.75rem; }}
  .cifra .txt {{ margin-top: 0; }}
}}
.claridad {{ display: inline-block; margin: 0.4rem 0 0; padding: 0.3rem 0.75rem; border: 1px solid {c['borde']};
             border-radius: 999px; font-size: 0.9rem; color: {c['tenue']}; }}
.claridad b {{ color: {c['tinta']}; }}
.paso {{ font-variant-numeric: tabular-nums; font-weight: 700; text-align: center; margin: 0; }}
.leyenda {{ display: flex; flex-wrap: wrap; gap: 0.4rem 1.2rem; font-size: 0.9rem; color: {c['tenue']}; margin: 0.25rem 0; }}
.leyenda span::before {{ content: ""; display: inline-block; width: 0.85em; height: 0.85em; margin-right: 0.4em;
                        vertical-align: -0.05em; border-radius: 2px; background: var(--c); border: 1px solid {c['borde']}; }}
</style>""")


def seccion(kicker: str, titular: str, bajada: str | None = None) -> None:
    """Encabezado de sección: rótulo pequeño, titular con la conclusión y como máximo dos frases."""
    st.html(f'<div class="seccion"></div><p class="kicker">{html.escape(kicker)}</p>')
    st.header(titular, anchor=False)
    if bajada:
        st.html(f'<p class="bajada">{html.escape(bajada)}</p>')


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


def html_comparador(a: pd.Series, b: pd.Series, texto_a: str, texto_b: str, ajuste: dict | None = None) -> str:
    """Comparador antes/después con barra deslizante, sin dependencias externas.

    La foto de después ocupa todo el cuadro y la de antes se recorta desde la izquierda
    hasta la posición de la barra. La barra es un <input type="range"> transparente sobre
    las fotos: se arrastra con el mouse o el dedo y se mueve con las flechas del teclado.
    Con `ajuste`, la foto de después se mueve para coincidir con la de antes y las dos se
    amplían un poco para ocultar los bordes sin imagen.
    """
    aj = ajuste or {"tx": 0, "ty": 0, "rot": 0, "escala": 1, "zoom": 1, "vx": 0, "vy": 0}
    alt_a = html.escape(alt_foto(a["fecha_hora_foto"], "Foto de la izquierda (antes)."))
    alt_b = html.escape(alt_foto(b["fecha_hora_foto"], "Foto de la derecha (después)."))
    etiqueta = html.escape(f"Barra de comparación: a la izquierda {texto_a}, a la derecha {texto_b}")
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><style>
html, body {{ margin:0; padding:0; background:transparent; font-family:system-ui, sans-serif; }}
.comp {{ position:relative; width:100%; overflow:hidden; border-radius:10px; line-height:0; user-select:none; touch-action:pan-y; }}
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
.comp .rotulo {{ position:absolute; top:10px; padding:5px 9px; border-radius:4px; background:rgba(20,20,19,.78); color:#fff;
                font:600 13px/1.2 system-ui, sans-serif; pointer-events:none; }}
.comp .izq {{ left:10px; }} .comp .der {{ right:10px; }}
.comp input {{ position:absolute; inset:0; width:100%; height:100%; margin:0; opacity:0; cursor:ew-resize; }}
.comp:has(input:focus-visible) {{ outline:3px solid #0072B2; outline-offset:3px; }}
</style></head><body>
<div class="comp">
  <div class="lienzo">
    <img class="despues" src="data:image/jpeg;base64,{imagen_base64(b['foto'])}" alt="{alt_b}">
    <img class="antes" src="data:image/jpeg;base64,{imagen_base64(a['foto'])}" alt="{alt_a}">
  </div>
  <div class="linea"></div><div class="asa" aria-hidden="true">&#8596;</div>
  <span class="rotulo izq">{html.escape(texto_a)}</span><span class="rotulo der">{html.escape(texto_b)}</span>
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


def mostrar_comparacion(d: dict, a: pd.Series, b: pd.Series) -> None:
    """Deslizador si las dos fechas son de la misma vista; si no, las dos fotos lado a lado con aviso."""
    texto_a = f"{fecha(a['fecha_hora_foto'])}, {hora(a['fecha_hora_foto'])}"
    texto_b = f"{fecha(b['fecha_hora_foto'])}, {hora(b['fecha_hora_foto'])}"
    if a["vista"] == b["vista"]:
        corrimientos = corrimientos_entre(d["alineacion"], a, b)
        ajuste = ajuste_css(corrimientos)
        st.iframe(html_comparador(a, b, texto_a, texto_b, ajuste), height="content")
        nota = (f"Izquierda: {fecha(a['fecha'], dia_semana=True)}. Derecha: {fecha(b['fecha'], dia_semana=True)}. "
                "Misma vista de la cámara: lo que cambia es la obra.")
        if len(corrimientos):
            nota += (" La cámara se corrió ligeramente entre estas fechas"
                     + ("; la foto de la derecha se ajustó para que coincidan." if ajuste else "."))
        st.caption(nota)
    else:
        st.warning("La cámara se movió entre estas fechas, la comparación no es exacta.", icon="⚠️")
        for col, fila, texto in zip(st.columns(2), [a, b], [texto_a, texto_b]):
            col.image(str(APP / fila["foto"]), width="stretch", alt=alt_foto(fila["fecha_hora_foto"]), caption=texto)


# ============================================================================
# Portada
# ============================================================================

def titular_portada(hitos: pd.DataFrame) -> tuple[str, str | None]:
    """Titular con el hallazgo y la frase que lo respalda, calculados de hitos.csv."""
    en_uso = hitos[hitos["titulo"].str.contains(PALABRA_PUENTE_EN_USO, case=False, na=False)]
    if hitos.empty or en_uso.empty:
        return "Así cambió la obra del Puente María Aguilar", None
    primero, uso = hitos.iloc[0], en_uso.iloc[0]
    semanas = round((uso["fecha_fin"] - primero["fecha_inicio"]).days / 7)
    respaldo = (f"Del cambio «{primero['titulo'].lower()}» ({fecha(primero['fecha_inicio'], anio=False)}) "
                f"a «{uso['titulo'].lower()}» ({fecha(uso['fecha_fin'])}) pasaron {palabra(semanas)} semanas.")
    return f"En {palabra(semanas)} semanas, un hueco se convirtió en un puente", respaldo


def portada(d: dict) -> None:
    dias, hitos = d["dias"], d["hitos"]
    titular, respaldo = titular_portada(hitos)
    st.html('<p class="kicker">Puente María Aguilar · lo que muestran las fotos</p>')
    st.title(titular, anchor=False)
    st.html('<p class="bajada">¿Qué cambió en la obra, cuándo ocurrió y qué días no hay fotos para saberlo? '
            'Deslice la barra sobre la foto.</p>')

    # Comparador de portada: primer y último día con foto útil de la primera vista
    utiles = dias[dias["estado"].eq(UTIL)]
    primera_vista = utiles[utiles["vista"].eq(utiles["vista"].iloc[0])]
    mostrar_comparacion(d, primera_vista.iloc[0], primera_vista.iloc[-1])
    if respaldo:
        st.caption(respaldo)

    n_util = int(dias["estado"].eq(UTIL).sum())
    hueco = tramos_sin_evidencia(dias).iloc[0]
    st.html(f"""<div class="cifras" role="list">
  <div class="cifra si" role="listitem"><span class="num">{n_util}</span>
    <span class="txt">de {len(dias)} días con fotos útiles de la obra ({rango(dias['fecha'].min(), dias['fecha'].max())})</span></div>
  <div class="cifra no" role="listitem"><span class="num">{int(hueco['dias'])}</span>
    <span class="txt">días seguidos sin evidencia, del {fecha(hueco['inicio'], anio=False)} al {fecha(hueco['fin'])}</span></div>
  <div class="cifra" role="listitem"><span class="num">{len(hitos)}</span>
    <span class="txt">cambios visibles en la obra, revisados a mano</span></div>
</div>""")


# ============================================================================
# Historia guiada de los cambios
# ============================================================================

def titular_cambios(hitos: pd.DataFrame) -> str:
    n = len(hitos)
    if n == 0:
        return "Todavía no hay cambios identificados"
    por_mes = hitos.groupby(hitos["fecha_fin"].dt.to_period("M")).size()
    mes, k = por_mes.idxmax(), int(por_mes.max())
    if n >= 3 and k >= 2 and k > n / 3:
        return (f"{palabra(n, True)} cambios visibles; {palabra(k)} de ellos en "
                f"{MESES_LARGO[mes.month - 1]} de {mes.year}")
    return f"{palabra(n, True)} cambios visibles entre {fecha(hitos['fecha_inicio'].min())} y {fecha(hitos['fecha_fin'].max())}"


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
# que los puntos no se toquen en el celular.
LINEA_CSS = """
.linea { font-family: var(--st-font, sans-serif); color: var(--st-text-color); }
.linea .elegido { margin: 0 0 0.6rem; font-size: 1rem; line-height: 1.35; min-height: 2.7em; }
.linea .elegido b { font-weight: 700; }
.linea .elegido .num { display: inline-block; min-width: 1.6em; height: 1.6em; line-height: 1.6em; border-radius: 50%;
  text-align: center; font-weight: 700; font-size: 0.85rem; margin-right: 0.45em;
  background: var(--st-text-color); color: var(--st-background-color); }
.linea .elegido .fecha { opacity: 0.72; white-space: nowrap; }
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
.linea button:focus-visible { outline: 3px solid #0072B2; outline-offset: 3px; }
"""

LINEA_JS = """
export default function (component) {
  const { data, setTriggerValue, parentElement } = component;
  const SEPARACION = 44, FILA = 46, EJE = 30, ARRIBA = 30;
  // Streamlit vuelve a llamar a esta función cuando cambian los datos: se quita lo anterior
  parentElement.querySelectorAll('.linea').forEach((e) => e.remove());
  const raiz = document.createElement('div');
  raiz.className = 'linea';
  raiz.setAttribute('role', 'group');
  raiz.setAttribute('aria-label', 'Línea de tiempo de los cambios');
  parentElement.appendChild(raiz);

  function dibujar() {
    const ancho = raiz.clientWidth || 600;
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
    const sel = data.puntos.find((p) => p.elegido);
    let h = '<p class="elegido" aria-live="polite">' + (sel
      ? '<span class="num">' + sel.n + '</span><b>' + sel.titulo + '</b> <span class="fecha">· ' + sel.rango + '</span>'
      : '') + '</p>';
    h += '<div class="lienzo" style="height:' + alto + 'px">';
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
      h += '<button type="button" data-n="' + p.n + '" style="left:' + p.x + '%;top:' + y + 'px" title="' +
           p.titulo + ' · ' + p.rango + '" aria-label="Cambio ' + p.n + ': ' + p.titulo + ', ' + p.rango + '"' +
           (p.elegido ? ' aria-current="step"' : '') + '>' + p.n + '</button>';
    });
    h += '</div>';
    raiz.innerHTML = h;
    raiz.querySelectorAll('button').forEach((b) => {
      b.onclick = () => setTriggerValue('elegido', Number(b.dataset.n));
    });
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
            "Toque un punto de la línea de tiempo o use los botones para recorrerlos uno por uno." if len(hitos) else None)
    if hitos.empty:
        return
    total = len(hitos)
    paso = min(st.session_state.setdefault("paso", 0), total - 1)

    resultado = linea_componente(data=datos_linea(d, c, paso), key="linea_de_tiempo", on_elegido_change=lambda: None)
    elegido = getattr(resultado, "elegido", None)
    if elegido is not None and int(elegido) - 1 != paso:
        st.session_state.paso = min(max(int(elegido) - 1, 0), total - 1)
        st.rerun()
    hueco = tramos_sin_evidencia(d["dias"]).iloc[0]
    vista = cambios_de_vista(d["vistas"])
    st.caption(f"Línea de tiempo: {plural(total, 'cambio')} entre el {fecha(hitos['fecha_inicio'].min())} y el "
               f"{fecha(hitos['fecha_fin'].max())}. Zona sombreada: {rango(hueco['inicio'], hueco['fin'])}, sin fotos "
               "de la obra." + (f" Línea punteada: el {fecha(vista.iloc[0])} cambió la vista de la cámara." if len(vista) else ""))

    with st.container(horizontal=True, horizontal_alignment="distribute", vertical_alignment="center"):
        st.button("← Anterior", on_click=mover_paso, args=(-1, total), disabled=paso == 0, key="anterior")
        st.html(f'<p class="paso" aria-live="polite">Cambio {paso + 1} de {total}</p>')
        st.button("Siguiente →", on_click=mover_paso, args=(1, total), disabled=paso == total - 1, key="siguiente")

    h = hitos.iloc[paso]
    st.html(f'<p class="kicker" style="margin-top:1rem">{rango(h["fecha_inicio"], h["fecha_fin"])}</p>')
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


def calendario(d: dict, c: dict) -> go.Figure:
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
    # Hueco más largo: corchete y rótulo sobre el gráfico
    hueco = tramos_sin_evidencia(d["dias"]).iloc[0]
    x0, x1 = hueco["inicio"] - pd.Timedelta(hours=12), hueco["fin"] + pd.Timedelta(hours=12)
    arriba = HORAS_LUZ[0] - 0.5
    for xa, xb, ya, yb in [(x0, x1, arriba - 0.9, arriba - 0.9), (x0, x0, arriba - 0.9, arriba - 0.3),
                           (x1, x1, arriba - 0.9, arriba - 0.3)]:
        fig.add_shape(type="line", x0=xa, x1=xb, y0=ya, y1=yb, line=dict(color=c["no"], width=2))
    fig.add_annotation(x=x1, y=arriba - 1.0, yanchor="bottom", xanchor="right", showarrow=False, align="right",
                       text=f"<b>{int(hueco['dias'])} días seguidos sin evidencia</b><br>{rango(hueco['inicio'], hueco['fin'])}",
                       font=dict(size=12, color=c["no"]))
    for f in cambios_de_vista(d["vistas"]):
        x = f - pd.Timedelta(hours=12)
        fig.add_shape(type="line", x0=x, x1=x, y0=arriba - 1.0, y1=HORAS_LUZ[-1] + 0.5,
                      line=dict(color=c["tinta"], width=1.5, dash="dot"))
        fig.add_annotation(x=x, y=arriba - 1.0, yanchor="bottom", xanchor="left", xshift=5, showarrow=False,
                           text=f"cambió<br>la vista<br>{fecha(f, anio=False)}", font=dict(size=11, color=c["tinta"]),
                           align="left")
    marcas = list(range(HORAS_LUZ[0], HORAS_LUZ[-1] + 1, 3)) + [HORAS_LUZ[-1]]
    fig.update_yaxes(autorange=False, range=[HORAS_LUZ[-1] + 0.5, arriba - 3.2], tickvals=marcas,
                     ticktext=[f"{h} h" for h in marcas], title=None, showgrid=False, zeroline=False, fixedrange=True)
    eje_meses(fig, tabla.columns.min(), tabla.columns.max())
    fig.update_layout(height=400, margin=dict(l=40, r=8, t=8, b=8), plot_bgcolor="rgba(0,0,0,0)",
                      paper_bgcolor="rgba(0,0,0,0)", hoverlabel=dict(align="left"), separators=", ")
    return fig


def resumen_por_mes(dias: pd.DataFrame) -> list[str]:
    lineas = []
    for (anio, mes), g in dias.groupby([dias["fecha"].dt.year, dias["fecha"].dt.month]):
        sin_foto = int(g["estado"].eq(SIN_FOTO).sum())
        no_se_ve = int(g["estado"].eq(NO_SE_VE).sum())
        faltan = sin_foto + no_se_ve
        nombre = f"**{MESES_LARGO[mes - 1]} {anio}**"
        if faltan == 0:
            lineas.append(f"{nombre}: todos los días ({len(g)}) con fotos útiles de la obra.")
            continue
        detalle = []
        if sin_foto:
            detalle.append(f"en {sin_foto} no hay fotos")
        if no_se_ve:
            detalle.append(f"en {no_se_ve} hay fotos pero no se ve la obra")
        lineas.append(f"{nombre}: de {len(g)} días, {faltan} sin evidencia de la obra ({' y '.join(detalle)}).")
    return lineas


def lo_que_no_se_ve(d: dict, c: dict) -> None:
    dias = d["dias"]
    hueco = tramos_sin_evidencia(dias).iloc[0]
    seccion("Lo que no se ve", titular_calendario(dias),
            f"Cada columna es un día y cada fila una hora de luz. De noche la cámara también toma fotos, "
            "pero no sirven para ver la obra.")
    leyenda = "".join(f'<span style="--c:{c[COLOR_ESTADO[e]]}">{e[:1].upper() + e[1:]}</span>' for e in ESTADOS)
    st.html(f'<div class="leyenda" role="list" aria-label="Leyenda del calendario">{leyenda}</div>')
    st.plotly_chart(calendario(d, c), width="stretch", config={"displayModeBar": False, "scrollZoom": False})

    n = dias["estado"].value_counts()
    vista = cambios_de_vista(d["vistas"])
    st.caption(
        f"De {len(dias)} días, {n.get(UTIL, 0)} tienen fotos útiles de la obra; en {n.get(SIN_FOTO, 0)} no hay "
        f"ninguna foto y en {n.get(NO_SE_VE, 0)} hay fotos pero no se ve la obra. El hueco más largo va del "
        f"{fecha(hueco['inicio'])} al {fecha(hueco['fin'])}"
        + (f"; después, el {fecha(vista.iloc[0])}, cambió la vista de la cámara." if len(vista) == 1
           else f"; la vista de la cámara cambió {len(vista)} veces." if len(vista) else ".")
    )
    with st.expander("Mes a mes"):
        st.markdown("\n".join(f"- {linea}" for linea in resumen_por_mes(dias)))
    with st.expander("¿Por qué faltan datos?"):
        no_se_ve = int(n.get(NO_SE_VE, 0))
        st.markdown(
            f"- **No hay foto:** en {plural(int(n.get(SIN_FOTO, 0)), 'día')} la cámara no envió ninguna foto. "
            "Desde aquí no se puede saber por qué (corte de energía, de conexión u otra causa).\n"
            f"- **Hay foto pero no se ve la obra:** en {plural(no_se_ve, 'día')} la cámara apuntaba a otra cosa "
            "(el cielo, una superficie lisa o un techo) o las fotos estaban demasiado oscuras.\n"
            "- **De noche:** la cámara también toma fotos, pero no sirven para ver la obra; por eso el calendario "
            f"muestra solo de {HORAS_LUZ[0]} a {HORAS_LUZ[-1]} h.\n"
            "- **Fotos que no sirven:** algunas salen empañadas, borrosas, quemadas por el sol o con franjas; casi "
            "siempre hay otras útiles el mismo día.\n"
            + (f"- **La cámara se movió:** el {' y el '.join(fecha(f) for f in vista)} cambió de posición, así que "
               "comparar fotos de antes y después de esa fecha es menos exacto." if len(vista)
               else "- **La cámara no cambió de posición** en todo el periodo.")
        )


# ============================================================================
# Explore por su cuenta y pie
# ============================================================================

def explora(d: dict) -> None:
    dias = d["dias"]
    seccion("Explore por su cuenta", "Compare dos días cualquiera",
            "Elija dos fechas y deslice la barra; también funciona con las flechas del teclado.")
    utiles = dias[dias["estado"].eq(UTIL)].reset_index(drop=True)
    opciones = list(utiles.index)
    etiqueta = {i: fecha(utiles.at[i, "fecha"], dia_semana=True) for i in opciones}
    # Por defecto, la última vista de la cámara (la portada ya muestra la primera)
    ultima = utiles.index[utiles["vista"].eq(utiles["vista"].iloc[-1])]
    c1, c2 = st.columns(2)
    i = c1.selectbox("Primera fecha", opciones, index=int(ultima[0]), format_func=etiqueta.get, key="comp_antes")
    j = c2.selectbox("Segunda fecha", opciones, index=int(ultima[-1]), format_func=etiqueta.get, key="comp_despues")
    if i == j:
        st.info("Elija dos fechas distintas para compararlas.")
        return
    a, b = utiles.loc[min(i, j)], utiles.loc[max(i, j)]
    mostrar_comparacion(d, a, b)
    entre = d["hitos"][(d["hitos"]["fecha_fin"] > a["fecha"]) & (d["hitos"]["fecha_inicio"] < b["fecha"])]
    if len(entre):
        st.markdown(f"Entre estas fechas: " + "; ".join(f"{h.numero}. {h.titulo.lower()}" for h in entre.itertuples()) + ".")


def pie() -> None:
    st.html('<div class="seccion"></div>')
    with st.expander("Cómo se hizo"):
        st.markdown(
            "Se revisaron todas las fotos de la cámara y se descartaron las de noche, las demasiado oscuras, borrosas "
            "o dañadas y las de los días en que la cámara no apuntaba a la obra. De cada día con fotos útiles se eligió "
            "una cercana al mediodía. Los cambios se identificaron a mano, comparando una foto por semana y, para "
            "precisar la fecha, una foto por día. Cuando la cámara se corrió ligeramente, el comparador alinea las "
            "fotos para que coincidan."
        )
    st.caption(f"Fuente: fotografías de la Contraloría General de la República (CGR), proyecto dIAra, de uso público. "
               f"[Código y datos]({REPO_URL}). Proyecto Integrador III · Visualización de datos, Lead University, 2026.")


def main() -> None:
    d = cargar()
    c = COLORES[tema()]
    estilos(c)
    portada(d)
    historia(d, c)
    lo_que_no_se_ve(d, c)
    explora(d)
    pie()


main()
