"""Fotos reducidas y tablas livianas para la app web (app/streamlit_app.py).

Requiere haber ejecutado 04_fotos_utilizables.py (y anotado data/processed_data/hitos.csv).
La app solo lee app/, así que funciona desplegada sin data/raw_data. Genera:

  app/static/fotos/<AAAAMMDD-HHMMSS>.jpg  foto reducida (máx. ANCHO_MAX px, JPEG CALIDAD_JPG,
                                        sin EXIF) de la foto_del_dia de cada día con
                                        evidencia y de las fotos de hitos.csv; las que ya
                                        no se usan se borran. Está en app/static/ porque la
                                        app la sirve por URL (server.enableStaticServing)
                                        para el recorrido y el time-lapse.
  app/static/fotos/indice.csv           fecha, encuadre_id, vista, archivo, fecha_hora
  app/datos/dias.csv                    un día por fila: estado en lenguaje ciudadano, vista,
                                        foto del día y fotos excluidas por cada motivo
  app/datos/fotos.csv                   una fila por foto (las 21 644): fecha, hora y estado
                                        (útil, excluida por calidad, de noche, sin vista de
                                        la obra), sin rutas ni columnas técnicas
  app/datos/hitos.csv                   hitos con las fotos apuntando a app/static/fotos
  app/datos/vistas.csv                  fechas de cada vista de la cámara
  data/processed_data/alineacion_corrimientos.csv
                                        corrimiento de la cámara en cada SALTO_MENOR (el del
                                        2026-01-17), que 07 usa al registrar los días; la app
                                        no lo lee (usa app/datos/alineacion_dia.csv, de 07)

Las rutas de fotos en app/datos son relativas a app/ (static/fotos/<archivo>.jpg).

Vista: lo que el público percibe como la misma vista de la cámara. Agrupa encuadres:
un tramo que empieza con un corrimiento pequeño (SALTO_MENOR, como el del 2026-01-17,
~31 px) o con el cambio de etiqueta EXIF (ROTACION_180) sigue en la vista anterior; solo
un CAMBIO_CONFIRMADO (2026-03-04) empieza una vista nueva. Hoy: encuadres 1 y 2 -> vista 1,
encuadre 3 -> vista 2. encuadre_id no se modifica en data/processed_data; la app usa
solo vista. Para cada SALTO_MENOR se mide la transformación de similitud (ORB + RANSAC,
el mismo método de 02) entre las dos fotos de la frontera en cambios_encuadre.csv, sobre
las fotos tal como se muestran (ANCHO_MAX px); 07_indice_cambio.py lo usa al registrar
cada día contra el anterior (la cámara se desplaza además unos píxeles casi a diario).

Estados de cada día (dias.csv):
  hay foto útil                   al menos una foto utilizable
  hay foto pero no se ve la obra  hay fotos y ninguna es utilizable (noche, poca luz,
                                  borrosa, la cámara no apunta a la obra...)
  no hay foto                     la cámara no envió fotos

Las fotos siguen la regla para mostrar del README (píxeles crudos ignorando la etiqueta
EXIF + rotacion_desde_crudo grados) y se guardan sin EXIF, así que cualquier visor las
muestra derechas.

Uso:
  python src/06_fotos_app.py
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

# Reutiliza la regla para mostrar de 04 (crudo + rotacion_desde_crudo)
_spec = importlib.util.spec_from_file_location("fotos_utilizables", Path(__file__).with_name("04_fotos_utilizables.py"))
fu = importlib.util.module_from_spec(_spec)
sys.modules["fotos_utilizables"] = fu
_spec.loader.exec_module(fu)

ANCHO_MAX = 960
CALIDAD_JPG = 80
MAX_MB_APP = 30
TIPOS_MISMA_VISTA = {"SALTO_MENOR", "ROTACION_180"}  # inicio de tramo que no cambia la vista
ORB_PUNTOS = 5000
ORB_RATIO = 0.75
RANSAC_UMBRAL_PX = 3.0
MIN_INLIERS_ALINEACION = 50  # con menos coincidencias consistentes no se alinea (la app deja una nota)

UTIL = "hay foto útil"
NO_SE_VE = "hay foto pero no se ve la obra"
SIN_FOTO = "no hay foto"
ESTADO_DIA = {"CON_EVIDENCIA": UTIL, "SIN_VISTA_DE_OBRA": NO_SE_VE, "SIN_FOTOS_UTILES": NO_SE_VE, "SIN_FOTOS": SIN_FOTO}

# Estado de cada foto para la figura de puntos de la app (fotos.csv). Las exclusiones por
# luz insuficiente, calidad, orientación dudosa o archivo ilegible se agrupan como «excluida
# por calidad»: todas son fotos tomadas de día con vista de la obra que no se pueden leer bien.
ESTADO_FOTO = {"NOCTURNA": "de noche", "DIA_SIN_VISTA_DE_OBRA": "sin vista de la obra"}
FOTO_UTIL, FOTO_CALIDAD = "útil", "excluida por calidad"
# Columnas de dias.csv con las fotos excluidas de cada día, por motivo_exclusion de 04
MOTIVOS = {"NOCTURNA": "excluidas_nocturna", "LUZ_INSUFICIENTE": "excluidas_luz_insuficiente",
           "DIA_SIN_VISTA_DE_OBRA": "excluidas_dia_sin_vista", "CALIDAD": "excluidas_calidad",
           "ORIENTACION_DUDOSA": "excluidas_orientacion_dudosa", "ILEGIBLE": "excluidas_ilegible"}


def archivo_app(ruta) -> str | None:
    """20251008/20251008-115752.jpg -> static/fotos/20251008-115752.jpg (relativa a app/)."""
    return f"static/fotos/{Path(ruta).name}" if isinstance(ruta, str) and ruta else None


def guardar_jpg(imagen: np.ndarray, destino: Path, ancho_max: int, calidad: int) -> bool:
    alto, ancho = imagen.shape[:2]
    if ancho > ancho_max:
        imagen = cv2.resize(imagen, (ancho_max, round(alto * ancho_max / ancho)), interpolation=cv2.INTER_AREA)
    ok, datos = cv2.imencode(".jpg", imagen, [cv2.IMWRITE_JPEG_QUALITY, calidad, cv2.IMWRITE_JPEG_OPTIMIZE, 1])
    if ok:
        datos.tofile(str(destino))
    return bool(ok)


def reducir(raw: Path, ruta: str, rotacion: int, destino: Path) -> bool:
    imagen = fu.abrir_para_mostrar(str(raw), ruta, rotacion)
    return imagen is not None and guardar_jpg(imagen, destino, ANCHO_MAX, CALIDAD_JPG)


def vistas_por_encuadre(tramos: pd.DataFrame) -> dict[int, int]:
    """encuadre_id -> vista: solo un inicio de tramo fuera de TIPOS_MISMA_VISTA abre una vista nueva."""
    vista, mapa = 0, {}
    for t in tramos.sort_values("fecha_inicio").itertuples():
        if vista == 0 or t.tipo_inicio not in TIPOS_MISMA_VISTA:
            vista += 1
        if mapa.setdefault(int(t.encuadre_id), vista) != vista:
            raise ValueError(f"El encuadre {t.encuadre_id} quedaría en dos vistas distintas")
    return mapa


def matriz_corrimiento(raw: Path, foto_antes: str, foto_despues: str) -> tuple[np.ndarray | None, int, tuple[int, int]]:
    """Similitud (2x3) que lleva puntos de foto_antes a foto_despues, ambas como se muestran en la app."""
    imagenes, tamano = [], (0, 0)
    for ruta in (foto_antes, foto_despues):
        imagen = fu.abrir_para_mostrar(str(raw), ruta)
        if imagen is None:
            return None, 0, tamano
        alto, ancho = imagen.shape[:2]
        tamano = (ANCHO_MAX, round(alto * ANCHO_MAX / ancho))
        imagen = cv2.resize(imagen, tamano, interpolation=cv2.INTER_AREA)
        gris = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY))
        imagenes.append(cv2.ORB_create(nfeatures=ORB_PUNTOS).detectAndCompute(gris, None))
    (ka, da), (kb, db) = imagenes
    if da is None or db is None:
        return None, 0, tamano
    pares = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(da, db, k=2)
    buenas = [p[0] for p in pares if len(p) == 2 and p[0].distance < ORB_RATIO * p[1].distance]
    if len(buenas) < 4:
        return None, 0, tamano
    pa = np.float32([ka[m.queryIdx].pt for m in buenas])
    pb = np.float32([kb[m.trainIdx].pt for m in buenas])
    cv2.setRNGSeed(0)
    matriz, inliers = cv2.estimateAffinePartial2D(pa, pb, method=cv2.RANSAC, ransacReprojThreshold=RANSAC_UMBRAL_PX)
    return matriz, (0 if inliers is None else int(inliers.sum())), tamano


def alineaciones(raw: Path, tramos: pd.DataFrame, cambios: pd.DataFrame, vista: dict[int, int]) -> pd.DataFrame:
    filas = []
    for t in tramos[tramos["tipo_inicio"].eq("SALTO_MENOR")].itertuples():
        frontera = cambios[cambios["fecha"].eq(t.fecha_inicio) & cambios["resultado"].eq("SALTO_MENOR")]
        if frontera.empty:
            print(f"AVISO: no se encontró en cambios_encuadre.csv el corrimiento del {t.fecha_inicio}")
            continue
        f = frontera.iloc[0]
        matriz, inliers, (ancho, alto) = matriz_corrimiento(raw, f["foto_antes"], f["foto_despues"])
        ok = matriz is not None and inliers >= MIN_INLIERS_ALINEACION
        fila = {"vista": vista[int(t.encuadre_id)], "fecha": t.fecha_inicio, "alinear": ok, "coincidencias": inliers,
                "desplazamiento_px_02": f["desplazamiento_px"], "rotacion_02": f["rotacion"],
                "foto_antes": f["foto_antes"], "foto_despues": f["foto_despues"], "ancho": ancho, "alto": alto}
        for i, nombre in enumerate(["m00", "m01", "m02", "m10", "m11", "m12"]):
            fila[nombre] = round(float(matriz.flat[i]), 6) if ok else None
        filas.append(fila)
        estado = "se alinea" if ok else "NO se alinea (pocas coincidencias)"
        print(f"Corrimiento del {t.fecha_inicio}: {inliers} coincidencias consistentes, {estado}")
    return pd.DataFrame(filas, columns=["vista", "fecha", "alinear", "coincidencias", "desplazamiento_px_02",
                                        "rotacion_02", "foto_antes", "foto_despues", "ancho", "alto",
                                        "m00", "m01", "m02", "m10", "m11", "m12"])


def tabla_fotos(fotos: pd.DataFrame) -> pd.DataFrame:
    """Una fila por foto: fecha, hora (HH:MM:SS) y estado, sin rutas ni columnas técnicas."""
    estado = fotos["motivo_exclusion"].map(ESTADO_FOTO).fillna(FOTO_CALIDAD)
    estado = estado.where(fotos["motivo_exclusion"].notna(), FOTO_UTIL)
    tabla = pd.DataFrame({"fecha": fotos["fecha"], "hora": fotos["fecha_hora"].str[11:19], "estado": estado})
    return tabla.sort_values(["fecha", "hora"]).reset_index(drop=True)


def exclusiones_por_dia(fotos: pd.DataFrame) -> pd.DataFrame:
    """Fotos excluidas de cada día por motivo (columnas de MOTIVOS)."""
    desconocidos = set(fotos["motivo_exclusion"].dropna()) - set(MOTIVOS)
    if desconocidos:
        raise ValueError(f"motivo_exclusion desconocido: {sorted(desconocidos)}")
    tabla = pd.crosstab(fotos["fecha"], fotos["motivo_exclusion"]).reindex(columns=list(MOTIVOS), fill_value=0)
    return tabla.rename(columns=MOTIVOS)


def main() -> None:
    base = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--raw", type=Path, default=base / "data" / "raw_data")
    parser.add_argument("--datos", type=Path, default=base / "data" / "processed_data")
    parser.add_argument("--app", type=Path, default=base / "app")
    args = parser.parse_args()
    dir_fotos, dir_datos = args.app / "static" / "fotos", args.app / "datos"
    dir_fotos.mkdir(parents=True, exist_ok=True)
    dir_datos.mkdir(parents=True, exist_ok=True)

    resumen = pd.read_csv(args.datos / "resumen_diario_final.csv")
    fotos = pd.read_csv(args.datos / "fotos_utilizables.csv",
                        usecols=["ruta", "fecha", "fecha_hora", "hora", "encuadre_id", "utilizable", "motivo_exclusion",
                                 "rotacion_desde_crudo"])
    hitos = pd.read_csv(args.datos / "hitos.csv")
    tramos = pd.read_csv(args.datos / "tramos_encuadre.csv")
    cambios = pd.read_csv(args.datos / "cambios_encuadre.csv")
    vista = vistas_por_encuadre(tramos)
    print("Vistas: " + ", ".join(f"encuadre {e} -> vista {v}" for e, v in sorted(vista.items())))

    # --- Fotos -------------------------------------------------------------------
    del_dia = resumen.loc[resumen["estado_dia_final"].eq("CON_EVIDENCIA"), "foto_del_dia"].dropna()
    rutas = pd.concat([del_dia, hitos["ruta_foto_antes"], hitos["ruta_foto_despues"]]).dropna()
    rutas = sorted(set(rutas))
    info = fotos.set_index("ruta")
    faltan = [r for r in rutas if r not in info.index]
    if faltan:
        print(f"AVISO: {len(faltan)} foto(s) de hitos.csv no están en fotos_utilizables.csv: {faltan}")
    no_utiles = [r for r in rutas if r in info.index and not info.at[r, "utilizable"]]
    if no_utiles:
        print(f"AVISO: {len(no_utiles)} foto(s) referenciadas no son utilizables (se incluyen igual): {no_utiles}")

    indice, nuevas, errores = [], 0, []
    for ruta in rutas:
        destino = dir_fotos / Path(ruta).name
        rotacion = int(info.at[ruta, "rotacion_desde_crudo"]) if ruta in info.index else fu.ROTACION_DESDE_CRUDO
        if not destino.exists():
            if not reducir(args.raw, ruta, rotacion, destino):
                errores.append(ruta)
                continue
            nuevas += 1
        fila = info.loc[ruta] if ruta in info.index else None
        indice.append({"fecha": fila["fecha"] if fila is not None else f"{ruta[:4]}-{ruta[4:6]}-{ruta[6:8]}",
                       "encuadre_id": fila["encuadre_id"] if fila is not None else None,
                       "vista": vista.get(fila["encuadre_id"]) if fila is not None and pd.notna(fila["encuadre_id"]) else None,
                       "archivo": destino.name,
                       "fecha_hora": fila["fecha_hora"] if fila is not None else None})
    if errores:
        print(f"AVISO: no se pudieron abrir {len(errores)} foto(s) (¿falta data/raw_data?): {errores[:5]}")
    indice = pd.DataFrame(indice)
    indice[["encuadre_id", "vista"]] = indice[["encuadre_id", "vista"]].astype("Int64")
    indice.to_csv(dir_fotos / "indice.csv", index=False)
    vigentes = set(indice["archivo"])
    viejas = [p for p in dir_fotos.glob("*.jpg") if p.name not in vigentes]
    for p in viejas:
        p.unlink()
    print(f"Fotos: {len(indice)} en app/static/fotos ({nuevas} nuevas, {len(viejas)} borradas por no usarse)")

    # --- Tablas ------------------------------------------------------------------
    dias = resumen[["fecha", "estado_dia_final", "encuadre_id", "fotos_total", "fotos_utiles", "foto_del_dia"]].copy()
    dias["estado"] = dias["estado_dia_final"].map(ESTADO_DIA)
    if dias["estado"].isna().any():
        raise ValueError(f"estado_dia_final desconocido: {sorted(dias.loc[dias['estado'].isna(), 'estado_dia_final'].unique())}")
    dias.loc[dias["estado"].ne(UTIL), "foto_del_dia"] = None
    dias["fecha_hora_foto"] = dias["foto_del_dia"].map(info["fecha_hora"])
    dias["foto"] = dias["foto_del_dia"].map(archivo_app)
    dias["vista"] = dias["encuadre_id"].map(vista).astype("Int64")
    dias = dias.rename(columns={"fotos_total": "fotos"})
    excluidas = exclusiones_por_dia(fotos).reindex(dias["fecha"], fill_value=0).reset_index(drop=True)
    dias = pd.concat([dias.reset_index(drop=True), excluidas], axis=1)
    dias[["fecha", "estado", "vista", "fotos", "fotos_utiles", "foto", "fecha_hora_foto", *MOTIVOS.values()]].to_csv(
        dir_datos / "dias.csv", index=False)

    por_foto = tabla_fotos(fotos)
    # Coherencia: un día tiene foto útil si y solo si alguna de sus fotos lo es
    util_dia = por_foto.groupby("fecha")["estado"].apply(lambda s: s.eq(FOTO_UTIL).any())
    util_dia = util_dia.reindex(dias["fecha"], fill_value=False)
    distintos = int((util_dia.to_numpy() != dias["estado"].eq(UTIL).to_numpy()).sum())
    if distintos:
        print(f"AVISO: {distintos} día(s) con estado distinto entre dias.csv y fotos.csv")
    por_foto.to_csv(dir_datos / "fotos.csv", index=False)

    salida_hitos = hitos.assign(foto_antes=hitos["ruta_foto_antes"].map(archivo_app),
                                foto_despues=hitos["ruta_foto_despues"].map(archivo_app))
    salida_hitos["fecha_hora_antes"] = hitos["ruta_foto_antes"].map(info["fecha_hora"])
    salida_hitos["fecha_hora_despues"] = hitos["ruta_foto_despues"].map(info["fecha_hora"])
    salida_hitos["vista"] = hitos["encuadre_id"].map(vista).astype("Int64")
    salida_hitos = salida_hitos.sort_values(["fecha_inicio", "fecha_fin"])
    columnas = ["fecha_inicio", "fecha_fin", "vista", "titulo", "descripcion", "foto_antes", "foto_despues",
                "fecha_hora_antes", "fecha_hora_despues", "confianza"]
    salida_hitos[columnas].to_csv(dir_datos / "hitos.csv", index=False)

    vistas = tramos.assign(vista=tramos["encuadre_id"].map(vista)).groupby("vista").agg(
        fecha_inicio=("fecha_inicio", "min"), fecha_fin=("fecha_fin", "max"))
    vistas.reset_index().to_csv(dir_datos / "vistas.csv", index=False)
    # Tablas de versiones anteriores de la app que ya no se usan
    for vieja in ["camaras.csv", "evidencia_dia_hora.csv", "fotos_semanales.csv", "alineacion.csv"]:
        (dir_datos / vieja).unlink(missing_ok=True)
    alineaciones(args.raw, tramos, cambios, vista).to_csv(args.datos / "alineacion_corrimientos.csv", index=False)

    # --- Resumen -----------------------------------------------------------------
    print("\nRESUMEN")
    print(dias["estado"].value_counts().to_string())
    print(por_foto["estado"].value_counts().to_string())
    print(f"Hitos: {len(hitos)} | fotos: {len(por_foto):,}")
    tamanos = {d: sum(p.stat().st_size for p in (args.app / d).rglob("*") if p.is_file()) / 1e6
               for d in ["static", "datos"]}
    total = sum(p.stat().st_size for p in args.app.rglob("*") if p.is_file() and "__pycache__" not in p.parts) / 1e6
    print(f"Tamaño: fotos {tamanos['static']:.1f} MB | datos {tamanos['datos']:.2f} MB | app/ completa {total:.1f} MB")
    if total > MAX_MB_APP:
        print(f"AVISO: app/ supera {MAX_MB_APP} MB; baje ANCHO_MAX o CALIDAD_JPG")


if __name__ == "__main__":
    main()
