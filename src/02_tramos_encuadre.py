"""Tramos de encuadre fijo de la cámara y días que realmente muestran la obra.

Lee data/processed_data/inventario_fotos.csv (generado por 01_inventario.py) y genera:

  data/processed_data/tramos_encuadre.csv    un tramo de encuadre fijo por fila
  data/processed_data/dias_encuadre.csv      un día calendario por fila
  data/processed_data/cambios_encuadre.csv   cada frontera revisada entre días observados
  data/processed_data/fotos_encuadre.csv     cada foto analizada (hasta 3 por día)
  data/processed_data/revision_manual.csv    correcciones a mano (se crea vacía; la
                                             columna rotacion la usa 03_orientacion.py)
  reports/revision_tramos/*.jpg              hojas de contacto para revisión visual

Método
  1. Por día se toman hasta FOTOS_POR_DIA fotos EVALUADA lo más cercanas a las 12:00.
  2. Descriptor de orientaciones (método del notebook del curso): gris 640x480,
     desenfoque gaussiano 5x5, gradientes Sobel, histograma de 9 orientaciones
     ponderado por magnitud en 6x8 celdas; cada celda se normaliza (L2), lo que
     lo hace poco sensible al brillo y al contraste. El descriptor del día es el
     promedio de sus fotos, descartando antes la foto atípica si la hay.
  3. Días que no muestran la obra:
       a. nitidez mediana del día < FRACCION_NITIDEZ_MINIMA x mediana del periodo
          (lente tapado, superficie blanca, cielo);
       b. descriptor lejos tanto de los VENTANA_DIAS días observados anteriores
          como de los siguientes (un día aislado distinto de su entorno);
       c. tramos de menos de MIN_DIAS_TRAMO días lejos de sus dos tramos vecinos.
  4. Cambios de encuadre: se comparan días observados consecutivos (no días
     calendario) y ventanas de VENTANA_DIAS días antes y después. Toda frontera
     entre días observados se verifica con ORB + RANSAC (transformación de
     similitud) entre las fotos del día anterior y las del siguiente:
       - pocas coincidencias consistentes y el descriptor la marcó  -> CAMBIO_CONFIRMADO
       - coincide pero con rotación/escala/desplazamiento grandes   -> CAMBIO_CONFIRMADO
       - coincide con un desplazamiento pequeño pero real           -> SALTO_MENOR
       - coincide sin moverse aunque el descriptor la marcó         -> DESCARTADO
         (la cámara no se movió: cambió la escena, p. ej. avance de la obra)
     Para cada cambio se busca además el momento exacto entre las fotos de los
     dos días (ajuste de un escalón sobre la clasificación de cada foto).
  5. Los tramos se cortan en CAMBIO_CONFIRMADO y SALTO_MENOR.

Tramo y encuadre: un tramo es un periodo en que la imagen decodificada no cambia;
encuadre_id agrupa los tramos con la misma vista física de la cámara. La única
diferencia entre ambos es ROTACION_180: el 2025-10-09 ~15:30 deja de venir la etiqueta
EXIF Orientation = 3, la imagen decodificada se invierte y la cámara no se mueve.

Orientación: las imágenes se leen con cv2.imdecode, que aplica la etiqueta EXIF
Orientation (Pillow sin ImageOps.exif_transpose no lo hace). Para las hojas de contacto
se supone que el último tramo está rotado 180° y se invierte hacia atrás en cada
ROTACION_180. La orientación por foto, con confianza, la calcula 03_orientacion.py.
Las fotos y las tablas no se rotan.

Uso:
  python src/02_tramos_encuadre.py
  python src/02_tramos_encuadre.py --procesos 4
"""

from __future__ import annotations

import argparse
import os
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

# --- Selección de fotos ------------------------------------------------------
FOTOS_POR_DIA = 3          # fotos EVALUADA por día, las más cercanas a mediodía
HORA_REFERENCIA = 12

# --- Descriptor de orientaciones (notebook del curso) ------------------------
TAMANO_ANALISIS = (640, 480)
CELDAS = (6, 8)            # filas x columnas
BINS_ORIENTACION = 9       # 0-180°, 20° por bin

# --- Umbrales sobre el descriptor --------------------------------------------
# Distancias euclidianas entre vectores normalizados L2 (0 = idénticos, 1.41 = opuestos).
# Referencias medidas en este periodo: días con la misma vista separados entre
# sí 0.08-0.32; ventanas de 7 días con la misma vista 0.07-0.22; cambios reales
# de encuadre 0.34-0.72; lente tapado o techo 0.45-0.79.
VENTANA_DIAS = 7                 # días observados a cada lado
UMBRAL_FOTO_ATIPICA = 0.45       # foto lejos de las otras del mismo día -> no se promedia
UMBRAL_CAMBIO_VENTANA = 0.28     # ventana antes vs. después: por encima del ruido (≤0.22)
UMBRAL_CAMBIO_CONSECUTIVO = 0.35 # día contra día: por encima del ruido (≤0.32)
SEPARACION_CANDIDATOS = 3        # se queda el máximo local en ±3 fronteras
UMBRAL_DIA_ATIPICO = 0.40        # lejos de ambas ventanas; el mayor visto con obra es 0.26
FRACCION_NITIDEZ_MINIMA = 0.25   # x mediana del periodo; con obra el mínimo es ~0.40,
                                 # lente tapado/techo/cielo dan ≤0.11
MIN_DIAS_TRAMO = 3               # tramos más cortos se revisan como posibles atípicos

