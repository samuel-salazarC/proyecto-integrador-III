"""Puente María Aguilar: lo que muestran las fotos.

App de una página para la ciudadanía. Solo lee archivos de app/ (generados por
src/06_fotos_app.py), así que funciona desplegada sin las fotografías originales.

Uso local:
  streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import base64
import html
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

# Paleta validada para daltonismo (azul / bermellón, Okabe-Ito) más un gris neutro para
# "no hay foto"; los estados también se distinguen por la leyenda, el tooltip y el texto.
COLORES = {
    "light": {UTIL: "#0072B2", NO_SE_VE: "#D55E00", SIN_FOTO: "#DEDEDA", "linea": "#1A1A19"},
    "dark": {UTIL: "#3D9BE0", NO_SE_VE: "#E8743B", SIN_FOTO: "#3A3A38", "linea": "#F2F2F0"},
}
CLARIDAD = {"alta": "Se ve con claridad.",
            "media": "Se ve, pero con algunos detalles difíciles de distinguir.",
            "baja": "Se ve con poca claridad: es una interpretación tentativa."}
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
MESES_LARGO = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
               "septiembre", "octubre", "noviembre", "diciembre"]
DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
MAX_RADIO_HITOS = 15  # con más hitos, la lista se vuelve un desplegable
HORAS_LUZ = range(6, 18)  # el calendario muestra de 6:00 a 17:59; de noche no se ve la obra

st.set_page_config(page_title="Puente María Aguilar: lo que muestran las fotos", page_icon="🌉", layout="centered")


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
    """Rachas de días consecutivos sin foto útil (inicio, fin, días)."""
    sin = dias["estado"].ne(UTIL)
    grupo = (sin != sin.shift()).cumsum()
    rachas = dias[sin].groupby(grupo[sin])["fecha"].agg(["min", "max", "size"])
    return rachas.rename(columns={"min": "inicio", "max": "fin", "size": "dias"}).sort_values("dias", ascending=False)


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


def alt_foto(f: pd.Timestamp, extra: str = "") -> str:
    return (f"Foto de la cámara tomada el {fecha(f, dia_semana=True)} a las {hora(f)}: "
            f"vista del Puente María Aguilar y la vía a su alrededor.{(' ' + extra) if extra else ''}")


def tema() -> str:
    try:
        return "dark" if st.context.theme.type == "dark" else "light"
    except Exception:
        return "light"


# ============================================================================
# Secciones
# ============================================================================

def encabezado(d: dict) -> None:
    dias, hitos = d["dias"], d["hitos"]
    utiles = int(dias["estado"].eq(UTIL).sum())
    hueco = tramos_sin_evidencia(dias).iloc[0]
    inicio, fin = dias["fecha"].min(), dias["fecha"].max()

    st.title("Puente María Aguilar: lo que muestran las fotos")
    st.markdown("#### ¿Qué cambios se observan en la obra, cuándo ocurrieron y qué días no hay evidencia fotográfica?")

    tarjetas = [
        ("Días con fotos útiles de la obra", f"{utiles} de {len(dias)}",
         f"En {len(dias) - utiles} días no hay una foto donde se vea la obra."),
        ("Periodo más largo sin evidencia", plural(int(hueco["dias"]), "día"), rango(hueco["inicio"], hueco["fin"])),
        ("Cambios identificados en la obra", str(len(hitos)), "Revisados a mano, foto por foto."),
        ("Periodo cubierto", plural(len(dias), "día"), rango(inicio, fin)),
    ]
    for fila in (tarjetas[:2], tarjetas[2:]):
        for col, (titulo, valor, nota) in zip(st.columns(2), fila):
            with col.container(border=True):
                st.metric(titulo, valor)
                st.caption(nota)


def acto_contexto(d: dict) -> None:
    dias, horas = d["dias"], d["horas"]
    st.header("1. La obra y la cámara")
    total_fotos = int(horas["fotos"].sum())
    st.markdown(
        f"El **Puente María Aguilar** es una de las obras del programa PROERI. Una cámara fija instalada "
        f"por la Contraloría General de la República (sistema dIAra) tomó una foto cada pocos minutos, "
        f"de día y de noche, entre el {fecha(dias['fecha'].min())} y el {fecha(dias['fecha'].max())}: "
        f"unas {miles(total_fotos)} fotos en total."
    )
    st.markdown(
        "Este sitio usa esas fotos para responder tres preguntas: **qué cambios se ven** en la obra, "
        "**cuándo ocurrieron** y **qué días no hay fotos** que permitan verla. No muestra porcentajes de "
        "avance, plazos ni montos: solo lo que la cámara permite ver."
    )
    ultima = d["semanas"].dropna(subset=["foto"]).iloc[-1]
    st.image(str(APP / ultima["foto"]), width="stretch", alt=alt_foto(ultima["fecha_hora"]),
             caption=f"La última foto útil de la serie: {fecha(ultima['fecha_hora'], dia_semana=True)}, {hora(ultima['fecha_hora'])}.")


def tarjetas_semanales(d: dict, hito_sel: int | None) -> tuple[str, int]:
    """Tira horizontal (se desliza en el celular) con una foto por semana y los hitos de cada una."""
    semanas, hitos, dias = d["semanas"].dropna(subset=["foto"]), d["hitos"], d["dias"]
    semanas = semanas.sort_values(["semana_inicio", "vista"]).reset_index(drop=True)
    # Cada hito va en la semana (de su misma vista de la cámara) en que ya se ve el cambio
    asignado: dict[int, list] = {}
    for h in hitos.itertuples():
        mismas = semanas[semanas["vista"].eq(h.vista)]
        if mismas.empty:
            mismas = semanas
        distancia = (mismas["semana_inicio"] + pd.Timedelta(days=3) - h.fecha_fin).abs()
        asignado.setdefault(distancia.idxmin(), []).append(h)

    partes = []
    anterior = None
    for i, s in semanas.iterrows():
        if anterior is not None:
            avisos = []
            hueco = dias[(dias["fecha"] > anterior["fecha_hora"]) & (dias["fecha"] < s["fecha_hora"])]
            rachas = tramos_sin_evidencia(hueco) if len(hueco) else pd.DataFrame()
            if len(rachas) and rachas.iloc[0]["dias"] >= 7:
                r = rachas.iloc[0]
                avisos.append(f"<b>{rango(r['inicio'], r['fin'])}</b><br>{plural(int(r['dias']), 'día')} sin fotos útiles de la obra")
            if s["vista"] != anterior["vista"]:
                avisos.append("<b>La cámara se movió</b><br>la vista cambia desde aquí")
            if avisos:
                partes.append(f'<div class="corte" role="note">{"<hr>".join(avisos)}</div>')
        chips = "".join(
            f'<div class="hito{" sel" if h.numero == hito_sel else ""}"><span class="num">{h.numero}</span>'
            f'{html.escape(h.titulo)}<br><small>{rango(h.fecha_inicio, h.fecha_fin)}</small></div>'
            for h in asignado.get(i, []))
        fin = s["semana_inicio"] + pd.Timedelta(days=6)
        alt = alt_foto(s["fecha_hora"], f"Semana del {rango(s['semana_inicio'], fin)}.")
        miniatura = Path(s["foto"]).parent / "miniaturas" / Path(s["foto"]).name
        ruta = miniatura if (APP / miniatura).exists() else Path(s["foto"])
        seleccionada = any(h.numero == hito_sel for h in asignado.get(i, []))
        partes.append(
            f'<figure class="semana{" sel" if seleccionada else ""}">'
            f'<figcaption><b>Semana del {rango(s["semana_inicio"], fin)}</b><br>'
            f'<small>foto del {fecha(s["fecha_hora"], dia_semana=True, anio=False)}, {hora(s["fecha_hora"])}</small></figcaption>'
            f'<img src="data:image/jpeg;base64,{imagen_base64(str(ruta))}" alt="{html.escape(alt)}" loading="lazy">'
            f'{chips}</figure>')
        anterior = s
    return "".join(partes), len(semanas)


def linea_de_tiempo(d: dict, colores: dict) -> None:
    hitos = d["hitos"]
    st.subheader("Una foto por semana")
    st.markdown("Desliza la tira hacia los lados para recorrer la obra semana a semana. Los números marcan "
                "los cambios identificados; elige uno abajo para ver la foto de antes y la de después.")

    clave = "hito_elegido"
    hito_sel = st.session_state.get(clave, 1 if len(hitos) else None)
    contenido, n_semanas = tarjetas_semanales(d, hito_sel)
    st.html(f"""
