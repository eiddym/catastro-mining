import json
import os
from pathlib import Path

import psycopg2
from shapely.geometry import MultiPolygon, shape

DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgrespassword@db:5432/catastro_minero")
DEFAULT_PATH = "/app/data/municipios_bolivia_2024.geojson"


def as_multipolygon(geometry):
    parsed = shape(geometry)
    if parsed.geom_type == "Polygon":
        return MultiPolygon([parsed])
    if parsed.geom_type == "MultiPolygon":
        return parsed
    return None


def import_reference(path: str = DEFAULT_PATH) -> int:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"No existe la fuente: {source}")

    features = json.loads(source.read_text(encoding="utf-8"))["features"]
    inserted = 0
    with psycopg2.connect(DB_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute("TRUNCATE divisiones_politicas RESTART IDENTITY")
            for feature in features:
                properties = feature.get("properties", {})
                geometry = as_multipolygon(feature.get("geometry", {}))
                if geometry is None or geometry.is_empty:
                    continue
                department = properties.get("nombre_dep")
                municipality = properties.get("nombre_mun")
                if not department or not municipality:
                    continue
                code = "".join(str(properties.get(key, "")).zfill(2) for key in ("idep", "iprov", "imun"))
                cursor.execute(
                    """
                    INSERT INTO divisiones_politicas
                        (nivel, nombre, codigo_ine, departamento, geom)
                    VALUES (%s, %s, %s, %s, ST_Multi(ST_GeomFromText(%s, 4326)))
                    """,
                    ("municipio", municipality, code, department, geometry.wkt),
                )
                inserted += 1

            cursor.execute("""
                INSERT INTO divisiones_politicas (nivel, nombre, codigo_ine, departamento, geom)
                SELECT 'departamento', departamento, MIN(SUBSTRING(codigo_ine, 1, 2)), departamento,
                       ST_Multi(ST_Union(geom))
                FROM divisiones_politicas
                WHERE nivel = 'municipio'
                GROUP BY departamento
            """)
    print(f"Capas de referencia cargadas: {inserted} municipios y departamentos derivados.")
    return inserted


if __name__ == "__main__":
    import_reference()
