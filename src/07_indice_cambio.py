"""Índice de cambio visual entre días consecutivos con evidencia.

Para cada día con evidencia compara su imagen con la del día con evidencia anterior dentro de
la misma vista de la cámara y mide qué parte de la escena cambió. Se corre localmente, con
data/raw_data, después de 06_fotos_app.py (usa app/datos/dias.csv, app/datos/hitos.csv y
data/processed_data/alineacion_corrimientos.csv). Escribe:

  app/datos/indice_cambio.csv     un día con evidencia por fila: fecha, día anterior con el que
                                  se compara, días entre ambos, fotos combinadas, método de
                                  registro, índice (% de la zona analizada que cambió) y pico
  app/datos/alineacion_dia.csv    transformación de cada día al marco del primer día de su
                                  vista (m00..m12; la app la usa para alinear el comparador y
                                  estabilizar el time-lapse)
  reports/indice_cambio/          hoja con los 12 días de mayor índice (picos.jpg), zona
                                  analizada y diferencia típica por vista, registro_diario.csv

Método (umbrales al inicio del archivo):

1. Imagen del día. Mediana, píxel a píxel, de hasta FOTOS_POR_DIA fotos utilizables tomadas a
   menos de VENTANA_MIN minutos de la foto del día (incluida ella). Un vehículo o una persona
   que pasa aparece en una o dos fotos y la mediana lo borra; lo que permanece (la obra, la
   maquinaria estacionada) queda. No borra vehículos detenidos en una presa.
2. Registro. La cámara no está fija dentro de una vista: además del corrimiento del 16-17 de
   enero que mide 06, se desplaza unos píxeles casi todos los días (hasta ~75 px y 2° entre
   octubre y febrero). Cada día se registra contra el día anterior bien registrado, primero por
   puntos (ORB + RANSAC, como 02 y 06) y, si no alcanza, por intensidad (ECC); la transformación
   se encadena hasta el primer día de la vista. Si ninguno de los dos es confiable, se usa el
   corrimiento de 06 como aproximación, el día empieza un tramo nuevo y el par queda sin índice.
   El corrimiento del 16-17 de enero medido así coincide con el de 06 (diferencia < 2 px).
3. Diferencia de estructura, no de brillo. En escala de grises reducida a ANCHO_ANALISIS px se
   calcula, en ventanas gaussianas de SIGMA_VENTANA px, el término de contraste y estructura
   del índice SSIM: (2·cov + C) / (var1 + var2 + C). 1 menos ese valor es la diferencia local
   (0 = misma estructura). Un día nublado o soleado cambia el brillo pero poco la estructura, y
   con C alto el ruido de las zonas lisas (asfalto, cielo despejado) no cuenta.
4. Lo que no es obra. Para cada píxel se toma su diferencia típica (mediana de todos los pares
   de la vista). Se excluye el (100 − PERCENTIL_ZONA) % de píxeles que más cambia siempre: hojas
   del árbol y vegetación del primer plano movidas por el viento, nubes. En el resto, un píxel
   cuenta como cambio si su diferencia es al menos FACTOR_TIPICO veces su típica y mayor que
   DIFERENCIA_MINIMA, lo que atenúa además el tráfico habitual de la carretera.
   No se usa una máscara fija del cielo: la grúa y la perforadora de noviembre (hitos) se
   recortan contra el cielo y una máscara las ocultaría.
5. Índice = porcentaje de la zona analizada que cuenta como cambio. Un día es «pico» si su
   índice está en el 10 % más alto de su vista (PERCENTIL_PICO).

Validación (se imprime y queda en la nota metodológica): un hito coincide con un pico si
algún día con evidencia entre su fecha_inicio (excluida) y su fecha_fin (incluida) es pico. Se
informa también cuántas coincidencias se esperarían por azar con ventanas del mismo largo. Los
parámetros se ajustaron revisando a ojo los picos falsos (desalineos, luz, vegetación) con los
mismos hitos, así que la validación es optimista.

Uso:
  python src/07_indice_cambio.py
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

_spec = importlib.util.spec_from_file_location("fotos_utilizables", Path(__file__).with_name("04_fotos_utilizables.py"))
fu = importlib.util.module_from_spec(_spec)
sys.modules["fotos_utilizables"] = fu
_spec.loader.exec_module(fu)

FOTOS_POR_DIA = 5          # fotos que se combinan (mediana) para la imagen del día
VENTANA_MIN = 60           # minutos alrededor de la foto del día
ANCHO_APP = 960            # tamaño de las fotos de la app, en el que 06 mide la alineación
ANCHO_ANALISIS = 320       # ancho de trabajo (alto proporcional, 256 px)
SIGMA_VENTANA = 3.0        # ventana gaussiana del término de estructura (px de análisis)
C_ESTRUCTURA = (0.08 * 255) ** 2  # alto: en zonas lisas (asfalto, cielo) el ruido no cuenta
FACTOR_TIPICO = 2.5        # diferencia ≥ FACTOR_TIPICO × típica del píxel
DIFERENCIA_MINIMA = 0.25   # y además ≥ este valor (escala 0-1)
PERCENTIL_ZONA = 70        # se excluye el 30 % de píxeles que más cambia siempre (vegetación, árbol)
BORDE_PX = 8               # borde excluido (px de análisis)
PERCENTIL_PICO = 90        # pico: índice ≥ percentil 90 de su vista (10 % de días más altos)
ORB_PUNTOS, ORB_RATIO, RANSAC_UMBRAL_PX = 5000, 0.75, 3.0  # registro, mismos valores que 06
MIN_INLIERS = 20           # con menos coincidencias consistentes el registro por puntos no se acepta
ANCHO_ECC = 480            # registro por intensidad (ECC) si el de puntos falla
ECC_MIN_CORRELACION = 0.6  # con menos, ECC converge a alineaciones visiblemente erradas
ECC_MAX_DESPLAZAMIENTO_PX = 40  # entre dos días con evidencia, en px de ANCHO_APP


def imagen_del_dia(raw: Path, fotos_dia: pd.DataFrame, foto_del_dia: str) -> tuple[np.ndarray | None, int]:
    """Mediana de las fotos utilizables más cercanas a la foto del día, a ANCHO_APP px."""
    centro = pd.Timestamp(fotos_dia.loc[fotos_dia["ruta"].eq(foto_del_dia), "fecha_hora"].iloc[0])
    cerca = fotos_dia.assign(dist=(pd.to_datetime(fotos_dia["fecha_hora"]) - centro).abs())
    cerca = cerca[cerca["dist"] <= pd.Timedelta(minutes=VENTANA_MIN)].nsmallest(FOTOS_POR_DIA, "dist")
    imagenes = []
    for f in cerca.itertuples():
        img = fu.abrir_para_mostrar(str(raw), f.ruta, int(f.rotacion_desde_crudo))
        if img is None:
            continue
        alto, ancho = img.shape[:2]
        imagenes.append(cv2.resize(img, (ANCHO_APP, round(alto * ANCHO_APP / ancho)), interpolation=cv2.INTER_AREA))
    if not imagenes:
        return None, 0
    return np.median(np.stack(imagenes), axis=0).astype(np.uint8), len(imagenes)


def registrar(ref: tuple, img: np.ndarray) -> tuple[np.ndarray | None, int]:
    """Similitud 3x3 que lleva puntos de la referencia a `img` (ORB + RANSAC, como 02 y 06)."""
    kr, dr = ref
    gris = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    ki, di = cv2.ORB_create(nfeatures=ORB_PUNTOS).detectAndCompute(gris, None)
    if dr is None or di is None:
        return None, 0
    pares = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(dr, di, k=2)
    buenas = [p[0] for p in pares if len(p) == 2 and p[0].distance < ORB_RATIO * p[1].distance]
    if len(buenas) < 4:
        return None, 0
    pr = np.float32([kr[m.queryIdx].pt for m in buenas])
    pi = np.float32([ki[m.trainIdx].pt for m in buenas])
    cv2.setRNGSeed(0)
    matriz, inliers = cv2.estimateAffinePartial2D(pr, pi, method=cv2.RANSAC, ransacReprojThreshold=RANSAC_UMBRAL_PX)
    n = 0 if inliers is None else int(inliers.sum())
    if matriz is None or n < MIN_INLIERS:
        return None, n
    return np.vstack([matriz, [0, 0, 1]]), n


def gris_para_ecc(img: np.ndarray) -> np.ndarray:
    """Gris suavizado a ANCHO_ECC px para el registro por intensidad."""
    alto, ancho = img.shape[:2]
    gris = cv2.cvtColor(cv2.resize(img, (ANCHO_ECC, round(alto * ANCHO_ECC / ancho)), interpolation=cv2.INTER_AREA),
                        cv2.COLOR_BGR2GRAY)
    return cv2.GaussianBlur(cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gris), (0, 0), 1.5).astype(np.float32)


def registrar_ecc(anterior: np.ndarray, actual: np.ndarray) -> tuple[np.ndarray | None, float | None]:
    """Euclídea 3x3 (en px de ANCHO_APP) que lleva puntos del día anterior al actual, por ECC.
    None si no converge, si la correlación es baja o si el movimiento es implausible."""
    warp = np.eye(2, 3, dtype=np.float32)
    try:
        cc, warp = cv2.findTransformECC(anterior, actual, warp, cv2.MOTION_EUCLIDEAN,
                                        (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-6), None, 5)
    except cv2.error:
        return None, None
    escala = ANCHO_APP / ANCHO_ECC
    matriz = np.vstack([warp.astype(float), [0, 0, 1]])
    matriz[:2, 2] *= escala
    if cc < ECC_MIN_CORRELACION or np.hypot(matriz[0, 2], matriz[1, 2]) > ECC_MAX_DESPLAZAMIENTO_PX:
        return None, round(float(cc), 3)
    return matriz, round(float(cc), 3)


def puntos_imagen(img: np.ndarray) -> tuple:
    gris = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    return cv2.ORB_create(nfeatures=ORB_PUNTOS).detectAndCompute(gris, None)


def transformacion_acumulada(alineacion: pd.DataFrame, vista: int, inicio: pd.Timestamp, fecha: pd.Timestamp) -> np.ndarray:
    """Matriz 3x3 que lleva puntos del marco de `inicio` al de `fecha` (corrimientos entre ambas)."""
    total = np.eye(3)
    tramo = alineacion[alineacion["vista"].eq(vista) & (alineacion["fecha"] > inicio) & (alineacion["fecha"] <= fecha)]
    for c in tramo.sort_values("fecha").itertuples():
        if not c.alinear:
            raise ValueError(f"El corrimiento del {c.fecha.date()} no se pudo medir en 06; no se puede alinear")
        total = np.array([[c.m00, c.m01, c.m02], [c.m10, c.m11, c.m12], [0, 0, 1]]) @ total
    return total


def preparar(img: np.ndarray, total: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Lleva la imagen al marco de referencia de la vista y la reduce; devuelve gris, zona válida
    e imagen en color alineada (para la hoja de revisión)."""
    alto, ancho = img.shape[:2]
    valida = np.full((alto, ancho), 255, np.uint8)
    if not np.allclose(total, np.eye(3)):
        # dst(x) = img(total · x): x en el marco de referencia, total lo lleva al marco del día
        img = cv2.warpAffine(img, total[:2], (ancho, alto), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP)
        valida = cv2.warpAffine(valida, total[:2], (ancho, alto), flags=cv2.INTER_NEAREST | cv2.WARP_INVERSE_MAP)
    tamano = (ANCHO_ANALISIS, round(alto * ANCHO_ANALISIS / ancho))
    gris = cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), tamano, interpolation=cv2.INTER_AREA).astype(np.float32)
    valida = cv2.resize(valida, tamano, interpolation=cv2.INTER_NEAREST) > 0
    return gris, valida, cv2.resize(img, (400, 320), interpolation=cv2.INTER_AREA)


