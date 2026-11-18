# Proyecto Integrador III · Visualización de datos

Visualización del avance del Puente María Aguilar (PROERI) a partir de las fotografías capturadas por el sistema dIAra de la Contraloría General de la República (CGR). El proyecto responde una pregunta ciudadana: **¿qué cambios se observan en la obra, cuándo ocurrieron y qué días no hay evidencia fotográfica?**

Curso: Visualización de datos (BCD 8215), Lead University · III cuatrimestre 2026.

## Datos

- **Fuente:** carpeta `proeri_proyecto1` del proyecto dIAra (CGR).
- **Contenido:** ~21 600 fotografías originales, del 2 de octubre de 2025 al 17 de abril de 2026, organizadas en carpetas por fecha (`YYYYMMDD/YYYYMMDD-HHMMSS.jpg`).
- **Uso:** la CGR confirmó que las imágenes son de uso público y no contienen información sensible.
- Las fotografías originales **no se incluyen en el repositorio** por su tamaño. Para reproducir el proyecto, copie las carpetas por fecha y `control.csv` en `data/raw_data/`. No se utilizan las carpetas `imagenes_tratadas` ni `analisis_cambio_camara`.

## Estructura

```
data/
  raw_data/        # fotografías originales (no versionadas)
  processed_data/  # tablas generadas por el procesamiento
```

## Instalación

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Equipo

- José Ignacio Sánchez Víquez
- Samuel Salazar Calvo
- Roselind Vargas
- Honwi Zhen Feng