# --- Verificación ORB + RANSAC ------------------------------------------------
ORB_PUNTOS = 3000
ORB_RATIO = 0.75                 # prueba de razón de Lowe
RANSAC_UMBRAL_PX = 4.0           # error de reproyección a 640x480
MIN_INLIERS = 15                 # con menos, el ajuste es aleatorio (se ven 2-5)
MIN_FRACCION_INLIERS = 0.35
DESPLAZAMIENTO_SALTO_PX = 8.0    # misma vista: ≤5.3 px; salto menor real: 14-31 px
ROTACION_SALTO_GRADOS = 1.0      # misma vista: ≤0.5°
ESCALA_SALTO = 0.02              # misma vista: |escala-1| ≤ 0.01
DESPLAZAMIENTO_CAMBIO_PX = 60.0  # a partir de aquí ya es otro encuadre
ROTACION_CAMBIO_GRADOS = 10.0
ESCALA_CAMBIO = 0.10
ROTACION_MEDIA_VUELTA = 170.0    # giro de la imagen sin mover la vista (pasa en oct. 2025)
# Pocos inliers bastan si la transformación es casi la identidad: un ajuste
# aleatorio de RANSAC da rotaciones y escalas arbitrarias, no 0° y escala 1.
# Sirve en días con neblina o contraluz, donde ORB encuentra pocos puntos.
MIN_INLIERS_IDENTIDAD = 8
DESPLAZAMIENTO_IDENTIDAD_PX = 3.0
ROTACION_IDENTIDAD_GRADOS = 0.5
ESCALA_IDENTIDAD = 0.01

# --- Orientación ----------------------------------------------------------------
# ULTIMO_TRAMO_ROTADO_180: supuesto para rotar_180_para_ver (imagen con EXIF aplicada),
# que 03_orientacion.py usa como respaldo.
ULTIMO_TRAMO_ROTADO_180 = True
# Regla para MOSTRAR fotos (hojas de contacto, app, fotos reducidas): píxeles crudos,
# sin aplicar la etiqueta EXIF (cv2.IMREAD_IGNORE_ORIENTATION), girados 180°. Los
# píxeles crudos están siempre al revés; ver README y 04_fotos_utilizables.py.
ROTACION_PARA_MOSTRAR = 180

# --- Hojas de contacto --------------------------------------------------------
MINIATURA = (240, 192)
COLUMNAS_HOJA = 6
CALIDAD_JPG = 60
DIAS_CONTEXTO_CAMBIO = 3

CORTES = {"CAMBIO_CONFIRMADO", "SALTO_MENOR", "ROTACION_180"}
# revision_manual.csv: una fila por día (fecha) o por foto (ruta). obra_visible y
# tramo_id se aplican por día en este script; rotacion (0/180) la aplica 03_orientacion.py.
COLUMNAS_REVISION = ["fecha", "ruta", "obra_visible", "tramo_id", "rotacion", "nota"]
COLUMNAS_REVISION_OBLIGATORIAS = ["fecha", "obra_visible", "tramo_id", "nota"]


# ============================================================================
# Procesamiento de imágenes (se ejecuta en procesos paralelos)
# ============================================================================

def leer_gris(raiz: str, ruta: str) -> np.ndarray | None:
    try:
        imagen = cv2.imdecode(np.fromfile(os.path.join(raiz, ruta), dtype=np.uint8),
                              cv2.IMREAD_GRAYSCALE)
    except Exception:
        return None
    if imagen is None:
        return None
    return cv2.resize(imagen, TAMANO_ANALISIS, interpolation=cv2.INTER_AREA)


