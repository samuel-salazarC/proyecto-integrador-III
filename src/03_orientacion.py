"""Orientación (0° o 180°) de cada fotografía EVALUADA.

Requiere haber ejecutado 01_inventario.py y 02_tramos_encuadre.py. Genera:

  data/processed_data/orientacion_fotos.csv   una fila por foto EVALUADA
  data/processed_data/tramos_encuadre.csv     agrega rotacion_predominante y su %
                                              (si se vuelve a correr 02, correr 03 después)
  reports/revision_tramos/orientacion_por_dia_AAAA-MM.jpg   foto del día por mes (crudo + 180°)
  reports/revision_tramos/orientacion_distinta_a_tramo.jpg  fotos que no siguen a su tramo
  reports/revision_tramos/orientacion_dudosa.jpg            muestra de fotos dudosas

Las fotografías originales solo se leen; no se rotan ni se modifican.

IMPORTANTE: la columna rotacion es relativa a la imagen CON LA ETIQUETA EXIF
Orientation (274) YA APLICADA. Es lo que hay que girar esa imagen para verla derecha
(cielo arriba). Los píxeles guardados en el JPG están siempre al revés; lo que cambia
es la etiqueta: hasta el 2025-10-09 ~15:30 las fotos traen Orientation = 3 ("girar
180°") y después no la traen. cv2.imread y cv2.imdecode aplican la etiqueta (es lo que
usan 02 y este script), Pillow no. Por eso cualquier script posterior debe abrir las
fotos con cv2.imread / cv2.imdecode, o con Pillow + ImageOps.exif_transpose(), y solo
después girar según rotacion. Con Image.open() a secas, el resultado sale al revés en
las fotos que traen la etiqueta. La columna exif_orientation guarda el valor de la
etiqueta (vacía si no existe) para comprobarlo. Dos fotos (20251007-132740 y
20251008-170442) traen Orientation = 6 por error: sus píxeles están al revés como los
demás, pero al aplicar la etiqueta quedan giradas 90°; por eso salen como
ORIENTACION_DUDOSA (rotacion solo admite 0 o 180).

Referencias
  - La foto del día (la más cercana a las 12:00) de FECHA_REFERENCIA_DERECHA, que el
    equipo confirmó derecha, es la referencia de su tramo.
  - Cada otro tramo usa su foto de referencia (calculada en 02) y se orienta con el
    mismo método contra la referencia ya orientada del tramo vecino. Si no comparten
    vista (p. ej. el cambio de encuadre de marzo 2026), se usa la orientación que 02
    dedujo para el tramo y se marca como supuesta para revisarla en las hojas, salvo
    que el equipo la haya confirmado a mano (CONFIRMACIONES_A_MANO). La comparación con
    el vecino se hace por la frontera (ver orientar_referencias).

Método por foto
  1. Descriptor de orientaciones (el mismo de 02): distancia d0 entre la foto tal cual y
     la referencia orientada, y d180 entre la foto girada 180° y la referencia. Girar la
     imagen 180° no cambia el histograma de cada celda (las orientaciones van de 0 a
     180°, sin signo); solo invierte el orden de las celdas, así que d180 sale exacto
     sin volver a calcular nada. Margen relativo = |d180 - d0| / (d180 + d0).
  2. ORB + RANSAC contra la misma referencia. ORB es invariante a la rotación, así que
     basta una comparación: la rotación estimada sale ~0° o ~180°.

  Se usa el descriptor como criterio principal y ORB como confirmación porque, al
  probarlo sobre las 19 044 fotos con tramo, ORB solo llegó a una conclusión en el ~60 %
  (falla con poca luz, neblina o cuando la escena ya cambió mucho respecto a la
  referencia). Cuando sí concluyó, coincidió con el descriptor en el 100 % de los casos.
  El descriptor decide en todas las fotos y se mantiene estable aunque cambie la luz.

  Decisión:
    ORB concluye y coincide             -> confianza ALTA
    ORB concluye y no coincide          -> ORIENTACION_DUDOSA
    ORB no concluye, margen >= MARGEN_MINIMO -> confianza MEDIA
    ORB no concluye, margen <  MARGEN_MINIMO -> ORIENTACION_DUDOSA
    foto fuera de todo tramo (sin vista de la obra) -> ORIENTACION_DUDOSA

Corrección manual: en revision_manual.csv, columna rotacion (0 o 180). Con ruta se
aplica a esa foto; sin ruta, a todas las fotos EVALUADA de la fecha.

Uso:
  python src/03_orientacion.py
  python src/03_orientacion.py --procesos 4
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
from PIL import Image

# Reutiliza descriptor, ORB y lectura de revision_manual.csv de 02_tramos_encuadre.py
_spec = importlib.util.spec_from_file_location(
    "tramos_encuadre", Path(__file__).with_name("02_tramos_encuadre.py"))
te = importlib.util.module_from_spec(_spec)
sys.modules["tramos_encuadre"] = te
_spec.loader.exec_module(te)

# --- Parámetros ---------------------------------------------------------------
FECHA_REFERENCIA_DERECHA = "2025-10-05"  # confirmada a mano: cielo arriba sin girar
# Orientación de tramos confirmada a mano en las hojas orientacion_por_dia: fecha dentro
# del tramo -> rotacion. Se usa cuando la cadena por la frontera no puede orientarlo.
CONFIRMACIONES_A_MANO = {
    "2026-03-04": 180,  # tramo desde el cambio de encuadre de marzo: revisadas 2026-03 y 2026-04
}
MARGEN_MINIMO = 0.08       # margen relativo del descriptor. Por debajo solo quedan fotos
                           # sin vista útil (en blanco, corruptas, lente empañado, focos
                           # de noche); por encima, todas las revisadas quedaron derechas.
                           # Con vista normal el margen está entre 0.15 y 0.55.
ORB_TOLERANCIA_GRADOS = 20.0  # ORB concluye si la rotación está a ±20° de 0° o de 180°
CELDAS_DESCRIPTOR = te.CELDAS[0] * te.CELDAS[1]

# Hojas de contacto
MINIATURA = (192, 154)
ALTO_ETIQUETA = 33
CALIDAD_JPG = 50
MAX_EJEMPLOS = 24
DIAS_SEMANA = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]


# ============================================================================
# Comparación (procesos paralelos)
# ============================================================================

_REFERENCIAS: dict[int, tuple] = {}


def girar_descriptor(v: np.ndarray) -> np.ndarray:
    """Descriptor de la imagen girada 180°: mismas celdas en orden inverso."""
    return v.reshape(CELDAS_DESCRIPTOR, te.BINS_ORIENTACION)[::-1].ravel()


def preparar(raiz: str, ruta: str, rotar: bool = False):
    gris = te.leer_gris(raiz, ruta)
    if gris is None:
        return None
    if rotar:
        gris = cv2.rotate(gris, cv2.ROTATE_180)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gris)
    return te.descriptor_orientaciones(gris), cv2.ORB_create(nfeatures=te.ORB_PUNTOS).detectAndCompute(clahe, None)


def comparar(foto, referencia) -> dict:
    """d0, d180 y ORB de una foto (cruda) contra una referencia ya orientada."""
    (vf, kf), (vr, kr) = foto, referencia
    m = te.comparar_orb(kf, kr)
    return {"dist_0": te.distancia(vf, vr), "dist_180": te.distancia(girar_descriptor(vf), vr),
            "orb_inliers": m["n_inliers"], "orb_frac_inliers": m["frac_inliers"],
            "orb_rotacion": m["rotacion"], "orb_escala": m["escala"]}


def iniciar(raiz: str, referencias: dict[int, tuple[str, int]]) -> None:
    cv2.setNumThreads(1)
    cv2.setRNGSeed(0)
    for tramo, (ruta, rotacion) in referencias.items():
        _REFERENCIAS[tramo] = preparar(raiz, ruta, rotacion == 180)


def tarea_exif(tarea: tuple[str, str]) -> tuple[str, int | None]:
    """Valor de la etiqueta EXIF Orientation (274); solo lee la cabecera."""
    raiz, ruta = tarea
    try:
        with Image.open(os.path.join(raiz, ruta)) as imagen:
            valor = imagen.getexif().get(274)
    except Exception:
        valor = None
    return ruta, None if valor is None else int(valor)


def tarea_foto(tarea: tuple[str, str, int]) -> dict:
    raiz, ruta, tramo = tarea
    foto = preparar(raiz, ruta)
    if foto is None or _REFERENCIAS.get(tramo) is None:
        return {"ruta": ruta, "error": True}
    return {"ruta": ruta, **comparar(foto, _REFERENCIAS[tramo])}


# ============================================================================
# Decisión
# ============================================================================

def decidir(c: dict) -> dict:
    d0, d180 = c["dist_0"], c["dist_180"]
    margen = abs(d180 - d0) / (d180 + d0) if (d180 + d0) > 0 else 0.0
    por_descriptor = 0 if d0 < d180 else 180

    orb = None
    giro = c["orb_rotacion"]
    if (c["orb_inliers"] >= te.MIN_INLIERS and c["orb_frac_inliers"] >= te.MIN_FRACCION_INLIERS
            and not np.isnan(giro) and abs(c["orb_escala"] - 1) < te.ESCALA_CAMBIO):
        giro = abs((giro + 180) % 360 - 180)
        if giro <= ORB_TOLERANCIA_GRADOS:
            orb = 0
        elif giro >= 180 - ORB_TOLERANCIA_GRADOS:
            orb = 180

    if orb is not None and orb != por_descriptor:
        estado, nivel, motivo, rotacion = "ORIENTACION_DUDOSA", "DUDOSA", "ORB y descriptor no coinciden", None
    elif orb is not None:
        estado, nivel, motivo, rotacion = "OK", "ALTA", "", por_descriptor
    elif margen >= MARGEN_MINIMO:
        estado, nivel, motivo, rotacion = "OK", "MEDIA", "", por_descriptor
    else:
        estado, nivel, motivo, rotacion = "ORIENTACION_DUDOSA", "DUDOSA", "margen bajo y ORB sin conclusion", None
    return {"rotacion": rotacion, "estado_orientacion": estado, "nivel_confianza": nivel,
            "confianza_orientacion": round(margen, 4), "rotacion_descriptor": por_descriptor,
            "rotacion_orb": orb, "orb_confirma": None if orb is None else orb == por_descriptor,
            "motivo_duda": motivo}


def orientar(raiz: str, ruta: str, ruta_ref: str, rotacion_ref: int) -> dict:
    """Orientación de una foto cruda contra otra foto de rotación conocida."""
    return decidir(comparar(preparar(raiz, ruta), preparar(raiz, ruta_ref, rotacion_ref == 180)))


def orientar_referencias(raiz: str, tramos: pd.DataFrame, resumen: pd.DataFrame,
                         dias: pd.DataFrame) -> pd.DataFrame:
    """Referencia orientada de cada tramo, propagando desde el tramo con la foto derecha.

    Comparar directamente referencias de tramos vecinos falla cuando las separan semanas
    de obra, así que se encadena por la frontera, donde las fotos son de días seguidos:
      referencia del vecino -> foto del día del vecino junto a la frontera
      -> foto del día del tramo nuevo junto a la frontera -> referencia del tramo nuevo.
    El eslabón que cruza la frontera debe confirmarlo ORB (confianza ALTA). Si algún
    eslabón falla, la orientación del tramo se marca como SUPUESTA.
    """
    del_dia = resumen.set_index("fecha")["foto_del_dia"]
    ancla_foto = del_dia.get(FECHA_REFERENCIA_DERECHA)
    if not isinstance(ancla_foto, str):
        raise SystemExit(f"No hay foto del día útil el {FECHA_REFERENCIA_DERECHA}")
    ancla = tramos[(tramos["fecha_inicio"] <= FECHA_REFERENCIA_DERECHA)
                   & (tramos["fecha_fin"] >= FECHA_REFERENCIA_DERECHA)]["tramo_id"]
    if ancla.empty:
        raise SystemExit(f"{FECHA_REFERENCIA_DERECHA} no está dentro de ningún tramo")
    ancla = int(ancla.iloc[0])
    visibles = dias[dias["obra_visible"]].sort_values("fecha")
    fotos_tramo = {int(t): g["foto_representativa"].tolist() for t, g in visibles.groupby("tramo_id")}
    por_id = tramos.set_index("tramo_id")

    refs = {ancla: {"referencia_orientacion": ancla_foto, "rotacion_referencia": 0,
                    "origen_referencia": f"foto del dia {FECHA_REFERENCIA_DERECHA}, confirmada a mano",
                    "confianza_referencia": 1.0}}
    ids = sorted(por_id.index.astype(int))
    for direccion in (1, -1):
        tramo = ancla + direccion
        while tramo in ids:
            vecino = tramo - direccion
            r = refs[vecino]
            # foto del vecino junto a la frontera y foto del tramo nuevo junto a la frontera
            borde_vecino = fotos_tramo[vecino][-1 if direccion == 1 else 0]
            borde_nuevo = fotos_tramo[tramo][0 if direccion == 1 else -1]
            foto = por_id.loc[tramo, "foto_referencia"]
            pasos = [(borde_vecino, "borde del tramo vecino"), (borde_nuevo, "borde del tramo"),
                     (foto, "referencia del tramo")]
            ruta_conocida, rot_conocida = r["referencia_orientacion"], r["rotacion_referencia"]
            confianzas, fallo = [], None
            for ruta, nombre in pasos:
                d = orientar(raiz, ruta, ruta_conocida, rot_conocida)
                # Al cruzar la frontera solo ORB prueba que es la misma escena: el
                # descriptor entre vistas distintas da un margen sin significado.
                cruza = nombre == "borde del tramo"
                if d["estado_orientacion"] != "OK" or (cruza and d["nivel_confianza"] != "ALTA"):
                    fallo = nombre
                    break
                confianzas.append(f"{d['nivel_confianza'].lower()} {d['confianza_orientacion']:.2f}")
                ruta_conocida, rot_conocida = ruta, d["rotacion"]
            if fallo is None:
                refs[tramo] = {"referencia_orientacion": foto, "rotacion_referencia": rot_conocida,
                               "origen_referencia": f"cadena desde el tramo {vecino} por la frontera "
                                                    f"({borde_vecino[:8]} -> {borde_nuevo[:8]}); "
                                                    f"confianzas: {', '.join(confianzas)}",
                               "confianza_referencia": min(float(c.split()[1]) for c in confianzas)}
            confirmada = next((rot for fecha, rot in CONFIRMACIONES_A_MANO.items()
                               if por_id.loc[tramo, "fecha_inicio"] <= fecha <= por_id.loc[tramo, "fecha_fin"]), None)
            if confirmada is not None:
                conflicto = (f"; OJO: la cadena daba {rot_conocida}" if fallo is None and rot_conocida != confirmada else "")
                refs[tramo] = {"referencia_orientacion": foto, "rotacion_referencia": confirmada,
                               "origen_referencia": "confirmada a mano en orientacion_por_dia"
                                                    + ("" if fallo is None else f" (la cadena falla en '{fallo}')")
                                                    + conflicto,
                               "confianza_referencia": 1.0}
            elif fallo is None:
                pass  # ya asignada arriba
            else:
                supuesta = 180 if bool(por_id.loc[tramo, "rotar_180_para_ver"]) else 0
                refs[tramo] = {"referencia_orientacion": foto, "rotacion_referencia": supuesta,
                               "origen_referencia": f"SUPUESTA: la cadena desde el tramo {vecino} falla en "
                                                    f"'{fallo}' (sin vista comun); se usa la orientacion "
                                                    f"de 02, revisar hojas",
                               "confianza_referencia": np.nan}
            tramo += direccion
    return pd.DataFrame.from_dict(refs, orient="index").rename_axis("tramo_id").reset_index().sort_values("tramo_id")


# ============================================================================
# Hojas de contacto
# ============================================================================

def miniatura(raiz: Path, ruta: str | None, lineas: list[str], alerta: bool = False) -> np.ndarray:
    """Miniatura con la etiqueta en una barra encima, para no tapar el cielo. Se muestra
    con la regla general (píxeles crudos + 180°), no con la rotacion de este script."""
    ancho, alto = MINIATURA
    imagen = te.abrir_para_mostrar(raiz / ruta) if isinstance(ruta, str) else None
    if imagen is None:
        imagen = np.full((alto, ancho, 3), 225, np.uint8)
    else:
        imagen = cv2.resize(imagen, MINIATURA, interpolation=cv2.INTER_AREA)
    barra = np.full((ALTO_ETIQUETA, ancho, 3), (0, 0, 190) if alerta else (0, 0, 0), np.uint8)
    for i, linea in enumerate(lineas[:2]):
        cv2.putText(barra, linea, (3, 13 + 15 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA)
    marco = np.vstack([barra, imagen])
    marco[:, -1] = 255  # separación entre columnas
    return marco


def rejilla(miniaturas: list[np.ndarray], columnas: int, titulo: list[str],
            encabezados: list[str] | None = None) -> np.ndarray:
    alto, ancho = miniaturas[0].shape[:2]
    vacia = np.full((alto, ancho, 3), 255, np.uint8)
    miniaturas = miniaturas + [vacia] * (-len(miniaturas) % columnas)
    cuerpo = np.vstack([np.hstack(miniaturas[i:i + columnas]) for i in range(0, len(miniaturas), columnas)])
    filas_texto = len(titulo) + (1 if encabezados else 0)
    cabecera = np.full((8 + 18 * filas_texto, cuerpo.shape[1], 3), 255, np.uint8)
    for i, linea in enumerate(titulo):
        cv2.putText(cabecera, linea, (6, 17 + 18 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
    for j, texto in enumerate(encabezados or []):
        (w, _), _ = cv2.getTextSize(texto, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.putText(cabecera, texto, (j * ancho + (ancho - w) // 2, 17 + 18 * len(titulo)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
    return np.vstack([cabecera, cuerpo])


def guardar_jpg(ruta: Path, imagen: np.ndarray) -> None:
    ok, datos = cv2.imencode(".jpg", imagen, [cv2.IMWRITE_JPEG_QUALITY, CALIDAD_JPG, cv2.IMWRITE_JPEG_OPTIMIZE, 1])
    if ok:
        datos.tofile(str(ruta))


def etiqueta(fila) -> tuple[list[str], bool]:
    if fila["estado_orientacion"] == "ORIENTACION_DUDOSA":
        return ["DUDOSA"], True
    texto = f"{int(fila['rotacion'])} grados"
    if fila["estado_orientacion"] == "MANUAL":
        texto += " (manual)"
    else:
        texto += f" | conf. {fila['nivel_confianza'].lower()}"
    return [texto], False


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
    archivo_tramos = args.datos / "tramos_encuadre.csv"
    tramos = pd.read_csv(archivo_tramos)
    dias = pd.read_csv(args.datos / "dias_encuadre.csv")
    evaluadas = inventario.loc[inventario["estado"].eq("EVALUADA"),
                               ["ruta", "fecha", "fecha_hora"]].reset_index(drop=True)
    evaluadas["tramo_id"] = evaluadas["fecha"].map(dias.set_index("fecha")["tramo_id"]).astype("Int64")

    # 1. Referencias orientadas por tramo
    refs = orientar_referencias(raiz, tramos, resumen, dias)
    print("Referencias por tramo:")
    print(refs[["tramo_id", "referencia_orientacion", "rotacion_referencia", "origen_referencia"]].to_string(index=False))

    # 2. Cada foto contra la referencia de su tramo
    con_tramo = evaluadas[evaluadas["tramo_id"].notna()]
    print(f"\nFotos EVALUADA: {len(evaluadas):,} | con tramo: {len(con_tramo):,} | procesos: {args.procesos}")
    referencias = {int(r.tramo_id): (r.referencia_orientacion, int(r.rotacion_referencia)) for r in refs.itertuples()}
    tareas = [(raiz, r, int(t)) for r, t in zip(con_tramo["ruta"], con_tramo["tramo_id"])]
    resultados = []
    with ProcessPoolExecutor(max_workers=args.procesos, initializer=iniciar,
                             initargs=(raiz, referencias)) as ejecutor:
        for n, res in enumerate(ejecutor.map(tarea_foto, tareas, chunksize=32), 1):
            resultados.append(res)
            if n % 4000 == 0:
                print(f"  {n:,}/{len(tareas):,} ({time.time() - inicio:.0f} s)", flush=True)
    comparaciones = pd.DataFrame(resultados)
    tabla = evaluadas.merge(comparaciones, on="ruta", how="left")
    decisiones = [decidir(f) if not f.get("error", False) and not pd.isna(f.get("dist_0")) else
                  {"rotacion": None, "estado_orientacion": "ORIENTACION_DUDOSA", "nivel_confianza": "DUDOSA",
                   "confianza_orientacion": np.nan, "rotacion_descriptor": None, "rotacion_orb": None,
                   "orb_confirma": None,
                   "motivo_duda": "fuera de los tramos (dia sin vista de la obra)" if pd.isna(f["tramo_id"])
                   else "no se pudo leer la foto"}
                  for f in tabla.to_dict("records")]
    tabla = pd.concat([tabla.drop(columns=["error"], errors="ignore"), pd.DataFrame(decisiones)], axis=1)
    tabla["referencia"] = tabla["tramo_id"].map(refs.set_index("tramo_id")["referencia_orientacion"])
    with ProcessPoolExecutor(max_workers=args.procesos) as ejecutor:
        exif = dict(ejecutor.map(tarea_exif, [(raiz, r) for r in tabla["ruta"]], chunksize=64))
    tabla["exif_orientation"] = tabla["ruta"].map(exif).astype("Int64")
    tabla["ajuste_manual"] = ""

    # 3. Correcciones a mano (columna rotacion de revision_manual.csv)
    revision = te.leer_revision(args.datos / "revision_manual.csv")
    revision = revision[revision["rotacion"].ne("")]
    registro = []
    for fila in revision.itertuples():
        try:
            valor = int(float(fila.rotacion))
        except ValueError:
            valor = None
        if valor not in (0, 180):
            registro.append(f"{fila.ruta or fila.fecha}: rotacion '{fila.rotacion}' no es 0 ni 180, se ignora")
            continue
        filtro = tabla["ruta"].eq(fila.ruta) if fila.ruta else tabla["fecha"].eq(fila.fecha)
        if not filtro.any():
            registro.append(f"{fila.ruta or fila.fecha}: no hay fotos EVALUADA, se ignora")
            continue
        previas = tabla.loc[filtro, "rotacion"].map(lambda r: "dudosa" if pd.isna(r) else str(int(r)))
        tabla.loc[filtro, "ajuste_manual"] = [f"rotacion {p}->{valor}" + (f" ({fila.nota})" if fila.nota else "")
                                              for p in previas]
        tabla.loc[filtro, ["rotacion", "estado_orientacion", "nivel_confianza"]] = [valor, "MANUAL", "MANUAL"]
        cambiadas = int((previas != str(valor)).sum())
        registro.append(f"{fila.ruta or fila.fecha}: rotacion {valor} en {int(filtro.sum())} foto(s), "
                        f"{cambiadas} cambiaron" + (f" ({fila.nota})" if fila.nota else ""))

    tabla["rotacion"] = pd.to_numeric(tabla["rotacion"]).astype("Int64")
    for columna in ("rotacion_descriptor", "rotacion_orb"):
        tabla[columna] = pd.to_numeric(tabla[columna]).astype("Int64")
    for columna in ("dist_0", "dist_180"):
        tabla[columna] = tabla[columna].round(4)
    columnas = ["ruta", "fecha", "fecha_hora", "tramo_id", "rotacion", "exif_orientation", "estado_orientacion",
                "nivel_confianza", "confianza_orientacion", "motivo_duda", "rotacion_descriptor",
                "rotacion_orb", "orb_confirma", "dist_0", "dist_180", "orb_inliers",
                "orb_frac_inliers", "orb_rotacion", "referencia", "ajuste_manual"]
    tabla[columnas].to_csv(args.datos / "orientacion_fotos.csv", index=False)

    # Rotación predominante por tramo
    decididas = tabla[tabla["rotacion"].notna()]
    filas = []
    for tramo in tramos["tramo_id"].astype(int):
        r = decididas.loc[decididas["tramo_id"].eq(tramo), "rotacion"]
        todas = tabla["tramo_id"].eq(tramo)
        predominante = int(r.mode().iloc[0]) if len(r) else pd.NA
        filas.append({"tramo_id": tramo, "rotacion_predominante": predominante,
                      "pct_rotacion_predominante": round(100 * r.eq(predominante).mean(), 2) if len(r) else np.nan,
                      "fotos_orientadas": len(r), "fotos_otra_rotacion": int(r.ne(predominante).sum()) if len(r) else 0,
                      "fotos_orientacion_dudosa": int((todas & tabla["rotacion"].isna()).sum())})
    por_tramo = pd.DataFrame(filas).merge(refs, on="tramo_id")
    nuevas = [c for c in por_tramo.columns if c != "tramo_id"]
    tramos = tramos.drop(columns=[c for c in nuevas if c in tramos.columns]).merge(por_tramo, on="tramo_id", how="left")
    tramos.to_csv(archivo_tramos, index=False)

    # Hojas de contacto
    args.reportes.mkdir(parents=True, exist_ok=True)
    for viejo in args.reportes.glob("orientacion_*.jpg"):
        viejo.unlink()
    por_ruta = tabla.set_index("ruta")
    calendario = resumen[["fecha", "foto_del_dia"]].copy()
    calendario["mes"] = calendario["fecha"].str[:7]
    for mes, grupo in calendario.groupby("mes"):
        primero = pd.Timestamp(f"{mes}-01")
        relleno = np.full((ALTO_ETIQUETA + MINIATURA[1], MINIATURA[0], 3), 255, np.uint8)
        mins = [relleno] * primero.day_of_week
        for fecha, foto in zip(grupo["fecha"], grupo["foto_del_dia"]):
            if isinstance(foto, str) and foto in por_ruta.index:
                fila = por_ruta.loc[foto]
                lineas, alerta = etiqueta(fila)
                mins.append(miniatura(args.raw, foto, [fecha] + lineas, alerta))
            else:
                mins.append(miniatura(args.raw, None, [fecha, "sin foto util"]))
        titulo = [f"Orientacion por dia, {mes}: foto del dia mostrada con la regla general (crudo + "
                  f"{te.ROTACION_PARA_MOSTRAR} grados); etiqueta = rotacion detectada con EXIF aplicada"]
        guardar = args.reportes / f"orientacion_por_dia_{mes}.jpg"
        guardar_jpg(guardar, rejilla(mins, 7, titulo, DIAS_SEMANA))

    def muestra(filas: pd.DataFrame) -> pd.DataFrame:
        if len(filas) <= MAX_EJEMPLOS:
            return filas
        return filas.iloc[np.linspace(0, len(filas) - 1, MAX_EJEMPLOS).astype(int)]

    predominante = tramos.set_index("tramo_id")["rotacion_predominante"]
    distintas = decididas[decididas["rotacion"].ne(decididas["tramo_id"].map(predominante))].sort_values("fecha_hora")
    if len(distintas):
        mins = [miniatura(args.raw, f.ruta,
                          [f"{f.fecha_hora} t{f.tramo_id}", f"{f.rotacion} grados | conf. {str(f.nivel_confianza).lower()}"])
                for f in muestra(distintas).itertuples()]
        guardar_jpg(args.reportes / "orientacion_distinta_a_tramo.jpg",
                       rejilla(mins, 6, [f"Fotos con rotacion distinta a la predominante de su tramo "
                                         f"({len(distintas)}; se muestran hasta {MAX_EJEMPLOS}), ya rotadas"]))
    dudosas = tabla[tabla["estado_orientacion"].eq("ORIENTACION_DUDOSA") & tabla["tramo_id"].notna()].sort_values("fecha_hora")
    if len(dudosas):
        mins = [miniatura(args.raw, f.ruta, [str(f.fecha_hora), f"margen {f.confianza_orientacion:.3f}"], True)
                for f in muestra(dudosas).itertuples()]
        guardar_jpg(args.reportes / "orientacion_dudosa.jpg",
                       rejilla(mins, 6, [f"Fotos con orientacion dudosa dentro de tramos ({len(dudosas)}; "
                                         f"se muestran hasta {MAX_EJEMPLOS}), crudo + {te.ROTACION_PARA_MOSTRAR} grados"]))

    # Resumen
    pd.set_option("display.width", 200)
    print("\nRESUMEN")
    etiquetas = tabla["rotacion"].map(lambda r: "dudosa" if pd.isna(r) else f"{int(r)}°")
    print("Fotos por rotación:")
    print(etiquetas.value_counts().to_string())
    print("\nPor nivel de confianza:")
    print(tabla["nivel_confianza"].value_counts().to_string())
    print("\nPor tramo:")
    print(tramos[["tramo_id", "fecha_inicio", "fecha_fin", "rotacion_predominante", "pct_rotacion_predominante",
                  "fotos_orientadas", "fotos_otra_rotacion", "fotos_orientacion_dudosa",
                  "rotacion_referencia"]].to_string(index=False))
    print("\nDudosas por motivo:")
    print(tabla.loc[tabla["estado_orientacion"].eq("ORIENTACION_DUDOSA"), "motivo_duda"].value_counts().to_string())

    print("\nComprobaciones:")
    # La rotación detectada debe seguir a la etiqueta EXIF: con Orientation = 3 el
    # decodificador ya giró la imagen (rotacion 0); sin ella, hay que girar (180).
    esperada = pd.Series(np.where(tabla["exif_orientation"].eq(3).fillna(False), 0, 180), index=tabla.index)
    print("  Etiqueta EXIF Orientation vs. rotacion:")
    texto = lambda serie, vacio: serie.map(lambda v: vacio if pd.isna(v) else str(int(v)))
    cruce = pd.crosstab(texto(tabla["exif_orientation"], "sin etiqueta").rename("exif_orientation"),
                        texto(tabla["rotacion"], "dudosa").rename("rotacion"))
    print("    " + cruce.to_string().replace("\n", "\n    "))
    no_coinciden = tabla[tabla["rotacion"].notna() & tabla["rotacion"].ne(esperada)]
    print(f"  Fotos donde rotacion no coincide con la etiqueta: {len(no_coinciden)}")
    if len(no_coinciden):
        print(no_coinciden[["ruta", "exif_orientation", "rotacion", "nivel_confianza",
                            "confianza_orientacion"]].head(20).to_string(index=False))
    con_etiqueta = tabla.loc[tabla["exif_orientation"].eq(3), "fecha_hora"]
    sin_etiqueta = tabla.loc[tabla["exif_orientation"].isna() & tabla["fecha_hora"].gt(con_etiqueta.max()), "fecha_hora"]
    if len(con_etiqueta) and len(sin_etiqueta):
        mezcla = tabla["exif_orientation"].isna() & tabla["fecha_hora"].lt(con_etiqueta.max())
        print(f"  Última foto con Orientation=3: {con_etiqueta.max()} | primera sin etiqueta: "
              f"{sin_etiqueta.min()} | fotos sin etiqueta antes de esa fecha: {int(mezcla.sum())}")
    for fecha, esperada in (("2025-10-05", 0), ("2025-10-12", 180)):
        r = tabla.loc[tabla["fecha"].eq(fecha), "rotacion"]
        print(f"  {fecha}: {r.eq(esperada).sum()}/{len(r)} fotos a {esperada}°, "
              f"{r.isna().sum()} dudosas, {(r.notna() & r.ne(esperada)).sum()} con la otra rotación")
    foto = "20251002/20251002-112649.jpg"
    if foto in por_ruta.index:
        f = tabla.set_index("ruta").loc[foto]
        print(f"  {foto}: rotacion {f['rotacion']} | {f['nivel_confianza']} | margen {f['confianza_orientacion']} "
              f"| ORB {f['orb_inliers']} inliers, {f['orb_rotacion']}°")
    if len(distintas):
        print("  Fotos con rotación distinta a la predominante de su tramo, por día:")
        resumen_distintas = distintas.groupby(["tramo_id", "fecha"]).agg(
            fotos=("ruta", "size"), primera=("fecha_hora", "min"), ultima=("fecha_hora", "max"))
        print(resumen_distintas.to_string())
    if registro:
        print("\nRevisión manual aplicada:")
        print("\n".join(f"  {r}" for r in registro))
    else:
        print("\nRevisión manual: sin filas con rotacion")
    print(f"\nGuardado en {args.datos / 'orientacion_fotos.csv'}, {archivo_tramos.name} y {args.reportes} "
          f"({time.time() - inicio:.0f} s)")


if __name__ == "__main__":
    main()