<style>
.tira {{ display:flex; gap:12px; overflow-x:auto; padding:4px 2px 12px; scroll-snap-type:x proximity; }}
.tira figure {{ margin:0; flex:0 0 200px; scroll-snap-align:start; font-size:0.85rem; line-height:1.3; }}
.tira figure img {{ width:100%; border-radius:6px; display:block; margin:4px 0 6px; }}
.tira figure.sel img {{ outline:3px solid {colores[UTIL]}; outline-offset:2px; }}
.tira .hito {{ border-left:3px solid {colores['linea']}; padding:2px 0 2px 8px; margin-top:6px; }}
.tira .hito.sel {{ border-left-color:{colores[UTIL]}; font-weight:600; }}
.tira .num {{ display:inline-block; min-width:1.4em; height:1.4em; line-height:1.4em; text-align:center;
             border-radius:50%; background:{colores['linea']}; color:{'#1A1A19' if colores['linea'] != '#1A1A19' else '#FFFFFF'};
             font-size:0.75rem; font-weight:700; margin-right:6px; }}
.tira .corte {{ flex:0 0 130px; align-self:stretch; border:2px dashed currentColor; border-radius:6px; opacity:0.75;
               padding:10px; font-size:0.85rem; display:flex; flex-direction:column; justify-content:center; }}