def descriptor_orientaciones(gris: np.ndarray) -> np.ndarray:
    """Histograma de orientaciones ponderado por magnitud en una cuadrícula."""
    suave = cv2.GaussianBlur(gris, (5, 5), 0)
    gx = cv2.Sobel(suave, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(suave, cv2.CV_32F, 0, 1, ksize=3)
    magnitud, angulo = cv2.cartToPolar(gx, gy, angleInDegrees=True)
    bins = np.minimum((angulo % 180 / (180 / BINS_ORIENTACION)).astype(int), BINS_ORIENTACION - 1)
    alto, ancho = gris.shape
    filas, columnas = CELDAS
    celda = ((np.arange(alto) * filas // alto)[:, None] * columnas
             + (np.arange(ancho) * columnas // ancho)[None, :])
    hist = np.bincount((celda * BINS_ORIENTACION + bins).ravel(), weights=magnitud.ravel(),
                       minlength=filas * columnas * BINS_ORIENTACION)
    hist = hist.reshape(filas * columnas, BINS_ORIENTACION)
    hist /= np.linalg.norm(hist, axis=1, keepdims=True) + 1e-6
    vector = hist.ravel()
    return (vector / (np.linalg.norm(vector) + 1e-9)).astype(np.float32)


def tarea_descriptor(tarea: tuple[str, str]) -> tuple[str, np.ndarray | None]:
    cv2.setNumThreads(1)
    raiz, ruta = tarea
    gris = leer_gris(raiz, ruta)
    return ruta, None if gris is None else descriptor_orientaciones(gris)


def puntos_orb(raiz: str, ruta: str):
    gris = leer_gris(raiz, ruta)
    if gris is None:
        return None, None
    gris = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gris)
    return cv2.ORB_create(nfeatures=ORB_PUNTOS).detectAndCompute(gris, None)


def comparar_orb(a, b) -> dict:
    """Coincidencias ORB y transformación de similitud estimada con RANSAC."""
    (ka, da), (kb, db) = a, b
    vacio = {"n_coincidencias": 0, "n_inliers": 0, "frac_inliers": 0.0,
             "escala": np.nan, "rotacion": np.nan, "desplazamiento_px": np.nan}
    if da is None or db is None or len(ka) < 2 or len(kb) < 2:
        return vacio
    pares = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(da, db, k=2)
    buenas = [p[0] for p in pares if len(p) == 2 and p[0].distance < ORB_RATIO * p[1].distance]
    resultado = dict(vacio, n_coincidencias=len(buenas))
    if len(buenas) < 4:
        return resultado
    pa = np.float32([ka[m.queryIdx].pt for m in buenas])
    pb = np.float32([kb[m.trainIdx].pt for m in buenas])
    matriz, inliers = cv2.estimateAffinePartial2D(pa, pb, method=cv2.RANSAC,
                                                 ransacReprojThreshold=RANSAC_UMBRAL_PX)
    if matriz is None:
        return resultado
    centro = np.array([TAMANO_ANALISIS[0] / 2, TAMANO_ANALISIS[1] / 2, 1.0])
    n_inliers = int(inliers.sum())
    resultado.update(
        n_inliers=n_inliers,
        frac_inliers=round(n_inliers / len(buenas), 3),
        escala=round(float(np.hypot(matriz[0, 0], matriz[1, 0])), 4),
        rotacion=round(float(np.degrees(np.arctan2(matriz[1, 0], matriz[0, 0]))), 2),
        desplazamiento_px=round(float(np.linalg.norm(matriz @ centro - centro[:2])), 1),
    )
    return resultado


def tarea_frontera(tarea: tuple[str, list[str], list[str]]) -> dict:
    """Mejor comparación ORB entre las fotos de dos días (todas contra todas)."""
    cv2.setNumThreads(1)
    cv2.setRNGSeed(0)
    raiz, rutas_a, rutas_b = tarea
    puntos_a = [puntos_orb(raiz, r) for r in rutas_a]
    puntos_b = [puntos_orb(raiz, r) for r in rutas_b]
    mejor = None
    for ra, pa in zip(rutas_a, puntos_a):
        for rb, pb in zip(rutas_b, puntos_b):
            m = comparar_orb(pa, pb)
            m.update(foto_antes=ra, foto_despues=rb)
            clave = (m["n_inliers"], m["frac_inliers"])
            if mejor is None or clave > (mejor["n_inliers"], mejor["frac_inliers"]):
                mejor = m
    return mejor


def tarea_momento(tarea: tuple[str, str, str, str]) -> tuple[str, str, str]:
    """Clasifica una foto según a cuál de las dos referencias se parece sin moverse."""
    cv2.setNumThreads(1)
    cv2.setRNGSeed(0)
    raiz, ruta, ref_antes, ref_despues = tarea
    foto = puntos_orb(raiz, ruta)
    return (ruta,
            tipo_transformacion(comparar_orb(puntos_orb(raiz, ref_antes), foto)),
            tipo_transformacion(comparar_orb(puntos_orb(raiz, ref_despues), foto)))


def tipo_transformacion(m: dict) -> str:
    if m["n_inliers"] < MIN_INLIERS_IDENTIDAD:
        return "SIN_COINCIDENCIA"
    rotacion = abs((m["rotacion"] + 180) % 360 - 180)
    escala = abs(m["escala"] - 1)
    if m["n_inliers"] < MIN_INLIERS or m["frac_inliers"] < MIN_FRACCION_INLIERS:
        casi_identidad = (m["desplazamiento_px"] < DESPLAZAMIENTO_IDENTIDAD_PX
                          and rotacion < ROTACION_IDENTIDAD_GRADOS and escala < ESCALA_IDENTIDAD)
        return "IDENTIDAD" if casi_identidad else "SIN_COINCIDENCIA"
    if (rotacion >= ROTACION_MEDIA_VUELTA and escala < ESCALA_SALTO
            and m["desplazamiento_px"] < DESPLAZAMIENTO_CAMBIO_PX):
        return "MEDIA_VUELTA"
    if (rotacion >= ROTACION_CAMBIO_GRADOS or escala >= ESCALA_CAMBIO
            or m["desplazamiento_px"] >= DESPLAZAMIENTO_CAMBIO_PX):
        return "GRANDE"
    if (rotacion >= ROTACION_SALTO_GRADOS or escala >= ESCALA_SALTO
            or m["desplazamiento_px"] >= DESPLAZAMIENTO_SALTO_PX):
        return "SALTO"
    return "IDENTIDAD"


# ============================================================================
# Análisis por día
# ============================================================================

def unitario(v: np.ndarray) -> np.ndarray:
    return v / (np.linalg.norm(v) + 1e-9)


def mediana(vectores: list[np.ndarray]) -> np.ndarray:
    return unitario(np.median(np.vstack(vectores), axis=0))


def distancia(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.linalg.norm(a - b))


def seleccionar_fotos(inventario: pd.DataFrame) -> pd.DataFrame:
    evaluadas = inventario[inventario["estado"].eq("EVALUADA")].copy()
    momento = pd.to_datetime(evaluadas["fecha_hora"])
    evaluadas["dif_mediodia_h"] = (momento.dt.hour + momento.dt.minute / 60
                                   + momento.dt.second / 3600 - HORA_REFERENCIA).abs()
    seleccion = (evaluadas.sort_values(["fecha", "dif_mediodia_h", "fecha_hora"])
                 .groupby("fecha").head(FOTOS_POR_DIA))
    return seleccion.sort_values("fecha_hora").reset_index(drop=True)


def descriptores_diarios(fotos: pd.DataFrame, vectores: dict[str, np.ndarray]):
    """Descriptor del día (promedio sin la foto atípica) y foto representativa."""
    fotos = fotos[fotos["ruta"].map(lambda r: vectores.get(r) is not None)].copy()
    fotos["distancia_dia"] = np.nan
    fotos["foto_atipica"] = False
    por_dia, representativa = {}, {}
    for fecha, grupo in fotos.groupby("fecha"):
        vs = [vectores[r] for r in grupo["ruta"]]
        centro = mediana(vs)
        d = np.array([distancia(v, centro) for v in vs])
        atipica = (d > UMBRAL_FOTO_ATIPICA) if len(vs) >= 3 else np.zeros(len(vs), bool)
        fotos.loc[grupo.index, "distancia_dia"] = d.round(4)
        fotos.loc[grupo.index, "foto_atipica"] = atipica
        usadas = [v for v, a in zip(vs, atipica) if not a]
        por_dia[fecha] = unitario(np.mean(usadas, axis=0))
        representativa[fecha] = grupo["ruta"].iloc[int(np.argmin(d))]
    return fotos, por_dia, representativa


# ============================================================================
# Segmentación en tramos
# ============================================================================

class Segmentador:
    def __init__(self, observados: pd.DataFrame, vectores_dia: dict, fotos_dia: dict,
                 raiz: str, procesos: int):
        self.obs = observados          # índice fecha; columnas nitidez_baja
        self.v = vectores_dia
        self.fotos_dia = fotos_dia     # fecha -> rutas válidas para ORB
        self.raiz = raiz
        self.procesos = procesos
        self.cache_orb: dict[tuple[str, str], dict] = {}

    def orb(self, pares: list[tuple[str, str]]) -> None:
        faltan = [p for p in pares if p not in self.cache_orb]
        if not faltan:
            return
        tareas = [(self.raiz, self.fotos_dia[a], self.fotos_dia[b]) for a, b in faltan]
        with ProcessPoolExecutor(max_workers=self.procesos) as ejecutor:
            for par, res in zip(faltan, ejecutor.map(tarea_frontera, tareas, chunksize=2)):
                self.cache_orb[par] = res

    def ventanas(self, validos: list[str]) -> pd.DataFrame:
        """Distancia de cada día observado a la mediana de los días válidos antes/después."""
        orden = np.array(validos)
        filas = []
        for fecha in self.obs.index:
            antes = orden[orden < fecha][-VENTANA_DIAS:]
            despues = orden[orden > fecha][:VENTANA_DIAS]
            filas.append({
                "fecha": fecha,
                "dist_ventana_antes": distancia(self.v[fecha], mediana([self.v[f] for f in antes])) if len(antes) else np.nan,
                "dist_ventana_despues": distancia(self.v[fecha], mediana([self.v[f] for f in despues])) if len(despues) else np.nan,
            })
        return pd.DataFrame(filas).set_index("fecha")

    def ejecutar(self, forzado: dict[str, bool]) -> dict:
        motivo = pd.Series("VISTA_DE_OBRA", index=self.obs.index, dtype=object)
        motivo[self.obs["nitidez_baja"]] = "NITIDEZ_BAJA"
        for fecha, visible in forzado.items():
            if fecha in motivo.index:
                motivo[fecha] = "VISTA_DE_OBRA" if visible else "MANUAL"

        for _ in range(10):
            # (b) días aislados lejos de ambas ventanas
            for _ in range(5):
                validos = motivo.index[motivo.eq("VISTA_DE_OBRA")].tolist()
                vent = self.ventanas(validos)
                lejos = vent.min(axis=1, skipna=False).fillna(
                    vent.max(axis=1)) > UMBRAL_DIA_ATIPICO
                nuevos = lejos & motivo.eq("VISTA_DE_OBRA") & ~motivo.index.isin(
                    [f for f, v in forzado.items() if v])
                if not nuevos.any():
                    break
                motivo[nuevos] = "DESCRIPTOR_ATIPICO"

            validos = motivo.index[motivo.eq("VISTA_DE_OBRA")].tolist()
            fronteras = self.fronteras(validos)
            tramos = self.cortar(validos, fronteras)

            # (c) tramos cortos lejos de sus dos vecinos
            centros = [mediana([self.v[f] for f in t]) for t in tramos]
            atipicos = []
            for i, t in enumerate(tramos):
                if len(t) >= MIN_DIAS_TRAMO or len(tramos) == 1:
                    continue
                vecinos = [centros[j] for j in (i - 1, i + 1) if 0 <= j < len(tramos)]
                if all(distancia(centros[i], c) > UMBRAL_DIA_ATIPICO for c in vecinos):
                    atipicos += [f for f in t if not forzado.get(f, False)]
            if not atipicos:
                break
            motivo[atipicos] = "TRAMO_ATIPICO"

        return {"motivo": motivo, "ventanas": vent, "fronteras": fronteras,
                "tramos": tramos, "centros": centros}

    def fronteras(self, validos: list[str]) -> pd.DataFrame:
        filas = []
        for j in range(1, len(validos)):
            a, b = validos[j - 1], validos[j]
            antes = [self.v[f] for f in validos[max(0, j - VENTANA_DIAS):j]]
            despues = [self.v[f] for f in validos[j:j + VENTANA_DIAS]]
            filas.append({"fecha_anterior": a, "fecha": b,
                          "dist_consecutiva": round(distancia(self.v[a], self.v[b]), 4),
                          "dist_ventana": round(distancia(mediana(antes), mediana(despues)), 4)})
        tabla = pd.DataFrame(filas, columns=["fecha_anterior", "fecha", "dist_consecutiva", "dist_ventana"])
        if tabla.empty:
            return tabla
        maximo_local = tabla["dist_ventana"].eq(
            tabla["dist_ventana"].rolling(2 * SEPARACION_CANDIDATOS + 1, center=True, min_periods=1).max())
        tabla["candidato_descriptor"] = ((maximo_local & tabla["dist_ventana"].ge(UMBRAL_CAMBIO_VENTANA))
                                         | tabla["dist_consecutiva"].ge(UMBRAL_CAMBIO_CONSECUTIVO))
        pares = list(zip(tabla["fecha_anterior"], tabla["fecha"]))
        self.orb(pares)
        orb = pd.DataFrame([self.cache_orb[p] for p in pares])
        tabla = pd.concat([tabla, orb], axis=1)
        tabla["transformacion"] = [tipo_transformacion(m) for m in orb.to_dict("records")]
        tabla["verificacion"] = "directa"

        # Sin coincidencias (luz, neblina, obra tapando): se compara saltando un día
        # a cada lado. Si alguna de esas comparaciones da la misma vista, no hubo cambio.
        sin = tabla.index[tabla["transformacion"].eq("SIN_COINCIDENCIA")]
        alternativas = {}
        for j in sin:
            pos = j + 1  # posición de 'fecha' en validos
            opciones = []
            if pos - 2 >= 0:
                opciones.append((validos[pos - 2], validos[pos]))
            if pos + 1 < len(validos):
                opciones.append((validos[pos - 1], validos[pos + 1]))
            alternativas[j] = opciones
        self.orb([p for ops in alternativas.values() for p in ops])
        for j, opciones in alternativas.items():
            for par in opciones:
                if tipo_transformacion(self.cache_orb[par]) == "IDENTIDAD":
                    tabla.loc[j, "transformacion"] = "IDENTIDAD"
                    tabla.loc[j, "verificacion"] = f"saltando un dia: {par[0]} vs {par[1]}"
                    break
            else:
                tabla.loc[j, "verificacion"] = "sin coincidencias tampoco saltando un dia"

        tabla["resultado"] = [clasificar_frontera(t, c) for t, c in
                              zip(tabla["transformacion"], tabla["candidato_descriptor"])]
        return tabla

    @staticmethod
    def cortar(validos: list[str], fronteras: pd.DataFrame) -> list[list[str]]:
        if not validos:
            return []
        inicios = set(fronteras.loc[fronteras["resultado"].isin(CORTES), "fecha"]) if len(fronteras) else set()
        tramos = [[validos[0]]]
        for fecha in validos[1:]:
            if fecha in inicios:
                tramos.append([])
            tramos[-1].append(fecha)
        return tramos


def clasificar_frontera(transformacion: str, candidato: bool) -> str:
    if transformacion == "MEDIA_VUELTA":
        return "ROTACION_180"
    if transformacion == "GRANDE":
        return "CAMBIO_CONFIRMADO"
    if transformacion == "SALTO":
        return "SALTO_MENOR"
    if transformacion == "SIN_COINCIDENCIA":
        return "CAMBIO_CONFIRMADO" if candidato else "SIN_VERIFICAR"
    return "DESCARTADO" if candidato else "MISMO_ENCUADRE"


def momento_del_cambio(fila: pd.Series, evaluadas: pd.DataFrame, rep: dict, raiz: str,
                       procesos: int) -> tuple[str, str]:
    """Última foto con el encuadre anterior y primera con el nuevo (ajuste de escalón)."""
    a, b = fila["fecha_anterior"], fila["fecha"]
    fotos = evaluadas[evaluadas["fecha"].isin([a, b])].sort_values("fecha_hora")
    tareas = [(raiz, r, rep[a], rep[b]) for r in fotos["ruta"]]
    with ProcessPoolExecutor(max_workers=procesos) as ejecutor:
        res = {r: (ta, tb) for r, ta, tb in ejecutor.map(tarea_momento, tareas, chunksize=4)}
    etiquetas = []
    for ruta, momento in zip(fotos["ruta"], fotos["fecha_hora"]):
        ta, tb = res[ruta]
        if ta == "IDENTIDAD" and tb != "IDENTIDAD":
            etiquetas.append((momento, 0))
        elif tb == "IDENTIDAD" and ta != "IDENTIDAD":
            etiquetas.append((momento, 1))
    if len(etiquetas) < 4 or not any(e for _, e in etiquetas) or all(e for _, e in etiquetas):
        return "", ""
    marcas = np.array([e for _, e in etiquetas])
    errores = [marcas[:k].sum() + (1 - marcas[k:]).sum() for k in range(1, len(marcas))]
    k = int(np.argmin(errores)) + 1
    return str(etiquetas[k - 1][0]), str(etiquetas[k][0])


# ============================================================================
# Hojas de contacto
# ============================================================================

def abrir_para_mostrar(ruta: Path) -> np.ndarray | None:
    """Píxeles crudos (sin etiqueta EXIF) girados ROTACION_PARA_MOSTRAR grados."""
    imagen = cv2.imdecode(np.fromfile(str(ruta), dtype=np.uint8),
                          cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
    if imagen is not None and ROTACION_PARA_MOSTRAR == 180:
        imagen = cv2.rotate(imagen, cv2.ROTATE_180)
    return imagen


def miniatura(raiz: Path, ruta: str | None, texto: str, color=(255, 255, 255)) -> np.ndarray:
    ancho, alto = MINIATURA
    imagen = abrir_para_mostrar(raiz / ruta) if ruta else None
    if imagen is None:
        imagen = np.full((alto, ancho, 3), 40, np.uint8)
    imagen = cv2.resize(imagen, MINIATURA, interpolation=cv2.INTER_AREA)
    for i, linea in enumerate(texto.split("\n")):
        y = 16 + 16 * i
        cv2.rectangle(imagen, (0, y - 13), (ancho, y + 4), (0, 0, 0), -1)
        cv2.putText(imagen, linea, (4, y), cv2.FONT_HERSHEY_SIMPLEX, 0.42, color, 1, cv2.LINE_AA)
    return imagen


def hoja(miniaturas: list[np.ndarray], titulo: str, separador_en: int | None = None) -> np.ndarray:
    ancho, alto = MINIATURA
    columnas = COLUMNAS_HOJA  # ancho fijo para que el título quepa
    while len(miniaturas) % columnas:
        miniaturas.append(np.full((alto, ancho, 3), 255, np.uint8))
    if separador_en is not None:
        for m in miniaturas[separador_en:separador_en + 1]:
            cv2.rectangle(m, (0, 0), (3, alto), (0, 0, 255), -1)
    filas = [np.hstack(miniaturas[i:i + columnas]) for i in range(0, len(miniaturas), columnas)]
    cuerpo = np.vstack(filas)
    lineas = titulo.split("\n")
    cabecera = np.full((10 + 18 * len(lineas), cuerpo.shape[1], 3), 255, np.uint8)
    for i, linea in enumerate(lineas):
        cv2.putText(cabecera, linea, (6, 18 + 18 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (0, 0, 0), 1, cv2.LINE_AA)
    return np.vstack([cabecera, cuerpo])


def guardar_jpg(ruta: Path, imagen: np.ndarray) -> None:
    ok, datos = cv2.imencode(".jpg", imagen, [cv2.IMWRITE_JPEG_QUALITY, CALIDAD_JPG,
                                              cv2.IMWRITE_JPEG_OPTIMIZE, 1])
    if ok:
        datos.tofile(str(ruta))


# ============================================================================
# Revisión manual
# ============================================================================

def leer_revision(archivo: Path) -> pd.DataFrame:
    """Lee las correcciones a mano. Crea la plantilla vacía si no existe y, si está
    vacía pero le faltan columnas nuevas (ruta, rotacion), reescribe el encabezado."""
    if not archivo.exists():
        pd.DataFrame(columns=COLUMNAS_REVISION).to_csv(archivo, index=False)
    revision = pd.read_csv(archivo, dtype=str).fillna("")
    faltan = set(COLUMNAS_REVISION_OBLIGATORIAS) - set(revision.columns)
    if faltan:
        raise SystemExit(f"{archivo} no tiene las columnas {sorted(faltan)}")
    opcionales = [c for c in COLUMNAS_REVISION if c not in revision.columns]
    for columna in opcionales:
        revision[columna] = ""
    if opcionales and revision.empty:
        revision[COLUMNAS_REVISION].to_csv(archivo, index=False)
    revision = revision.apply(lambda s: s.str.strip())
    sin_fecha = revision["fecha"].eq("") & revision["ruta"].ne("")
    revision.loc[sin_fecha, "fecha"] = revision.loc[sin_fecha, "ruta"].str.extract(r"(\d{8})", expand=False)
    revision["fecha"] = pd.to_datetime(revision["fecha"], format="mixed").dt.strftime("%Y-%m-%d")
    return revision


def a_booleano(texto: str) -> bool | None:
    t = str(texto).strip().lower()
    if t in {"true", "verdadero", "si", "sí", "1"}:
        return True
    if t in {"false", "falso", "no", "0"}:
        return False
    return None


# ============================================================================
# Principal
# ============================================================================

def main() -> None:
    base = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--raw", type=Path, default=base / "data" / "raw_data")
    parser.add_argument("--datos", type=Path, default=base / "data" / "processed_data")
    parser.add_argument("--reportes", type=Path, default=base / "reports" / "revision_tramos")
    parser.add_argument("--procesos", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    args = parser.parse_args()
    inicio = time.time()
    raiz = str(args.raw)

    inventario = pd.read_csv(args.datos / "inventario_fotos.csv")
    resumen = pd.read_csv(args.datos / "resumen_diario.csv")
    evaluadas = inventario[inventario["estado"].eq("EVALUADA")].copy()
    seleccion = seleccionar_fotos(inventario)
    print(f"Fotos EVALUADA: {len(evaluadas):,} | analizadas (≤{FOTOS_POR_DIA}/día): "
          f"{len(seleccion):,} en {seleccion['fecha'].nunique()} días | procesos: {args.procesos}")

    # 1-2. Descriptores
    with ProcessPoolExecutor(max_workers=args.procesos) as ejecutor:
        vectores = dict(ejecutor.map(tarea_descriptor, [(raiz, r) for r in seleccion["ruta"]], chunksize=8))
    fotos, vectores_dia, representativa = descriptores_diarios(seleccion, vectores)
    print(f"Descriptores calculados ({time.time() - inicio:.0f} s). "
          f"Fotos atípicas dentro de su día: {int(fotos['foto_atipica'].sum())}")

    # 3a. Nitidez
    nitidez = evaluadas.groupby("fecha")["nitidez"].median()
    referencia_nitidez = float(nitidez.median())
    umbral_nitidez = FRACCION_NITIDEZ_MINIMA * referencia_nitidez
    observados = pd.DataFrame(index=sorted(vectores_dia))
    observados["nitidez_mediana"] = nitidez.reindex(observados.index).round(2)
    observados["nitidez_baja"] = observados["nitidez_mediana"] < umbral_nitidez
    fotos_dia = {f: g.loc[~g["foto_atipica"], "ruta"].tolist() for f, g in fotos.groupby("fecha")}

    # 3-5. Segmentación automática y con revisión manual
    archivo_revision = args.datos / "revision_manual.csv"
    revision = leer_revision(archivo_revision)
    # Aquí solo cuentan las filas por día con obra_visible o tramo_id (o solo una nota);
    # las de rotación son para 03_orientacion.py.
    revision = revision[revision["ruta"].eq("") & (
        revision["obra_visible"].ne("") | revision["tramo_id"].ne("")
        | (revision["nota"].ne("") & revision["rotacion"].eq("")))].reset_index(drop=True)
    forzado = {f: b for f, b in zip(revision["fecha"], revision["obra_visible"].map(a_booleano))
               if b is not None}
    seg = Segmentador(observados, vectores_dia, fotos_dia, raiz, args.procesos)
    auto = seg.ejecutar({})
    final = seg.ejecutar(forzado) if forzado else auto
    print(f"Segmentación lista ({time.time() - inicio:.0f} s). Fronteras verificadas con ORB: "
          f"{len(seg.cache_orb)}")

    tramos, centros, fronteras = final["tramos"], final["centros"], final["fronteras"]

    # Orientación: el último tramo está rotado; se invierte en cada cambio de ~180°.
    rotar = [ULTIMO_TRAMO_ROTADO_180] * len(tramos)
    por_inicio = fronteras.set_index("fecha") if len(fronteras) else pd.DataFrame()
    for i in range(len(tramos) - 2, -1, -1):
        media_vuelta = por_inicio.loc[tramos[i + 1][0], "resultado"] == "ROTACION_180"
        rotar[i] = (not rotar[i + 1]) if media_vuelta else rotar[i + 1]

    # Momento de cada cambio
    fronteras["ultima_foto_antes"] = ""
    fronteras["primera_foto_despues"] = ""
    for idx in fronteras.index[fronteras["resultado"].isin(CORTES)]:
        antes, despues = momento_del_cambio(fronteras.loc[idx], evaluadas, representativa,
                                            raiz, args.procesos)
        fronteras.loc[idx, ["ultima_foto_antes", "primera_foto_despues"]] = [antes, despues]

    # Deriva: cada semana del tramo contra su foto de referencia (medoide del tramo)
    medoides, semanas = [], []
    for t, centro in zip(tramos, centros):
        dists = {f: distancia(vectores_dia[f], centro) for f in t}
        medoides.append(min(dists, key=dists.get))
        semanas.append(pd.Series(t, index=pd.to_datetime(t)).groupby(
            lambda d: d - pd.Timedelta(days=d.day_of_week)).first().tolist())
    tareas = [(raiz, [representativa[m]], [representativa[f]])
              for m, sem in zip(medoides, semanas) for f in sem]
    with ProcessPoolExecutor(max_workers=args.procesos) as ejecutor:
        deriva_orb = iter(ejecutor.map(tarea_frontera, tareas, chunksize=2))
        deriva = [{f: next(deriva_orb) for f in sem} for sem in semanas]

    def texto_deriva(m: dict) -> str:
        tipo = tipo_transformacion(m)
        return f"{m['desplazamiento_px']:.0f} px" if tipo in {"IDENTIDAD", "SALTO"} else "sin coincidencia"

    # Tabla de tramos
    filas_tramos = []
    for i, t in enumerate(tramos, 1):
        centro = centros[i - 1]
        dists = {f: distancia(vectores_dia[f], centro) for f in t}
        medoide = medoides[i - 1]
        medibles = [m["desplazamiento_px"] for m in deriva[i - 1].values()
                    if tipo_transformacion(m) in {"IDENTIDAD", "SALTO"}]
        if i == 1:
            tipo, momento = "INICIO_DEL_REGISTRO", ""
        else:
            fr = fronteras.set_index("fecha").loc[t[0]]
            tipo, momento = fr["resultado"], fr["primera_foto_despues"]
        calendario = pd.date_range(t[0], t[-1], freq="D").strftime("%Y-%m-%d")
        filas_tramos.append({
            "tramo_id": i, "fecha_inicio": t[0], "fecha_fin": t[-1],
            "dias_calendario": len(calendario), "dias_observados": len(t),
            "tipo_inicio": tipo, "momento_inicio": momento,
            "foto_referencia": representativa[medoide], "fecha_referencia": medoide,
            "distancia_media": round(float(np.mean(list(dists.values()))), 4),
            "distancia_max": round(float(max(dists.values())), 4),
            "deriva_max_px": round(max(medibles), 1) if medibles else np.nan,
            "semanas_sin_coincidencia": len(deriva[i - 1]) - len(medibles),
            "rotar_180_para_ver": rotar[i - 1],
        })
    tabla_tramos = pd.DataFrame(filas_tramos)
    # encuadre_id: misma vista física. Una ROTACION_180 no mueve la cámara (en estos
    # datos es el cambio de la etiqueta EXIF del 2025-10-09), así que comparte encuadre;
    # cualquier otro corte (CAMBIO_CONFIRMADO, SALTO_MENOR) abre un encuadre nuevo.
    # El comparador antes/después debe agrupar por encuadre_id, no por tramo_id.
    tabla_tramos.insert(1, "encuadre_id",
                        (~tabla_tramos["tipo_inicio"].eq("ROTACION_180")).cumsum().astype(int))

    def tabla_dias(resultado: dict, tramos_tabla: list[dict]) -> pd.DataFrame:
        dias = resumen[["fecha", "dia_semana", "estado_dia", "fotos_total", "fotos_utiles"]].copy()
        dias["fotos_analizadas"] = dias["fecha"].map(fotos.groupby("fecha").size()).fillna(0).astype(int)
        dias["nitidez_mediana"] = dias["fecha"].map(observados["nitidez_mediana"])
        dias["tramo_id"] = [next((f["tramo_id"] for f in tramos_tabla
                                  if f["fecha_inicio"] <= d <= f["fecha_fin"]), np.nan)
                            for d in dias["fecha"]]
        centro_de = {f["tramo_id"]: c for f, c in zip(tramos_tabla, resultado["centros"])}
        dias["distancia_tramo"] = [round(distancia(vectores_dia[d], centro_de[t]), 4)
                                   if d in vectores_dia and t in centro_de else np.nan
                                   for d, t in zip(dias["fecha"], dias["tramo_id"])]
        vent = resultado["ventanas"].round(4)
        dias = dias.join(vent, on="fecha")
        motivo = dias["fecha"].map(resultado["motivo"])
        motivo = motivo.where(motivo.notna(), np.where(dias["fotos_total"].eq(0), "SIN_FOTOS", "SIN_FOTOS_UTILES"))
        dias["motivo"] = motivo
        dias["obra_visible"] = motivo.eq("VISTA_DE_OBRA")
        dias["estado_dia_revisado"] = np.select(
            [dias["fotos_total"].eq(0), dias["fotos_utiles"].eq(0) | dias["fotos_analizadas"].eq(0),
             ~dias["obra_visible"]],
            ["SIN_FOTOS", "SIN_FOTOS_UTILES", "SIN_VISTA_DE_OBRA"], default="CON_EVIDENCIA")
        dias["foto_representativa"] = dias["fecha"].map(representativa)
        return dias

    dias = tabla_dias(final, filas_tramos)
    dias["tramo_id"] = dias["tramo_id"].astype("Int64")
    dias["ajuste_manual"] = ""

    # Registro de lo que cambió la revisión manual
    cambios_manuales = []
    if len(revision):
        if forzado:
            filas_auto = []
            for i, t in enumerate(auto["tramos"], 1):
                filas_auto.append({"tramo_id": i, "fecha_inicio": t[0], "fecha_fin": t[-1]})
            dias_auto = tabla_dias(auto, filas_auto).set_index("fecha")
        else:
            dias_auto = dias.set_index("fecha")
        for fila in revision.itertuples():
            if fila.fecha not in set(dias["fecha"]):
                cambios_manuales.append(f"{fila.fecha}: fecha fuera del periodo, se ignora")
                continue
            idx = dias.index[dias["fecha"].eq(fila.fecha)][0]
            partes = []
            antes = dias_auto.loc[fila.fecha]
            if bool(antes["obra_visible"]) != bool(dias.loc[idx, "obra_visible"]):
                partes.append(f"obra_visible {bool(antes['obra_visible'])}->{bool(dias.loc[idx, 'obra_visible'])}")
            tramo_manual = str(fila.tramo_id).strip()
            if tramo_manual:
                nuevo = int(float(tramo_manual))
                if dias.loc[idx, "tramo_id"] is pd.NA or dias.loc[idx, "tramo_id"] != nuevo:
                    partes.append(f"tramo_id {dias.loc[idx, 'tramo_id']}->{nuevo}")
                    dias.loc[idx, "tramo_id"] = nuevo
            elif not pd.isna(antes["tramo_id"]) and antes["tramo_id"] != dias.loc[idx, "tramo_id"]:
                partes.append(f"tramo_id {antes['tramo_id']}->{dias.loc[idx, 'tramo_id']}")
            texto = "; ".join(partes) if partes else "sin cambios respecto al automático"
            dias.loc[idx, "ajuste_manual"] = texto + (f" ({fila.nota})" if fila.nota else "")
            cambios_manuales.append(f"{fila.fecha}: {dias.loc[idx, 'ajuste_manual']}")

    # Tabla de fotos analizadas
    visible_dia = dias.set_index("fecha")["obra_visible"]
    fotos = fotos.merge(evaluadas[["ruta"]], on="ruta")
    fotos["obra_visible"] = (fotos["fecha"].map(visible_dia).fillna(False).astype(bool)
                             & ~fotos["foto_atipica"] & fotos["nitidez"].ge(umbral_nitidez))
    fotos["es_representativa"] = fotos["ruta"].isin(set(representativa.values()))
    fotos["tramo_id"] = fotos["fecha"].map(dias.set_index("fecha")["tramo_id"])
    tabla_fotos = fotos[["ruta", "fecha", "fecha_hora", "nitidez", "distancia_dia", "foto_atipica",
                         "es_representativa", "obra_visible", "tramo_id"]]

    # Guardar tablas
    columnas_dias = ["fecha", "dia_semana", "estado_dia", "estado_dia_revisado", "obra_visible",
                     "motivo", "tramo_id", "distancia_tramo", "dist_ventana_antes",
                     "dist_ventana_despues", "fotos_total", "fotos_utiles", "fotos_analizadas",
                     "nitidez_mediana", "foto_representativa", "ajuste_manual"]
    dias[columnas_dias].to_csv(args.datos / "dias_encuadre.csv", index=False)
    tabla_tramos.to_csv(args.datos / "tramos_encuadre.csv", index=False)
    columnas_fronteras = ["fecha_anterior", "fecha", "resultado", "candidato_descriptor",
                          "dist_consecutiva", "dist_ventana", "n_coincidencias", "n_inliers",
                          "frac_inliers", "escala", "rotacion", "desplazamiento_px",
                          "transformacion", "verificacion", "ultima_foto_antes", "primera_foto_despues",
                          "foto_antes", "foto_despues"]
    fronteras[columnas_fronteras].to_csv(args.datos / "cambios_encuadre.csv", index=False)
    tabla_fotos.to_csv(args.datos / "fotos_encuadre.csv", index=False)

    # Hojas de contacto
    args.reportes.mkdir(parents=True, exist_ok=True)
    for viejo in list(args.reportes.glob("tramo_*.jpg")) + list(args.reportes.glob("cambio_*.jpg")) \
            + list(args.reportes.glob("sin_vista_de_obra*.jpg")):
        viejo.unlink()
    for fila in filas_tramos:
        i = fila["tramo_id"] - 1
        mins = [miniatura(args.raw, representativa[f],
                          f"{f}{'  REFERENCIA' if f == medoides[i] else ''}\n"
                          f"vs referencia: {texto_deriva(deriva[i][f])}")
                for f in semanas[i]]
        titulo = (f"Tramo {fila['tramo_id']}: {fila['fecha_inicio']} a {fila['fecha_fin']} | "
                  f"{fila['dias_observados']} dias observados | inicio: {fila['tipo_inicio']} | "
                  f"deriva max {fila['deriva_max_px']} px\n"
                  f"Una foto por semana (la mas cercana a mediodia) | referencia {medoides[i]} | "
                  f"pixeles crudos + {ROTACION_PARA_MOSTRAR} grados")
        guardar_jpg(args.reportes / f"tramo_{fila['tramo_id']:02d}_{fila['fecha_inicio']}_{fila['fecha_fin']}.jpg",
                    hoja(mins, titulo))

    validos = final["motivo"].index[final["motivo"].eq("VISTA_DE_OBRA")].tolist()
    revisar = fronteras[fronteras["candidato_descriptor"] | fronteras["resultado"].isin(CORTES | {"SIN_VERIFICAR"})]
    for fr in revisar.itertuples():
        j = validos.index(fr.fecha)
        antes = validos[max(0, j - DIAS_CONTEXTO_CAMBIO):j]
        despues = validos[j:j + DIAS_CONTEXTO_CAMBIO]
        mins = [miniatura(args.raw, representativa[f], f) for f in antes + despues]
        momento = f" | cambio entre {fr.ultima_foto_antes} y {fr.primera_foto_despues}" if fr.primera_foto_despues else ""
        titulo = (f"{fr.fecha}: {fr.resultado} | ventana {fr.dist_ventana:.2f} consecutiva {fr.dist_consecutiva:.2f}"
                  f"{momento}\nORB {fr.fecha_anterior} vs {fr.fecha}: {fr.n_coincidencias} coincidencias, "
                  f"{fr.n_inliers} inliers ({fr.frac_inliers:.0%}), escala {fr.escala}, "
                  f"rotacion {fr.rotacion}, desplazamiento {fr.desplazamiento_px} px")
        guardar_jpg(args.reportes / f"cambio_{fr.fecha}_{fr.resultado}.jpg",
                    hoja(mins, titulo, separador_en=len(antes)))

    sin_vista = dias[dias["estado_dia_revisado"].eq("SIN_VISTA_DE_OBRA")]
    if len(sin_vista):
        mins = [miniatura(args.raw, r, f"{f}\n{m}")
                for f, r, m in zip(sin_vista["fecha"], sin_vista["foto_representativa"], sin_vista["motivo"])]
        guardar_jpg(args.reportes / "sin_vista_de_obra.jpg",
                    hoja(mins, "Dias con fotos utiles que no muestran la obra (foto representativa del dia)"))

    # Resumen
    pd.set_option("display.width", 200)
    print("\nRESUMEN")
    print(f"Umbral de nitidez: {umbral_nitidez:,.0f} ({FRACCION_NITIDEZ_MINIMA} x mediana {referencia_nitidez:,.0f})")
    print(f"\nTramos de encuadre fijo: {len(tabla_tramos)}")
    print(tabla_tramos[["tramo_id", "fecha_inicio", "fecha_fin", "dias_observados", "tipo_inicio",
                        "momento_inicio", "deriva_max_px", "rotar_180_para_ver"]].to_string(index=False))
    cortes = fronteras[fronteras["resultado"].isin(CORTES | {"SIN_VERIFICAR"}) | fronteras["candidato_descriptor"]]
    print("\nFronteras candidatas o con movimiento de cámara:")
    print(cortes[["fecha_anterior", "fecha", "resultado", "dist_ventana", "dist_consecutiva",
                  "n_coincidencias", "n_inliers", "frac_inliers", "escala", "rotacion",
                  "desplazamiento_px"]].to_string(index=False))
    print(f"\nDías SIN_VISTA_DE_OBRA: {len(sin_vista)}")
    print(sin_vista[["fecha", "motivo", "fotos_utiles", "nitidez_mediana", "dist_ventana_antes",
                     "dist_ventana_despues"]].to_string(index=False))
    print("\nEstado del día (original -> revisado):")
    print(pd.crosstab(dias["estado_dia"], dias["estado_dia_revisado"]).to_string())
    if cambios_manuales:
        print("\nRevisión manual aplicada:")
        print("\n".join(f"  {c}" for c in cambios_manuales))
    else:
        print(f"\nRevisión manual: sin filas en {archivo_revision.name}")
    print(f"\nGuardado en {args.datos} y {args.reportes} ({time.time() - inicio:.0f} s)")


if __name__ == "__main__":
    main()
