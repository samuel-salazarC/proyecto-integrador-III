"""Inventario y métricas de calidad de las fotografías originales.

Recorre data/raw_data (carpetas YYYYMMDD con archivos YYYYMMDD-HHMMSS.jpg) y genera:

  data/processed_data/inventario_fotos.csv   una fila por fotografía
  data/processed_data/resumen_diario.csv     una fila por día calendario
                                             (incluye los días sin fotografías)

Las fotografías originales solo se leen; nunca se modifican.

Métricas (mismas definiciones que los notebooks del curso):
  brillo            intensidad media en escala de grises, 0-255, a 640x480
  pct_subexpuesta   % de píxeles con intensidad < 20
  nitidez           Tenengrad: energía media de gradientes Sobel tras reducir
                    ruido. Mayor = más energía de bordes. Solo se calcula en
                    fotografías diurnas con luz suficiente.

Uso:
  python src/01_inventario.py
  python src/01_inventario.py --procesos 4
  python src/01_inventario.py --rehacer        # ignora resultados previos

Si se interrumpe, al volver a ejecutarlo continúa donde quedó.
"""

from __future__ import annotations

import argparse
import os
import re
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

# --- Parámetros (documentarlos en el informe si se cambian) -----------------
HORA_INICIO_DIA = 6        # las fotos de 06:00 a 17:59 se consideran diurnas
HORA_FIN_DIA = 17
TAMANO_ANALISIS = (640, 480)
BRILLO_MINIMO = 30         # umbral preliminar, igual al de los notebooks
MAX_PCT_SUBEXPUESTA = 80   # umbral preliminar, igual al de los notebooks
REDUCCION_RUIDO_H = 10
HORA_REFERENCIA = 12       # la "foto del día" es la útil más cercana a esta hora

PATRON = re.compile(r"(?<!\d)(20\d{2})(\d{2})(\d{2})[-_](\d{2})(\d{2})(\d{2})(?!\d)")
COLUMNAS = [
    "ruta", "carpeta", "archivo", "fecha_hora", "fecha", "hora", "es_diurna",
    "bytes", "ancho", "alto", "brillo", "pct_subexpuesta", "nitidez", "estado",
]
GUARDAR_CADA = 500


def listar_fotos(raiz: Path) -> tuple[pd.DataFrame, list[str]]:
    """Lista los JPG y extrae fecha y hora del nombre, sin abrir las imágenes."""
    filas, sin_fecha = [], []
    for ruta in sorted(raiz.rglob("*")):
        if not ruta.is_file() or ruta.suffix.lower() not in {".jpg", ".jpeg"}:
            continue
        if ruta.name.startswith("._"):
            continue
        relativa = ruta.relative_to(raiz).as_posix()
        coincidencia = PATRON.search(ruta.stem)
        if not coincidencia:
            sin_fecha.append(relativa)
            continue
        try:
            momento = pd.to_datetime("".join(coincidencia.groups()), format="%Y%m%d%H%M%S")
        except ValueError:
            sin_fecha.append(relativa)
            continue
        filas.append({
            "ruta": relativa,
            "carpeta": ruta.parent.name,
            "archivo": ruta.name,
            "fecha_hora": momento,
            "fecha": momento.strftime("%Y-%m-%d"),
            "hora": momento.hour,
            "es_diurna": HORA_INICIO_DIA <= momento.hour <= HORA_FIN_DIA,
            "bytes": ruta.stat().st_size,
        })
    return pd.DataFrame(filas), sin_fecha


