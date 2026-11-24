"""Hojas semanales (y diarias) para identificar a mano los hitos visibles de la obra.

Requiere haber ejecutado 04_fotos_utilizables.py. Lee resumen_diario_final.csv y
fotos_utilizables.csv y genera:

  data/processed_data/fotos_semanales.csv          una fila por semana y encuadre con la
                                                   foto elegida (vacía si no hay evidencia)
  data/processed_data/hitos.csv                    tabla de hitos para anotar a mano; se
                                                   crea solo si no existe, con el hito ya
                                                   identificado (losa del puente)
  reports/hitos/semanas_encuadre_<id>.jpg          miniaturas semanales en orden cronológico
                                                   (_parte1, _parte2... si no caben)
  reports/hitos/dias_<inicio>_<fin>.jpg            modo diario (--dias)

Selección semanal: semanas de lunes a domingo. Por cada semana y encuadre_id se toman
los días con estado_dia_final == CON_EVIDENCIA y, entre sus foto_del_dia, la de mayor
nitidez (la de 01, columna nitidez de fotos_utilizables.csv; empate -> la más antigua).
Una semana que se reparte entre dos encuadres (p. ej. 2026-01-12 a 2026-01-18) aparece
en la hoja de cada uno. Las semanas de un encuadre sin días con evidencia quedan como
celda "sin evidencia". Las semanas sin ningún día asignado a un encuadre (el periodo sin
vista de la obra, 2026-02-06 a 2026-03-03) no aparecen en ninguna hoja.

Las miniaturas siguen la regla para mostrar del README (píxeles crudos ignorando la
etiqueta EXIF + rotacion_desde_crudo grados) y llevan la fecha y hora encima.

Los hitos no se detectan automáticamente: se anotan a mano en hitos.csv, y el modo
diario sirve para acotar la fecha de un cambio que se ve entre dos semanas.

Uso:
  python src/05_hojas_semanales.py
  python src/05_hojas_semanales.py --dias 2025-10-06 2025-10-12
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

# --- Hojas --------------------------------------------------------------------------
MINIATURA = (640, 512)      # mitad de la foto original (1280x1024)
COLUMNAS = 4                # hoja de 2560 px de ancho
MAX_FILAS = 3               # más filas -> se divide en partes
ALTO_ETIQUETA = 62
CALIDAD_JPG = 80
FUENTE = cv2.FONT_HERSHEY_SIMPLEX
GRIS_VACIA = 225
DIAS_SEMANA = ["lun", "mar", "mie", "jue", "vie", "sab", "dom"]

# --- Hitos --------------------------------------------------------------------------
COLUMNAS_HITOS = ["fecha_inicio", "fecha_fin", "encuadre_id", "titulo", "descripcion",
                  "ruta_foto_antes", "ruta_foto_despues", "confianza", "identificado_por"]
HITOS_INICIALES = [{
    "fecha_inicio": "2025-10-08", "fecha_fin": "2025-10-09", "encuadre_id": 1,
    "titulo": "Colocación de la losa del puente",
    "descripcion": "La losa del puente aparece colocada entre la foto del día del 2025-10-08 y la del 2025-10-09.",
    "ruta_foto_antes": "20251008/20251008-115752.jpg", "ruta_foto_despues": "20251009/20251009-120012.jpg",
    "confianza": "alta", "identificado_por": "equipo"}]


# ============================================================================
# Selección
# ============================================================================

def cargar(datos: Path) -> pd.DataFrame:
    """Resumen diario con la nitidez, fecha_hora y rotación de la foto del día."""
    resumen = pd.read_csv(datos / "resumen_diario_final.csv")
    fotos = pd.read_csv(datos / "fotos_utilizables.csv", usecols=["ruta", "fecha_hora", "nitidez", "rotacion_desde_crudo"])
    dias = resumen[["fecha", "estado_dia_final", "encuadre_id", "foto_del_dia"]].merge(
        fotos.rename(columns={"ruta": "foto_del_dia"}), on="foto_del_dia", how="left")
    dias["fecha"] = pd.to_datetime(dias["fecha"])
    dias["encuadre_id"] = dias["encuadre_id"].astype("Int64")
    dias["semana_inicio"] = dias["fecha"] - pd.to_timedelta(dias["fecha"].dt.day_of_week, unit="D")
    dias["con_evidencia"] = dias["estado_dia_final"].eq("CON_EVIDENCIA") & dias["foto_del_dia"].notna()
    return dias


def seleccion_semanal(dias: pd.DataFrame) -> pd.DataFrame:
    """Una fila por (semana, encuadre) con días asignados al encuadre; ruta vacía si no hay evidencia."""
    con_encuadre = dias[dias["encuadre_id"].notna()]
    semanas = con_encuadre.groupby(["encuadre_id", "semana_inicio"]).agg(
        dias_encuadre=("fecha", "size"), dias_con_evidencia=("con_evidencia", "sum")).reset_index()
    candidatas = con_encuadre[con_encuadre["con_evidencia"]].sort_values(
        ["nitidez", "fecha_hora"], ascending=[False, True])
    mejores = candidatas.drop_duplicates(["encuadre_id", "semana_inicio"])[
        ["encuadre_id", "semana_inicio", "foto_del_dia", "fecha_hora", "nitidez", "rotacion_desde_crudo"]]
    semanas = semanas.merge(mejores, on=["encuadre_id", "semana_inicio"], how="left").rename(columns={"foto_del_dia": "ruta"})
    return semanas.sort_values(["encuadre_id", "semana_inicio"]).reset_index(drop=True)


# ============================================================================
# Hojas
# ============================================================================

def celda(raiz: Path, ruta, rotacion, lineas: list[str]) -> np.ndarray:
    ancho, alto = MINIATURA
    imagen = fu.abrir_para_mostrar(str(raiz), ruta, int(rotacion)) if isinstance(ruta, str) else None
    if imagen is None:
        imagen = np.full((alto, ancho, 3), GRIS_VACIA, np.uint8)
        texto = "sin evidencia" if not isinstance(ruta, str) else "no se pudo abrir"
        (w, h), _ = cv2.getTextSize(texto, FUENTE, 1.4, 2)
        cv2.putText(imagen, texto, ((ancho - w) // 2, (alto + h) // 2), FUENTE, 1.4, (90, 90, 90), 2, cv2.LINE_AA)
    else:
        imagen = cv2.resize(imagen, MINIATURA, interpolation=cv2.INTER_AREA)
    barra = np.zeros((ALTO_ETIQUETA, ancho, 3), np.uint8)
    for i, linea in enumerate(lineas[:2]):
        cv2.putText(barra, linea, (8, 25 + 28 * i), FUENTE, 0.75 if i == 0 else 0.6,
                    (255, 255, 255), 2 if i == 0 else 1, cv2.LINE_AA)
    marco = np.vstack([barra, imagen])
    marco[:, -2:] = 255
    marco[-2:, :] = 255
    return marco


def partes(n: int) -> list[slice]:
    """Divide n celdas en partes parejas de como máximo COLUMNAS x MAX_FILAS."""
    por_hoja = COLUMNAS * MAX_FILAS
    k = max(1, -(-n // por_hoja))
    tamano = -(-n // k)
    tamano = -(-tamano // COLUMNAS) * COLUMNAS  # filas completas salvo en la última parte
    return [slice(i, min(i + tamano, n)) for i in range(0, n, tamano)]


def guardar_hojas(destino: Path, nombre: str, celdas: list[np.ndarray], titulo: str) -> list[Path]:
    for viejo in [destino / f"{nombre}.jpg", *destino.glob(f"{nombre}_parte*.jpg")]:
        viejo.unlink(missing_ok=True)
    trozos = partes(len(celdas))
    guardadas = []
    for i, trozo in enumerate(trozos, start=1):
        sufijo = f"_parte{i}" if len(trozos) > 1 else ""
        texto = f"{titulo}{f' (parte {i} de {len(trozos)})' if len(trozos) > 1 else ''}"
        hoja = rejilla(celdas[trozo], texto)
        ruta = destino / f"{nombre}{sufijo}.jpg"
        ok, datos = cv2.imencode(".jpg", hoja, [cv2.IMWRITE_JPEG_QUALITY, CALIDAD_JPG, cv2.IMWRITE_JPEG_OPTIMIZE, 1])
        if ok:
            datos.tofile(str(ruta))
            guardadas.append(ruta)
    return guardadas


def rejilla(celdas: list[np.ndarray], titulo: str) -> np.ndarray:
    alto, ancho = celdas[0].shape[:2]
    columnas = min(COLUMNAS, len(celdas))
    vacia = np.full((alto, ancho, 3), 255, np.uint8)
    celdas = celdas + [vacia] * (-len(celdas) % columnas)
    cuerpo = np.vstack([np.hstack(celdas[i:i + columnas]) for i in range(0, len(celdas), columnas)])
    cabecera = np.full((50, cuerpo.shape[1], 3), 255, np.uint8)
    cv2.putText(cabecera, titulo, (10, 34), FUENTE, 0.9, (0, 0, 0), 2, cv2.LINE_AA)
    return np.vstack([cabecera, cuerpo])


def hojas_semanales(semanas: pd.DataFrame, raw: Path, destino: Path) -> None:
    for viejo in destino.glob("semanas_encuadre_*.jpg"):
        viejo.unlink()
    for encuadre, filas in semanas.groupby("encuadre_id"):
        celdas = []
        for f in filas.itertuples():
            fin = f.semana_inicio + pd.Timedelta(days=6)
            semana = f"Semana {f.semana_inicio:%Y-%m-%d} a {fin:%m-%d}"
            if isinstance(f.ruta, str):
                momento = pd.Timestamp(f.fecha_hora)
                lineas = [f"{momento:%Y-%m-%d %H:%M:%S} ({DIAS_SEMANA[momento.weekday()]})",
                          f"{semana} | {f.dias_con_evidencia}/{f.dias_encuadre} dias con evidencia | nitidez {f.nitidez:.0f}"]
            else:
                lineas = [semana, f"0/{f.dias_encuadre} dias con evidencia"]
            celdas.append(celda(raw, f.ruta, f.rotacion_desde_crudo if isinstance(f.ruta, str) else 0, lineas))
        primera, ultima = filas["semana_inicio"].min(), filas["semana_inicio"].max() + pd.Timedelta(days=6)
        titulo = (f"Encuadre {encuadre}: foto del dia mas nitida de cada semana, {primera:%Y-%m-%d} a {ultima:%Y-%m-%d}"
                  f" | crudo + 180 grados")
        for ruta in guardar_hojas(destino, f"semanas_encuadre_{encuadre}", celdas, titulo):
            print(f"  {ruta}")


def hoja_diaria(dias: pd.DataFrame, inicio: pd.Timestamp, fin: pd.Timestamp, raw: Path, destino: Path) -> None:
    rango = pd.DataFrame({"fecha": pd.date_range(inicio, fin, freq="D")}).merge(dias, on="fecha", how="left")
    celdas = []
    for f in rango.itertuples():
        encuadre = f"encuadre {f.encuadre_id}" if pd.notna(f.encuadre_id) else "sin encuadre"
        if f.con_evidencia is True:
            momento = pd.Timestamp(f.fecha_hora)
            lineas = [f"{momento:%Y-%m-%d %H:%M:%S} ({DIAS_SEMANA[momento.weekday()]})",
                      f"{encuadre} | nitidez {f.nitidez:.0f} | {f.foto_del_dia}"]
            celdas.append(celda(raw, f.foto_del_dia, f.rotacion_desde_crudo, lineas))
        else:
            estado = f.estado_dia_final if isinstance(f.estado_dia_final, str) else "fuera del registro"
            celdas.append(celda(raw, None, 0, [f"{f.fecha:%Y-%m-%d} ({DIAS_SEMANA[f.fecha.weekday()]})",
                                               f"{encuadre} | {estado}"]))
    titulo = f"Foto del dia, {inicio:%Y-%m-%d} a {fin:%Y-%m-%d} | crudo + 180 grados"
    for ruta in guardar_hojas(destino, f"dias_{inicio:%Y-%m-%d}_{fin:%Y-%m-%d}", celdas, titulo):
        print(f"  {ruta}")


# ============================================================================
# Hitos
# ============================================================================

def crear_hitos(ruta: Path) -> None:
    if ruta.exists():
        print(f"{ruta} ya existe: no se modifica")
        return
    pd.DataFrame(HITOS_INICIALES, columns=COLUMNAS_HITOS).to_csv(ruta, index=False)
    print(f"Creado {ruta} con {len(HITOS_INICIALES)} hito(s)")


# ============================================================================
# Principal
# ============================================================================

def main() -> None:
    base = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--raw", type=Path, default=base / "data" / "raw_data")
    parser.add_argument("--datos", type=Path, default=base / "data" / "processed_data")
    parser.add_argument("--reportes", type=Path, default=base / "reports" / "hitos")
    parser.add_argument("--dias", nargs=2, metavar=("INICIO", "FIN"),
                        help="modo diario: foto del día de cada día del rango (AAAA-MM-DD AAAA-MM-DD)")
    args = parser.parse_args()
    args.reportes.mkdir(parents=True, exist_ok=True)
    dias = cargar(args.datos)

    if args.dias:
        inicio, fin = (pd.Timestamp(d) for d in args.dias)
        if fin < inicio:
            parser.error("--dias: la fecha final es anterior a la inicial")
        print(f"Hoja diaria {inicio:%Y-%m-%d} a {fin:%Y-%m-%d}:")
        hoja_diaria(dias, inicio, fin, args.raw, args.reportes)
        return

    semanas = seleccion_semanal(dias)
    salida = semanas[["semana_inicio", "encuadre_id", "ruta", "fecha_hora", "nitidez"]].copy()
    salida["semana_inicio"] = salida["semana_inicio"].dt.strftime("%Y-%m-%d")
    salida.to_csv(args.datos / "fotos_semanales.csv", index=False)
    crear_hitos(args.datos / "hitos.csv")

    print("Hojas semanales:")
    hojas_semanales(semanas, args.raw, args.reportes)

    # Resumen
    print("\nRESUMEN")
    print(semanas.groupby("encuadre_id").agg(semanas=("semana_inicio", "size"),
                                             sin_evidencia=("ruta", lambda s: int(s.isna().sum()))).to_string())
    repetidas = semanas.groupby("semana_inicio")["encuadre_id"].nunique()
    for semana in repetidas[repetidas > 1].index:
        print(f"Semana {semana:%Y-%m-%d} repartida entre encuadres "
              f"{', '.join(str(e) for e in semanas.loc[semanas['semana_inicio'].eq(semana), 'encuadre_id'])}")
    todas = pd.date_range(dias["semana_inicio"].min(), dias["semana_inicio"].max(), freq="7D")
    fuera = todas.difference(pd.DatetimeIndex(semanas["semana_inicio"].unique()))
    if len(fuera):
        print(f"Semanas sin ningún encuadre (no aparecen en las hojas): {', '.join(f'{s:%Y-%m-%d}' for s in fuera)}")
    print(f"\nGuardado en {args.datos / 'fotos_semanales.csv'} y {args.reportes}")


if __name__ == "__main__":
    main()
