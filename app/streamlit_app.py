"""Puente sobre el río María Aguilar: lo que muestran las fotos.

App en tres pestañas bajo una franja fija (nombre del puente, fuente y última foto):

  La historia            para la ciudadanía, sin tecnicismos. Lo esencial arriba (estado y tres
                         cifras) y un recorrido en tres partes más un cierre: cómo estaba la obra
                         al inicio, qué cambió (un paso por hito, con foto fija que cambia al
                         desplazarse), cómo está hoy (time-lapse) y lo que no se ve (un punto
                         por foto, por mes).
  Explorar y verificar   para auditoría: detalle de cualquier día, comparador libre de dos
                         fechas y lista completa de hitos con su claridad.
  Datos y método         para auditoría: cobertura por mes, motivos de exclusión, índice de
                         cambio visual con su validación, método y descargas.

Solo lee archivos de app/ (generados por src/06_fotos_app.py y src/07_indice_cambio.py), así
que funciona desplegada sin las fotos originales. Las fotos de app/static/ se sirven por URL
(server.enableStaticServing en .streamlit/config.toml). Nada depende de un número fijo de
hitos: todo se calcula de app/datos.

Uso local:
  streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import html
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

APP = Path(__file__).resolve().parent
DATOS = APP / "datos"
REPO_URL = "https://github.com/samuel-salazarC/proyecto-integrador-III"
NOTA_URL = f"{REPO_URL}/blob/main/docs/nota_metodologica.md"
NOMBRE_OBRA = "Puente sobre el río María Aguilar"

# Estado de cada día (dias.csv)
UTIL = "hay foto útil"
NO_SE_VE = "hay foto pero no se ve la obra"
SIN_FOTO = "no hay foto"
ESTADOS = [UTIL, NO_SE_VE, SIN_FOTO]
CLAVE_ESTADO = {UTIL: "util", NO_SE_VE: "nose", SIN_FOTO: "sin"}
LEYENDA = {UTIL: "Con foto útil", NO_SE_VE: "Con fotos, sin vista de la obra", SIN_FOTO: "Sin foto"}

# Estado de cada foto (fotos.csv), en el orden en que se dibujan
ESTADOS_FOTO = ["útil", "excluida por calidad", "de noche", "sin vista de la obra"]
CLAVE_FOTO = {"útil": "util", "excluida por calidad": "calidad", "de noche": "noche", "sin vista de la obra": "sinvista"}

# Motivos de exclusión (columnas de dias.csv) con el criterio de 01 y 04
MOTIVOS = [
    ("excluidas_nocturna", "Nocturna", "Tomada fuera del horario de 06:00 a 17:59."),
    ("excluidas_luz_insuficiente", "Luz insuficiente",
     "Brillo medio menor a 30 (de 255) o más del 80 % de la imagen subexpuesta."),
    ("excluidas_dia_sin_vista", "Día sin vista de la obra", "La cámara no apuntaba a la obra ese día."),
    ("excluidas_calidad", "Calidad", "Dañada, sobreexpuesta, empañada o iluminada solo por focos al atardecer."),
    ("excluidas_orientacion_dudosa", "Orientación dudosa",
     "No fue posible determinar con confianza la orientación de la imagen."),
    ("excluidas_ilegible", "Ilegible", "El archivo no pudo abrirse."),
]

# Colores. Azul = hay evidencia de la obra; bermellón = no la hay (Okabe-Ito, aptos para
# daltonismo). Para el estado de cada foto se suman ocre (excluida por calidad) y violeta (de
# noche); la paleta de cuatro se validó con el validador de la skill de visualización en claro
# y oscuro (separación para daltonismo y contraste ≥ 3:1). Nunca se usa solo el color: hay
# forma, posición o etiqueta.
COLORES = {
    "light": {"si": "#0072B2", "si_texto": "#FFFFFF", "no": "#D55E00", "no_suave": "#F0B48C", "tinta": "#1A1A19",
              "tenue": "#66635C", "fondo": "#FBFAF7", "fondo2": "#F1EFE9", "borde": "#DEDBD3",
              "hueco": "rgba(213,94,0,0.10)", "banda": "rgba(0,114,178,0.10)",
              "util": "#0072B2", "calidad": "#B07D00", "noche": "#7650B8", "sinvista": "#D55E00"},
    "dark": {"si": "#3D9BE0", "si_texto": "#10100F", "no": "#E8743B", "no_suave": "#7E3A16", "tinta": "#EDEBE6",
             "tenue": "#A8A59D", "fondo": "#141413", "fondo2": "#1F1F1D", "borde": "#3A3936",
             "hueco": "rgba(232,116,59,0.16)", "banda": "rgba(61,155,224,0.16)",
             "util": "#3D9BE0", "calidad": "#C8921A", "noche": "#9C78E0", "sinvista": "#E8743B"},
}
CLARIDAD = {"alta": "muy claro", "media": "claro", "baja": "poco claro"}  # según la confianza de hitos.csv
CRITERIO_CLARIDAD = {"muy claro": "cualquier persona ve el cambio sin que se le indique dónde mirar",
                     "claro": "se ve, pero hay que señalar la zona",
                     "poco claro": "requiere interpretación; otra persona podría no estar de acuerdo"}
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
MESES_LARGO = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
               "septiembre", "octubre", "noviembre", "diciembre"]
DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
DIAS_LARGO = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
NUMEROS = ["cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez",
           "once", "doce", "trece", "catorce", "quince", "dieciséis", "diecisiete", "dieciocho",
           "diecinueve", "veinte"]
# Hito que marca el puente en uso (frase de estado y cifras): se busca esta palabra en el
# título. Si ningún hito la tiene, se usa el último cambio visible.
PALABRA_PUENTE_EN_USO = "vehículos"
FOTO_RADIO = "10px"
FOTO_PROPORCION = "5 / 4"
FOTO_ANCHO, FOTO_ALTO = 960, 768  # tamaño de las fotos de app/static/fotos
ANCHO_CONTENIDO = 960
MINUTOS_LEJOS_MEDIODIA = 30  # en el time-lapse se señala la hora si la foto se aleja más de esto de las 12:00
TOTAL_PARTES = 4

st.set_page_config(page_title="Puente sobre el río María Aguilar: lo que muestran las fotos", page_icon="🌉",
                   layout="wide")


# ============================================================================
# Datos
# ============================================================================

@st.cache_data
def cargar() -> dict[str, pd.DataFrame]:
    dias = pd.read_csv(DATOS / "dias.csv", parse_dates=["fecha", "fecha_hora_foto"])
    fotos = pd.read_csv(DATOS / "fotos.csv", parse_dates=["fecha"])
    hitos = pd.read_csv(DATOS / "hitos.csv", parse_dates=["fecha_inicio", "fecha_fin", "fecha_hora_antes", "fecha_hora_despues"])
    vistas = pd.read_csv(DATOS / "vistas.csv", parse_dates=["fecha_inicio", "fecha_fin"])
    alineacion = pd.read_csv(DATOS / "alineacion_dia.csv", parse_dates=["fecha"])
    indice = pd.read_csv(DATOS / "indice_cambio.csv", parse_dates=["fecha", "fecha_anterior"])
    for tabla in (dias, hitos, vistas, alineacion, indice):
        tabla["vista"] = tabla["vista"].astype("Int64")
    hitos = hitos.sort_values(["fecha_inicio", "fecha_fin"]).reset_index(drop=True)
    hitos["numero"] = range(1, len(hitos) + 1)
    fotos["mes"] = fotos["fecha"].dt.to_period("M")
    fotos["hora_h"] = fotos["hora"].str[:2].astype(int)
    return {"dias": dias, "fotos": fotos, "hitos": hitos, "vistas": vistas, "alineacion": alineacion,
            "indice": indice}


def url_foto(ruta: str) -> str:
    """static/fotos/x.jpg (relativa a app/) -> URL que sirve Streamlit."""
    return f"app/{ruta}"


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


def utiles(dias: pd.DataFrame) -> pd.DataFrame:
    return dias[dias["estado"].eq(UTIL)].set_index("fecha", drop=False)


# ============================================================================
# Formato
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


def mes_largo(periodo: pd.Period) -> str:
    return f"{mayuscula(MESES_LARGO[periodo.month - 1])} de {periodo.year}"


def hora(f: pd.Timestamp) -> str:
    return f"{f.hour}:{f.minute:02d}"


def miles(n: float) -> str:
    """21644 -> '21 644' (espacio fino como separador de miles)."""
    return f"{int(n):,}".replace(",", " ")


def decimal(x: float, d: int = 1) -> str:
    """1.5 -> '1,5' (coma decimal)."""
    return f"{x:.{d}f}".replace(".", ",")


def plural(n: int, singular: str, plural_: str | None = None) -> str:
    return f"{miles(n)} {singular if n == 1 else (plural_ or singular + 's')}"


def palabra(n: int, mayus: bool = False) -> str:
    texto = NUMEROS[n] if 0 <= n < len(NUMEROS) else str(n)
    return mayuscula(texto) if mayus else texto


def mayuscula(texto: str) -> str:
    return texto[:1].upper() + texto[1:]


def minuscula(texto: str) -> str:
    return texto[:1].lower() + texto[1:]


def enumerar(partes: list[str]) -> str:
    """['a', 'b', 'c'] -> 'a, b y c'."""
    return partes[0] if len(partes) == 1 else ", ".join(partes[:-1]) + " y " + partes[-1]


def alt_foto(f: pd.Timestamp, extra: str = "") -> str:
    return (f"Foto de la cámara tomada el {fecha_larga(f, dia_semana=True)} a las {hora(f)}: "
            f"vista del puente sobre el río María Aguilar y la vía a su alrededor.{(' ' + extra) if extra else ''}")


def claridad(h) -> str | None:
    return CLARIDAD.get(str(h["confianza"]).strip().lower())


def tema() -> str:
    try:
        return "dark" if st.context.theme.type == "dark" else "light"
    except Exception:
        return "light"


# ============================================================================
# Alineación (alineacion_dia.csv, de 07): cada día al marco del primer día de su vista
# ============================================================================

def matriz_dia(alineacion: pd.DataFrame, f: pd.Timestamp) -> np.ndarray | None:
    fila = alineacion[alineacion["fecha"].eq(f)]
    if fila.empty:
        return None
    m = fila.iloc[0]
    return np.array([[m.m00, m.m01, m.m02], [m.m10, m.m11, m.m12], [0, 0, 1]], dtype=float)


def matriz_entre(alineacion: pd.DataFrame, a: pd.Timestamp, b: pd.Timestamp) -> np.ndarray | None:
    """Puntos de la foto del día a -> foto del día b (misma vista)."""
    ta, tb = matriz_dia(alineacion, a), matriz_dia(alineacion, b)
    return None if ta is None or tb is None else tb @ np.linalg.inv(ta)


def transformacion_css(inversa: np.ndarray) -> dict:
    """Traslación, giro y escala CSS (origen al centro) que llevan una foto a otro marco.
    `inversa` lleva puntos de esa foto al marco de destino."""
    centro = np.array([FOTO_ANCHO / 2, FOTO_ALTO / 2, 1.0])
    desplazamiento = (inversa @ centro)[:2] - centro[:2]
    return {"tx": round(desplazamiento[0] / FOTO_ANCHO * 100, 4), "ty": round(desplazamiento[1] / FOTO_ALTO * 100, 4),
            "rot": round(float(np.degrees(np.arctan2(inversa[1, 0], inversa[0, 0]))), 4),
            "escala": round(float(np.hypot(inversa[0, 0], inversa[1, 0])), 5)}


def ventana_comun(inversas: list[np.ndarray]) -> dict:
    """Recorte (zoom y esquina, en % del marco) que oculta los bordes sin imagen de todas las fotos."""
    izq, arr, der, aba = 0.0, 0.0, float(FOTO_ANCHO), float(FOTO_ALTO)
    esquinas = np.array([[0, FOTO_ANCHO, 0, FOTO_ANCHO], [0, 0, FOTO_ALTO, FOTO_ALTO], [1, 1, 1, 1]])
    for inv in inversas:
        e = inv @ esquinas
        izq, der = max(izq, e[0, 0], e[0, 2]), min(der, e[0, 1], e[0, 3])
        arr, aba = max(arr, e[1, 0], e[1, 1]), min(aba, e[1, 2], e[1, 3])
    zoom = max(FOTO_ANCHO / (der - izq), FOTO_ALTO / (aba - arr)) * 1.005
    vx = min(max((izq + der) / 2 - FOTO_ANCHO / zoom / 2, izq), der - FOTO_ANCHO / zoom)
    vy = min(max((arr + aba) / 2 - FOTO_ALTO / zoom / 2, arr), aba - FOTO_ALTO / zoom)
    return {"zoom": round(zoom, 5), "vx": round(vx / FOTO_ANCHO * 100, 4), "vy": round(vy / FOTO_ALTO * 100, 4)}


def ajuste_par(alineacion: pd.DataFrame, a: pd.Timestamp, b: pd.Timestamp) -> dict | None:
    """Ajuste CSS que lleva la foto de b al marco de la de a, con el recorte común."""
    total = matriz_entre(alineacion, a, b)
    if total is None:
        return None
    inversa = np.linalg.inv(total)
    return {**transformacion_css(inversa), **ventana_comun([np.eye(3), inversa])}


# ============================================================================
# Estilo
# ============================================================================

def estilos(c: dict) -> None:
    st.html(f"""<style>
[data-testid="stMainBlockContainer"] {{ max-width: {ANCHO_CONTENIDO + 40}px; padding: 1.5rem 1rem 5rem; }}
h1, h2, h3 {{ font-family: "Source Serif 4", Georgia, serif !important; }}
[data-testid="stHeadingWithActionElements"] h2, [data-testid="stHeadingWithActionElements"] h3 {{ padding-top: 0.2rem !important; }}
h1 {{ font-size: clamp(2rem, 1.3rem + 3.2vw, 3.3rem) !important; line-height: 1.05 !important;
      letter-spacing: -0.02em; padding-bottom: 0.3rem !important; }}
h2 {{ font-size: clamp(1.5rem, 1.15rem + 1.8vw, 2.3rem) !important; line-height: 1.12 !important; letter-spacing: -0.01em; }}
h3 {{ font-size: clamp(1.2rem, 1.05rem + 0.8vw, 1.6rem) !important; line-height: 1.2 !important; }}
[data-testid="stMarkdownContainer"] p, [data-testid="stCaptionContainer"] p {{ max-width: 68ch; }}

/* Franja superior, fija sobre las pestañas */
.franja {{ display: flex; flex-wrap: wrap; justify-content: space-between; gap: 0.25rem 1.5rem; padding: 0 0 0.6rem;
           border-bottom: 1px solid {c['borde']}; font-size: 0.88rem; line-height: 1.4; color: {c['tenue']}; }}
.franja b {{ color: {c['tinta']}; font-weight: 700; }}
.franja .datos {{ display: flex; flex-wrap: wrap; gap: 0.25rem 1.25rem; }}
.franja .datos span {{ white-space: nowrap; }}
/* Pestañas: zona táctil de 44 px, texto legible y nombres completos (si no caben, la fila se
   desplaza en horizontal en vez de cortarlos) */
[data-baseweb="tab-list"] {{ overflow-x: auto; scrollbar-width: none; }}
[data-baseweb="tab-list"] button {{ min-height: 44px; flex-shrink: 0; }}
[data-baseweb="tab-list"] button p {{ font-size: 1rem; font-weight: 600; white-space: nowrap; }}
@media (max-width: 420px) {{
  [data-baseweb="tab-list"] {{ gap: 0.9rem; }}
  [data-baseweb="tab-list"] button p {{ font-size: 0.93rem; }}
}}
/* Destinos de los saltos: quedan bajo la barra superior de Streamlit */
.ancla {{ scroll-margin-top: 4.5rem; outline: none; }}
/* Aviso solo en celular (Datos y método) */
.solo-celular {{ display: none; }}
/* Índice de cambio: en celular el gráfico conserva un ancho legible y se desplaza en horizontal */
@media (max-width: 640px) {{
  .solo-celular {{ display: block; margin: 0.2rem 0 0.4rem; font-size: 0.85rem; color: {c['tenue']}; }}
  .st-key-indice {{ overflow-x: auto; }}
  .st-key-indice > div {{ min-width: 720px; }}
}}

/* Textos */
.kicker {{ text-transform: uppercase; letter-spacing: 0.09em; font-size: 0.78rem; font-weight: 700;
           color: {c['tenue']}; margin: 0; }}
.bajada {{ font-size: clamp(1.05rem, 1rem + 0.35vw, 1.25rem); line-height: 1.45; color: {c['tenue']};
           max-width: 60ch; margin: 0; }}
.estado {{ font-size: clamp(1.1rem, 1.02rem + 0.5vw, 1.35rem); line-height: 1.4; color: {c['tinta']};
           max-width: 52ch; margin: 0; }}
.estado::before {{ content: ""; display: inline-block; width: 0.6em; height: 0.6em; border-radius: 50%;
                   background: {c['si']}; margin-right: 0.5em; vertical-align: 0.08em; }}
.seccion {{ margin: 3rem 0 0.75rem; border-top: 1px solid {c['borde']}; }}
.partes {{ display: flex; gap: 4px; margin: 0 0 0.4rem; }}
.partes span {{ width: 1.6rem; height: 4px; border-radius: 2px; background: {c['borde']}; }}
.partes span.hecha {{ background: {c['tinta']}; }}

/* Cifras */
.cifras {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.75rem 1.5rem; margin: 0.25rem 0 0; }}
.cifra {{ border-top: 3px solid {c['borde']}; padding-top: 0.6rem; }}
.cifra.si {{ border-top-color: {c['si']}; }} .cifra.no {{ border-top-color: {c['no']}; }}
.cifra .num {{ display: block; font-family: "Source Serif 4", serif; font-weight: 700; line-height: 1;
              font-size: clamp(1.8rem, 1.4rem + 1.6vw, 2.6rem); color: {c['tinta']}; font-variant-numeric: tabular-nums; }}