.tira .corte hr {{ margin:8px 0; border:none; border-top:1px solid currentColor; }}
</style>
<div class="tira" role="region" aria-label="Una foto por semana, en orden cronológico" tabindex="0">{contenido}</div>
""")
    if hitos.empty:
        st.info("Todavía no hay cambios identificados.")
        return
    st.caption(f"{plural(n_semanas, 'semana')} con foto útil y {plural(len(hitos), 'cambio identificado', 'cambios identificados')}, "
               f"entre el {fecha(hitos['fecha_inicio'].min())} y el {fecha(hitos['fecha_fin'].max())}.")

    st.subheader("Los cambios, uno por uno")
    etiquetas = {h.numero: f"{h.numero}. {rango(h.fecha_inicio, h.fecha_fin)} · {h.titulo}" for h in hitos.itertuples()}
    if len(hitos) <= MAX_RADIO_HITOS:
        numero = st.radio("Elige un cambio", list(etiquetas), format_func=etiquetas.get, key=clave)
    else:
        numero = st.selectbox("Elige un cambio", list(etiquetas), format_func=etiquetas.get, key=clave)
    h = hitos[hitos["numero"].eq(numero)].iloc[0]
    with st.container(border=True):
        st.markdown(f"**{h['titulo']}** · {rango(h['fecha_inicio'], h['fecha_fin'])}")
        st.markdown(h["descripcion"])
        st.caption(CLARIDAD.get(str(h["confianza"]).strip().lower(), ""))
        for col, (cuando, foto, momento) in zip(
                st.columns(2), [("Antes", h["foto_antes"], h["fecha_hora_antes"]), ("Después", h["foto_despues"], h["fecha_hora_despues"])]):
            with col:
                if isinstance(foto, str) and (APP / foto).exists():
                    st.image(str(APP / foto), width="stretch",
                             alt=alt_foto(momento, f"{cuando} del cambio: {h['titulo']}."),
                             caption=f"{cuando}: {fecha(momento, dia_semana=True)}, {hora(momento)}")
                else:
                    st.caption(f"{cuando}: foto no disponible")


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
.comp {{ position:relative; width:100%; overflow:hidden; border-radius:8px; line-height:0; user-select:none; touch-action:pan-y; }}
.comp .lienzo {{ position:relative; transform-origin:0 0; transform:scale({aj['zoom']:.5f}) translate({-aj['vx']:.4f}%, {-aj['vy']:.4f}%); }}
.comp img {{ width:100%; height:auto; display:block; }}
.comp .despues {{ transform-origin:50% 50%;
                 transform:translate({aj['tx']:.4f}%, {aj['ty']:.4f}%) rotate({aj['rot']:.4f}deg) scale({aj['escala']:.5f}); }}
.comp .antes {{ position:absolute; inset:0; clip-path:inset(0 50% 0 0); }}
.comp .linea {{ position:absolute; top:0; bottom:0; left:50%; width:3px; margin-left:-1.5px; background:#fff;
               box-shadow:0 0 4px rgba(0,0,0,.6); pointer-events:none; }}
.comp .asa {{ position:absolute; top:50%; left:50%; width:40px; height:40px; margin:-20px 0 0 -20px; border-radius:50%;
             background:#fff; box-shadow:0 0 6px rgba(0,0,0,.6); pointer-events:none; display:flex; align-items:center;
             justify-content:center; font:700 16px/1 system-ui, sans-serif; color:#1a1a19; }}
.comp .rotulo {{ position:absolute; top:8px; padding:4px 8px; border-radius:4px; background:rgba(0,0,0,.7); color:#fff;
                font:600 13px/1.2 system-ui, sans-serif; pointer-events:none; }}
.comp .izq {{ left:8px; }} .comp .der {{ right:8px; }}
.comp input {{ position:absolute; inset:0; width:100%; height:100%; margin:0; opacity:0; cursor:ew-resize; }}
.comp:has(input:focus-visible) {{ outline:3px solid #0072B2; outline-offset:2px; }}
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


def comparador(d: dict) -> None:
    dias = d["dias"]
    st.subheader("Compara dos fechas")
    st.markdown("Elige dos días y desliza la barra sobre la foto (o usa las flechas del teclado) para ver qué cambió.")
    utiles = dias[dias["estado"].eq(UTIL)].reset_index(drop=True)
    opciones = list(utiles.index)
    etiqueta = {i: fecha(utiles.at[i, "fecha"], dia_semana=True) for i in opciones}
    primera = utiles["vista"].iloc[0]
    defecto_despues = utiles.index[utiles["vista"].eq(primera)][-1]
    c1, c2 = st.columns(2)
    i = c1.selectbox("Primera fecha", opciones, index=0, format_func=etiqueta.get, key="comp_antes")
    j = c2.selectbox("Segunda fecha", opciones, index=int(defecto_despues), format_func=etiqueta.get, key="comp_despues")
    if i == j:
        st.info("Elige dos fechas distintas para compararlas.")
        return
    a, b = utiles.loc[min(i, j)], utiles.loc[max(i, j)]
    texto_a = f"{fecha(a['fecha_hora_foto'])}, {hora(a['fecha_hora_foto'])}"
    texto_b = f"{fecha(b['fecha_hora_foto'])}, {hora(b['fecha_hora_foto'])}"
    if a["vista"] == b["vista"]:
        corrimientos = corrimientos_entre(d["alineacion"], a, b)
        ajuste = ajuste_css(corrimientos)
        st.iframe(html_comparador(a, b, texto_a, texto_b, ajuste), height="content")
        st.caption(f"Comparación con barra deslizante. A la izquierda, la foto del {fecha(a['fecha'], dia_semana=True)}; "
                   f"a la derecha, la del {fecha(b['fecha'], dia_semana=True)}. Las dos fotos muestran la misma vista "
                   f"de la cámara, así que lo que cambia es la obra.")
        if len(corrimientos):
            st.caption("La cámara se corrió ligeramente entre estas fechas"
                       + ("; la foto de la derecha se ajustó para que coincidan." if ajuste else "."))
    else:
        st.warning("La cámara se movió entre estas fechas, la comparación no es exacta.", icon="⚠️")
        for col, fila, texto in zip(st.columns(2), [a, b], [texto_a, texto_b]):
            col.image(str(APP / fila["foto"]), width="stretch", alt=alt_foto(fila["fecha_hora_foto"]), caption=texto)
    entre = d["hitos"][(d["hitos"]["fecha_fin"] > a["fecha"]) & (d["hitos"]["fecha_inicio"] < b["fecha"])]
    if len(entre):
        st.markdown(f"Entre estas fechas se identificaron {plural(len(entre), 'cambio')}: "
                    + "; ".join(f"{h.numero}. {h.titulo.lower()}" for h in entre.itertuples()) + ".")


def acto_lo_que_se_ve(d: dict, colores: dict) -> None:
    st.header("2. Lo que se ve")
    linea_de_tiempo(d, colores)
    comparador(d)


def calendario(d: dict, colores: dict) -> go.Figure:
    horas, vistas = d["horas"][d["horas"]["hora"].isin(HORAS_LUZ)], d["vistas"]
    codigo = {e: k for k, e in enumerate(ESTADOS)}
    tabla = horas.pivot(index="hora", columns="fecha", values="estado")
    fotos = horas.pivot(index="hora", columns="fecha", values="fotos")
    z = tabla.apply(lambda col: col.map(codigo)).astype(float).values
    texto = [[f"{fecha(c, dia_semana=True)}, {h}:00–{h}:59<br><b>{tabla.at[h, c]}</b>"
              + (f" ({plural(int(fotos.at[h, c]), 'foto')})" if fotos.at[h, c] else "")
              for c in tabla.columns] for h in tabla.index]
    escala = []
    for k, e in enumerate(ESTADOS):
        escala += [[k / len(ESTADOS), colores[e]], [(k + 1) / len(ESTADOS), colores[e]]]
    fig = go.Figure(go.Heatmap(z=z, x=tabla.columns, y=tabla.index, zmin=-0.5, zmax=len(ESTADOS) - 0.5,
                               colorscale=escala, showscale=False, text=texto, hovertemplate="%{text}<extra></extra>",
                               xgap=0, ygap=1))
    for e in ESTADOS:  # leyenda con nombre para cada estado
        fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", name=e, hoverinfo="skip",
                                 marker=dict(symbol="square", size=14, color=colores[e],
                                             line=dict(width=1, color=colores["linea"]))))
    cambios = vistas.sort_values("fecha_inicio").iloc[1:]  # solo los cambios de vista
    for k, c in enumerate(cambios.itertuples()):
        x = c.fecha_inicio - pd.Timedelta(hours=12)
        # Etiquetas alternadas a izquierda y derecha de la línea para que no se encimen en pantallas angostas
        lado = "right" if k % 2 == 0 and k + 1 < len(cambios) else "left"
        fig.add_shape(type="line", x0=x, x1=x, y0=HORAS_LUZ[0] - 0.5, y1=HORAS_LUZ[-1] + 0.5,
                      line=dict(color=colores["linea"], width=2, dash="dot"))
        fig.add_annotation(x=x, y=HORAS_LUZ[0] - 0.5, yanchor="bottom", text=f"la cámara<br>se movió<br>{fecha(c.fecha_inicio, anio=False)}",
                           showarrow=False, font=dict(size=11, color=colores["linea"]), xanchor=lado,
                           align=lado, xshift=4 if lado == "left" else -4)
    marcas = list(range(HORAS_LUZ[0], HORAS_LUZ[-1] + 1, 3)) + [HORAS_LUZ[-1]]
    fig.update_yaxes(autorange="reversed", tickvals=marcas, ticktext=[f"{h} h" for h in marcas],
                     title=None, showgrid=False, fixedrange=True)
    # Meses en español, rotulados a mitad de mes
    meses = pd.date_range(tabla.columns.min().to_period("M").to_timestamp(), tabla.columns.max(), freq="MS")
    fig.update_xaxes(tickvals=[m + pd.Timedelta(days=14) for m in meses],
                     ticktext=[MESES[m.month - 1] + (f"<br>{m.year}" if i == 0 or m.month == 1 else "")
                               for i, m in enumerate(meses)],
                     ticks="", title=None, showgrid=False, fixedrange=True)
    fig.update_layout(height=400, margin=dict(l=40, r=10, t=60, b=10), plot_bgcolor="rgba(0,0,0,0)",
                      legend=dict(orientation="h", yanchor="top", y=-0.24, x=0, title=None),
                      hoverlabel=dict(align="left"), separators=", ")
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
        lineas.append(f"{nombre}: de {len(g)} días, {faltan} sin evidencia de la obra "
                      f"({' y '.join(detalle)}).")
    return lineas


def acto_lo_que_no_se_ve(d: dict, colores: dict) -> None:
    dias, horas, vistas = d["dias"], d["horas"], d["vistas"]
    st.header("3. Lo que no se ve")
    st.markdown(f"Cada columna es un día y cada fila una hora de luz, de {HORAS_LUZ[0]} a {HORAS_LUZ[-1]} h. El color "
                "indica si en esa hora hay una foto donde se vea la obra. La cámara también toma fotos de noche, pero "
                "no sirven para ver la obra, por eso no aparecen. Pasa el cursor (o toca) sobre el gráfico para ver "
                "el detalle.")
    st.plotly_chart(calendario(d, colores), width="stretch", config={"displayModeBar": False, "scrollZoom": False})

    luz = horas[horas["hora"].isin(HORAS_LUZ)]
    horas_utiles = int(luz["estado"].eq(UTIL).sum())
    hueco = tramos_sin_evidencia(dias).iloc[0]
    n = dias["estado"].value_counts()
    cambios = vistas.sort_values("fecha_inicio")["fecha_inicio"].iloc[1:]
    st.markdown(
        f"**En resumen:** de {len(dias)} días, {n.get(UTIL, 0)} tienen al menos una foto útil, en "
        f"{n.get(NO_SE_VE, 0)} hay fotos pero no se ve la obra y en {n.get(SIN_FOTO, 0)} no hay ninguna foto. "
        f"De las {miles(len(luz))} horas de luz del periodo, {miles(horas_utiles)} tienen al menos una foto útil. "
        f"El periodo más largo "
        f"sin evidencia va del {fecha(hueco['inicio'])} al {fecha(hueco['fin'])} ({plural(int(hueco['dias']), 'día')})"
        + (f". La cámara se movió una sola vez, el {fecha(cambios.iloc[0])}." if len(cambios) == 1
           else f". La cámara se movió {len(cambios)} veces: el {' y el '.join(fecha(c) for c in cambios)}." if len(cambios)
           else ".")
    )

    st.subheader("Mes a mes")
    st.markdown("\n".join(f"- {linea}" for linea in resumen_por_mes(dias)))

    st.subheader("¿Por qué faltan datos?")
    no_se_ve = dias[dias["estado"].eq(NO_SE_VE)]
    st.markdown(
        f"- **No hay foto:** en {plural(n.get(SIN_FOTO, 0), 'día')} la cámara no envió ninguna foto. "
        "Desde aquí no se puede saber por qué (corte de energía, de conexión u otra causa).\n"
        f"- **Hay foto pero no se ve la obra:** en {plural(len(no_se_ve), 'día')} hubo fotos, pero en ninguna se ve "
        "la obra: la cámara apuntaba a otra cosa (el cielo, una superficie lisa o un techo) o las fotos estaban "
        "demasiado oscuras.\n"
        "- **De noche:** la cámara también toma fotos de noche, pero no sirven para ver la obra. Por eso el "
        f"calendario muestra solo las horas de luz, de {HORAS_LUZ[0]} a {HORAS_LUZ[-1]} h.\n"
        "- **Fotos que no sirven:** algunas fotos de día salen empañadas, borrosas, quemadas por el sol o con "
        "franjas; no se usan, pero casi siempre hay otras útiles el mismo día.\n"
        "- **La cámara se movió:** "
        + (f"el {' y el '.join(fecha(c) for c in cambios)} la cámara cambió de posición y la vista ya no es la "
           "misma, así que comparar fotos de antes y después de esa fecha es menos exacto."
           if len(cambios) else "la cámara no cambió de posición en todo el periodo.")
    )


def pie() -> None:
    st.divider()
    st.subheader("Cómo se hizo")
    st.markdown(
        "Revisamos todas las fotos de la cámara y descartamos las de noche, las demasiado oscuras, borrosas o "
        "dañadas y las de los días en que la cámara no apuntaba a la obra. De cada día con fotos útiles elegimos "
        "una cercana al mediodía. Los cambios en la obra los identificó el equipo a mano, comparando una foto por "
        "semana y, para precisar la fecha, una foto por día.\n\n"
        "**Fuente:** fotografías de la Contraloría General de la República (CGR), proyecto dIAra. La CGR confirmó "
        "que son de uso público.\n\n"
        f"**Código y datos:** [repositorio del proyecto]({REPO_URL}).\n\n"
        "Proyecto Integrador III · Visualización de datos, Lead University, 2026."
    )


def main() -> None:
    d = cargar()
    colores = COLORES[tema()]
    encabezado(d)
    acto_contexto(d)
    acto_lo_que_se_ve(d, colores)
    acto_lo_que_no_se_ve(d, colores)
    pie()


main()