def medir(tarea: tuple[str, str, bool]) -> dict:
    """Calcula las métricas de una fotografía. Se ejecuta en procesos paralelos."""
    raiz, relativa, es_diurna = tarea
    cv2.setNumThreads(1)
    resultado = {"ruta": relativa, "ancho": np.nan, "alto": np.nan, "brillo": np.nan,
                 "pct_subexpuesta": np.nan, "nitidez": np.nan, "estado": "ILEGIBLE"}
    try:
        datos = np.fromfile(os.path.join(raiz, relativa), dtype=np.uint8)
        imagen = cv2.imdecode(datos, cv2.IMREAD_GRAYSCALE)
    except Exception:
        imagen = None
    if imagen is None:
        return resultado

    resultado["alto"], resultado["ancho"] = imagen.shape[:2]
    gris = cv2.resize(imagen, TAMANO_ANALISIS, interpolation=cv2.INTER_AREA)
    brillo = float(gris.mean())
    subexpuesta = float((gris < 20).mean() * 100)
    resultado["brillo"] = round(brillo, 2)
    resultado["pct_subexpuesta"] = round(subexpuesta, 2)

    if not es_diurna:
        resultado["estado"] = "NOCTURNA"
        return resultado
    if brillo < BRILLO_MINIMO or subexpuesta > MAX_PCT_SUBEXPUESTA:
        resultado["estado"] = "LUZ_INSUFICIENTE"
        return resultado

    limpia = cv2.fastNlMeansDenoising(gris, None, h=REDUCCION_RUIDO_H,
                                      templateWindowSize=7, searchWindowSize=21)
    gx = cv2.Sobel(limpia, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(limpia, cv2.CV_64F, 0, 1, ksize=3)
    resultado["nitidez"] = round(float(np.mean(gx ** 2 + gy ** 2)), 2)
    resultado["estado"] = "EVALUADA"
    return resultado


def resumen_diario(fotos: pd.DataFrame) -> pd.DataFrame:
    """Una fila por día calendario entre la primera y la última fotografía."""
    fotos = fotos.copy()
    fotos["fecha"] = pd.to_datetime(fotos["fecha"])
    fotos["fecha_hora"] = pd.to_datetime(fotos["fecha_hora"])
    fotos["util"] = fotos["estado"].eq("EVALUADA")
    calendario = pd.date_range(fotos["fecha"].min(), fotos["fecha"].max(), freq="D")

    grupo = fotos.groupby("fecha")
    resumen = pd.DataFrame({
        "fotos_total": grupo.size(),
        "fotos_diurnas": grupo["es_diurna"].sum(),
        "fotos_utiles": grupo["util"].sum(),
        "fotos_luz_insuficiente": grupo["estado"].apply(lambda s: s.eq("LUZ_INSUFICIENTE").sum()),
        "fotos_ilegibles": grupo["estado"].apply(lambda s: s.eq("ILEGIBLE").sum()),
        "primera_foto": grupo["fecha_hora"].min().dt.strftime("%H:%M:%S"),
        "ultima_foto": grupo["fecha_hora"].max().dt.strftime("%H:%M:%S"),
    })
    utiles = fotos[fotos["util"]]
    if not utiles.empty:
        por_dia = utiles.groupby("fecha")
        resumen["brillo_medio"] = por_dia["brillo"].mean().round(2)
        resumen["nitidez_mediana"] = por_dia["nitidez"].median().round(2)
        distancia = (utiles["fecha_hora"].dt.hour + utiles["fecha_hora"].dt.minute / 60
                     - HORA_REFERENCIA).abs()
        mejores = utiles.loc[distancia.groupby(utiles["fecha"]).idxmin()]
        resumen["foto_del_dia"] = mejores.set_index("fecha")["ruta"]

    resumen = resumen.reindex(calendario)
    conteos = ["fotos_total", "fotos_diurnas", "fotos_utiles",
               "fotos_luz_insuficiente", "fotos_ilegibles"]
    resumen[conteos] = resumen[conteos].fillna(0).astype(int)
    resumen["estado_dia"] = np.select(
        [resumen["fotos_total"].eq(0), resumen["fotos_utiles"].eq(0)],
        ["SIN_FOTOS", "SIN_FOTOS_UTILES"], default="CON_EVIDENCIA")
    resumen.index.name = "fecha"
    resumen = resumen.reset_index()
    resumen["dia_semana"] = resumen["fecha"].dt.dayofweek.map(
        dict(enumerate(["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"])))
    resumen["fecha"] = resumen["fecha"].dt.strftime("%Y-%m-%d")
    primeras = ["fecha", "dia_semana", "estado_dia"]
    return resumen[primeras + [c for c in resumen.columns if c not in primeras]]


def main() -> None:
    base = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--raw", type=Path, default=base / "data" / "raw_data")
    parser.add_argument("--salida", type=Path, default=base / "data" / "processed_data")
    parser.add_argument("--procesos", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument("--rehacer", action="store_true", help="ignora resultados previos")
    args = parser.parse_args()

    if not args.raw.is_dir():
        raise SystemExit(f"No existe la carpeta de fotografías: {args.raw}")
    args.salida.mkdir(parents=True, exist_ok=True)
    archivo_fotos = args.salida / "inventario_fotos.csv"
    archivo_dias = args.salida / "resumen_diario.csv"

    print(f"Listando fotografías en {args.raw} ...")
    inventario, sin_fecha = listar_fotos(args.raw)
    if inventario.empty:
        raise SystemExit("No se encontraron fotografías con fecha y hora en el nombre.")
    print(f"Fotografías encontradas: {len(inventario):,} | sin fecha reconocible: {len(sin_fecha)}")

    # Reutilizar mediciones previas si el archivo no cambió de tamaño
    metricas = ["ancho", "alto", "brillo", "pct_subexpuesta", "nitidez", "estado"]
    hechas = pd.DataFrame(columns=["ruta", "bytes"] + metricas)
    if archivo_fotos.exists() and not args.rehacer:
        previo = pd.read_csv(archivo_fotos)
        if set(["ruta", "bytes"] + metricas) <= set(previo.columns):
            hechas = previo[["ruta", "bytes"] + metricas].dropna(subset=["estado"])
    hechas = hechas.merge(inventario[["ruta", "bytes"]], on=["ruta", "bytes"])
    pendientes = inventario[~inventario["ruta"].isin(hechas["ruta"])]
    print(f"Ya medidas: {len(hechas):,} | por medir: {len(pendientes):,} | procesos: {args.procesos}")

    resultados = hechas[["ruta"] + metricas].to_dict("records")

    def guardar() -> pd.DataFrame:
        tabla = inventario.merge(pd.DataFrame(resultados, columns=["ruta"] + metricas),
                                 on="ruta", how="left")
        tabla = tabla.sort_values("fecha_hora")[COLUMNAS]
        for columna in ("ancho", "alto"):
            tabla[columna] = pd.to_numeric(tabla[columna], errors="coerce").astype("Int64")
        tabla.to_csv(archivo_fotos, index=False)
        return tabla

    if len(pendientes):
        tareas = [(str(args.raw), r, bool(d)) for r, d in zip(pendientes["ruta"], pendientes["es_diurna"])]
        inicio = time.time()
        with ProcessPoolExecutor(max_workers=args.procesos) as ejecutor:
            for n, resultado in enumerate(ejecutor.map(medir, tareas, chunksize=16), 1):
                resultados.append(resultado)
                if n % GUARDAR_CADA == 0 or n == len(tareas):
                    guardar()
                    ritmo = n / (time.time() - inicio)
                    falta = (len(tareas) - n) / ritmo / 60
                    print(f"  {n:,}/{len(tareas):,} | {ritmo:.1f} fotos/s | faltan ~{falta:.0f} min", flush=True)

    tabla = guardar()
    dias = resumen_diario(tabla)
    dias.to_csv(archivo_dias, index=False)

    print("\nRESUMEN")
    print(f"Periodo: {dias['fecha'].iloc[0]} a {dias['fecha'].iloc[-1]} ({len(dias)} días)")
    print(dias["estado_dia"].value_counts().to_string())
    print("\nFotografías por estado:")
    print(tabla["estado"].value_counts().to_string())
    if sin_fecha:
        print(f"\nArchivos sin fecha reconocible (no incluidos): {len(sin_fecha)}; ejemplos: {sin_fecha[:5]}")
    print(f"\nGuardado:\n  {archivo_fotos}\n  {archivo_dias}")


if __name__ == "__main__":
    main()
