import os
import xml.etree.ElementTree as ET
from pathlib import Path

import psycopg2

DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgrespassword@db:5432/catastro_minero")
DEFAULT_PATH = "/app/data/populated_places.kml"


def clean_population(value: str | None) -> int:
    try:
        return max(0, int((value or "0").strip()))
    except ValueError:
        return 0


def import_points(path: str = DEFAULT_PATH) -> int:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"No existe la fuente: {source}")

    inserted = 0
    with psycopg2.connect(DB_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute("TRUNCATE poblaciones RESTART IDENTITY")
            for _, placemark in ET.iterparse(source, events=("end",)):
                if placemark.tag.rsplit("}", 1)[-1] != "Placemark":
                    continue
                point = next((element for element in placemark.iter() if element.tag.rsplit("}", 1)[-1] == "Point"), None)
                coordinates = next((element for element in placemark.iter() if element.tag.rsplit("}", 1)[-1] == "coordinates"), None)
                if point is None or coordinates is None or not coordinates.text:
                    placemark.clear()
                    continue

                metadata = {}
                for element in placemark.iter():
                    if element.tag.rsplit("}", 1)[-1] == "SimpleData":
                        key = element.attrib.get("name")
                        if key:
                            metadata[key] = (element.text or "").strip()
                name = next(
                    ((element.text or "").strip() for element in placemark.iter()
                     if element.tag.rsplit("}", 1)[-1] == "name" and (element.text or "").strip()),
                    None,
                )
                name = name or metadata.get("name_latin") or metadata.get("adm3_name") or metadata.get("id") or "Lugar poblado"
                raw_coordinates = coordinates.text.strip().split(",")
                if len(raw_coordinates) < 2:
                    placemark.clear()
                    continue
                try:
                    latitude, longitude = float(raw_coordinates[0]), float(raw_coordinates[1])
                except ValueError:
                    placemark.clear()
                    continue
                if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
                    placemark.clear()
                    continue

                cursor.execute(
                    """
                    INSERT INTO poblaciones
                        (nombre, tipo, municipio, departamento, poblacion, geom)
                    VALUES (%s, %s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
                    """,
                    (
                        name[:150],
                        metadata.get("place", "pueblo")[:50],
                        metadata.get("adm3_name", "")[:100],
                        metadata.get("adm1_name", "")[:100],
                        clean_population(metadata.get("population")),
                        longitude,
                        latitude,
                    ),
                )
                inserted += 1
                placemark.clear()
    print(f"Poblaciones cargadas: {inserted} puntos.")
    return inserted


if __name__ == "__main__":
    import_points()
