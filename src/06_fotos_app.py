"""Fotos reducidas y tablas livianas para la app web (app/streamlit_app.py).

Requiere haber ejecutado 04_fotos_utilizables.py y 05_hojas_semanales.py (y anotado
data/processed_data/hitos.csv). La app solo lee app/, así que funciona desplegada sin
data/raw_data. Genera:

  app/fotos/<AAAAMMDD-HHMMSS>.jpg       foto reducida (máx. ANCHO_MAX px, JPEG CALIDAD_JPG,
                                        sin EXIF) de la foto_del_dia de cada día con
                                        evidencia y de las fotos de hitos.csv y
                                        fotos_semanales.csv; las que ya no se usan se borran
  app/fotos/indice.csv                  fecha, encuadre_id, vista, archivo, fecha_hora
  app/fotos/miniaturas/<archivo>.jpg    miniatura (ANCHO_MINIATURA px) de las fotos semanales,
                                        para la tira de la línea de tiempo
  app/datos/dias.csv                    un día por fila: estado en lenguaje ciudadano,
                                        vista y foto del día
  app/datos/evidencia_dia_hora.csv      un día y hora (0-23) por fila: estado y número de fotos
  app/datos/hitos.csv                   hitos con las fotos apuntando a app/fotos (y la frase
                                        breve `resumen`, si hitos.csv la trae)
  app/datos/fotos_semanales.csv         foto más nítida de cada semana y vista
  app/datos/vistas.csv                  fechas de cada vista de la cámara
  app/datos/alineacion.csv              corrimiento de la cámara dentro de una misma vista,
                                        para alinear fotos en el comparador

Las rutas de fotos en app/datos son relativas a app/ (fotos/<archivo>.jpg).

Vista: lo que el público percibe como la misma vista de la cámara. Agrupa encuadres:
un tramo que empieza con un corrimiento pequeño (SALTO_MENOR, como el del 2026-01-17,
~31 px) o con el cambio de etiqueta EXIF (ROTACION_180) sigue en la vista anterior; solo
un CAMBIO_CONFIRMADO (2026-03-04) empieza una vista nueva. Hoy: encuadres 1 y 2 -> vista 1,
encuadre 3 -> vista 2. encuadre_id no se modifica en data/processed_data; la app usa
solo vista. Para cada SALTO_MENOR se mide la transformación de similitud (ORB + RANSAC,
el mismo método de 02) entre las dos fotos de la frontera en cambios_encuadre.csv, sobre
las fotos tal como se muestran (ANCHO_MAX px), y la app la usa para alinear la segunda
foto del comparador cuando las fechas quedan a lados distintos del corrimiento.

Estados (los mismos para el día y para cada hora):
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
ANCHO_MINIATURA = 400       # se muestran a ~200 px; el doble para pantallas de alta densidad
CALIDAD_MINIATURA = 70
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


def archivo_app(ruta) -> str | None:
    """20251008/20251008-115752.jpg -> fotos/20251008-115752.jpg (relativa a app/)."""
    return f"fotos/{Path(ruta).name}" if isinstance(ruta, str) and ruta else None


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


def evidencia_por_hora(fotos: pd.DataFrame, fechas: pd.Series) -> pd.DataFrame:
    rejilla = pd.MultiIndex.from_product([fechas, range(24)], names=["fecha", "hora"]).to_frame(index=False)
    conteo = fotos.groupby(["fecha", "hora"]).agg(fotos=("ruta", "size"), fotos_utiles=("utilizable", "sum")).reset_index()
    tabla = rejilla.merge(conteo, on=["fecha", "hora"], how="left").fillna({"fotos": 0, "fotos_utiles": 0})
    tabla[["fotos", "fotos_utiles"]] = tabla[["fotos", "fotos_utiles"]].astype(int)
    tabla["estado"] = np.select([tabla["fotos_utiles"].gt(0), tabla["fotos"].gt(0)], [UTIL, NO_SE_VE], default=SIN_FOTO)
    return tabla[["fecha", "hora", "estado", "fotos", "fotos_utiles"]]


def main() -> None:
    base = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--raw", type=Path, default=base / "data" / "raw_data")
    parser.add_argument("--datos", type=Path, default=base / "data" / "processed_data")
    parser.add_argument("--app", type=Path, default=base / "app")
    args = parser.parse_args()
    dir_fotos, dir_datos = args.app / "fotos", args.app / "datos"
    dir_fotos.mkdir(parents=True, exist_ok=True)
    dir_datos.mkdir(parents=True, exist_ok=True)

    resumen = pd.read_csv(args.datos / "resumen_diario_final.csv")
    fotos = pd.read_csv(args.datos / "fotos_utilizables.csv",
                        usecols=["ruta", "fecha", "fecha_hora", "hora", "encuadre_id", "utilizable", "rotacion_desde_crudo"])
    hitos = pd.read_csv(args.datos / "hitos.csv")
    semanales = pd.read_csv(args.datos / "fotos_semanales.csv")
    tramos = pd.read_csv(args.datos / "tramos_encuadre.csv")
    cambios = pd.read_csv(args.datos / "cambios_encuadre.csv")
    vista = vistas_por_encuadre(tramos)
    print("Vistas: " + ", ".join(f"encuadre {e} -> vista {v}" for e, v in sorted(vista.items())))

    # Una foto por semana y vista: la más nítida entre las de sus encuadres (p. ej. la semana
    # del 2026-01-12, repartida entre los encuadres 1 y 2, queda con una sola foto)
    semanales["vista"] = semanales["encuadre_id"].map(vista).astype("Int64")
    semanales = (semanales.dropna(subset=["ruta"]).sort_values(["nitidez", "fecha_hora"], ascending=[False, True])
                 .drop_duplicates(["semana_inicio", "vista"]).sort_values(["semana_inicio", "vista"]))

    # --- Fotos -------------------------------------------------------------------
    del_dia = resumen.loc[resumen["estado_dia_final"].eq("CON_EVIDENCIA"), "foto_del_dia"].dropna()
    rutas = pd.concat([del_dia, hitos["ruta_foto_antes"], hitos["ruta_foto_despues"], semanales["ruta"]]).dropna()
    rutas = sorted(set(rutas))
    info = fotos.set_index("ruta")
    faltan = [r for r in rutas if r not in info.index]
    if faltan:
        print(f"AVISO: {len(faltan)} foto(s) de hitos.csv o fotos_semanales.csv no están en fotos_utilizables.csv: {faltan}")
    no_utiles = [r for r in rutas if r in info.index and not info.at[r, "utilizable"]]
    if no_utiles:
        print(f"AVISO: {len(no_utiles)} foto(s) referenciadas no son utilizables (se incluyen igual): {no_utiles}")

    indice, nuevas, errores = [], 0, []
    for ruta in rutas:
        destino = args.app / archivo_app(ruta)
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
    print(f"Fotos: {len(indice)} en app/fotos ({nuevas} nuevas, {len(viejas)} borradas por no usarse)")

    # Miniaturas de las fotos semanales (desde la foto reducida, que ya está derecha)
    dir_minis = dir_fotos / "miniaturas"
    dir_minis.mkdir(exist_ok=True)
    minis = {Path(r).name for r in semanales["ruta"].dropna() if (dir_fotos / Path(r).name).exists()}
    for nombre in minis:
        if not (dir_minis / nombre).exists():
            imagen = cv2.imread(str(dir_fotos / nombre), cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
            guardar_jpg(imagen, dir_minis / nombre, ANCHO_MINIATURA, CALIDAD_MINIATURA)
    for p in dir_minis.glob("*.jpg"):
        if p.name not in minis:
            p.unlink()
    print(f"Miniaturas semanales: {len(minis)}")

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
    dias[["fecha", "estado", "vista", "fotos", "fotos_utiles", "foto", "fecha_hora_foto"]].to_csv(
        dir_datos / "dias.csv", index=False)

    por_hora = evidencia_por_hora(fotos, resumen["fecha"])
    # Coherencia: un día tiene foto útil si y solo si alguna de sus horas la tiene
    util_dia = por_hora.groupby("fecha")["estado"].apply(lambda s: s.eq(UTIL).any())
    distintos = (util_dia != dias.set_index("fecha")["estado"].eq(UTIL)).sum()
    if distintos:
        print(f"AVISO: {distintos} día(s) con estado distinto entre dias.csv y evidencia_dia_hora.csv")
    por_hora.to_csv(dir_datos / "evidencia_dia_hora.csv", index=False)

    salida_hitos = hitos.assign(foto_antes=hitos["ruta_foto_antes"].map(archivo_app),
                                foto_despues=hitos["ruta_foto_despues"].map(archivo_app))
    salida_hitos["fecha_hora_antes"] = hitos["ruta_foto_antes"].map(info["fecha_hora"])
    salida_hitos["fecha_hora_despues"] = hitos["ruta_foto_despues"].map(info["fecha_hora"])
    salida_hitos["vista"] = hitos["encuadre_id"].map(vista).astype("Int64")
    salida_hitos = salida_hitos.sort_values(["fecha_inicio", "fecha_fin"])
    # resumen: frase breve opcional («se pintan las líneas») para el resumen mensual de la app
    columnas = ["fecha_inicio", "fecha_fin", "vista", "titulo", "descripcion", "foto_antes", "foto_despues",
                "fecha_hora_antes", "fecha_hora_despues", "confianza"] + (["resumen"] if "resumen" in hitos else [])
    salida_hitos[columnas].to_csv(dir_datos / "hitos.csv", index=False)

    semanales.assign(foto=semanales["ruta"].map(archivo_app))[
        ["semana_inicio", "vista", "foto", "fecha_hora"]].to_csv(dir_datos / "fotos_semanales.csv", index=False)

    vistas = tramos.assign(vista=tramos["encuadre_id"].map(vista)).groupby("vista").agg(
        fecha_inicio=("fecha_inicio", "min"), fecha_fin=("fecha_fin", "max"))
    vistas.reset_index().to_csv(dir_datos / "vistas.csv", index=False)
    (dir_datos / "camaras.csv").unlink(missing_ok=True)  # reemplazada por vistas.csv
    alineaciones(args.raw, tramos, cambios, vista).to_csv(dir_datos / "alineacion.csv", index=False)

    # --- Resumen -----------------------------------------------------------------
    print("\nRESUMEN")
    print(dias["estado"].value_counts().to_string())
    print(f"Hitos: {len(hitos)} | semanas: {len(semanales)} | horas: {len(por_hora):,}")
    tamanos = {d: sum(p.stat().st_size for p in (args.app / d).rglob("*") if p.is_file()) / 1e6
               for d in ["fotos", "datos"]}  # fotos incluye miniaturas
    total = sum(p.stat().st_size for p in args.app.rglob("*") if p.is_file() and "__pycache__" not in p.parts) / 1e6
    print(f"Tamaño: fotos {tamanos['fotos']:.1f} MB | datos {tamanos['datos']:.2f} MB | app/ completa {total:.1f} MB")
    if total > MAX_MB_APP:
        print(f"AVISO: app/ supera {MAX_MB_APP} MB; baje ANCHO_MAX o CALIDAD_JPG")


if __name__ == "__main__":
    main()