def diferencia_estructura(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """1 − término de contraste y estructura de SSIM, por píxel (0 = misma estructura)."""
    g = lambda x: cv2.GaussianBlur(x, (0, 0), SIGMA_VENTANA)
    ma, mb = g(a), g(b)
    va = np.maximum(g(a * a) - ma * ma, 0)
    vb = np.maximum(g(b * b) - mb * mb, 0)
    cov = g(a * b) - ma * mb
    cs = (2 * cov + C_ESTRUCTURA) / (va + vb + C_ESTRUCTURA)
    return np.clip(1 - cs, 0, 2) / 2  # 0-1


def hoja_picos(destino: Path, filas: list[dict], imagenes: dict, mapas: dict) -> None:
    """Hoja de revisión: por cada día de mayor índice, imagen anterior, del día y zonas de cambio."""
    celdas = []
    for f in filas:
        ant, act = imagenes[f["fecha_anterior"]], imagenes[f["fecha"]]
        mapa = cv2.resize(mapas[f["fecha"]].astype(np.uint8) * 255, (act.shape[1], act.shape[0]), interpolation=cv2.INTER_NEAREST)
        rojo = act.copy()
        rojo[mapa > 0] = (0.45 * rojo[mapa > 0] + 0.55 * np.array([0, 60, 230])).astype(np.uint8)
        fila = np.hstack([cv2.resize(x, (400, 320)) for x in (ant, act, rojo)])
        cv2.putText(fila, f"{f['fecha_anterior']} -> {f['fecha']}  indice {f['indice']:.1f} %  ({f['dias_entre']} d)",
                    (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
        celdas.append(fila)
    if celdas:
        destino.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(destino), np.vstack(celdas), [cv2.IMWRITE_JPEG_QUALITY, 80])


def validar(indice: pd.DataFrame, hitos: pd.DataFrame) -> pd.DataFrame:
    """Por hito: días con evidencia en su ventana, índice máximo y si coincide con un pico."""
    filas = []
    for h in hitos.itertuples():
        ventana = indice[(indice["fecha"] > h.fecha_inicio) & (indice["fecha"] <= h.fecha_fin) & indice["indice"].notna()]
        filas.append({"titulo": h.titulo, "fecha_inicio": h.fecha_inicio.date(), "fecha_fin": h.fecha_fin.date(),
                      "dias_en_ventana": len(ventana),
                      "indice_max": round(float(ventana["indice"].max()), 2) if len(ventana) else None,
                      "coincide": bool(ventana["pico"].any()) if len(ventana) else False})
    return pd.DataFrame(filas)


def main() -> None:
    base = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--raw", type=Path, default=base / "data" / "raw_data")
    parser.add_argument("--datos", type=Path, default=base / "data" / "processed_data")
    parser.add_argument("--app", type=Path, default=base / "app")
    parser.add_argument("--reportes", type=Path, default=base / "reports" / "indice_cambio")
    args = parser.parse_args()
    args.reportes.mkdir(parents=True, exist_ok=True)

    dias = pd.read_csv(args.app / "datos" / "dias.csv", parse_dates=["fecha"])
    alineacion = pd.read_csv(args.datos / "alineacion_corrimientos.csv", parse_dates=["fecha"])
    hitos = pd.read_csv(args.app / "datos" / "hitos.csv", parse_dates=["fecha_inicio", "fecha_fin"])
    resumen = pd.read_csv(args.datos / "resumen_diario_final.csv", usecols=["fecha", "foto_del_dia"], parse_dates=["fecha"])
    fotos = pd.read_csv(args.datos / "fotos_utilizables.csv",
                        usecols=["ruta", "fecha", "fecha_hora", "utilizable", "rotacion_desde_crudo"])
    fotos = fotos[fotos["utilizable"]]
    por_fecha = dict(tuple(fotos.groupby("fecha")))

    con = dias[dias["estado"].eq("hay foto útil")].merge(resumen, on="fecha")
    con["vista"] = con["vista"].astype(int)

    # 1-2. Imagen del día, alineada al marco del primer día de su vista
    grises, validas, color, n_fotos, registro = {}, {}, {}, {}, {}
    for v, g in con.groupby("vista"):
        inicio = g["fecha"].min()
        previo = None
        for d in g.itertuples():
            clave = d.fecha.strftime("%Y-%m-%d")
            img, n = imagen_del_dia(args.raw, por_fecha[clave], d.foto_del_dia)
            if img is None:
                print(f"AVISO: no se pudo abrir ninguna foto del {clave}")
                continue
            puntos, gris_ecc = puntos_imagen(img), gris_para_ecc(img)
            if previo is None:  # primer día de la vista: es la referencia
                total, calidad, metodo = np.eye(3), None, "referencia"
            else:
                # Registro contra el último día bien registrado (días cercanos se parecen más que
                # días lejanos): primero por puntos (ORB), si no alcanza por intensidad (ECC).
                relativo, calidad = registrar(previo["puntos"], img)
                metodo = "ORB"
                if relativo is None:
                    relativo, calidad = registrar_ecc(previo["gris_ecc"], gris_ecc)
                    metodo = "ECC"
                if relativo is not None:
                    total = relativo @ previo["matriz"]
                else:
                    # Sin registro confiable: se usan los corrimientos de 06 como aproximación y el
                    # día empieza un tramo nuevo (los siguientes se registran contra él). El par
                    # anterior-actual queda sin índice: el desalineo contaría como cambio.
                    total = transformacion_acumulada(alineacion, v, previo["fecha"], d.fecha) @ previo["matriz"]
                    metodo = "sin registro"
            previo = {"puntos": puntos, "gris_ecc": gris_ecc, "matriz": total, "fecha": d.fecha}
            registro[clave] = {"vista": v, "matriz": total, "calidad": calidad, "metodo": metodo}
            grises[clave], validas[clave], color[clave] = preparar(img, total)
            n_fotos[clave] = n
        print(f"Vista {v}: {len(g)} días con evidencia")

    reg = pd.DataFrame([{"fecha": k, **{x: r[x] for x in ("vista", "calidad", "metodo")},
                         **{n: round(float(r["matriz"].flat[i]), 6) for n, i in
                            zip(["m00", "m01", "m02", "m10", "m11", "m12"], [0, 1, 2, 3, 4, 5])},
                         "desplazamiento_px": float(np.hypot(r["matriz"][0, 2], r["matriz"][1, 2])),
                         "rotacion": float(np.degrees(np.arctan2(r["matriz"][1, 0], r["matriz"][0, 0]))),
                         "escala": float(np.hypot(r["matriz"][0, 0], r["matriz"][1, 0]))}
                        for k, r in registro.items()])
    reg.to_csv(args.reportes / "registro_diario.csv", index=False)
    reg.rename(columns={"metodo": "registro"})[["fecha", "vista", "registro", "m00", "m01", "m02", "m10", "m11", "m12"]
                                               ].to_csv(args.app / "datos" / "alineacion_dia.csv", index=False)
    print("\nREGISTRO DE CADA DÍA CONTRA LA REFERENCIA DE SU VISTA")
    print(reg["metodo"].value_counts().to_string())
    print(reg.groupby("vista")[["desplazamiento_px", "rotacion", "escala"]].describe().round(2).T.to_string())
    # Comprobación con 06: el corrimiento del 16-17 de enero medido aquí y el de alineacion.csv
    for c in alineacion[alineacion["alinear"]].itertuples():
        fechas = sorted(k for k in registro if registro[k]["vista"] == c.vista)
        antes = max((k for k in fechas if k < c.fecha.strftime("%Y-%m-%d")), default=None)
        despues = min((k for k in fechas if k >= c.fecha.strftime("%Y-%m-%d")), default=None)
        if antes and despues:
            rel = registro[despues]["matriz"] @ np.linalg.inv(registro[antes]["matriz"])
            print(f"Corrimiento {antes} -> {despues}: aquí ({rel[0, 2]:.1f}, {rel[1, 2]:.1f}) px; "
                  f"06 ({c.m02:.1f}, {c.m12:.1f}) px")

    # 3. Diferencia de estructura de cada par de días consecutivos con evidencia en la misma vista
    pares = []
    for v, g in con.groupby("vista"):
        fechas = [f.strftime("%Y-%m-%d") for f in g["fecha"] if f.strftime("%Y-%m-%d") in grises]
        for anterior, actual in zip(fechas[:-1], fechas[1:]):
            if registro[actual]["metodo"] == "sin registro":
                continue  # sin alineación confiable con el día anterior no se mide
            zona = validas[anterior] & validas[actual]
            zona[:BORDE_PX, :] = zona[-BORDE_PX:, :] = zona[:, :BORDE_PX] = zona[:, -BORDE_PX:] = False
            pares.append({"vista": v, "fecha_anterior": anterior, "fecha": actual, "zona": zona,
                          "dif": diferencia_estructura(grises[anterior], grises[actual])})

    # 4-5. Atenuación por la diferencia típica de cada píxel en su vista, e índice
    filas, mapas = [], {}
    for v in sorted({p["vista"] for p in pares}):
        de_vista = [p for p in pares if p["vista"] == v]
        tipica = np.median(np.stack([p["dif"] for p in de_vista]), axis=0)
        estable = tipica <= np.percentile(tipica, PERCENTIL_ZONA)
        # Zona analizada sobre la imagen de referencia (lo excluido queda oscuro)
        muestra = cv2.resize(color[de_vista[0]["fecha_anterior"]], estable.shape[::-1], interpolation=cv2.INTER_AREA)
        cv2.imwrite(str(args.reportes / f"zona_analizada_vista_{v}.jpg"),
                    np.where(estable[..., None], muestra, muestra // 5).astype(np.uint8))
        for p in de_vista:
            p["zona"] = p["zona"] & estable
            cambio = (p["dif"] >= FACTOR_TIPICO * tipica) & (p["dif"] >= DIFERENCIA_MINIMA) & p["zona"]
            mapas[p["fecha"]] = cambio
            filas.append({"fecha": p["fecha"], "fecha_anterior": p["fecha_anterior"], "vista": v,
                          "dias_entre": (pd.Timestamp(p["fecha"]) - pd.Timestamp(p["fecha_anterior"])).days,
                          "fotos_combinadas": n_fotos[p["fecha"]], "registro": registro[p["fecha"]]["metodo"],
                          "indice": round(100 * cambio.sum() / max(p["zona"].sum(), 1), 3)})
        # Mapa de la diferencia típica (blanco = cambia casi siempre, se atenúa)
        cv2.imwrite(str(args.reportes / f"diferencia_tipica_vista_{v}.jpg"),
                    np.clip(tipica / max(float(tipica.max()), 1e-6) * 255, 0, 255).astype(np.uint8))

    indice = pd.DataFrame(filas)
    # Días sin índice: el primero de cada vista (no hay con qué comparar) y los que no se pudieron
    # alinear con su día anterior
    faltan = [{"fecha": k, "vista": r["vista"], "fotos_combinadas": n_fotos[k], "registro": r["metodo"]}
              for k, r in registro.items() if k not in set(indice["fecha"])]
    indice = pd.concat([pd.DataFrame(faltan), indice])
    indice["fecha"] = pd.to_datetime(indice["fecha"])
    umbral = indice.groupby("vista")["indice"].transform(lambda s: s.quantile(PERCENTIL_PICO / 100))
    indice["pico"] = indice["indice"].ge(umbral) & indice["indice"].notna()
    indice = indice.sort_values("fecha")
    columnas = ["fecha", "fecha_anterior", "vista", "dias_entre", "fotos_combinadas", "registro", "indice", "pico"]
    indice["dias_entre"] = indice["dias_entre"].astype("Int64")
    indice["fotos_combinadas"] = indice["fotos_combinadas"].astype("Int64")
    indice[columnas].to_csv(args.app / "datos" / "indice_cambio.csv", index=False)

    # Hoja de revisión con los 12 días de mayor índice
    top = indice.dropna(subset=["indice"]).nlargest(12, "indice")
    top_filas = [{**r, "fecha": r["fecha"].strftime("%Y-%m-%d")} for r in top.to_dict("records")]
    hoja_picos(args.reportes / "picos.jpg", top_filas, color, mapas)

    # --- Resumen y validación contra los hitos ---------------------------------------
    print(f"\nÍndice: {indice['indice'].notna().sum()} días con par | picos: {int(indice['pico'].sum())}")
    print(indice.groupby("vista")["indice"].describe().round(2).to_string())
    val = validar(indice, hitos)
    print("\nVALIDACIÓN CONTRA LOS HITOS")
    print(val.to_string(index=False))
    tasa = indice.groupby("vista")["pico"].mean()
    esperado = 0.0
    for h in hitos.itertuples():
        n = int(((indice["fecha"] > h.fecha_inicio) & (indice["fecha"] <= h.fecha_fin) & indice["indice"].notna()).sum())
        esperado += 1 - (1 - tasa.get(h.vista, 0)) ** n
    print(f"\nCoinciden {int(val['coincide'].sum())} de {len(val)} hitos; por azar se esperarían {esperado:.1f}.")
    en_hito = indice["pico"] & indice.apply(
        lambda r: ((hitos["fecha_inicio"] < r["fecha"]) & (hitos["fecha_fin"] >= r["fecha"])).any(), axis=1)
    print(f"De {int(indice['pico'].sum())} picos, {int(en_hito.sum())} caen dentro de un hito.")
    print("Picos fuera de hitos:", ", ".join(indice.loc[indice["pico"] & ~en_hito, "fecha"].dt.strftime("%Y-%m-%d")))


if __name__ == "__main__":
    main()