.cifra .num small {{ font-size: 0.5em; font-weight: 600; margin-left: 0.2em; }}
.cifra .txt {{ display: block; margin-top: 0.35rem; font-size: 0.93rem; line-height: 1.35; color: {c['tenue']}; }}
.cifras.cuatro {{ grid-template-columns: repeat(4, minmax(0, 1fr)); }}
.cifras.tres {{ grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.75rem; }}
@media (max-width: 640px) {{
  .cifras {{ grid-template-columns: 1fr; gap: 0.9rem; }}
  .cifras.cuatro {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
  .cifras.tres {{ grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.6rem; }}
}}

/* Tablas para auditoría */
.tabla {{ width: 100%; border-collapse: collapse; font-size: 0.92rem; line-height: 1.4; font-variant-numeric: tabular-nums; }}
.tabla caption {{ text-align: left; font-weight: 700; padding: 0 0 0.4rem; }}
.tabla th, .tabla td {{ text-align: left; vertical-align: top; padding: 0.45rem 0.6rem 0.45rem 0; border-top: 1px solid {c['borde']}; }}
.tabla th {{ font-size: 0.8rem; color: {c['tenue']}; font-weight: 600; }}
.tabla td.n, .tabla th.n {{ text-align: right; white-space: nowrap; }}
.tabla .tenue {{ color: {c['tenue']}; }}
.envoltura {{ overflow-x: auto; }}
.marca {{ display: inline-flex; align-items: center; gap: 0.35em; white-space: nowrap; }}
.marca::before {{ content: ""; width: 0.7em; height: 0.7em; border-radius: 50%; box-sizing: border-box; }}
.marca.si::before {{ background: {c['tinta']}; }}
.marca.no::before {{ border: 1.5px solid {c['tenue']}; }}
.leyenda {{ display: flex; flex-wrap: wrap; gap: 0.4rem 1.2rem; font-size: 0.9rem; color: {c['tenue']}; margin: 0.25rem 0; }}
.leyenda span::before {{ content: ""; display: inline-block; width: 0.85em; height: 0.85em; margin-right: 0.4em;
                        vertical-align: -0.05em; border-radius: 2px; background: var(--c); }}
.claridad {{ display: inline-block; margin: 0; padding: 0.3rem 0.75rem; border: 1px solid {c['borde']};
             border-radius: 999px; font-size: 0.9rem; color: {c['tenue']}; }}
.claridad b {{ color: {c['tinta']}; }}
.alcance {{ margin: 0; font-size: 0.95rem; color: {c['tinta']}; max-width: 68ch; }}

/* Fotos: un solo marco (misma proporción, esquinas y borde), sin ampliar más allá de su tamaño */
[data-testid="stImage"] img {{ aspect-ratio: {FOTO_PROPORCION}; object-fit: cover; border-radius: {FOTO_RADIO};
                               border: 1px solid {c['borde']}; box-sizing: border-box; max-width: {ANCHO_CONTENIDO}px; }}
[data-testid="stImage"] [data-testid="stImageCaption"], [data-testid="stImage"] + div p {{ font-size: 0.88rem; }}
.stButton button, .stDownloadButton button {{ min-height: 44px; padding: 0.4rem 1rem; }}
</style>""")


def seccion(kicker: str, titular: str, frase: str | None = None, parte: int | None = None,
            id_: str | None = None) -> None:
    """Encabezado de sección: rótulo, titular con la conclusión y como máximo una frase. Con
    `parte`, una barra de avance indica en qué parte de la historia va el lector."""
    barra = ""
    if parte:
        barra = ('<div class="partes" aria-hidden="true">'
                 + "".join(f'<span class="{"hecha" if k <= parte else ""}"></span>' for k in range(1, TOTAL_PARTES + 1))
                 + "</div>")
    marca = f'<div id="{id_}" tabindex="-1" class="ancla"></div>' if id_ else ""
    st.html(f'<div class="seccion" aria-hidden="true"></div>{marca}{barra}<p class="kicker">{html.escape(kicker)}</p>')
    st.header(titular, anchor=False)
    if frase:
        st.html(f'<p class="bajada">{html.escape(frase)}</p>')


def descripcion(texto: str, titulo: str = "Descripción del gráfico") -> None:
    with st.expander(titulo):
        st.markdown(texto)


# ============================================================================
# Visor a pantalla completa (compartido por los componentes con fotos)
# ============================================================================

# Tocar o hacer clic en una foto (o en su botón «Ampliar») la abre en un <dialog> modal a
# pantalla completa: botones para acercar y alejar (también + y −, 0 vuelve al tamaño
# inicial, doble clic alterna 1× y 2×), flechas para pasar entre las fotos del conjunto
# (antes y después) y «Cerrar». Escape cierra (comportamiento nativo del <dialog>) y el foco
# vuelve al elemento que lo abrió. Con zoom, la foto se recorre desplazándose.
VISOR_CSS = """
dialog.visor { padding: 0; border: 0; margin: 0; width: 100vw; height: 100dvh; max-width: 100vw; max-height: 100dvh;
  background: #0c0c0b; color: #fff; font-family: var(--st-font, sans-serif); }
dialog.visor::backdrop { background: rgba(0, 0, 0, 0.85); }
.visor .barra { position: absolute; top: 0; left: 0; right: 0; display: flex; align-items: center; gap: 0.4rem; padding: 0.5rem;
  background: rgba(0, 0, 0, 0.7); z-index: 2; font: 600 0.95rem/1.25 var(--st-font, sans-serif); }
.visor .barra .tit { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.visor button { min-width: 44px; min-height: 44px; border-radius: 0.5rem; border: 1px solid rgba(255, 255, 255, 0.5);
  background: transparent; color: #fff; font: 700 1.05rem/1 var(--st-font, sans-serif); cursor: pointer; padding: 0 0.7rem; }
.visor button:focus-visible { outline: 3px solid #fff; outline-offset: 2px; }
.visor .zona { position: absolute; top: 60px; left: 0; right: 0; bottom: 0; overflow: auto; display: flex; }
.visor .zona img { display: block; margin: auto; flex-shrink: 0; max-width: none; user-select: none; }
button.ampliar { position: absolute; right: 8px; bottom: 8px; z-index: 4; min-width: 44px; min-height: 44px; padding: 0 0.7rem;
  border-radius: 0.5rem; border: 0; background: rgba(20, 20, 19, 0.82); color: #fff; cursor: pointer;
  font: 600 0.9rem/1 var(--st-font, sans-serif); }
button.ampliar:hover { background: rgba(20, 20, 19, 0.95); }
button.ampliar:focus-visible { outline: 3px solid #fff; outline-offset: 2px; box-shadow: 0 0 0 5px rgba(20, 20, 19, 0.9); }
"""

VISOR_JS = """
function abrirVisor(raiz, fotos, inicial) {
  const origen = raiz.getRootNode().activeElement;
  const d = document.createElement('dialog');
  d.className = 'visor';
  d.setAttribute('aria-label', 'Foto ampliada');
  const varias = fotos.length > 1;
  d.innerHTML = '<div class="barra"><span class="tit" aria-live="polite"></span>' +
    (varias ? '<button type="button" data-a="ant" aria-label="Foto anterior">&#8249;</button>' +
              '<button type="button" data-a="sig" aria-label="Foto siguiente">&#8250;</button>' : '') +
    '<button type="button" data-a="menos" aria-label="Alejar">&#8722;</button>' +
    '<button type="button" data-a="mas" aria-label="Acercar">+</button>' +
    '<button type="button" data-a="cerrar" aria-label="Cerrar la foto ampliada (Escape)">&#10005; Cerrar</button></div>' +
    '<div class="zona"><img alt=""></div>';
  raiz.appendChild(d);
  const img = d.querySelector('img'), zona = d.querySelector('.zona'), tit = d.querySelector('.tit');
  let i = inicial || 0, zoom = 1;
  function ajustar() {
    const r = (img.naturalWidth / img.naturalHeight) || 1.25;
    const base = Math.min(zona.clientWidth, zona.clientHeight * r);
    img.style.width = Math.round(base * zoom) + 'px';
    zona.scrollLeft = (zona.scrollWidth - zona.clientWidth) / 2;
    zona.scrollTop = (zona.scrollHeight - zona.clientHeight) / 2;
  }
  function mostrar() {
    const f = fotos[i];
    if (img.getAttribute('src') !== f.u) { img.onload = ajustar; img.src = f.u; }
    img.alt = f.alt || '';
    tit.textContent = f.t + (varias ? ' (' + (i + 1) + ' de ' + fotos.length + ')' : '') + (zoom > 1 ? ' · ' + zoom + '×' : '');
    ajustar();
  }
  const acercar = (z) => { zoom = Math.min(4, Math.max(1, z)); mostrar(); };
  const pasar = (k) => { i = (i + k + fotos.length) % fotos.length; mostrar(); };
  d.addEventListener('click', (e) => {
    if (e.target === d) { d.close(); return; }
    const a = e.target.closest('[data-a]');
    if (!a) return;
    ({ cerrar: () => d.close(), mas: () => acercar(zoom + 1), menos: () => acercar(zoom - 1),
       ant: () => pasar(-1), sig: () => pasar(1) })[a.dataset.a]();
  });
  img.addEventListener('dblclick', () => acercar(zoom > 1 ? 1 : 2));
  d.addEventListener('keydown', (e) => {
    if (e.key === '+' || e.key === '=') acercar(zoom + 1);
    else if (e.key === '-') acercar(zoom - 1);
    else if (e.key === '0') acercar(1);
    else if (varias && e.key === 'ArrowRight' && zoom === 1) pasar(1);
    else if (varias && e.key === 'ArrowLeft' && zoom === 1) pasar(-1);
    else return;
    e.preventDefault();
  });
  window.addEventListener('resize', ajustar);
  d.addEventListener('close', () => {
    window.removeEventListener('resize', ajustar);
    d.remove();
    if (origen && origen.focus) origen.focus({ preventScroll: true });
  });
  d.showModal();
  d.querySelector('[data-a="cerrar"]').focus();
  mostrar();
}
"""


def componente(nombre: str, css: str, js: str):
    """Componente propio con el visor a pantalla completa disponible (abrirVisor)."""
    return st.components.v2.component(nombre, css=css + VISOR_CSS, js=VISOR_JS + js)


def css_transform(t: dict | None) -> str:
    return f"translate({t['tx']}%,{t['ty']}%) rotate({t['rot']}deg) scale({t['escala']})" if t else "none"


def css_ventana(v: dict | None) -> str:
    return f"scale({v['zoom']}) translate({-v['vx']}%,{-v['vy']}%)" if v else "none"


# ============================================================================
# Foto suelta ampliable (detalle del día)
# ============================================================================

FOTO_CSS = """
.foto { font-family: var(--st-font, sans-serif); color: var(--st-text-color); }
.foto .marco { position: relative; aspect-ratio: 5 / 4; overflow: hidden; border-radius: 10px; border: 1px solid var(--borde);
  box-sizing: border-box; cursor: zoom-in; }
.foto .marco img { width: 100%; height: 100%; object-fit: cover; display: block; }
.foto p { font-size: 0.88rem; opacity: 0.8; margin: 0.35rem 0 0; }
"""

FOTO_JS = """
export default function (component) {
  const { data, parentElement } = component;
  parentElement.querySelectorAll('.foto').forEach((e) => e.remove());
  const raiz = document.createElement('div');
  raiz.className = 'foto';
  raiz.style.setProperty('--borde', data.borde);
  parentElement.appendChild(raiz);
  raiz.innerHTML = '<div class="marco"><img src="' + data.u + '" alt="' + data.alt + '">' +
    '<button type="button" class="ampliar" aria-label="Ampliar la foto a pantalla completa">&#10530; Ampliar</button></div>' +
    (data.pie ? '<p>' + data.pie + '</p>' : '');
  const abrir = () => abrirVisor(raiz, [{ u: data.u, alt: data.alt, t: data.t }], 0);
  raiz.querySelector('.marco img').addEventListener('click', abrir);
  raiz.querySelector('.ampliar').addEventListener('click', abrir);
  return () => raiz.remove();
}
"""

foto_componente = componente("foto_ampliable", FOTO_CSS, FOTO_JS)


def mostrar_foto(ruta: str, momento: pd.Timestamp, pie: str, c: dict, key: str) -> None:
    foto_componente(data={"u": url_foto(ruta), "alt": html.escape(alt_foto(momento)), "pie": html.escape(pie),
                          "t": f"{fecha(momento, dia_semana=True)}, {hora(momento)}", "borde": c["borde"]}, key=key)


# ============================================================================
# Comparador (Explorar y verificar): barra, lado a lado y parpadeo
# ============================================================================

# Tres modos sobre las mismas dos fotos, con la de después alineada a la de antes cuando son
# de la misma vista (alineacion_dia.csv) y las dos recortadas a la zona común:
#   barra      la de antes se recorta hasta la posición de una barra (<input type="range">,
#              mouse, dedo o flechas del teclado).
#   lado       las dos fotos una junto a la otra (una sobre otra en pantallas angostas).
#   parpadeo   alterna las dos fotos cada 0,8 s en el mismo lugar; botón para pausar. Con
#              «reducir movimiento» empieza en pausa.
# «Mostrar dónde cambió» (solo si las fechas son días con evidencia consecutivos de la misma
# vista) superpone el mapa de cambio de 07 en magenta. El modo elegido se recuerda.
COMPARADOR_CSS = """
.cmp { font-family: var(--st-font, sans-serif); color: var(--st-text-color); max-width: 960px; }
.cmp .ctl { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem 1rem; margin: 0 0 0.6rem; }
.cmp .modos { display: flex; flex-wrap: wrap; gap: 0.35rem; }
.cmp button.m, .cmp .pausa { min-height: 44px; padding: 0 0.85rem; border-radius: 0.6rem; border: 1px solid var(--borde);
  background: transparent; color: inherit; font: 600 0.92rem/1 var(--st-font, sans-serif); cursor: pointer; }
.cmp button.m[aria-pressed="true"] { border-color: var(--st-text-color); box-shadow: inset 0 0 0 1px var(--st-text-color); }
.cmp button:focus-visible, .cmp input:focus-visible + .foco { outline: 3px solid var(--st-text-color); outline-offset: 2px; }
.cmp .chk { display: inline-flex; align-items: center; gap: 0.45rem; min-height: 44px; font-size: 0.95rem; cursor: pointer; }
.cmp .chk input { width: 20px; height: 20px; accent-color: var(--mapa); }
.cmp .chk input:focus-visible { outline: 3px solid var(--st-text-color); outline-offset: 2px; }
.cmp .marco { position: relative; aspect-ratio: 5 / 4; overflow: hidden; border-radius: 10px; border: 1px solid var(--borde);
  box-sizing: border-box; line-height: 0; user-select: none; touch-action: pan-y; background: var(--fondo2); }
.cmp .lienzo { position: absolute; inset: 0; transform-origin: 0 0; }
.cmp .lienzo img { width: 100%; height: auto; display: block; transform-origin: 50% 50%; }
.cmp .lienzo .encima { position: absolute; inset: 0; }
.cmp .lienzo .mapa { position: absolute; left: 0; top: 0; width: 100%; height: auto; pointer-events: none; }
.cmp .rotulo { position: absolute; top: 10px; z-index: 3; padding: 5px 9px; border-radius: 4px; background: rgba(20, 20, 19, 0.82);
  color: #fff; font: 600 13px/1.2 var(--st-font, sans-serif); pointer-events: none; }
.cmp .izq { left: 10px; } .cmp .der { right: 10px; }
.cmp .linea { position: absolute; top: 0; bottom: 0; left: 50%; width: 3px; margin-left: -1.5px; background: #fff; z-index: 2;
  box-shadow: 0 0 4px rgba(0, 0, 0, 0.6); pointer-events: none; }
.cmp .asa { position: absolute; top: 50%; left: 50%; width: 44px; height: 44px; margin: -22px 0 0 -22px; border-radius: 50%; z-index: 2;
  background: #fff; box-shadow: 0 1px 8px rgba(0, 0, 0, 0.55); pointer-events: none; display: flex; align-items: center;
  justify-content: center; font: 700 18px/1 system-ui, sans-serif; color: #1a1a19; }
.cmp input[type=range] { position: absolute; inset: 0; width: 100%; height: 100%; margin: 0; opacity: 0; cursor: ew-resize; z-index: 3; }
.cmp .marco:has(input[type=range]:focus-visible) { outline: 3px solid var(--st-text-color); outline-offset: 2px; }
.cmp .doble { display: grid; grid-template-columns: 1fr 1fr; gap: 0.6rem; }
.cmp .doble .marco { cursor: zoom-in; }
.cmp .solo .marco { cursor: zoom-in; }
.cmp .nota { font-size: 0.88rem; opacity: 0.8; margin: 0.4rem 0 0; line-height: 1.4; }
.cmp .nota i { display: inline-block; width: 0.8em; height: 0.8em; background: var(--mapa); border-radius: 2px; vertical-align: -0.05em; }
@media (max-width: 560px) { .cmp .doble { grid-template-columns: 1fr; } }
"""

COMPARADOR_JS = """
const memoriaCmp = new Map();

export default function (component) {
  const { data, parentElement } = component;
  parentElement.querySelectorAll('.cmp').forEach((e) => e.remove());
  const m = memoriaCmp.get(data.id) || { modo: 'barra', mapa: false };
  memoriaCmp.set(data.id, m);
  if (!data.mapa) m.mapa = false;
  const raiz = document.createElement('div');
  raiz.className = 'cmp';
  Object.entries(data.colores).forEach(([k, v]) => raiz.style.setProperty('--' + k, v));
  parentElement.appendChild(raiz);
  const A = data.a, B = data.b;
  const quieto = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const MODOS = [['barra', 'Barra deslizante'], ['lado', 'Lado a lado'], ['parpadeo', 'Parpadeo']];
  let temporizador = null, pausado = quieto, verB = false;
  const fotos = [{ u: A.u, alt: A.alt, t: A.t }, { u: B.u, alt: B.alt, t: B.t }];
  const tf = (t) => t ? 'translate(' + t.tx + '%,' + t.ty + '%) rotate(' + t.rot + 'deg) scale(' + t.escala + ')' : 'none';
  const ven = data.ventana ? 'scale(' + data.ventana.zoom + ') translate(' + (-data.ventana.vx) + '%,' + (-data.ventana.vy) + '%)' : 'none';
  const mapa = () => m.mapa && data.mapa ? '<img class="mapa" alt="" src="' + data.mapa.u + '" style="transform-origin:50% 50%;transform:' + tf(data.mapa.aj) + '">' : '';
  const img = (f, aj, clase) => '<img class="' + (clase || '') + '" src="' + f.u + '" alt="' + f.alt + '" style="transform:' + tf(aj) + '">';
  const ampliar = (k) => '<button type="button" class="ampliar" data-ampliar="' + k + '" aria-label="Ampliar las fotos a pantalla completa">&#10530; Ampliar</button>';

  function escena() {
    if (m.modo === 'barra') {
      return '<div class="marco"><div class="lienzo" style="transform:' + ven + '">' + img(B, data.aj) +
        '<div class="encima antes">' + img(A, null) + '</div>' + mapa() + '</div>' +
        '<div class="linea"></div><div class="asa" aria-hidden="true">&#8596;</div>' +
        '<span class="rotulo izq" aria-hidden="true">' + A.t + '</span><span class="rotulo der" aria-hidden="true">' + B.t + '</span>' +
        '<input type="range" min="0" max="100" step="1" value="' + (m.barra || 50) + '" aria-label="Barra de comparación: a la izquierda ' +
        A.t + ', a la derecha ' + B.t + '">' + ampliar(0) + '</div>';
    }
    if (m.modo === 'lado') {
      return '<div class="doble">' +
        '<div class="marco" data-foto="0"><div class="lienzo" style="transform:' + ven + '">' + img(A, null) + '</div>' +
        '<span class="rotulo izq" aria-hidden="true">' + A.t + '</span>' + ampliar(0) + '</div>' +
        '<div class="marco" data-foto="1"><div class="lienzo" style="transform:' + ven + '">' + img(B, data.aj) + mapa() + '</div>' +
        '<span class="rotulo izq" aria-hidden="true">' + B.t + '</span>' + ampliar(1) + '</div></div>';
    }
    return '<div class="solo"><div class="marco" data-foto="parpadeo"><div class="lienzo" style="transform:' + ven + '">' + img(A, null) +
      '<div class="encima despues">' + img(B, data.aj) + '</div>' + mapa() + '</div>' +
      '<span class="rotulo izq" aria-hidden="true"></span>' + ampliar('parpadeo') + '</div></div>';
  }

  function dibujar(enfocar) {
    clearInterval(temporizador);
    let h = '<div class="ctl"><div class="modos" role="group" aria-label="Modo de comparación">' +
      MODOS.map(([k, t]) => '<button type="button" class="m" data-m="' + k + '" aria-pressed="' + (m.modo === k) + '">' + t + '</button>').join('') +
      '</div>' + (m.modo === 'parpadeo' ? '<button type="button" class="pausa"></button>' : '') +
      (data.mapa ? '<label class="chk"><input type="checkbox"' + (m.mapa ? ' checked' : '') + '> Mostrar dónde cambió</label>' : '') +
      '</div>' + escena();
    if (data.mapa && m.mapa) h += '<p class="nota"><i></i> Zonas donde el índice de cambio visual detectó un cambio entre estas dos fechas (' +
      data.mapa.indice + ' de la zona analizada). Las zonas que cambian casi siempre (vegetación, nubes) no se analizan.</p>';
    else if (data.nota) h += '<p class="nota">' + data.nota + '</p>';
    raiz.innerHTML = h;
    raiz.querySelectorAll('button.m').forEach((b) => b.addEventListener('click', () => { m.modo = b.dataset.m; dibujar('[data-m="' + m.modo + '"]'); }));
    const chk = raiz.querySelector('.chk input');
    if (chk) chk.addEventListener('change', () => { m.mapa = chk.checked; dibujar('.chk input'); });
    raiz.querySelectorAll('[data-ampliar]').forEach((b) => b.addEventListener('click', (e) => {
      e.stopPropagation();
      const k = b.dataset.ampliar;
      abrirVisor(raiz, fotos, k === 'parpadeo' ? (verB ? 1 : 0) : Number(k));
    }));
    raiz.querySelectorAll('[data-foto]').forEach((el) => el.addEventListener('click', () => {
      const k = el.dataset.foto;
      abrirVisor(raiz, fotos, k === 'parpadeo' ? (verB ? 1 : 0) : Number(k));
    }));
    if (m.modo === 'barra') {
      const r = raiz.querySelector('input[type=range]'), z = data.ventana ? data.ventana.zoom : 1, vx = data.ventana ? data.ventana.vx : 0;
      const mover = () => {
        const v = Number(r.value), x = vx + v / z;
        m.barra = v;
        raiz.querySelector('.antes').style.clipPath = 'inset(0 ' + (100 - x) + '% 0 0)';
        raiz.querySelector('.linea').style.left = v + '%';
        raiz.querySelector('.asa').style.left = v + '%';
        r.setAttribute('aria-valuetext', v + ' por ciento de la foto de la izquierda visible');
      };
      r.addEventListener('input', mover); mover();
    }
    if (m.modo === 'parpadeo') {
      const capa = raiz.querySelector('.despues'), rot = raiz.querySelector('.solo .rotulo'), boton = raiz.querySelector('.pausa');
      const poner = () => { capa.style.opacity = verB ? 1 : 0; rot.textContent = (verB ? 'Después · ' : 'Antes · ') + (verB ? B.t : A.t); };
      const botones = () => { boton.textContent = pausado ? '▶ Reanudar' : '❚❚ Pausar';
        boton.setAttribute('aria-label', pausado ? 'Reanudar el parpadeo' : 'Pausar el parpadeo'); };
      const correr = () => { clearInterval(temporizador); if (!pausado) temporizador = setInterval(() => { verB = !verB; poner(); }, 800); };
      boton.addEventListener('click', () => { pausado = !pausado; botones(); correr(); });
      poner(); botones(); correr();
    }
    if (enfocar) { const el = raiz.querySelector(enfocar); if (el) el.focus({ preventScroll: true }); }
  }
  dibujar();
  return () => { clearInterval(temporizador); raiz.remove(); };
}
"""

comparador_componente = componente("comparador", COMPARADOR_CSS, COMPARADOR_JS)


def mapa_de_cambio(d: dict, a: pd.Series, b: pd.Series) -> dict | None:
    """Mapa de 07 para el par (a, b) si b se comparó con a en el índice (días con evidencia
    consecutivos de la misma vista), con la transformación que lo lleva al marco de la foto de a."""
    fila = d["indice"][d["indice"]["fecha"].eq(b["fecha"]) & d["indice"]["fecha_anterior"].eq(a["fecha"])]
    ruta = APP / "static" / "cambio" / f"{b['fecha']:%Y-%m-%d}.png"
    t_a = matriz_dia(d["alineacion"], a["fecha"])
    if fila.empty or pd.isna(fila.iloc[0]["indice"]) or not ruta.exists() or t_a is None:
        return None
    # El mapa está en el marco del primer día de la vista; T_a lleva ese marco al de la foto de a
    return {"u": url_foto(f"static/cambio/{ruta.name}"), "aj": transformacion_css(t_a),
            "indice": f"{decimal(fila.iloc[0]['indice'])} %"}


def mostrar_comparacion(d: dict, c: dict, a: pd.Series, b: pd.Series, texto_a: str | None = None,
                        texto_b: str | None = None, key: str = "comparador") -> None:
    """Comparador en tres modos si las dos fechas son de la misma vista (alineadas); si no, las
    dos fotos lado a lado con aviso."""
    texto_a, texto_b = texto_a or fecha(a["fecha"]), texto_b or fecha(b["fecha"])
    misma = a["vista"] == b["vista"]
    if not misma:
        st.warning("La cámara apuntaba a otro lugar en una de estas fechas (otra vista): las fotos no se pueden "
                   "superponer y solo se muestran lado a lado.", icon="⚠️")
    ajuste = ajuste_par(d["alineacion"], a["fecha"], b["fecha"]) if misma else None
    mapa = mapa_de_cambio(d, a, b) if misma else None
    datos = {
        "id": key,
        "a": {"u": url_foto(a["foto"]), "alt": html.escape(alt_foto(a["fecha_hora_foto"], "Foto de antes.")), "t": texto_a},
        "b": {"u": url_foto(b["foto"]), "alt": html.escape(alt_foto(b["fecha_hora_foto"], "Foto de después.")), "t": texto_b},
        "aj": {k: ajuste[k] for k in ("tx", "ty", "rot", "escala")} if ajuste else None,
        "ventana": {k: ajuste[k] for k in ("zoom", "vx", "vy")} if ajuste else None,
        "mapa": mapa,
        "nota": None if mapa or not misma else "«Mostrar dónde cambió» está disponible solo para dos días con evidencia "
                                               "consecutivos de la misma vista.",
        "colores": {"borde": c["borde"], "fondo2": c["fondo2"], "mapa": "#E6007E"},
    }
    comparador_componente(data=datos, key=key)


# ============================================================================
# Navegación: del dato a la evidencia
# ============================================================================

# «Ver en detalle» (hitos, picos del índice, días del time-lapse) deja elegidos el día y, si
# corresponde, el par de fechas en «Explorar y verificar», cambia a esa pestaña (las pestañas
# guardan su estado: st.tabs con key y on_change) y desplaza la página hasta la sección. Como
# la pestaña es un widget, no se puede cambiar después de dibujarla: se guarda en
# «ir_pestana» y se aplica al comienzo de la siguiente ejecución, antes de st.tabs.
PESTANAS = ["La historia", "Explorar y verificar", "Datos y método"]
EXPLORAR = PESTANAS[1]


def ir_a_detalle(dia: str, par: tuple[str, str] | None = None, motivo: str = "") -> None:
    ss = st.session_state
    ss.dia_explora = dia
    if par:
        ss.fechas_explora = tuple(sorted(par))
    destino = "comparar" if par else "detalle-dia"
    ss.ir_pestana = EXPLORAR
    ss.desplazar = {"id": destino, "n": ss.get("desplazar_n", 0) + 1}
    ss.desplazar_n = ss.desplazar["n"]
    ss.aviso_detalle = {"id": destino, "texto": motivo}


def aviso_de_detalle(destino: str) -> None:
    aviso = st.session_state.get("aviso_detalle")
    if aviso and aviso["id"] == destino:
        st.success(aviso["texto"], icon="✅")
        del st.session_state["aviso_detalle"]


def atender_detalle(valor) -> None:
    """Valor de un componente con «Ver en detalle»: {'dia': ...} o {'a': ..., 'b': ..., 'texto': ...}."""
    if not valor:
        return
    if valor.get("a") and valor.get("b"):
        ir_a_detalle(valor["b"], (valor["a"], valor["b"]), valor.get("texto", ""))
    elif valor.get("dia"):
        ir_a_detalle(valor["dia"], None, valor.get("texto", ""))
    else:
        return
    st.rerun()


DESPLAZAR_JS = """
export default function (component) {
  const { data } = component;
  let intentos = 0;
  const ir = () => {
    const el = document.getElementById(data.id);
    if (!el) { if (intentos++ < 20) setTimeout(ir, 150); return; }
    el.scrollIntoView({ block: 'start' });
    el.focus({ preventScroll: true });
  };
  setTimeout(ir, 250);
}
"""

desplazar_componente = st.components.v2.component("desplazar", js=DESPLAZAR_JS)



# ============================================================================
# Franja superior
# ============================================================================

def franja(dias: pd.DataFrame) -> None:
    st.html(f"""<header class="franja">
  <b>{NOMBRE_OBRA}</b>
  <span class="datos"><span>Fotos: CGR, proyecto dIAra</span><span>Última foto: {fecha(ultima_foto(dias))}</span></span>
</header>""")


# ============================================================================
# La historia: lo esencial
# ============================================================================

def titular_portada(dias: pd.DataFrame) -> str:
    dias_con_foto = dias.loc[dias["fotos"].gt(0), "fecha"]
    meses = round((dias_con_foto.max() - dias_con_foto.min()).days / 30.44)
    if meses < 2:
        return "La obra vista por una cámara"
    return f"{palabra(meses, True)} meses de obra vistos por una cámara"


def frase_estado(hitos: pd.DataFrame) -> str | None:
    uso = hito_en_uso(hitos)
    if uso is not None:
        return f"En las fotos circulan vehículos sobre el puente desde el {fecha_larga(uso['fecha_fin'])}."
    if len(hitos):
        ultimo = hitos.sort_values("fecha_fin").iloc[-1]
        return f"Último cambio visible en las fotos: {minuscula(ultimo['titulo'])}, el {fecha_larga(ultimo['fecha_fin'])}."
    return None


def cifras_portada(dias: pd.DataFrame, hitos: pd.DataFrame) -> list[tuple[str, str, str, str]]:
    """(clase, número, unidad, texto) de cada cifra, calculadas de los datos."""
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


def html_cifras(cifras: list[tuple[str, str, str, str]], clase: str = "") -> str:
    items = "".join(
        f'<div class="cifra {k}" role="listitem"><span class="num">{html.escape(num)}<small>{html.escape(unidad)}</small>'
        f'</span><span class="txt">{html.escape(texto)}</span></div>' for k, num, unidad, texto in cifras)
    return f'<div class="cifras {clase}" role="list">{items}</div>'


def lo_esencial(d: dict) -> None:
    dias, hitos = d["dias"], d["hitos"]
    st.title(titular_portada(dias), anchor=False)
    estado = frase_estado(hitos)
    if estado:
        st.html(f'<p class="estado">{html.escape(estado)}</p>')
    st.html(html_cifras(cifras_portada(dias, hitos)))


# ============================================================================
# Partes 1 y 2: recorrido con foto fija (componente propio)
# ============================================================================

# Scrollytelling: la foto queda fija (position: sticky) y los bloques de texto avanzan al
# desplazarse; con cada desplazamiento se calcula qué bloque pasó la línea de lectura y la
# foto cambia a la de ese bloque. Cada hito tiene dos bloques: antes y después, sobre la
# misma foto fija (la de después alineada a la de antes), para que el cambio se vea en el
# mismo lugar. Arriba de la foto, una línea de tiempo compacta marca el hito actual. En
# pantallas anchas el texto va a la izquierda y la foto a la derecha; en angostas la foto
# arriba y el texto pasa por debajo. Teclado: cada bloque es enfocable (Tab) y al enfocarlo
# se desplaza a la altura de lectura; el botón «Ver antes/después» alterna la foto.
HISTORIA_CSS = """
.histw { font-family: var(--st-font, sans-serif); color: var(--st-text-color); }
.saltos { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: 0 0 1.1rem; }
.saltos .rot { font-size: 0.85rem; opacity: 0.75; margin-right: 0.2rem; }
.saltos button { min-height: 44px; min-width: 44px; padding: 0 0.8rem; border-radius: 0.6rem; border: 1px solid var(--borde);
  background: transparent; color: inherit; font: 600 0.92rem/1 var(--st-font, sans-serif); cursor: pointer; }
.saltos button.num { padding: 0; font-variant-numeric: tabular-nums; }
.saltos button:hover { border-color: var(--st-text-color); }
.saltos button:focus-visible { outline: 3px solid var(--st-text-color); outline-offset: 2px; }
.hist { position: relative; font-family: var(--st-font, sans-serif); color: var(--st-text-color);
  --top: 3.6rem; display: grid; grid-template-columns: minmax(0, 1fr); }
.hist .marco { cursor: zoom-in; }
.hist .tarjeta .detalle { margin-top: 0.6rem; min-height: 44px; padding: 0 0.9rem; border-radius: 0.6rem; border: 1px solid var(--borde);
  background: transparent; color: inherit; font: 600 0.92rem/1 var(--st-font, sans-serif); cursor: pointer; }
.hist .tarjeta .detalle:hover { border-color: var(--st-text-color); }
.hist .tarjeta .detalle:focus-visible { outline: 3px solid var(--st-text-color); outline-offset: 2px; }
.hist .graf { position: sticky; top: var(--top); z-index: 2; background: var(--st-background-color);
  padding: 0.35rem 0 0.6rem; align-self: start; }
.hist .cab { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; min-height: 44px; }
.hist .parte { font-size: 0.8rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; opacity: 0.75; margin: 0; }
.hist .alternar { min-height: 44px; padding: 0 0.9rem; border-radius: 0.6rem; border: 1px solid var(--borde);
  background: transparent; color: inherit; font: 600 0.9rem/1 var(--st-font, sans-serif); cursor: pointer; }
.hist .alternar:hover { border-color: var(--st-text-color); }
.hist .alternar:focus-visible { outline: 3px solid var(--st-text-color); outline-offset: 2px; }
.hist .alternar[hidden] { display: none; }
.hist .eje { position: relative; height: 34px; margin: 0.1rem 6px 0.35rem; }
.hist .eje .linea { position: absolute; left: 0; right: 0; top: 11px; height: 2px; background: var(--borde); }
.hist .eje .mes { position: absolute; top: 20px; transform: translateX(-50%); font-size: 0.68rem; opacity: 0.7; white-space: nowrap; }
.hist .eje .punto { position: absolute; top: 12px; width: 9px; height: 9px; margin: -4.5px 0 0 -4.5px; border-radius: 50%;
  background: var(--st-background-color); border: 1.5px solid var(--st-text-color); box-sizing: border-box; }
.hist .eje .punto.hecho { background: var(--st-text-color); }
.hist .eje .punto.actual { width: 15px; height: 15px; margin: -7.5px 0 0 -7.5px; background: var(--si); border-color: var(--si); }
.hist .marco { position: relative; aspect-ratio: 5 / 4; overflow: hidden; border-radius: 10px; border: 1px solid var(--borde);
  box-sizing: border-box; width: min(100%, calc((100vh - var(--top) - 8.5rem) * 1.25)); margin: 0 auto; background: var(--fondo2); }
.hist .cuadro { position: absolute; inset: 0; opacity: 0; transition: opacity 0.45s ease; }
.hist .cuadro.visible { opacity: 1; }
.hist .cuadro .lienzo { position: absolute; inset: 0; transform-origin: 0 0; }
.hist .cuadro img { width: 100%; height: auto; display: block; transform-origin: 50% 50%; }
.hist .rotulo { position: absolute; left: 10px; top: 10px; z-index: 3; padding: 5px 9px; border-radius: 4px;
  background: rgba(20, 20, 19, 0.82); color: #fff; font: 600 13px/1.25 var(--st-font, sans-serif); }
.hist .pasos { position: relative; z-index: 1; padding: 0 0 30vh; }
.hist .paso { min-height: 52vh; display: flex; align-items: center; }
.hist .paso:first-child { min-height: 45vh; }
.hist .tarjeta { background: var(--fondo2); border: 1px solid var(--borde); border-radius: 10px; padding: 0.9rem 1rem;
  max-width: 32rem; box-sizing: border-box; width: 100%; line-height: 1.45; font-size: 1rem; opacity: 0.55;
  transition: opacity 0.3s ease; }
.hist .paso.activo .tarjeta { opacity: 1; }
.hist .tarjeta:focus-visible { outline: 3px solid var(--st-text-color); outline-offset: 3px; }
.hist .tarjeta h3 { font-family: "Source Serif 4", Georgia, serif; font-size: 1.2rem; line-height: 1.2; margin: 0.15rem 0 0.4rem; }
.hist .tarjeta p { margin: 0.3rem 0 0; }
.hist .tarjeta .meta { font-size: 0.82rem; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; opacity: 0.75; margin: 0; }
.hist .tarjeta .clar { font-size: 0.88rem; opacity: 0.8; }
@media (min-width: 820px) {
  .hist { grid-template-columns: minmax(0, 0.8fr) minmax(0, 1.5fr); column-gap: 2rem; }
  .hist .graf { grid-column: 2; grid-row: 1; }
  .hist .pasos { grid-column: 1; grid-row: 1; padding-bottom: 40vh; }
  .hist .paso { min-height: 80vh; }
  .hist .paso:first-child { min-height: 70vh; }
}
@media (prefers-reduced-motion: reduce) {
  .hist .cuadro, .hist .tarjeta { transition: none; }
}
"""

HISTORIA_JS = """
export default function (component) {
  const { data, parentElement, setTriggerValue } = component;
  parentElement.querySelectorAll('.histw').forEach((e) => e.remove());
  const raiz = document.createElement('div');
  raiz.className = 'histw';
  Object.entries(data.colores).forEach(([k, v]) => raiz.style.setProperty('--' + k, v));
  parentElement.appendChild(raiz);
  const pasos = data.pasos;
  const quieto = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const transform = (t) => t ? 'translate(' + t.tx + '%,' + t.ty + '%) rotate(' + t.rot + 'deg) scale(' + t.escala + ')' : 'none';
  const ventana = (v) => v ? 'scale(' + v.zoom + ') translate(' + (-v.vx) + '%,' + (-v.vy) + '%)' : 'none';

  // Botones para saltar a cualquier parte: a un paso del recorrido o a una sección de la página
  let h = '<nav class="saltos" aria-label="Ir a una parte de la historia"><span class="rot" aria-hidden="true">Ir a</span>' +
    data.saltos.map((s, k) => '<button type="button" data-salto="' + k + '"' + (s.aria ? ' aria-label="' + s.aria + '"' : '') +
      (s.n ? ' class="num"' : '') + '>' + s.t + '</button>').join('') + '</nav><div class="hist">';
  h += '<div class="graf"><div class="cab"><p class="parte" aria-hidden="true"></p>' +
    '<button type="button" class="alternar" hidden></button></div>' +
    '<div class="eje" aria-hidden="true"><div class="linea"></div>' +
    data.eje.meses.map((m) => '<span class="mes" style="left:' + m.x + '%">' + m.texto + '</span>').join('') +
    data.eje.hitos.map((p) => '<span class="punto" data-n="' + p.n + '" style="left:' + p.x + '%"></span>').join('') +
    '</div><div class="marco">' +
    pasos.map((p, i) => '<div class="cuadro" data-i="' + i + '"><div class="lienzo" style="transform:' + ventana(p.ventana) +
      '"><img alt="' + p.alt + '" data-src="' + p.foto + '" style="transform:' + transform(p.ajuste) + '"></div></div>').join('') +
    '<span class="rotulo" aria-hidden="true"></span>' +
    '<button type="button" class="ampliar" aria-label="Ampliar la foto a pantalla completa">&#10530; Ampliar</button></div></div>';
  h += '<div class="pasos">' + pasos.map((p, i) => '<section class="paso" data-i="' + i + '"><div class="tarjeta" tabindex="0">' +
    p.html + '</div></section>').join('') + '</div></div>';
  raiz.innerHTML = h;

  const cuadros = [...raiz.querySelectorAll('.cuadro')];
  const secciones = [...raiz.querySelectorAll('.paso')];
  const rotulo = raiz.querySelector('.rotulo');
  const parte = raiz.querySelector('.parte');
  const alternar = raiz.querySelector('.alternar');
  const puntos = [...raiz.querySelectorAll('.punto')];
  const tarjetas = secciones.map((s) => s.querySelector('.tarjeta'));
  let actual = -1, mostrado = -1;

  function cargar(i) {
    const img = cuadros[i] && cuadros[i].querySelector('img');
    if (img && !img.getAttribute('src')) img.setAttribute('src', img.dataset.src);
  }
  function mostrar(i) {  // cuadro i en la foto fija (puede ser el par del paso actual)
    mostrado = i;
    for (let k = i - 1; k <= i + 3; k++) cargar(k);
    cuadros.forEach((c, k) => { c.classList.toggle('visible', k === i); c.setAttribute('aria-hidden', k === i ? 'false' : 'true'); });
    rotulo.textContent = pasos[i].rotulo;
    const p = pasos[actual];
    if (p && p.par !== null && p.par !== undefined) {
      alternar.hidden = false;
      alternar.textContent = i === actual ? (p.tipo === 'antes' ? 'Ver después' : 'Ver antes') : 'Volver';
      alternar.setAttribute('aria-label', 'Alternar la foto entre antes y después del cambio ' + p.hito);
    } else alternar.hidden = true;
  }
  function activar(i) {
    if (i === actual) return;
    actual = i;
    const p = pasos[i];
    secciones.forEach((s, k) => s.classList.toggle('activo', k === i));
    parte.textContent = p.parte;
    puntos.forEach((el) => {
      const n = Number(el.dataset.n);
      el.classList.toggle('actual', p.hito === n);
      el.classList.toggle('hecho', p.hito !== null && n < p.hito);
    });
    mostrar(i);
  }
  // Foto a pantalla completa: el par antes/después del paso actual (o la foto sola)
  function ampliar() {
    const p = pasos[actual];
    const ids = p.par !== null && p.par !== undefined ? [Math.min(actual, p.par), Math.max(actual, p.par)] : [actual];
    abrirVisor(raiz, ids.map((k) => ({ u: pasos[k].foto, alt: pasos[k].alt, t: pasos[k].rotulo })), Math.max(0, ids.indexOf(mostrado)));
  }
  raiz.querySelector('.marco').addEventListener('click', (e) => { if (!e.target.closest('.ampliar')) ampliar(); });
  raiz.querySelector('.graf .ampliar').addEventListener('click', ampliar);
  raiz.querySelectorAll('[data-detalle-a]').forEach((b) => b.addEventListener('click', () => {
    setTriggerValue('detalle', { a: b.dataset.detalleA, b: b.dataset.detalleB, texto: b.dataset.texto });
  }));
  raiz.querySelectorAll('[data-salto]').forEach((b) => b.addEventListener('click', () => {
    const s = data.saltos[Number(b.dataset.salto)];
    if (s.paso !== undefined && s.paso !== null) { tarjetas[s.paso].focus(); return; }
    const el = document.getElementById(s.ancla);
    if (el) { el.scrollIntoView({ block: 'start', behavior: quieto ? 'auto' : 'smooth' }); el.focus({ preventScroll: true }); }
  }));

  alternar.addEventListener('click', () => {
    const p = pasos[actual];
    if (p.par === null || p.par === undefined) return;
    mostrar(mostrado === actual ? p.par : actual);
  });

  // Paso activo: el último cuya tarjeta ya pasó la línea de lectura. Se calcula con la posición y no con IntersectionObserver para que un salto
  // rápido (rueda, teclado, barra de desplazamiento) no deje la foto desfasada.
  let pendiente = false;
  function revisar() {
    pendiente = false;
    if (!raiz.isConnected) return;
    // Línea de lectura: con la foto al lado del texto, al 60 % de la ventana; con la foto
    // arriba (pantallas angostas), al 40 % del espacio que queda bajo la foto.
    const alto = window.innerHeight, g = raiz.querySelector('.graf').getBoundingClientRect();
    const alLado = g.left >= tarjetas[0].getBoundingClientRect().right;
    const linea = alLado ? alto * 0.6 : g.bottom + (alto - g.bottom) * 0.4;
    let i = 0;
    tarjetas.forEach((t, k) => { if (t.getBoundingClientRect().top <= linea) i = k; });
    activar(i);
  }
  const alDesplazar = () => { if (!pendiente) { pendiente = true; requestAnimationFrame(revisar); } };
  document.addEventListener('scroll', alDesplazar, { capture: true, passive: true });
  window.addEventListener('resize', alDesplazar);
  // Al enfocar una tarjeta (Tab o botones de salto) se lleva a la altura de lectura: al centro
  // con la foto al lado; justo debajo de la foto fija en pantallas angostas.
  secciones.forEach((s) => s.querySelector('.tarjeta').addEventListener('focus', () => {
    activar(Number(s.dataset.i));
    const t = s.querySelector('.tarjeta'), g = raiz.querySelector('.graf').getBoundingClientRect();
    const alLado = g.left >= t.getBoundingClientRect().right;
    t.style.scrollMarginTop = alLado ? '' : Math.round(g.height + parseFloat(getComputedStyle(raiz.querySelector('.graf')).top) + 12) + 'px';
    t.scrollIntoView({ block: alLado ? 'center' : 'start', behavior: quieto ? 'auto' : 'smooth' });
  }));
  activar(0);
  revisar();
  return () => {
    document.removeEventListener('scroll', alDesplazar, { capture: true });
    window.removeEventListener('resize', alDesplazar);
    raiz.remove();
  };
}
"""

historia_componente = componente("historia_recorrido", HISTORIA_CSS, HISTORIA_JS)


def x_en_periodo(dias: pd.DataFrame, f: pd.Timestamp, margen: float = 2.0) -> float:
    inicio, fin = dias["fecha"].min(), dias["fecha"].max()
    return round(margen + (f - inicio) / (fin - inicio) * (100 - 2 * margen), 3)


def tarjeta(meta: str, titulo: str | None, parrafos: list[str], clar: str | None = None,
            detalle: dict | None = None) -> str:
    partes = [f'<p class="meta">{html.escape(meta)}</p>']
    if titulo:
        partes.append(f"<h3>{html.escape(titulo)}</h3>")
    partes += [f"<p>{html.escape(t)}</p>" for t in parrafos]
    if clar:
        partes.append(f'<p class="clar">Qué tan claro se ve en las fotos: <b>{html.escape(clar)}</b></p>')
    if detalle:
        partes.append(f'<button type="button" class="detalle" data-detalle-a="{detalle["a"]}" data-detalle-b="{detalle["b"]}" '
                      f'data-texto="{html.escape(detalle["texto"])}" aria-label="{html.escape(detalle["aria"])}">'
                      "Ver en detalle →</button>")
    return "".join(partes)


def detalle_hito(h) -> dict:
    """Par de fechas del hito para «Ver en detalle» y el aviso que se muestra al llegar."""
    a, b = h.fecha_hora_antes.normalize(), h.fecha_hora_despues.normalize()
    return {"a": f"{a:%Y-%m-%d}", "b": f"{b:%Y-%m-%d}",
            "texto": f"Cambio {h.numero}, {minuscula(h.titulo)}: comparador con el {fecha(a)} y el {fecha(b)}, y detalle "
                     f"del {fecha(b)}.",
            "aria": f"Ver en detalle el cambio {h.numero}: {h.titulo}"}


def datos_recorrido(d: dict, c: dict) -> dict:
    dias, hitos, alineacion = d["dias"], d["hitos"], d["alineacion"]
    util = utiles(dias)
    primera = util.iloc[0]
    meses = round((util["fecha"].max() - primera["fecha"]).days / 30.44)
    sin_ajuste = {"tx": 0, "ty": 0, "rot": 0, "escala": 1}
    pasos = [{
        "tipo": "inicio", "hito": None, "par": None, "parte": f"Parte 1 de {TOTAL_PARTES} · Al inicio",
        "foto": url_foto(primera["foto"]), "alt": html.escape(alt_foto(primera["fecha_hora_foto"])),
        "rotulo": f"{fecha(primera['fecha'], dia_semana=True)}, {hora(primera['fecha_hora_foto'])}",
        "ajuste": sin_ajuste, "ventana": None,
        "html": tarjeta(f"Parte 1 · {fecha(primera['fecha'])}", "Así se veía la obra al inicio",
                        [f"Es la primera foto útil de la cámara, del {fecha_larga(primera['fecha'])}. Desde aquí la "
                         f"cámara siguió la obra durante unos {palabra(meses) if meses < len(NUMEROS) else meses} meses.",
                         "Siga bajando para ver qué cambió."])}]
    total = len(hitos)
    for h in hitos.itertuples():
        a_fecha, b_fecha = h.fecha_hora_antes.normalize(), h.fecha_hora_despues.normalize()
        ajuste = ajuste_par(alineacion, a_fecha, b_fecha) if pd.notna(h.vista) else None
        ventana = {k: ajuste[k] for k in ("zoom", "vx", "vy")} if ajuste else None
        aj_despues = {k: ajuste[k] for k in ("tx", "ty", "rot", "escala")} if ajuste else sin_ajuste
        parte = f"Parte 2 de {TOTAL_PARTES} · Cambio {h.numero} de {total}"
        i = len(pasos)
        pasos.append({
            "tipo": "antes", "hito": int(h.numero), "par": i + 1, "parte": parte,
            "foto": url_foto(h.foto_antes), "alt": html.escape(alt_foto(h.fecha_hora_antes, f"Antes del cambio: {h.titulo}.")),
            "rotulo": f"Antes · {fecha(h.fecha_hora_antes, dia_semana=True)}, {hora(h.fecha_hora_antes)}",
            "ajuste": sin_ajuste, "ventana": ventana,
            "html": tarjeta(f"Cambio {h.numero} de {total} · antes", h.titulo,
                            [f"Foto del {fecha_larga(h.fecha_hora_antes, dia_semana=True)}, a las {hora(h.fecha_hora_antes)}."])})
        pasos.append({
            "tipo": "despues", "hito": int(h.numero), "par": i, "parte": parte,
            "foto": url_foto(h.foto_despues),
            "alt": html.escape(alt_foto(h.fecha_hora_despues, f"Después del cambio: {h.titulo}.")),
            "rotulo": f"Después · {fecha(h.fecha_hora_despues, dia_semana=True)}, {hora(h.fecha_hora_despues)}",
            "ajuste": aj_despues, "ventana": ventana,
            "html": tarjeta(f"Cambio {h.numero} de {total} · después · {rango(h.fecha_inicio, h.fecha_fin)}", h.titulo,
                            [h.descripcion], claridad(pd.Series(h._asdict())), detalle_hito(h))})
    inicio, fin = dias["fecha"].min(), dias["fecha"].max()
    meses_eje = pd.date_range(inicio.to_period("M").to_timestamp(), fin, freq="MS")
    saltos = [{"t": "Inicio", "paso": 0, "aria": "Ir al inicio del recorrido"}]
    saltos += [{"t": str(p["hito"]), "n": True, "paso": k, "aria": f"Ir al cambio {p['hito']}: {hitos.iloc[p['hito'] - 1]['titulo']}"}
               for k, p in enumerate(pasos) if p["tipo"] == "antes"]
    saltos += [{"t": "Hoy", "ancla": "parte-hoy", "aria": "Ir a la parte 3: cómo está hoy"},
               {"t": "Lo que no se ve", "ancla": "parte-no-se-ve", "aria": "Ir al cierre: lo que no se ve"}]
    return {
        "pasos": pasos,
        "saltos": saltos,
        "eje": {"meses": [{"x": x_en_periodo(dias, max(m + pd.Timedelta(days=14), inicio)), "texto": MESES[m.month - 1]}
                          for m in meses_eje],
                "hitos": [{"n": int(h.numero), "x": x_en_periodo(dias, h.fecha_fin)} for h in hitos.itertuples()]},
        "colores": {"si": c["si"], "borde": c["borde"], "fondo2": c["fondo2"]},
    }


def recorrido(d: dict, c: dict) -> None:
    hitos = d["hitos"]
    n = len(hitos)
    seccion("Partes 1 y 2 · Al inicio y qué cambió",
            f"{palabra(n, True) if n < len(NUMEROS) else n} {'cambio visible' if n == 1 else 'cambios visibles'} en la obra"
            if n else "Cómo estaba la obra al inicio",
            "Baje para avanzar: la foto se queda fija y cambia con el texto." if n else None, parte=2 if n else 1)
    resultado = historia_componente(data=datos_recorrido(d, c), key="recorrido", on_detalle_change=lambda: None)
    atender_detalle(getattr(resultado, "detalle", None))


# ============================================================================
# Parte 3: time-lapse (componente propio)
# ============================================================================

# Un cuadro por día del periodo: la foto del día (la útil más cercana a las 12:00) o, si no
# hay evidencia, un cuadro «sin foto» del mismo largo, para que la falta se vea como una pausa.
# Las fotos de una vista se estabilizan con alineacion_dia.csv (la cámara se desplaza unos
# píxeles casi a diario) y se recortan a la zona común. Reproducir/pausar, tres velocidades,
# barra para ir a cualquier día (flechas del teclado) y una tira con la evidencia de cada día
# debajo. Las fotos se cargan por adelantado de a pocas; si la siguiente no llegó, se espera.
TIMELAPSE_CSS = """
.tl { font-family: var(--st-font, sans-serif); color: var(--st-text-color); max-width: 960px; }
.tl .marco { position: relative; aspect-ratio: 5 / 4; overflow: hidden; border-radius: 10px; border: 1px solid var(--borde);
  box-sizing: border-box; background: var(--fondo2); width: min(100%, calc((100vh - 17rem) * 1.25)); }
.tl .lienzo { position: absolute; inset: 0; transform-origin: 0 0; }
.tl .lienzo img { width: 100%; height: auto; display: block; transform-origin: 50% 50%; cursor: zoom-in; }
.tl .ampliar[hidden] { display: none; }
.tl .vacio { position: absolute; inset: 0; display: none; flex-direction: column; align-items: center; justify-content: center;
  gap: 0.4rem; text-align: center; padding: 1rem; background: var(--hueco); border: 2px dashed var(--no); border-radius: 10px;
  box-sizing: border-box; }
.tl .vacio b { font-size: clamp(1.1rem, 1rem + 1vw, 1.6rem); }
.tl .vacio span { font-size: 0.95rem; opacity: 0.85; }
.tl.sin-foto .vacio { display: flex; }
.tl.sin-foto .lienzo { visibility: hidden; }
.tl .fecha { position: absolute; left: 10px; top: 10px; padding: 6px 10px; border-radius: 5px; background: rgba(20, 20, 19, 0.82);
  color: #fff; font: 700 clamp(14px, 12px + 0.8vw, 19px)/1.2 var(--st-font, sans-serif); font-variant-numeric: tabular-nums; }
.tl .fecha small { font-weight: 600; opacity: 0.85; margin-left: 0.35em; }
.tl .fecha small.lejos { color: #FFD08A; }
.tl .aviso { position: absolute; left: 10px; bottom: 10px; right: 10px; padding: 6px 10px; border-radius: 5px;
  background: rgba(20, 20, 19, 0.82); color: #fff; font: 600 14px/1.3 var(--st-font, sans-serif); display: none; }
.tl .aviso.visible { display: block; }
.tl .controles { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem 0.75rem; margin: 0.7rem 0 0.4rem; }
.tl button { min-height: 44px; min-width: 44px; padding: 0 0.9rem; border-radius: 0.6rem; border: 1px solid var(--borde);
  background: transparent; color: inherit; font: 600 0.95rem/1 var(--st-font, sans-serif); cursor: pointer; }
.tl button:hover { border-color: var(--st-text-color); }
.tl button:focus-visible, .tl input:focus-visible { outline: 3px solid var(--st-text-color); outline-offset: 2px; }
.tl .play { background: var(--st-text-color); color: var(--st-background-color); border-color: var(--st-text-color); min-width: 8.5rem; }
.tl .vel { display: flex; gap: 0.35rem; align-items: center; }
.tl .vel .rot { font-size: 0.85rem; opacity: 0.75; margin-right: 0.15rem; }
.tl .vel button[aria-pressed="true"] { border-color: var(--st-text-color); box-shadow: inset 0 0 0 1px var(--st-text-color); }
.tl .pos { font-size: 0.88rem; opacity: 0.8; font-variant-numeric: tabular-nums; margin-left: auto; }
.tl .barra { position: relative; }
.tl input[type=range] { width: 100%; margin: 0; height: 44px; accent-color: var(--st-text-color); cursor: pointer; }
.tl .tira { display: flex; height: 10px; gap: 0; margin-top: -8px; border-radius: 2px; overflow: hidden; }
.tl .tira span { flex: 1 1 0; }
.tl .tira .util { background: var(--si); }
.tl .tira .nose { background: repeating-linear-gradient(135deg, var(--no) 0 1.5px, transparent 1.5px 3.5px); }
.tl .tira .sin { background: var(--hueco); box-shadow: inset 0 -2px 0 var(--no); }
.tl .marcas { position: relative; height: 2.4rem; font-size: 0.72rem; }
.tl .marcas span { position: absolute; top: 3px; transform: translateX(-50%); white-space: nowrap; opacity: 0.75; }
.tl .marcas .vista { top: 0; height: 2.3rem; transform: none; border-left: 1.5px dotted var(--st-text-color); padding: 1.05rem 0 0 4px;
  box-sizing: border-box; opacity: 1; }
.tl .sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
@media (max-width: 640px) { .tl .pos { margin-left: 0; width: 100%; } }
"""

TIMELAPSE_JS = """
export default function (component) {
  const { data, parentElement, setTriggerValue } = component;
  parentElement.querySelectorAll('.tl').forEach((e) => e.remove());
  const raiz = document.createElement('div');
  raiz.className = 'tl';
  Object.entries(data.colores).forEach(([k, v]) => raiz.style.setProperty('--' + k, v));
  parentElement.appendChild(raiz);
  const C = data.cuadros, N = C.length;
  const VELOCIDADES = data.velocidades;  // [etiqueta, cuadros por segundo]
  let i = data.inicio, vel = 1, reproduciendo = false, temporizador = null;
  const cache = new Map();

  raiz.innerHTML = '<div class="marco"><div class="lienzo"><img alt=""></div>' +
    '<div class="vacio" aria-hidden="true"><b>Sin foto de la obra</b><span></span></div>' +
    '<span class="fecha" aria-hidden="true"></span><span class="aviso" aria-hidden="true"></span>' +
    '<button type="button" class="ampliar" aria-label="Pausar y ampliar la foto a pantalla completa">&#10530; Ampliar</button></div>' +
    '<div class="controles"><button type="button" class="play"></button>' +
    '<div class="vel" role="group" aria-label="Velocidad"><span class="rot" aria-hidden="true">Velocidad</span>' +
    VELOCIDADES.map((v, k) => '<button type="button" data-v="' + k + '">' + v[0] + '</button>').join('') + '</div>' +
    '<button type="button" class="ir">Ver este día en detalle →</button>' +
    '<span class="pos" aria-hidden="true"></span></div>' +
    '<div class="barra"><input type="range" min="0" max="' + (N - 1) + '" step="1" aria-label="Día del time-lapse">' +
    '<div class="tira" aria-hidden="true">' + C.map((c) => '<span class="' + c.e + '"></span>').join('') + '</div>' +
    '<div class="marcas" aria-hidden="true">' + data.marcas.map((m) =>
      '<span class="' + (m.vista ? 'vista' : '') + '" style="left:' + m.x + '%">' + m.texto + '</span>').join('') + '</div></div>' +
    '<p class="sr" aria-live="polite"></p>';

  const img = raiz.querySelector('.lienzo img'), lienzo = raiz.querySelector('.lienzo');
  const fecha = raiz.querySelector('.fecha'), aviso = raiz.querySelector('.aviso');
  const vacio = raiz.querySelector('.vacio span'), pos = raiz.querySelector('.pos');
  const play = raiz.querySelector('.play'), rango = raiz.querySelector('input'), vivo = raiz.querySelector('.sr');
  const botonesVel = [...raiz.querySelectorAll('.vel button')];

  function precargar(desde) {
    for (let k = desde; k < Math.min(N, desde + 12); k++) {
      const u = C[k].u;
      if (u && !cache.has(u)) { const im = new Image(); im.src = u; cache.set(u, im); }
    }
  }
  const listo = (k) => !C[k].u || (cache.has(C[k].u) && cache.get(C[k].u).complete);

  function dibujar(anunciar) {
    const c = C[i];
    raiz.classList.toggle('sin-foto', !c.u);
    if (c.u) {
      img.src = c.u;
      img.alt = c.alt;
      const v = data.vistas[c.v];
      lienzo.style.transform = v ? 'scale(' + v.zoom + ') translate(' + (-v.vx) + '%,' + (-v.vy) + '%)' : 'none';
      img.style.transform = c.a ? 'translate(' + c.a.tx + '%,' + c.a.ty + '%) rotate(' + c.a.rot + 'deg) scale(' + c.a.escala + ')' : 'none';
    } else vacio.textContent = c.motivo;
    fecha.innerHTML = c.t + (c.h ? '<small class="' + (c.lejos ? 'lejos' : '') + '">' + c.h + '</small>' : '');
    btnAmpliar.hidden = !c.u;
    aviso.textContent = c.aviso || '';
    aviso.classList.toggle('visible', !!c.aviso);
    pos.textContent = 'Día ' + (i + 1) + ' de ' + N;
    rango.value = i;
    rango.setAttribute('aria-valuetext', c.largo + (c.u ? ', foto de las ' + c.h : ', sin foto de la obra'));
    if (anunciar) vivo.textContent = c.largo + (c.u ? '' : ', sin foto de la obra') + (c.aviso ? '. ' + c.aviso : '');
    precargar(i + 1);
  }
  function paso() {
    if (i >= N - 1) { pausar(); return; }
    if (!listo(i + 1)) { precargar(i + 1); return; }  // la siguiente foto aún no llega: se espera
    i += 1;
    dibujar(false);
  }
  function reproducir() {
    if (i >= N - 1) i = 0;
    reproduciendo = true;
    clearInterval(temporizador);
    temporizador = setInterval(paso, 1000 / VELOCIDADES[vel][1]);
    actualizarBotones();
    dibujar(false);
  }
  function pausar() {
    reproduciendo = false;
    clearInterval(temporizador);
    actualizarBotones();
    vivo.textContent = 'En pausa: ' + C[i].largo;
  }
  function actualizarBotones() {
    play.textContent = reproduciendo ? '❚❚ Pausar' : (i >= N - 1 ? '▶ Reproducir' : '▶ Reproducir');
    play.setAttribute('aria-label', reproduciendo ? 'Pausar el time-lapse' : 'Reproducir el time-lapse');
    botonesVel.forEach((b, k) => b.setAttribute('aria-pressed', k === vel ? 'true' : 'false'));
  }
  play.addEventListener('click', () => (reproduciendo ? pausar() : reproducir()));
  const btnAmpliar = raiz.querySelector('.ampliar');
  function ampliar() {
    if (reproduciendo) pausar();
    const c = C[i];
    if (c.u) abrirVisor(raiz, [{ u: c.u, alt: c.alt, t: c.largo + ', ' + c.h }], 0);
  }
  btnAmpliar.addEventListener('click', ampliar);
  img.addEventListener('click', ampliar);
  raiz.querySelector('.ir').addEventListener('click', () => {
    if (reproduciendo) pausar();
    setTriggerValue('detalle', { dia: C[i].f, texto: 'Detalle del ' + C[i].largo + ', elegido en el time-lapse.' });
  });
  botonesVel.forEach((b, k) => b.addEventListener('click', () => {
    vel = k;
    if (reproduciendo) reproducir(); else actualizarBotones();
  }));
  rango.addEventListener('input', () => { if (reproduciendo) pausar(); i = Number(rango.value); dibujar(true); });

  precargar(Math.max(0, i - 2));
  dibujar(false);
  actualizarBotones();
  const vigia = new MutationObserver(() => { if (!raiz.isConnected) { clearInterval(temporizador); vigia.disconnect(); } });
  vigia.observe(parentElement, { childList: true });
  return () => { clearInterval(temporizador); raiz.remove(); };
}
"""

timelapse_componente = componente("timelapse", TIMELAPSE_CSS, TIMELAPSE_JS)


def estabilizacion(alineacion: pd.DataFrame) -> tuple[dict, dict]:
    """Por día: ajuste CSS que lleva su foto al marco del día central de su vista; por vista: el
    recorte común que oculta los bordes sin imagen de todas sus fotos."""
    por_dia, por_vista = {}, {}
    for v, g in alineacion.groupby("vista"):
        g = g.sort_values("fecha")
        centro = matriz_dia(alineacion, g["fecha"].iloc[len(g) // 2])
        inversas = []
        for f in g["fecha"]:
            inversa = np.linalg.inv(matriz_dia(alineacion, f) @ np.linalg.inv(centro))  # foto del día -> marco central
            inversas.append(inversa)
            por_dia[f] = transformacion_css(inversa)
        por_vista[int(v)] = ventana_comun(inversas)
    return por_dia, por_vista


def datos_timelapse(d: dict, c: dict) -> dict:
    dias, vistas = d["dias"], d["vistas"]
    ajustes, recortes = estabilizacion(d["alineacion"])
    cambios = list(cambios_de_vista(vistas))
    cuadros = []
    for r in dias.itertuples():
        base = {"f": f"{r.fecha:%Y-%m-%d}", "t": fecha(r.fecha, dia_semana=True), "largo": fecha_larga(r.fecha, dia_semana=True),
                "e": CLAVE_ESTADO[r.estado]}
        aviso = next((f"Desde el {fecha(f, anio=False)} la cámara muestra otra vista" for f in cambios
                      if pd.Timedelta(0) <= r.fecha - f < pd.Timedelta(days=4)), None)
        if r.estado == UTIL:
            minutos = abs(r.fecha_hora_foto.hour * 60 + r.fecha_hora_foto.minute - 720)
            cuadros.append({**base, "u": url_foto(r.foto), "h": hora(r.fecha_hora_foto),
                            "lejos": minutos > MINUTOS_LEJOS_MEDIODIA, "v": int(r.vista), "a": ajustes.get(r.fecha),
                            "alt": alt_foto(r.fecha_hora_foto), "aviso": aviso})
        else:
            motivo = "No hay foto ese día" if r.estado == SIN_FOTO else "Hay fotos, pero no se ve la obra"
            cuadros.append({**base, "u": None, "motivo": motivo, "aviso": aviso})
    inicio, fin = dias["fecha"].min(), dias["fecha"].max()
    x = lambda f: round((f - inicio) / (fin - inicio + pd.Timedelta(days=1)) * 100, 3)
    marcas = [{"x": x(m + pd.Timedelta(days=15)), "texto": MESES[m.month - 1], "vista": False}
              for m in pd.date_range(inicio.to_period("M").to_timestamp(), fin, freq="MS") if m + pd.Timedelta(days=15) >= inicio]
    marcas += [{"x": x(f), "texto": "otra vista", "vista": True} for f in cambios]
    ultimo_util = int(np.flatnonzero(dias["estado"].eq(UTIL).to_numpy())[-1])
    return {"cuadros": cuadros, "vistas": {str(k): v for k, v in recortes.items()}, "marcas": marcas,
            "inicio": ultimo_util, "velocidades": [["Lenta", 3], ["Normal", 6], ["Rápida", 12]],
            "colores": {"si": c["si"], "no": c["no"], "hueco": c["hueco"], "borde": c["borde"], "fondo2": c["fondo2"]}}


def hoy(d: dict) -> None:
    dias, hitos = d["dias"], d["hitos"]
    util = utiles(dias)
    ultima = util.iloc[-1]
    cambio = cambios_de_vista(d["vistas"])
    seccion("Parte 3 · Cómo está hoy", f"La última foto útil es del {fecha_larga(ultima['fecha'])}", id_="parte-hoy",
            frase=
            "Cada cuadro es un día, con la foto más cercana al mediodía. Los días sin evidencia aparecen como una "
            "pausa en lugar de saltarse.", parte=3)
    resultado = timelapse_componente(data=datos_timelapse(d, d["c"]), key="timelapse", on_detalle_change=lambda: None)
    atender_detalle(getattr(resultado, "detalle", None))
    lejos = util[(util["fecha_hora_foto"].dt.hour * 60 + util["fecha_hora_foto"].dt.minute - 720).abs()
                 > MINUTOS_LEJOS_MEDIODIA]
    texto = []
    estado = frase_estado(hitos)
    if estado:
        texto.append(estado)
    if len(cambio):
        texto.append(f"El {fecha_larga(cambio.iloc[0])} la cámara pasó a mostrar otra vista, más cerca de la vía; "
                     "desde entonces el puente casi no se ve.")
    st.markdown(" ".join(texto))
    descripcion(
        f"Time-lapse de {len(dias)} días, {rango_largo(dias['fecha'].min(), dias['fecha'].max())}. "
        f"{len(util)} cuadros tienen foto y {len(dias) - len(util)} son pausas «sin foto de la obra» (cuadro con borde "
        "punteado). La tira bajo la barra muestra cada día: relleno azul si hay foto útil, rayado si hay fotos pero "
        "no se ve la obra y franja inferior si no hay foto. "
        + (f"Una línea punteada marca el cambio de vista del {fecha_larga(cambio.iloc[0])}. " if len(cambio) else "")
        + (f"En {plural(len(lejos), 'día')} no hay foto útil cerca del mediodía y se muestra la más cercana; su hora "
           "aparece resaltada junto a la fecha. " if len(lejos) else "")
        + "Las fotos se alinean entre sí porque la cámara se desplaza unos píxeles casi a diario; por eso se ven un "
          "poco recortadas.",
        "Descripción del time-lapse")


# ============================================================================
# Cierre: lo que no se ve (un punto por foto, por mes; componente propio)
# ============================================================================

# Una fila por mes; cada punto es una foto. Los puntos se agrupan por estado (útil, excluida
# por calidad, de noche, sin vista de la obra), siempre en ese orden y separados por un
# espacio: la posición identifica el estado además del color. Todas las filas tienen el mismo
# alto, así que el largo es proporcional al número de fotos. Las cifras de cada mes van en
# texto junto a la fila. El paso entre puntos se elige según el ancho disponible.
PUNTOS_CSS = """
.pts { font-family: var(--st-font, sans-serif); color: var(--st-text-color); position: relative; }
.pts .ley { list-style: none; display: flex; flex-wrap: wrap; gap: 0.35rem 1.1rem; padding: 0; margin: 0 0 0.8rem; font-size: 0.9rem; }
.pts .ley li { display: flex; align-items: center; gap: 0.4rem; }
.pts .ley i { width: 0.8rem; height: 0.8rem; border-radius: 50%; display: inline-block; }
.pts .ley small { opacity: 0.75; font-variant-numeric: tabular-nums; }
.pts .fila { display: grid; grid-template-columns: 8.5rem minmax(0, 1fr); column-gap: 0.9rem; align-items: center;
  padding: 0.35rem 0; border-top: 1px solid var(--borde); }
.pts .rot { font-size: 0.88rem; line-height: 1.3; }
.pts .rot b { display: block; font-size: 0.95rem; }
.pts .rot span { opacity: 0.78; font-variant-numeric: tabular-nums; }
.pts canvas { display: block; }
.pts .tip { position: absolute; pointer-events: none; padding: 6px 9px; border-radius: 5px; background: var(--st-text-color);
  color: var(--st-background-color); font-size: 0.85rem; line-height: 1.3; white-space: nowrap; display: none; z-index: 3; }
@media (max-width: 560px) {
  .pts .fila { grid-template-columns: minmax(0, 1fr); row-gap: 0.25rem; }
  .pts .rot b { display: inline; margin-right: 0.4rem; }
}
"""

PUNTOS_JS = """
export default function (component) {
  const { data, parentElement } = component;
  parentElement.querySelectorAll('.pts').forEach((e) => e.remove());
  const raiz = document.createElement('div');
  raiz.className = 'pts';
  raiz.style.setProperty('--borde', data.borde);
  parentElement.appendChild(raiz);
  const orden = data.orden;
  const fmt = (n) => n.toLocaleString('es-CR').replace(/\\s|\\./g, '\\u202f');

  raiz.innerHTML = '<ul class="ley" aria-label="Leyenda: cada punto es una foto">' + orden.map((k) =>
    '<li><i style="background:' + data.colores[k] + '"></i>' + data.etiquetas[k] + ' <small>' + fmt(data.totales[k]) +
    '</small></li>').join('') + '</ul>' +
    data.meses.map((m, j) => '<div class="fila"><div class="rot"><b>' + m.nombre + '</b><span>' + fmt(m.total) + ' fotos · ' +
      fmt(m.n.util) + ' útiles</span></div><canvas data-j="' + j + '" role="img" aria-label="' + m.aria + '"></canvas></div>').join('') +
    '<div class="tip" aria-hidden="true"></div>';
  const lienzos = [...raiz.querySelectorAll('canvas')];
  const tip = raiz.querySelector('.tip');
  let disposicion = null;

  function disponer(ancho) {
    // Paso (px entre puntos) y filas por mes: el mayor paso con el que el mes más grande cabe
    // en el ancho sin que una fila pase de ALTO_MAX px.
    const ALTO_MAX = ancho < 560 ? 54 : 64, HUECO = 2;
    for (const p of [6, 5, 4.5, 4, 3.5, 3, 2.5, 2, 1.5]) {
      for (let r = 1; r * p <= ALTO_MAX; r++) {
        const cols = data.meses.map((m) => orden.reduce((s, k) => s + Math.ceil(m.n[k] / r) + (m.n[k] ? HUECO : 0), -HUECO));
        if (Math.max(...cols) * p <= ancho) return { p, r, HUECO };
      }
    }
    return { p: 1.5, r: Math.ceil(ALTO_MAX / 1.5), HUECO };
  }

  function dibujar() {
    const ancho = lienzos[0].parentElement.clientWidth - (raiz.clientWidth >= 560 ? lienzos[0].previousElementSibling.offsetWidth + 14 : 0);
    if (ancho <= 0) return;
    disposicion = disponer(ancho);
    const { p, r, HUECO } = disposicion;
    const dpr = window.devicePixelRatio || 1;
    lienzos.forEach((cv) => {
      const m = data.meses[Number(cv.dataset.j)];
      cv.width = Math.round(ancho * dpr); cv.height = Math.round(r * p * dpr);
      cv.style.width = ancho + 'px'; cv.style.height = (r * p) + 'px';
      const ctx = cv.getContext('2d');
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, ancho, r * p);
      let col = 0;
      cv._segmentos = [];
      orden.forEach((k) => {
        const n = m.n[k];
        if (!n) return;
        ctx.fillStyle = data.colores[k];
        const x0 = col * p;
        for (let i = 0; i < n; i++) {
          const x = (col + Math.floor(i / r)) * p, y = (i % r) * p;
          if (p >= 3) { ctx.beginPath(); ctx.arc(x + p / 2, y + p / 2, p * 0.4, 0, 6.2832); ctx.fill(); }
          else ctx.fillRect(x, y, Math.max(p - 0.4, 1), Math.max(p - 0.4, 1));
        }
        col += Math.ceil(n / r);
        cv._segmentos.push({ x0, x1: col * p, k, n });
        col += HUECO;
      });
    });
  }
  lienzos.forEach((cv) => {
    cv.addEventListener('mousemove', (ev) => {
      const rc = cv.getBoundingClientRect(), x = ev.clientX - rc.left;
      const s = (cv._segmentos || []).find((g) => x >= g.x0 && x <= g.x1 + 2);
      if (!s) { tip.style.display = 'none'; return; }
      const m = data.meses[Number(cv.dataset.j)];
      tip.textContent = m.nombre + ' · ' + data.etiquetas[s.k] + ': ' + fmt(s.n) + ' fotos';
      const rr = raiz.getBoundingClientRect();
      tip.style.display = 'block';
      tip.style.left = Math.min(ev.clientX - rr.left + 12, rr.width - tip.offsetWidth - 4) + 'px';
      tip.style.top = (rc.top - rr.top - 34) + 'px';
    });
    cv.addEventListener('mouseleave', () => { tip.style.display = 'none'; });
  });
  dibujar();
  const obs = new ResizeObserver(() => { if (!raiz.isConnected) { obs.disconnect(); return; } dibujar(); });
  obs.observe(raiz);
  return () => { obs.disconnect(); raiz.remove(); };
}
"""

puntos_componente = componente("puntos_por_mes", PUNTOS_CSS, PUNTOS_JS)


def conteo_mensual(fotos: pd.DataFrame) -> pd.DataFrame:
    """Fotos por mes y estado (columnas en el orden de ESTADOS_FOTO)."""
    return pd.crosstab(fotos["mes"], fotos["estado"]).reindex(columns=ESTADOS_FOTO, fill_value=0)


def lo_que_no_se_ve(d: dict, c: dict) -> None:
    tabla = conteo_mensual(d["fotos"])
    util = tabla["útil"]
    poco, mucho = util.idxmin(), util.idxmax()
    seccion("Cierre · Lo que no se ve",
            f"En {MESES_LARGO[poco.month - 1]} de {poco.year} casi no hay fotos útiles de la obra",
            f"Cada punto es una de las {miles(len(d['fotos']))} fotos que tomó la cámara. "
            f"{mes_largo(mucho)} tiene {miles(util[mucho])} fotos útiles; {MESES_LARGO[poco.month - 1]} de {poco.year}, "
            f"solo {miles(util[poco])}.", parte=4, id_="parte-no-se-ve")
    etiquetas = {CLAVE_FOTO[e]: mayuscula(e) for e in ESTADOS_FOTO}
    meses = []
    for periodo, fila in tabla.iterrows():
        n = {CLAVE_FOTO[e]: int(fila[e]) for e in ESTADOS_FOTO}
        aria = f"{mes_largo(periodo)}: " + ", ".join(f"{miles(fila[e])} {e}" for e in ESTADOS_FOTO)
        meses.append({"nombre": f"{mayuscula(MESES[periodo.month - 1])} {periodo.year}", "n": n, "total": int(fila.sum()),
                      "aria": html.escape(aria)})
    puntos_componente(data={"meses": meses, "orden": [CLAVE_FOTO[e] for e in ESTADOS_FOTO], "etiquetas": etiquetas,
                            "totales": {CLAVE_FOTO[e]: int(tabla[e].sum()) for e in ESTADOS_FOTO},
                            "colores": {k: c[k] for k in ("util", "calidad", "noche", "sinvista")}, "borde": c["borde"]},
                      key="puntos_mes")
    tramos = tramos_sin_evidencia(d["dias"])
    st.markdown(
        f"En {plural(int(d['dias']['estado'].ne(UTIL).sum()), 'día')} de {len(d['dias'])} no hay ninguna foto útil de la obra. "
        + (f"El tramo más largo va {rango_largo(tramos.iloc[0]['inicio'], tramos.iloc[0]['fin'])}: "
           f"{int(tramos.iloc[0]['dias'])} días seguidos en los que la obra pudo cambiar sin quedar registrada." if len(tramos) else ""))
    with st.expander("Descripción del gráfico y tabla"):
        st.markdown(
            f"Una fila por mes, {rango_largo(d['dias']['fecha'].min(), d['dias']['fecha'].max())}. Cada punto es una foto; "
            "dentro de cada fila los puntos van agrupados, de izquierda a derecha, en fotos útiles, excluidas por calidad, "
            "de noche y sin vista de la obra, separados por un espacio. El largo de cada grupo es proporcional a su número "
            "de fotos. Las fotos «excluidas por calidad» incluyen las de luz insuficiente, dañadas, sobreexpuestas, "
            "empañadas, de orientación dudosa e ilegibles.")
        tabla_html = "".join(
            f"<tr><th scope='row'>{mes_largo(p)}</th>" + "".join(f"<td class='n'>{miles(v)}</td>" for v in fila)
            + f"<td class='n'>{miles(fila.sum())}</td></tr>" for p, fila in tabla.iterrows())
        st.html(f"<div class='envoltura'><table class='tabla'><caption>Fotos por mes y estado</caption><thead><tr><th>Mes</th>"
                + "".join(f"<th class='n'>{mayuscula(e)}</th>" for e in ESTADOS_FOTO)
                + f"<th class='n'>Total</th></tr></thead><tbody>{tabla_html}</tbody></table></div>")


def pestana_historia(d: dict, c: dict) -> None:
    lo_esencial(d)
    recorrido(d, c)
    hoy(d)
    lo_que_no_se_ve(d, c)
    resumen_historia(d, c)
    st.html('<div class="seccion" aria-hidden="true"></div>')
    st.html('<p class="alcance">Este sitio muestra únicamente lo que se observa en las fotos de la cámara; no informa '
            'presupuesto, plazos ni porcentaje de avance de la obra. El detalle de cada día y el método están en las '
            'pestañas «Explorar y verificar» y «Datos y método».</p>')


# ============================================================================
# Calendario de días (componente propio)
# ============================================================================

# Una cuadrícula por mes con los días de la semana. Cada día se distingue por color y por
# forma: relleno azul (con foto útil), rayado (con fotos, sin vista de la obra) y contorno
# punteado (sin foto). Dos modos, los dos con botones de 44 px y meses en una fila con
# desplazamiento horizontal:
#   dia     se elige un día cualquiera del periodo para ver su detalle.
#   elegir  se eligen dos días con foto útil para compararlos.
# Teclado: Tab entra al calendario, las flechas recorren los días elegibles, Inicio/Fin van al
# primero y al último, Enter o Espacio eligen.
CALENDARIO_CSS = """
.cal { position: relative; font-family: var(--st-font, sans-serif); color: var(--tinta); }
.cal td, .cal .dia, .cal .meses { position: relative; }
.cal .sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
.cal button { font: inherit; color: inherit; -webkit-tap-highlight-color: transparent; touch-action: manipulation; }

.cal .c { position: relative; display: flex; align-items: center; justify-content: center; box-sizing: border-box;
  width: 100%; height: 100%; border-radius: 5px; border: 1.5px solid transparent; font-variant-numeric: tabular-nums; }
.cal .c.util { background: var(--si); color: var(--si-texto); }
.cal .c.nose { border-color: var(--no); color: var(--tinta);
  background: repeating-linear-gradient(135deg, var(--no-suave) 0 2.5px, transparent 2.5px 6px); }
.cal .c.sin { border: 1.5px dashed var(--no); color: var(--tinta); }
.cal .c.fuera { color: var(--tenue); opacity: 0.5; }
.cal .c.sel { background: var(--tinta); color: var(--fondo); border-color: var(--tinta); }

.cal .leyenda { list-style: none; display: flex; flex-wrap: wrap; gap: 0.4rem 1.25rem; padding: 0; margin: 0 0 0.9rem;
  font-size: 0.9rem; color: var(--tenue); }
.cal .leyenda li { display: flex; align-items: center; gap: 0.45rem; }
.cal .leyenda .c { width: 1.15rem; height: 1.15rem; border-radius: 4px; }

.cal table { border-collapse: collapse; border-spacing: 0; table-layout: fixed; width: calc(7 * var(--celda)); }
.cal caption { text-align: left; font-weight: 700; font-size: 0.95rem; padding: 0 0 0.3rem; }
.cal th { font-size: 0.7rem; font-weight: 600; color: var(--tenue); height: 1.4rem; padding: 0; }
.cal td { width: var(--celda); height: var(--celda); padding: 0; box-sizing: border-box; }
.cal { --celda: 44px; --hueco: 3px; }
.cal .dia { display: block; width: var(--celda); height: var(--celda); padding: var(--hueco); margin: 0;
  border: 0; background: none; box-sizing: border-box; }
.cal button.dia { cursor: pointer; border-radius: 8px; }
.cal button.dia:hover .c { box-shadow: 0 0 0 2px var(--tinta); }
.cal button.dia:focus-visible { outline: 3px solid var(--tinta); outline-offset: -1px; }
.cal .c { font-size: 0.85rem; }
.cal .c.util, .cal .c.sel { font-weight: 700; }
.cal .marca { display: inline-flex; align-items: center; justify-content: center; min-width: 18px; height: 18px;
  border-radius: 9px; box-sizing: border-box; border: 1.5px solid var(--tinta); background: var(--fondo);
  color: var(--tinta); font-size: 0.7rem; font-weight: 700; line-height: 1; }
.cal .c .marca { position: absolute; top: -6px; right: -6px; }
.cal .meses { display: flex; gap: 16px; overflow-x: auto; scroll-snap-type: x mandatory; overscroll-behavior-x: contain;
  padding: 2px 2px 10px; scrollbar-width: thin; }
.cal .mes { flex: 0 0 auto; scroll-snap-align: start; }

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
  const activoAntes = parentElement.getRootNode().activeElement;
  if (activoAntes && parentElement.contains(activoAntes)) m.enfocar = selector(activoAntes);
  const viejo = parentElement.querySelector('.cal');
  if (viejo) m.scroll = viejo.querySelector('.meses').scrollLeft;
  parentElement.querySelectorAll('.cal').forEach((e) => e.remove());

  const unico = data.modo === 'dia';  // un día cualquiera; si no, dos días con foto útil
  const raiz = document.createElement('div');
  raiz.className = 'cal ' + data.modo;
  Object.entries(data.colores).forEach(([k, v]) => raiz.style.setProperty('--' + k, v));
  parentElement.appendChild(raiz);

  const SEMANA = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'];
  const TEXTO = { util: 'hay foto útil', nose: 'hay fotos pero no se ve la obra', sin: 'no hay foto', fuera: 'fuera del periodo' };
  const NOMBRE = { primera: 'primera', segunda: 'segunda' };
  const esc = (s) => String(s).replace(/[&<>"]/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));
  const dia = {};
  const elegibles = [];
  data.meses.forEach((mes) => mes.dias.forEach((d) => {
    dia[d.f] = d;
    if (unico ? !!d.e : d.e === 'util') elegibles.push(d.f);
  }));
  let primera = data.primera, segunda = data.segunda, elegido = data.dia;
  let activo = m.activo || 'primera';
  let foco = m.foco && elegibles.includes(m.foco) ? m.foco : (unico ? elegido : (activo === 'primera' ? primera : segunda)) || elegibles[0];
  let aviso = '', avisoSr = '';

  function selector(el) {
    if (el.dataset && el.dataset.f) return '[data-f="' + el.dataset.f + '"]';
    if (el.dataset && el.dataset.ranura) return '[data-ranura="' + el.dataset.ranura + '"]';
    if (el.dataset && el.dataset.nav) return '[data-nav="' + el.dataset.nav + '"]';
    return null;
  }

  function celda(d) {
    const estado = d.e || 'fuera';
    if (elegibles.includes(d.f)) {
      const n = unico ? (d.f === elegido ? 1 : 0) : (d.f === primera ? 1 : d.f === segunda ? 2 : 0);
      const etiqueta = d.t + ', ' + TEXTO[estado] +
        (unico ? (n ? ', día elegido' : '') : (n === 1 ? ', primera fecha' : n === 2 ? ', segunda fecha' : ''));
      return '<td><button type="button" class="dia" data-f="' + d.f + '" tabindex="' + (d.f === foco ? 0 : -1) +
        '" aria-pressed="' + (n ? 'true' : 'false') + '" aria-label="' + esc(etiqueta) + '"><span class="c ' +
        (n ? 'sel' : estado) + '" aria-hidden="true">' + d.d + (n && !unico ? '<span class="marca">' + n + '</span>' : '') +
        '</span></button></td>';
    }
    const extra = d.e ? '; no se puede elegir' : '';
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
    let h = '<div class="controles">';
    if (!unico) h += '<div role="group" aria-label="Fechas a comparar" class="controles" style="margin:0">' +
      ranura('primera', 1, primera) + ranura('segunda', 2, segunda) + '</div>';
    h += '<div class="nav"><button type="button" class="boton" data-nav="-1" aria-label="Ver meses anteriores">&#8249;</button>' +
      '<button type="button" class="boton" data-nav="1" aria-label="Ver meses siguientes">&#8250;</button></div></div>';
    const porDefecto = unico ? 'Toque un día para ver su detalle.' : 'Toque un día con foto útil para elegir la ' + NOMBRE[activo] + ' fecha.';
    h += '<p class="aviso" aria-live="polite">' + (avisoSr ? '<span class="sr">' + esc(avisoSr) + '</span>' : '') +
      esc(aviso || porDefecto) + '</p>';
    h += '<ul class="leyenda" aria-label="Leyenda del calendario">' + data.leyenda.map((l) =>
      '<li><span class="c ' + l.e + '" aria-hidden="true"></span>' + esc(l.texto) + '</li>').join('') + '</ul>';
    h += '<div class="meses">' + data.meses.map(mesHtml).join('') + '</div>';
    raiz.innerHTML = h;

    const meses = raiz.querySelector('.meses');
    if (scroll !== undefined) meses.scrollLeft = scroll;
    else {  // primera vez: que se vea el mes del día elegido (o de la segunda fecha)
      const el = raiz.querySelector('[data-f="' + (unico ? elegido : segunda) + '"]');
      const mes = el && el.closest('.mes');
      if (mes) meses.scrollLeft = Math.max(0, mes.offsetLeft + mes.offsetWidth - meses.clientWidth + 2);
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
    if (unico) {
      elegido = f;
      foco = m.foco = f;
      avisoSr = 'Día elegido: ' + dia[f].t + '.';
      aviso = 'Detalle del ' + dia[f].c + ' debajo del calendario.';
      dibujar('[data-f="' + f + '"]');
      m.aviso = [aviso, avisoSr];
      setTriggerValue('dia', f);
      return;
    }
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

  if (m.aviso) { [aviso, avisoSr] = m.aviso; m.aviso = null; }
  dibujar(m.enfocar);
  m.enfocar = null;
  return () => raiz.remove();
}
"""

calendario_componente = st.components.v2.component("calendario_dias", css=CALENDARIO_CSS, js=CALENDARIO_JS)


def datos_calendario(dias: pd.DataFrame, c: dict, modo: str, primera: str | None = None,
                     segunda: str | None = None, dia: str | None = None) -> dict:
    estado = dias.set_index("fecha")["estado"]
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
    leyenda = [{"e": CLAVE_ESTADO[e], "texto": LEYENDA[e]} for e in ESTADOS]
    return {"id": modo, "modo": modo, "meses": meses, "leyenda": leyenda, "colores": colores,
            "primera": primera, "segunda": segunda, "dia": dia}


# Lista de hitos (resumen al final de la historia y lista completa en «Explorar y verificar»):
# un elemento por hito con número, título, fechas y claridad, y un botón «Ver en detalle» que
# deja ese par de fechas en el comparador. En la lista completa se agregan vista y descripción.
HITOS_CSS = """
.lh { font-family: var(--st-font, sans-serif); color: var(--st-text-color); list-style: none; margin: 0; padding: 0; }
.lh li { display: grid; grid-template-columns: 2rem minmax(0, 1fr) auto; column-gap: 0.75rem; row-gap: 0.15rem;
  align-items: center; padding: 0.45rem 0; border-top: 1px solid var(--borde); }
.lh li:last-child { border-bottom: 1px solid var(--borde); }
.lh .n { font-weight: 700; font-variant-numeric: tabular-nums; text-align: right; align-self: start; padding-top: 0.15rem; }
.lh .linea { display: flex; flex-wrap: wrap; align-items: baseline; gap: 0.1rem 0.6rem; min-width: 0; line-height: 1.35; }
.lh .linea b { font-weight: 700; }
.lh .meta { font-size: 0.88rem; opacity: 0.78; white-space: nowrap; }
.lh .clar { font-size: 0.85rem; white-space: nowrap; padding: 0.15rem 0.55rem; border: 1px solid var(--borde); border-radius: 999px; }
.lh .desc { grid-column: 2 / 3; font-size: 0.93rem; line-height: 1.45; margin: 0.15rem 0 0; opacity: 0.9; }
.lh button { min-height: 44px; padding: 0 0.85rem; border-radius: 0.6rem; border: 1px solid var(--borde); background: transparent;
  color: inherit; font: 600 0.9rem/1 var(--st-font, sans-serif); cursor: pointer; white-space: nowrap; grid-column: 3; grid-row: 1; }
.lh button:hover { border-color: var(--st-text-color); }
.lh button:focus-visible { outline: 3px solid var(--st-text-color); outline-offset: 2px; }
.lh.tabla li { align-items: start; padding: 0.7rem 0; }
@media (max-width: 560px) {
  .lh li { grid-template-columns: 1.6rem minmax(0, 1fr); }
  .lh button { grid-column: 2; grid-row: auto; justify-self: start; margin-top: 0.3rem; }
  .lh .desc { grid-column: 2; }
}
"""

HITOS_JS = """
export default function (component) {
  const { data, parentElement, setTriggerValue } = component;
  parentElement.querySelectorAll('.lh').forEach((e) => e.remove());
  const raiz = document.createElement('ol');
  raiz.className = 'lh ' + data.modo;
  raiz.setAttribute('aria-label', data.titulo);
  raiz.style.setProperty('--borde', data.borde);
  parentElement.appendChild(raiz);
  raiz.innerHTML = data.hitos.map((h, k) => '<li><span class="n" aria-hidden="true">' + h.n + '</span>' +
    '<div class="linea"><b>' + h.titulo + '</b><span class="meta">' + h.meta + '</span>' +
    (h.clar ? '<span class="clar">' + h.clar + '</span>' : '') + '</div>' +
    (h.desc ? '<p class="desc">' + h.desc + '</p>' : '') +
    '<button type="button" data-k="' + k + '" aria-label="' + h.detalle.aria + '">Ver en detalle →</button></li>').join('');
  raiz.querySelectorAll('button').forEach((b) => b.addEventListener('click', () => {
    const h = data.hitos[Number(b.dataset.k)];
    setTriggerValue('detalle', { a: h.detalle.a, b: h.detalle.b, texto: h.detalle.texto });
  }));
  return () => raiz.remove();
}
"""

hitos_componente = st.components.v2.component("lista_hitos", css=HITOS_CSS, js=HITOS_JS)


def mostrar_hitos(d: dict, c: dict, modo: str, key: str) -> None:
    hitos = d["hitos"]
    filas = []
    for h in hitos.itertuples():
        clar = claridad(pd.Series(h._asdict()))
        filas.append({"n": int(h.numero), "titulo": html.escape(h.titulo),
                      "meta": rango(h.fecha_inicio, h.fecha_fin) + (f" · vista {h.vista}" if modo == "tabla" else ""),
                      "clar": html.escape(clar) if clar else "", "detalle": detalle_hito(h),
                      "desc": html.escape(h.descripcion) if modo == "tabla" else ""})
    resultado = hitos_componente(data={"modo": modo, "hitos": filas, "borde": c["borde"],
                                       "titulo": "Resumen de los cambios" if modo == "resumen" else "Lista de hitos"},
                                 key=key, on_detalle_change=lambda: None)
    atender_detalle(getattr(resultado, "detalle", None))


def resumen_historia(d: dict, c: dict) -> None:
    if d["hitos"].empty:
        return
    seccion("Resumen", "Los cambios, de un vistazo",
            "Número, fechas y qué tan claro se ve cada cambio. «Ver en detalle» abre sus fotos en «Explorar y verificar».")
    mostrar_hitos(d, c, "resumen", "resumen_hitos")


# ============================================================================
# Explorar y verificar
# ============================================================================

def grafico_por_hora(fotos_dia: pd.DataFrame, c: dict) -> go.Figure:
    tabla = pd.crosstab(fotos_dia["hora_h"], fotos_dia["estado"]).reindex(index=range(24), columns=ESTADOS_FOTO, fill_value=0)
    fig = go.Figure()
    for e in ESTADOS_FOTO:
        fig.add_bar(x=tabla.index, y=tabla[e], name=mayuscula(e), marker_color=c[CLAVE_FOTO[e]], marker_line_width=0,
                    hovertemplate=f"%{{x}}:00–%{{x}}:59 · {e}: %{{y}} fotos<extra></extra>")
    fig.update_layout(barmode="stack", bargap=0.15, height=230, margin=dict(l=36, r=8, t=8, b=30),
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", showlegend=False,
                      font=dict(color=c["tinta"]), separators=", ")
    fig.update_xaxes(tickvals=list(range(0, 24, 3)), ticktext=[f"{h} h" for h in range(0, 24, 3)], showgrid=False,
                     fixedrange=True, range=[-0.6, 23.6])
    fig.update_yaxes(gridcolor=c["borde"], zeroline=False, fixedrange=True, title=None)
    return fig


def leyenda_fotos(c: dict) -> None:
    st.html('<div class="leyenda" role="list" aria-label="Leyenda: estado de cada foto">'
            + "".join(f'<span role="listitem" style="--c:{c[CLAVE_FOTO[e]]}">{mayuscula(e)}</span>' for e in ESTADOS_FOTO)
            + "</div>")


def dia_util_anterior(d: dict, f: pd.Timestamp) -> pd.Timestamp | None:
    """Día con evidencia anterior a f en la misma vista (None si f es el primero o no es útil)."""
    util = utiles(d["dias"])
    if f not in util.index:
        return None
    antes = util[(util["fecha"] < f) & util["vista"].eq(util.loc[f, "vista"])]
    return None if antes.empty else antes["fecha"].iloc[-1]


def detalle_dia(d: dict, c: dict, f: pd.Timestamp) -> None:
    """Foto del día y, debajo en celular o a la derecha en escritorio, los datos del día."""
    dia = d["dias"].set_index("fecha").loc[f]
    fotos_dia = d["fotos"][d["fotos"]["fecha"].eq(f)]
    excluidas = int(dia["fotos"] - dia["fotos_utiles"])
    st.subheader(mayuscula(fecha_larga(f, dia_semana=True)), anchor=False)
    vista = f"vista {int(dia['vista'])} de la cámara" if pd.notna(dia["vista"]) else "sin vista de la obra"
    st.html(f'<p class="bajada">{mayuscula(dia["estado"])} · {vista}</p>')
    foto, datos = st.columns([1, 1], gap="medium")
    with foto:
        if dia["estado"] == UTIL:
            momento = pd.Timestamp(dia["fecha_hora_foto"])
            mostrar_foto(dia["foto"], momento, f"Foto del día (la utilizable más cercana a las 12:00): {hora(momento)}. "
                                               "Toque la foto para ampliarla.", c, key=f"foto_{f.date()}")
        else:
            st.info("Este día no tiene foto del día: ninguna foto es utilizable.", icon="ℹ️")
    with datos:
        st.html(html_cifras([("", miles(dia["fotos"]), "", "fotos tomadas"),
                             ("si", miles(dia["fotos_utiles"]), "", "utilizables"),
                             ("no", miles(excluidas), "", "excluidas")], "tres"))
        if excluidas:
            filas = "".join(f"<tr><td>{nombre}<br><span class='tenue'>{criterio}</span></td><td class='n'>{int(dia[col])}</td></tr>"
                            for col, nombre, criterio in MOTIVOS if dia[col])
            st.html(f"<div class='envoltura'><table class='tabla'><caption>Motivos de exclusión</caption><thead><tr>"
                    f"<th>Criterio de exclusión</th><th class='n'>Fotos</th></tr></thead><tbody>{filas}</tbody></table></div>")
        else:
            st.markdown("Ninguna foto excluida." if dia["fotos"] else "La cámara no envió fotos este día.")
        idx = d["indice"][d["indice"]["fecha"].eq(f)]
        if len(idx) and pd.notna(idx.iloc[0]["indice"]):
            r = idx.iloc[0]
            st.markdown(f"**Índice de cambio visual:** {decimal(r['indice'])} % respecto del "
                        f"{fecha(r['fecha_anterior'])}" + (" — **pico** (10 % más alto de su vista)." if r["pico"] else ".")
                        + f" Registro: {r['registro']}.")
        elif len(idx):
            r = idx.iloc[0]
            motivo = ("es el primer día de su vista" if r["registro"] == "referencia"
                      else "no se pudo alinear con el día con evidencia anterior")
            st.markdown(f"**Índice de cambio visual:** sin valor; {motivo}.")
        anterior = dia_util_anterior(d, f)
        if anterior is not None:
            par = (f"{anterior:%Y-%m-%d}", f"{f:%Y-%m-%d}")
            st.button(f"Comparar con el {fecha(anterior)} (día con evidencia anterior) ↓", key="comparar_anterior",
                      on_click=ir_a_detalle, args=(par[1], par, f"Comparador con el {fecha(anterior)} y el {fecha(f)}."))
    if len(fotos_dia):
        st.markdown("**Fotos por hora**")
        leyenda_fotos(c)
        st.plotly_chart(grafico_por_hora(fotos_dia, c), width="stretch", config={"displayModeBar": False},
                        key=f"horas_{f.date()}")
        conteo = fotos_dia["estado"].value_counts()
        descripcion(f"Barras apiladas por hora (0 a 23 h) con las {len(fotos_dia)} fotos del día: "
                    + ", ".join(f"{conteo.get(e, 0)} {e}" for e in ESTADOS_FOTO)
                    + f". La primera foto es de las {fotos_dia['hora'].min()[:5]} y la última de las "
                      f"{fotos_dia['hora'].max()[:5]}.")


def dia_por_dia(d: dict, c: dict) -> None:
    dias = d["dias"]
    seccion("Día por día", "Detalle de cualquier día",
            "Elija un día en el calendario: foto del día, fotos tomadas y utilizables, motivos de exclusión e índice de "
            "cambio.", id_="detalle-dia")
    aviso_de_detalle("detalle-dia")
    validas = set(dias["fecha"].dt.strftime("%Y-%m-%d"))
    actual = st.session_state.get("dia_explora", utiles(dias)["fecha"].iloc[-1].strftime("%Y-%m-%d"))
    if actual not in validas:
        actual = utiles(dias)["fecha"].iloc[-1].strftime("%Y-%m-%d")
    resultado = calendario_componente(data=datos_calendario(dias, c, "dia", dia=actual), key="calendario_dia",
                                      on_dia_change=lambda: None)
    nuevo = getattr(resultado, "dia", None)
    if nuevo and nuevo in validas and nuevo != actual:
        st.session_state.dia_explora = nuevo
        st.rerun()
    detalle_dia(d, c, pd.Timestamp(actual))


def comparar(d: dict, c: dict) -> None:
    dias = d["dias"]
    seccion("Comparar", "Compare dos días cualquiera",
            "Dos días con foto útil; las fechas se cambian en el calendario de abajo. Dentro de una misma vista de la "
            "cámara las fotos se alinean para corregir el corrimiento diario de la cámara.", id_="comparar")
    aviso_de_detalle("comparar")
    util = utiles(dias)
    validas = set(util.index.strftime("%Y-%m-%d"))
    primera_vista = util[util["vista"].eq(util["vista"].iloc[0])]
    por_defecto = (primera_vista.index[0].strftime("%Y-%m-%d"), primera_vista.index[-1].strftime("%Y-%m-%d"))
    actual = tuple(st.session_state.get("fechas_explora", por_defecto))
    if not (set(actual) <= validas and actual[0] < actual[1]):
        actual = por_defecto
    st.session_state.fechas_explora = actual
    # Primero el resultado (las dos fotos) y después el calendario para cambiar las fechas
    a, b = util.loc[pd.Timestamp(actual[0])], util.loc[pd.Timestamp(actual[1])]
    mostrar_comparacion(d, c, a, b)
    entre = d["hitos"][(d["hitos"]["fecha_fin"] > a["fecha"]) & (d["hitos"]["fecha_inicio"] < b["fecha"])]
    if len(entre):
        st.markdown("Hitos entre estas fechas: " + "; ".join(f"{h.numero}. {minuscula(h.titulo)}" for h in entre.itertuples()) + ".")
    st.markdown("**Cambiar las fechas**")
    resultado = calendario_componente(data=datos_calendario(dias, c, "elegir", *actual), key="calendario_explora",
                                      on_fechas_change=lambda: None)
    nuevas = getattr(resultado, "fechas", None)
    if nuevas:
        par = tuple(sorted((str(nuevas.get("primera")), str(nuevas.get("segunda")))))
        if par != actual and set(par) <= validas and par[0] != par[1]:
            st.session_state.fechas_explora = par
            st.rerun()


def lista_hitos(d: dict, c: dict) -> None:
    hitos = d["hitos"]
    seccion("Hitos", f"Los {len(hitos)} cambios identificados y su claridad" if len(hitos) else "Sin hitos identificados",
            "Se identificaron a mano, comparando una foto por semana y luego una por día. La claridad la asignó el "
            "equipo al revisar las dos fotos a tamaño completo. «Ver en detalle» lleva el par de fotos al comparador.")
    if hitos.empty:
        return
    mostrar_hitos(d, c, "tabla", "lista_hitos")
    st.caption(" · ".join(f"**{mayuscula(k)}:** {v}" for k, v in CRITERIO_CLARIDAD.items()))


def pestana_explorar(d: dict, c: dict) -> None:
    st.html('<p class="bajada" style="margin-top:0.75rem">Para verificar lo que muestra «La historia»: el detalle '
            'de cada día, un comparador libre y la lista completa de hitos. Aquí se usan los términos del '
            'procesamiento (vista de la cámara, corrimiento, criterio de exclusión).</p>')
    dia_por_dia(d, c)
    comparar(d, c)
    lista_hitos(d, c)
    destino = st.session_state.pop("desplazar", None)
    if destino:
        desplazar_componente(data=destino, key="desplazar")


# ============================================================================
# Datos y método
# ============================================================================

def estilo_figura(fig: go.Figure, c: dict, alto: int) -> go.Figure:
    fig.update_layout(height=alto, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                      font=dict(color=c["tinta"], size=13), separators=", ", hoverlabel=dict(align="left"),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None))
    fig.update_xaxes(fixedrange=True, showgrid=False, zeroline=False, linecolor=c["borde"], tickfont=dict(color=c["tenue"]))
    fig.update_yaxes(fixedrange=True, gridcolor=c["borde"], zeroline=False, tickfont=dict(color=c["tenue"]))
    return fig


def grafico_dias_mes(dias: pd.DataFrame, c: dict) -> tuple[go.Figure, pd.DataFrame]:
    tabla = pd.crosstab(dias["fecha"].dt.to_period("M"), dias["estado"]).reindex(columns=ESTADOS, fill_value=0)
    etiquetas = [f"{MESES[p.month - 1]}<br>{p.year}" if i == 0 or p.month == 1 else MESES[p.month - 1]
                 for i, p in enumerate(tabla.index)]
    fig = go.Figure()
    estilos_barra = {UTIL: dict(color=c["si"]), NO_SE_VE: dict(color=c["no_suave"], pattern=dict(shape="/", fgcolor=c["no"])),
                     SIN_FOTO: dict(color=c["no"])}
    for e in ESTADOS:
        fig.add_bar(x=etiquetas, y=tabla[e], name=LEYENDA[e], marker=dict(**estilos_barra[e], line=dict(width=1.5, color=c["fondo"])),
                    text=[str(v) if v >= 3 else "" for v in tabla[e]], textposition="inside", insidetextanchor="middle",
                    textfont=dict(color=c["si_texto"] if e == UTIL else c["tinta"] if e == NO_SE_VE else "#FFFFFF"),
                    hovertemplate=f"%{{x}}: %{{y}} días · {LEYENDA[e].lower()}<extra></extra>")
    estilo_figura(fig, c, 340)
    fig.update_layout(barmode="stack", bargap=0.3, margin=dict(l=36, r=8, t=40, b=8), legend_traceorder="normal")
    fig.update_yaxes(title=None, dtick=10)
    return fig, tabla


def grafico_motivos(dias: pd.DataFrame, c: dict) -> tuple[go.Figure, pd.Series]:
    totales = pd.Series({nombre: int(dias[col].sum()) for col, nombre, _ in MOTIVOS}).sort_values()
    fig = go.Figure(go.Bar(x=totales.values, y=totales.index, orientation="h", marker=dict(color=c["no"], line=dict(width=0)),
                           text=[miles(v) for v in totales.values], textposition="outside", cliponaxis=False,
                           hovertemplate="%{y}: %{x} fotos<extra></extra>"))
    estilo_figura(fig, c, 300)
    fig.update_layout(margin=dict(l=8, r=48, t=8, b=8), bargap=0.35)
    fig.update_xaxes(showticklabels=False, showgrid=False)
    fig.update_yaxes(showgrid=False, automargin=True)
    return fig, totales


def validacion(indice: pd.DataFrame, hitos: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    """Por hito: días con índice en su ventana (fecha_inicio, fecha_fin], índice máximo y si
    coincide con un pico. Devuelve también las coincidencias esperadas por azar."""
    con = indice[indice["indice"].notna()]
    tasa = con.groupby("vista")["pico"].mean()
    filas, esperado = [], 0.0
    for h in hitos.itertuples():
        ventana = con[(con["fecha"] > h.fecha_inicio) & (con["fecha"] <= h.fecha_fin)]
        esperado += 1 - (1 - float(tasa.get(h.vista, 0))) ** len(ventana)
        filas.append({"numero": h.numero, "titulo": h.titulo, "rango": rango(h.fecha_inicio, h.fecha_fin),
                      "dias": len(ventana), "maximo": ventana["indice"].max() if len(ventana) else np.nan,
                      "coincide": bool(ventana["pico"].any())})
    return pd.DataFrame(filas), esperado


def grafico_indice(d: dict, c: dict) -> go.Figure:
    indice, hitos = d["indice"], d["hitos"]
    con = indice[indice["indice"].notna()]
    fig = go.Figure()
    tope = float(con["indice"].max()) * 1.22
    nivel, anterior = 0, None
    for h in hitos.itertuples():
        fig.add_vrect(x0=h.fecha_inicio + pd.Timedelta(hours=12), x1=h.fecha_fin + pd.Timedelta(hours=12),
                      fillcolor=c["banda"], line_width=0, layer="below")
        # Números de hitos cercanos en dos alturas, para que no se encimen
        nivel = 1 - nivel if anterior is not None and (h.fecha_fin - anterior).days < 6 else 0
        anterior = h.fecha_fin
        fig.add_annotation(x=h.fecha_fin, y=tope * (1 - 0.07 * nivel), text=str(h.numero), showarrow=False, yanchor="top",
                           font=dict(size=11, color=c["tinta"]))
    for pico, nombre, color in [(False, "Resto de los días", c["tenue"]), (True, "Pico (10 % más alto de su vista)", c["tinta"])]:
        g = con[con["pico"].eq(pico)]
        fig.add_bar(x=g["fecha"], y=g["indice"], name=nombre, marker=dict(color=color, opacity=0.45 if not pico else 1,
                    line=dict(width=0)), width=24 * 3600 * 1000 * 0.75,
                    customdata=np.stack([g["fecha_anterior"].dt.strftime("%d/%m"), g["registro"]], axis=-1),
                    hovertemplate="%{x|%d/%m/%Y} vs %{customdata[0]}: %{y:.1f} % · registro %{customdata[1]}<extra></extra>")
    for v, g in con.groupby("vista"):
        umbral = float(g.loc[g["pico"], "indice"].min())
        fig.add_shape(type="line", x0=g["fecha"].min() - pd.Timedelta(days=1), x1=g["fecha"].max() + pd.Timedelta(days=1),
                      y0=umbral, y1=umbral, line=dict(color=c["tinta"], width=1, dash="dot"))
    sin = indice[indice["indice"].isna() & indice["registro"].eq("sin registro")]
    if len(sin):
        fig.add_scatter(x=sin["fecha"], y=[0] * len(sin), mode="markers", name="Sin índice (no se pudo alinear)",
                        marker=dict(symbol="x-thin", size=9, line=dict(width=2, color=c["no"])),
                        hovertemplate="%{x|%d/%m/%Y}: no se pudo alinear con el día anterior<extra></extra>")
    for f in cambios_de_vista(d["vistas"]):
        x = f - pd.Timedelta(hours=12)
        fig.add_shape(type="line", x0=x, x1=x, y0=0, y1=tope, line=dict(color=c["tinta"], width=1.5, dash="dot"))
        fig.add_annotation(x=x, y=tope * 0.9, text="otra vista", showarrow=False, xanchor="left", xshift=4,
                           font=dict(size=11, color=c["tinta"]))
    estilo_figura(fig, c, 380)
    fig.update_layout(barmode="overlay", margin=dict(l=40, r=8, t=56, b=8))
    fig.update_yaxes(title=dict(text="% de la zona analizada", font=dict(size=12)), range=[0, tope])
    fig.update_xaxes(tickformat="%b", dtick="M1", ticklabelmode="period")
    return fig


def ver_pico(d: dict) -> None:
    """Callback de los botones de picos: lleva el par (día anterior, pico) a «Explorar y verificar»."""
    elegido = st.session_state.get("pico_detalle")
    st.session_state.pico_detalle = None
    if not elegido:
        return
    f = pd.Timestamp(elegido)
    r = d["indice"][d["indice"]["fecha"].eq(f)].iloc[0]
    ir_a_detalle(elegido, (f"{r['fecha_anterior']:%Y-%m-%d}", elegido),
                 f"Pico del índice de cambio del {fecha(f)} ({decimal(r['indice'])} %), comparado con el "
                 f"{fecha(r['fecha_anterior'])}. Active «Mostrar dónde cambió» para ver las zonas detectadas.")


def indice_cambio(d: dict, c: dict) -> None:
    indice, hitos = d["indice"], d["hitos"]
    val, esperado = validacion(indice, hitos)
    coinciden = int(val["coincide"].sum()) if len(val) else 0
    con = indice[indice["indice"].notna()]
    picos = con[con["pico"]]
    en_hito = picos[picos["fecha"].apply(lambda f: ((hitos["fecha_inicio"] < f) & (hitos["fecha_fin"] >= f)).any())]
    seccion("Índice de cambio visual",
            f"El índice marca {coinciden} de {len(val)} hitos; por azar marcaría unos {esperado:.0f}",
            "Mide qué parte de la imagen cambió respecto del día con evidencia anterior. Sirve como alerta para revisar "
            "días concretos, no para identificar cambios por sí solo.")
    st.html('<p class="solo-celular">Para revisar con detalle se recomienda una computadora o el teléfono en horizontal; '
            'el gráfico se puede desplazar hacia los lados.</p>')
    seleccion = st.plotly_chart(grafico_indice(d, c), width="stretch", config={"displayModeBar": False}, key="indice",
                                on_select="rerun", selection_mode="points")
    puntos = (seleccion or {}).get("selection", {}).get("points", []) if hasattr(seleccion, "get") else []
    if puntos:
        f = pd.Timestamp(str(puntos[0].get("x"))[:10])
        fila = con[con["fecha"].eq(f)]
        if len(fila):
            r = fila.iloc[0]
            ir_a_detalle(f"{f:%Y-%m-%d}", (f"{r['fecha_anterior']:%Y-%m-%d}", f"{f:%Y-%m-%d}"),
                         f"Día {fecha(f)} del índice de cambio ({decimal(r['indice'])} %), comparado con el "
                         f"{fecha(r['fecha_anterior'])}.")
            st.rerun()
    opciones = {f"{r.fecha:%Y-%m-%d}": f"{fecha(r.fecha, anio=False)} · {decimal(r.indice)} %"
                for r in picos.sort_values("fecha").itertuples()}
    st.pills("Ver un pico en detalle (abre el par de fotos en «Explorar y verificar»; también puede tocar una barra)",
             list(opciones), format_func=lambda k: opciones[k], key="pico_detalle", on_change=ver_pico, args=(d,))
    st.caption("Bandas azules numeradas: ventana de cada hito (de la foto de antes a la de después). Línea punteada "
               "horizontal: umbral de pico de cada vista.")
    sin = indice[indice["indice"].isna()]
    descripcion(
        f"Barras por día con evidencia, {rango_largo(con['fecha'].min(), con['fecha'].max())}: {len(con)} días con "
        f"índice, de {decimal(con['indice'].min())} % a {decimal(con['indice'].max())} % (mediana {decimal(con['indice'].median())} %). "
        f"{len(picos)} días son pico (barras oscuras). {len(sin)} días no tienen índice: el primero de cada vista y "
        f"{int(sin['registro'].eq('sin registro').sum())} que no se pudieron alinear con su día anterior (marcados con ×). "
        "Las bandas sombreadas son las ventanas de los hitos.")

    filas = "".join(
        f"<tr><td class='n'>{r.numero}</td><td>{html.escape(r.titulo)}<br><span class='tenue'>{r.rango}</span></td>"
        f"<td class='n'>{r.dias}</td><td class='n'>{'' if pd.isna(r.maximo) else decimal(r.maximo) + ' %'}</td>"
        f"<td><span class='marca {'si' if r.coincide else 'no'}'>{'Sí' if r.coincide else 'No'}</span></td></tr>"
        for r in val.itertuples())
    st.html(f"<div class='envoltura'><table class='tabla'><caption>Validación contra los hitos</caption><thead><tr>"
            f"<th class='n'>N.º</th><th>Hito</th><th class='n'>Días con índice</th><th class='n'>Índice máx.</th>"
            f"<th>¿Pico?</th></tr></thead><tbody>{filas}</tbody></table></div>")
    st.caption("Días con índice: días con evidencia dentro de la ventana del hito (de la foto de antes, excluida, a la "
               "de después). ¿Pico?: si alguno de esos días está en el 10 % más alto de su vista.")
    no = val.loc[~val["coincide"], "numero"].astype(str).tolist()
    st.markdown(
        f"**Qué tan útil es.** Coincide con un pico en {coinciden} de {len(val)} hitos, cuando por azar se esperarían "
        f"unos {decimal(esperado)}; de {len(picos)} picos, {len(en_hito)} caen dentro de un hito. Detecta cambios grandes de "
        "estructura (la losa, el pavimento, maquinaria que llega) y no detecta cambios finos o lejanos "
        + (f"(hitos {enumerar(no)}: barandas, líneas pintadas, la perforadora que se retira al fondo, tierra removida). "
           if no else ". ")
        + "Los picos sin hito corresponden, en la revisión de sus fotos, a tráfico detenido en la segunda vista, "
          "maquinaria que cambia de lugar y ramas cercanas a la cámara. Los parámetros se ajustaron mirando los picos "
          "falsos con estos mismos hitos, así que esta validación es optimista.")
    with st.expander("Cómo se calcula"):
        st.markdown(
            "1. **Imagen del día:** mediana de hasta 5 fotos utilizables tomadas a menos de 60 minutos de la foto del "
            "día; borra vehículos y personas que pasan (no los que están detenidos).\n"
            "2. **Registro:** la cámara se corre unos píxeles casi a diario (hasta ~75 px y 2° en la primera vista). "
            "Cada día se alinea con el anterior por puntos característicos (ORB + RANSAC) o, si no alcanza, por "
            "intensidad (ECC); el corrimiento del 16-17 de enero coincide con el medido por `06` (< 2 px). Si ninguno "
            "es confiable, el día queda sin índice.\n"
            "3. **Diferencia de estructura:** término de contraste y estructura del SSIM, que cambia poco con la luz.\n"
            "4. **Lo que no es obra:** se excluye el 30 % de la imagen que más cambia en cualquier par de días "
            "(hojas del árbol y vegetación del primer plano, nubes) y un píxel cuenta solo si cambia al menos 2,5 "
            "veces más que lo habitual en ese punto (atenúa el tráfico de la carretera). No se usa una máscara fija "
            "del cielo porque ocultaría la grúa y la perforadora.\n"
            "5. **Índice:** % de la zona analizada que cambió. **Pico:** 10 % de días más altos de cada vista.\n\n"
            f"Script: `src/07_indice_cambio.py`. Detalle en la [nota metodológica]({NOTA_URL}).")


def descargas() -> None:
    seccion("Descargas", "Tablas de la aplicación", "Las mismas tablas que usa esta aplicación, en CSV (UTF-8).")
    archivos = [
        ("dias.csv", "Un día por fila: estado, vista, fotos, fotos útiles, foto del día y fotos excluidas por motivo."),
        ("fotos.csv", "Una fila por foto (21 644): fecha, hora y estado (útil, excluida por calidad, de noche, sin vista de la obra)."),
        ("hitos.csv", "Hitos identificados: fechas, título, descripción, fotos de antes y después y confianza (claridad)."),
        ("indice_cambio.csv", "Índice de cambio visual por día: día anterior comparado, registro, índice y pico."),
        ("alineacion_dia.csv", "Transformación de cada día al marco del primer día de su vista (registro de la cámara)."),
        ("vistas.csv", "Fechas de cada vista de la cámara."),
    ]
    for nombre, texto in archivos:
        ruta = DATOS / nombre
        if not ruta.exists():
            continue
        izq, der = st.columns([3, 1], vertical_alignment="center")
        izq.markdown(f"**{nombre}** · {texto}")
        der.download_button("Descargar", ruta.read_bytes(), file_name=nombre, mime="text/csv", key=f"dl_{nombre}",
                            width="stretch")


def pestana_datos(d: dict, c: dict) -> None:
    dias, fotos = d["dias"], d["fotos"]
    utilizables = int(fotos["estado"].eq("útil").sum())
    st.html('<div style="height:0.75rem"></div>' + html_cifras([
        ("", miles(len(fotos)), "", "fotos originales"),
        ("si", miles(utilizables), "", f"utilizables ({round(100 * utilizables / len(fotos))} %)"),
        ("", miles(len(dias)), "", f"días, {rango(dias['fecha'].min(), dias['fecha'].max())}"),
        ("si", miles(dias["estado"].eq(UTIL).sum()), "", "días con evidencia de la obra")], "cuatro"))

    fig, tabla = grafico_dias_mes(dias, c)
    peor = (tabla[UTIL] / tabla.sum(axis=1)).idxmin()
    seccion("Cobertura", f"{mes_largo(peor)} es el mes con menos días con evidencia",
            f"{tabla.loc[peor, UTIL]} de {tabla.loc[peor].sum()} días con foto útil de la obra.")
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key="dias_mes")
    descripcion(
        "Barras apiladas, una por mes, con los días según su estado: con evidencia (azul), con fotos pero sin vista de "
        "la obra (rayado; incluye los días con solo fotos nocturnas) y sin foto (bermellón). "
        + "; ".join(f"{mes_largo(p)}: {f[UTIL]} con evidencia, {f[NO_SE_VE]} sin vista, {f[SIN_FOTO]} sin foto"
                    for p, f in tabla.iterrows()) + ".")

    fig, totales = grafico_motivos(dias, c)
    seccion("Depuración", f"De {miles(len(fotos))} fotos, {miles(utilizables)} son utilizables",
            f"Se excluyeron {miles(totales.sum())}; la mayoría, por ser nocturnas.")
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key="motivos")
    descripcion("Barras horizontales con las fotos excluidas por cada motivo, de mayor a menor: "
                + "; ".join(f"{k}: {miles(v)}" for k, v in totales.sort_values(ascending=False).items()) + ". "
                + " ".join(f"**{nombre}:** {criterio}" for _, nombre, criterio in MOTIVOS))

    indice_cambio(d, c)

    seccion("Método", "Cómo se hizo")
    st.markdown(
        "Las fotos son de la cámara instalada en la obra por la Contraloría General de la República (CGR), proyecto "
        "dIAra, y son de uso público. Se revisaron todas y se descartaron las de noche, las demasiado oscuras, borrosas "
        "o dañadas y las de los días en que la cámara no apuntaba a la obra. De cada día con fotos útiles se eligió una "
        "cercana al mediodía. Los hitos se identificaron a mano, comparando una foto por semana y, para precisar la "
        "fecha, una foto por día; el índice de cambio visual se calculó después, de forma automática, y se contrastó "
        "con ellos. No se usan datos externos: el sitio no informa presupuesto, plazos ni porcentaje de avance.\n\n"
        f"El procedimiento completo, con cifras y limitaciones, está en la [nota metodológica]({NOTA_URL}). "
        f"Código y datos: [repositorio]({REPO_URL}).")
    descargas()
    st.caption("Proyecto Integrador III · Visualización de datos, Lead University, 2026")


# ============================================================================

def main() -> None:
    d = cargar()
    c = COLORES[tema()]
    d = {**d, "c": c}
    estilos(c)
    franja(d["dias"])
    # Pestañas con estado (key + on_change) y sincronizadas con la URL (?pestana=...): así
    # «Ver en detalle» puede cambiar de pestaña y un enlace abre directamente una de ellas. Solo
    # se dibuja la pestaña abierta.
    if "ir_pestana" in st.session_state:
        st.session_state.pestana = st.session_state.pop("ir_pestana")
    historia, explorar, datos = st.tabs(PESTANAS, key="pestana", on_change="rerun", bind="query-params")
    if historia.open:
        with historia:
            pestana_historia(d, c)
    if explorar.open:
        with explorar:
            pestana_explorar(d, c)
    if datos.open:
        with datos:
            pestana_datos(d, c)


main()
