"""Tabla final de fotografías utilizables y resumen diario recalculado.

Requiere haber ejecutado 01_inventario.py, 02_tramos_encuadre.py y 03_orientacion.py.
Genera:

  data/processed_data/fotos_utilizables.csv     una fila por fotografía del inventario
  data/processed_data/resumen_diario_final.csv  resumen diario con fotos_utiles y
                                                foto_del_dia calculados solo con fotos
                                                utilizables
  reports/revision_tramos/exclusion_<tipo>.jpg       muestra de fotos excluidas por tipo
  reports/revision_tramos/verificacion_crudo_exif6.jpg
  reports/revision_tramos/foto_del_dia_cambiada.jpg

resumen_diario.csv (de 01) no se sobrescribe: 02 y 03 lo leen, y reescribirlo desde
aquí haría que el resultado dependiera del orden en que se corrieron los scripts.

Regla para mostrar fotos (app, hojas de contacto, fotos reducidas): abrir con
cv2.IMREAD_IGNORE_ORIENTATION (píxeles crudos, sin aplicar la etiqueta EXIF) y girar
rotacion_desde_crudo grados. Los píxeles crudos están siempre al revés, así que es
180 en todas las fotos; si alguna vez se comprueba una excepción, va en
EXCEPCIONES_ROTACION_CRUDO.

Una foto es utilizable si:
  1. 01 la marcó EVALUADA (diurna, con luz suficiente, legible);
  2. su día muestra la obra según 02 (obra_visible) y está dentro de un tramo;
  3. tiene orientación: 03 no la dejó dudosa, o la duda era solo por una etiqueta EXIF
     errónea y la verificación en píxeles crudos confirma 180°;
  4. no cae en ninguna regla de calidad (ver abajo).

Tipos de exclusión por calidad (en este orden; umbrales al inicio del script):
  danada             bandas horizontales: las filas varían mucho más que las columnas
  sobreexpuesta      más de la mitad de los píxeles casi blancos
  nocturna_focos     oscura y con mucha subexposición (atardecer, faros y focos)
  empanada           casi sin bordes (nitidez muy baja) pero con contraste normal
  fuera_de_encuadre  superficie uniforme (techo); solo se aplica a fotos con orientación
                     dudosa, porque en fotos normales también atrapa atardeceres
  revisar            orientación dudosa sin ninguna de las anteriores

Uso:
  python src/04_fotos_utilizables.py
  python src/04_fotos_utilizables.py --procesos 4
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

# Reutiliza descriptor y ORB (02) y la comparación de orientación (03)
_spec = importlib.util.spec_from_file_location("orientacion", Path(__file__).with_name("03_orientacion.py"))
orient = importlib.util.module_from_spec(_spec)
sys.modules["orientacion"] = orient
_spec.loader.exec_module(orient)
te = orient.te

# --- Rotación para mostrar -------------------------------------------------------
ROTACION_DESDE_CRUDO = te.ROTACION_PARA_MOSTRAR  # 180, definida en 02
EXCEPCIONES_ROTACION_CRUDO: dict[str, int] = {}  # ruta -> rotación comprobada a mano

# --- Reglas de calidad (imagen cruda reducida a 640x512) --------------------------
# Calibradas con las 93 fotos de orientación dudosa revisadas a mano y verificadas en
# hojas de contacto sobre el resto de fotos que atrapan.
COCIENTE_FILAS_DANADA = 5.0     # |dif. entre filas| / |dif. entre columnas|; normal 1-2.5
BANDAS_DANADA = 3.0             # variación media del perfil vertical; normal < 1.5
PCT_SOBREEXPUESTA = 50.0        # % de píxeles > 240
BRILLO_NOCTURNA = 50.0          # brillo medio (0-255)
PCT_SUBEXPUESTA_NOCTURNA = 30.0 # % de píxeles < 20
NITIDEZ_EMPANADA = 100.0        # nitidez de 01 (Tenengrad); con vista normal > 1 000
DESVIACION_UNIFORME = 30.0      # desviación del gris; el techo da 8-28

# --- Hojas de contacto --------------------------------------------------------------
MINIATURA = (192, 154)
CALIDAD_JPG = 50
MAX_EJEMPLOS = 24
TIPOS = ["danada", "sobreexpuesta", "nocturna_focos", "empanada", "fuera_de_encuadre", "revisar"]


# ============================================================================
# Imágenes crudas (procesos paralelos)
# ============================================================================

def leer_crudo(raiz: str, ruta: str, color: bool = False) -> np.ndarray | None:
    """Píxeles tal como están en el JPG, sin aplicar la etiqueta EXIF."""
    modo = (cv2.IMREAD_COLOR if color else cv2.IMREAD_GRAYSCALE) | cv2.IMREAD_IGNORE_ORIENTATION
    try:
        return cv2.imdecode(np.fromfile(os.path.join(raiz, ruta), dtype=np.uint8), modo)
    except Exception:
        return None


def abrir_para_mostrar(raiz: str, ruta: str, rotacion: int = ROTACION_DESDE_CRUDO) -> np.ndarray | None:
    imagen = leer_crudo(raiz, ruta, color=True)
    if imagen is not None and rotacion == 180:
        imagen = cv2.rotate(imagen, cv2.ROTATE_180)
    return imagen


def tarea_calidad(tarea: tuple[str, str]) -> dict:
    cv2.setNumThreads(1)
    raiz, ruta = tarea
    imagen = leer_crudo(raiz, ruta, color=True)
    if imagen is None:
        return {"ruta": ruta}
    imagen = cv2.resize(imagen, (640, 512), interpolation=cv2.INTER_AREA)
    gris = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY).astype(np.float32)
    filas = np.abs(np.diff(gris, axis=0)).mean()
    columnas = np.abs(np.diff(gris, axis=1)).mean()
    return {"ruta": ruta,
            "desviacion": round(float(gris.std()), 2),
            "pct_sobreexpuesta": round(float((gris > 240).mean() * 100), 2),
            "cociente_filas": round(float(filas / (columnas + 1e-6)), 3),
            "bandas": round(float(np.abs(np.diff(gris.mean(axis=1))).mean()), 3)}


def preparar_crudo(raiz: str, ruta: str, rotar: bool):
    gris = leer_crudo(raiz, ruta)
    if gris is None:
        return None
    gris = cv2.resize(gris, te.TAMANO_ANALISIS, interpolation=cv2.INTER_AREA)
    if rotar:
        gris = cv2.rotate(gris, cv2.ROTATE_180)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gris)
    return te.descriptor_orientaciones(gris), cv2.ORB_create(nfeatures=te.ORB_PUNTOS).detectAndCompute(clahe, None)


def tarea_verificar_crudo(tarea: tuple[str, str, str]) -> dict:
    """Orientación de los píxeles crudos contra la referencia del tramo (cruda + 180°)."""
    cv2.setNumThreads(1)
    cv2.setRNGSeed(0)
    raiz, ruta, referencia = tarea
    foto = preparar_crudo(raiz, ruta, rotar=False)
    ref = preparar_crudo(raiz, referencia, rotar=ROTACION_DESDE_CRUDO == 180)
    decision = orient.decidir(orient.comparar(foto, ref))
    return {"ruta": ruta, **decision}


# ============================================================================
# Clasificación
# ============================================================================

def tipo_calidad(f: pd.Series, dudosa: bool) -> str:
    if f["cociente_filas"] > COCIENTE_FILAS_DANADA or f["bandas"] > BANDAS_DANADA:
        return "danada"
    if f["pct_sobreexpuesta"] >= PCT_SOBREEXPUESTA:
        return "sobreexpuesta"
    if f["brillo"] < BRILLO_NOCTURNA and f["pct_subexpuesta"] >= PCT_SUBEXPUESTA_NOCTURNA:
        return "nocturna_focos"
    if dudosa and f["desviacion"] < DESVIACION_UNIFORME:
        return "fuera_de_encuadre"
    if f["nitidez"] < NITIDEZ_EMPANADA:
        return "empanada"
    return "revisar" if dudosa else ""


def miniatura(raiz: Path, ruta: str | None, rotacion, lineas: list[str]) -> np.ndarray:
    ancho, alto = MINIATURA
    imagen = abrir_para_mostrar(str(raiz), ruta, rotacion) if isinstance(ruta, str) else None
    imagen = np.full((alto, ancho, 3), 225, np.uint8) if imagen is None else \
        cv2.resize(imagen, MINIATURA, interpolation=cv2.INTER_AREA)
    barra = np.zeros((orient.ALTO_ETIQUETA, ancho, 3), np.uint8)
    for i, linea in enumerate(lineas[:2]):
        cv2.putText(barra, linea, (3, 13 + 15 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA)
    marco = np.vstack([barra, imagen])
    marco[:, -1] = 255
    return marco


def guardar_hoja(ruta: Path, miniaturas: list[np.ndarray], titulo: list[str], columnas: int = 6) -> None:
    hoja = orient.rejilla(miniaturas, columnas, titulo)
    ok, datos = cv2.imencode(".jpg", hoja, [cv2.IMWRITE_JPEG_QUALITY, CALIDAD_JPG, cv2.IMWRITE_JPEG_OPTIMIZE, 1])
    if ok:
        datos.tofile(str(ruta))


def muestra(filas: pd.DataFrame, n: int = MAX_EJEMPLOS) -> pd.DataFrame:
    return filas if len(filas) <= n else filas.iloc[np.linspace(0, len(filas) - 1, n).astype(int)]


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
    dias = pd.read_csv(args.datos / "dias_encuadre.csv")
    tramos = pd.read_csv(args.datos / "tramos_encuadre.csv")
    orientacion = pd.read_csv(args.datos / "orientacion_fotos.csv")

    tabla = inventario[["ruta", "fecha", "fecha_hora", "hora", "estado", "brillo", "pct_subexpuesta", "nitidez"]].copy()
    tabla = tabla.merge(dias[["fecha", "tramo_id", "obra_visible", "estado_dia_revisado"]], on="fecha", how="left")
    tabla["tramo_id"] = tabla["tramo_id"].astype("Int64")
    tabla = tabla.merge(tramos[["tramo_id", "encuadre_id"]], on="tramo_id", how="left")
    tabla["encuadre_id"] = tabla["encuadre_id"].astype("Int64")
    tabla = tabla.merge(orientacion[["ruta", "rotacion", "exif_orientation", "estado_orientacion",
                                     "nivel_confianza", "motivo_duda"]], on="ruta", how="left")
    evaluada = tabla["estado"].eq("EVALUADA")
    print(f"Fotografías: {len(tabla):,} | EVALUADA: {int(evaluada.sum()):,} | procesos: {args.procesos}")

    # Métricas de calidad sobre los píxeles crudos
    with ProcessPoolExecutor(max_workers=args.procesos) as ejecutor:
        calidad = pd.DataFrame(list(ejecutor.map(tarea_calidad, [(raiz, r) for r in tabla.loc[evaluada, "ruta"]],
                                                 chunksize=32)))
    tabla = tabla.merge(calidad, on="ruta", how="left")
    print(f"Métricas de calidad calculadas ({time.time() - inicio:.0f} s)")

    # Rotación desde píxeles crudos: derivada de 03 + etiqueta EXIF, y verificada en
    # crudo cuando la etiqueta no es la habitual (3 o ausente).
    tabla["rotacion_desde_crudo"] = tabla["ruta"].map(EXCEPCIONES_ROTACION_CRUDO).fillna(ROTACION_DESDE_CRUDO).astype(int)
    exif = tabla["exif_orientation"]
    habitual = exif.isna() | exif.eq(3)
    derivada = (tabla["rotacion"] + np.where(exif.eq(3).fillna(False), 180, 0)) % 360
    tabla["verificacion_rotacion"] = np.select(
        [~evaluada, tabla["rotacion"].notna() & habitual & derivada.eq(ROTACION_DESDE_CRUDO),
         tabla["rotacion"].notna() & habitual],
        ["no evaluada", "03 + etiqueta EXIF", "CONTRADICE 03"], default="sin orientacion en 03")
    rarezas = tabla[evaluada & ~habitual & tabla["tramo_id"].notna()]
    referencia = tramos.set_index("tramo_id")["referencia_orientacion"]
    tareas = [(raiz, r, referencia[t]) for r, t in zip(rarezas["ruta"], rarezas["tramo_id"])]
    with ProcessPoolExecutor(max_workers=args.procesos) as ejecutor:
        verificadas = {v["ruta"]: v for v in ejecutor.map(tarea_verificar_crudo, tareas)}
    for idx in rarezas.index:
        v = verificadas[tabla.at[idx, "ruta"]]
        ok = v["estado_orientacion"] == "OK" and v["rotacion"] == tabla.at[idx, "rotacion_desde_crudo"]
        tabla.at[idx, "verificacion_rotacion"] = (
            f"crudo verificado {v['rotacion']} ({v['nivel_confianza'].lower()}, margen {v['confianza_orientacion']:.2f})"
            if ok else f"crudo NO verificado ({v['estado_orientacion']}, {v['rotacion']})")
    tabla["orientacion_resuelta"] = (tabla["estado_orientacion"].isin(["OK", "MANUAL"])
                                     | tabla["verificacion_rotacion"].str.startswith("crudo verificado"))

    # Tipo de calidad y utilizable
    dudosa = tabla["estado_orientacion"].eq("ORIENTACION_DUDOSA") & ~tabla["orientacion_resuelta"]
    tabla["tipo_exclusion"] = ""
    for idx in tabla.index[evaluada & tabla["desviacion"].notna()]:
        tabla.at[idx, "tipo_exclusion"] = tipo_calidad(tabla.loc[idx], bool(dudosa[idx]))
    sin_vista = ~tabla["obra_visible"].fillna(False).astype(bool) | tabla["tramo_id"].isna()
    tabla["motivo_exclusion"] = np.select(
        [~evaluada, sin_vista, dudosa, tabla["tipo_exclusion"].ne("")],
        [tabla["estado"], "DIA_SIN_VISTA_DE_OBRA", "ORIENTACION_DUDOSA", "CALIDAD"], default="")
    tabla.loc[tabla["motivo_exclusion"].isin(["DIA_SIN_VISTA_DE_OBRA"]) | ~evaluada, "tipo_exclusion"] = ""
    tabla["utilizable"] = tabla["motivo_exclusion"].eq("")

    columnas = ["ruta", "fecha", "fecha_hora", "hora", "tramo_id", "encuadre_id", "utilizable",
                "motivo_exclusion", "tipo_exclusion", "rotacion_desde_crudo", "verificacion_rotacion",
                "estado", "estado_dia_revisado", "estado_orientacion", "nivel_confianza", "rotacion",
                "exif_orientation", "brillo", "pct_subexpuesta", "pct_sobreexpuesta", "desviacion",
                "nitidez", "cociente_filas", "bandas"]
    tabla[columnas].to_csv(args.datos / "fotos_utilizables.csv", index=False)

    # Resumen diario recalculado
    utiles = tabla[tabla["utilizable"]].copy()
    momento = pd.to_datetime(utiles["fecha_hora"])
    # Misma definición que 01 (hora + minutos, primera en caso de empate) para que la foto
    # del día solo cambie cuando se excluyó la anterior.
    utiles["dif"] = (momento.dt.hour + momento.dt.minute / 60 - orient.te.HORA_REFERENCIA).abs()
    nueva_del_dia = utiles.loc[utiles.groupby("fecha")["dif"].idxmin()].set_index("fecha")["ruta"]
    final = resumen[["fecha", "dia_semana", "estado_dia", "fotos_total", "fotos_utiles", "foto_del_dia"]].rename(
        columns={"fotos_utiles": "fotos_evaluadas", "foto_del_dia": "foto_del_dia_inventario"})
    final = final.merge(dias[["fecha", "estado_dia_revisado", "tramo_id"]], on="fecha", how="left")
    final["tramo_id"] = final["tramo_id"].astype("Int64")
    final = final.merge(tramos[["tramo_id", "encuadre_id"]], on="tramo_id", how="left")
    final["encuadre_id"] = final["encuadre_id"].astype("Int64")
    final["fotos_utiles"] = final["fecha"].map(utiles.groupby("fecha").size()).fillna(0).astype(int)
    excluidas = tabla[tabla["motivo_exclusion"].isin(["ORIENTACION_DUDOSA", "CALIDAD"])].groupby("fecha").size()
    final["fotos_excluidas_calidad"] = final["fecha"].map(excluidas).fillna(0).astype(int)
    final["foto_del_dia"] = final["fecha"].map(nueva_del_dia)
    final["foto_del_dia_cambio"] = final["foto_del_dia"].ne(final["foto_del_dia_inventario"]) & final["foto_del_dia_inventario"].notna()
    final["estado_dia_final"] = np.select(
        [final["fotos_total"].eq(0), final["fotos_evaluadas"].eq(0), final["fotos_utiles"].eq(0)],
        ["SIN_FOTOS", "SIN_FOTOS_UTILES", "SIN_VISTA_DE_OBRA"], default="CON_EVIDENCIA")
    final["rotacion_desde_crudo"] = final["foto_del_dia"].map(tabla.set_index("ruta")["rotacion_desde_crudo"]).astype("Int64")
    final = final[["fecha", "dia_semana", "estado_dia", "estado_dia_revisado", "estado_dia_final", "tramo_id",
                   "encuadre_id", "fotos_total", "fotos_evaluadas", "fotos_utiles", "fotos_excluidas_calidad",
                   "foto_del_dia", "rotacion_desde_crudo", "foto_del_dia_inventario", "foto_del_dia_cambio"]]
    final.to_csv(args.datos / "resumen_diario_final.csv", index=False)

    # Hojas de contacto (regla de mostrar: crudo + 180°)
    args.reportes.mkdir(parents=True, exist_ok=True)
    for viejo in list(args.reportes.glob("exclusion_*.jpg")) + list(args.reportes.glob("verificacion_crudo_*.jpg")) \
            + list(args.reportes.glob("foto_del_dia_cambiada.jpg")):
        viejo.unlink()
    excl = tabla[tabla["tipo_exclusion"].ne("")].sort_values("fecha_hora")
    for tipo in TIPOS:
        filas = excl[excl["tipo_exclusion"].eq(tipo)]
        if filas.empty:
            continue
        mins = [miniatura(args.raw, f.ruta, f.rotacion_desde_crudo,
                          [str(f.fecha_hora), f"{f.motivo_exclusion.lower()} | n{f.nitidez:.0f} b{f.brillo:.0f}"])
                for f in muestra(filas).itertuples()]
        guardar_hoja(args.reportes / f"exclusion_{tipo}.jpg", mins,
                     [f"Excluidas por calidad, tipo {tipo}: {len(filas)} fotos (se muestran hasta {MAX_EJEMPLOS}), "
                      f"crudo + {ROTACION_DESDE_CRUDO} grados"])
    if len(rarezas):
        mins = []
        for f in rarezas.itertuples():
            vecinas = tabla[evaluada & tabla["fecha"].eq(f.fecha)].sort_values("fecha_hora")
            pos = vecinas.index.get_loc(f.Index)
            for idx in vecinas.index[max(0, pos - 1):pos + 2]:
                v = tabla.loc[idx]
                mins.append(miniatura(args.raw, v["ruta"], v["rotacion_desde_crudo"],
                                      [str(v["fecha_hora"]), f"EXIF {v['exif_orientation']} | crudo+{v['rotacion_desde_crudo']}"]))
        guardar_hoja(args.reportes / "verificacion_crudo_exif6.jpg", mins,
                     ["Fotos con etiqueta EXIF poco habitual (centro de cada grupo de 3) junto a sus vecinas, "
                      f"crudo + {ROTACION_DESDE_CRUDO} grados"], columnas=6)
    cambiadas = final[final["foto_del_dia_cambio"]]
    if len(cambiadas):
        mins = []
        for f in cambiadas.itertuples():
            mins.append(miniatura(args.raw, f.foto_del_dia_inventario, ROTACION_DESDE_CRUDO,
                                  [f"{f.fecha} antes", f.foto_del_dia_inventario[9:24]]))
            mins.append(miniatura(args.raw, f.foto_del_dia, ROTACION_DESDE_CRUDO,
                                  [f"{f.fecha} ahora", f.foto_del_dia[9:24] if isinstance(f.foto_del_dia, str) else "sin foto utilizable"]))
        guardar_hoja(args.reportes / "foto_del_dia_cambiada.jpg", mins,
                     ["Dias cuya foto del dia cambio al excluir fotos no utilizables (antes | ahora)"])

    # Resumen
    pd.set_option("display.width", 200)
    print("\nRESUMEN")
    print("Fotografías por motivo de exclusión:")
    print(tabla["motivo_exclusion"].replace("", "(utilizable)").value_counts().to_string())
    print(f"\nUtilizables: {int(tabla['utilizable'].sum()):,} de {int(evaluada.sum()):,} EVALUADA")
    print("\nTipo de exclusión (fotos EVALUADA de días con vista de la obra):")
    print(pd.crosstab(excl["tipo_exclusion"], excl["motivo_exclusion"], margins=True, margins_name="total").to_string())
    print("\nRotación desde crudo:")
    print(tabla.loc[evaluada, "rotacion_desde_crudo"].value_counts().to_string())
    print(tabla.loc[evaluada, "verificacion_rotacion"].value_counts().to_string())
    for f in rarezas.itertuples():
        g = tabla.loc[f.Index]
        print(f"  {f.ruta}: EXIF {g['exif_orientation']} | {g['verificacion_rotacion']} | utilizable {g['utilizable']}"
              f"{'' if g['utilizable'] else ' (' + g['motivo_exclusion'] + ')'}")
    print("\nEstado del día (revisado en 02 -> final):")
    print(pd.crosstab(final["estado_dia_revisado"], final["estado_dia_final"]).to_string())
    print(f"\nDías con foto del día distinta a la de 01: {int(final['foto_del_dia_cambio'].sum())}")
    if len(cambiadas):
        print(cambiadas[["fecha", "foto_del_dia_inventario", "foto_del_dia"]].to_string(index=False))
    del_dia = set(final["foto_del_dia"].dropna())
    malas = tabla[tabla["ruta"].isin(del_dia) & ~tabla["utilizable"]]
    print(f"Fotos del día no utilizables: {len(malas)}")
    print(f"\nGuardado en {args.datos} y {args.reportes} ({time.time() - inicio:.0f} s)")


if __name__ == "__main__":
    main()
