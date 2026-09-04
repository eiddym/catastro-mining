import os
import xml.etree.ElementTree as ET

import psycopg2
from bs4 import BeautifulSoup
from shapely.geometry import Polygon
from shapely.validation import explain_validity

DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgrespassword@localhost:5432/catastro_minero",
)
KML_NAMESPACE = {"kml": "http://www.opengis.net/kml/2.2"}


def clean_number(value: str | None) -> float:
    if not value:
        return 0.0
    normalized = value.strip().replace(".", "").replace(",", ".")
    try:
        return float(normalized)
    except ValueError:
        return 0.0


def clean_int(value: str | None, default: int = 0) -> int:
    try:
        return int((value or "").strip())
    except ValueError:
        return default


def parse_metadata(description: str) -> dict[str, str]:
    soup = BeautifulSoup(description, "html.parser")
    metadata = {}
    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) == 2:
            metadata[cells[0].get_text(strip=True)] = cells[1].get_text(strip=True)
    return metadata


def parse_polygon(placemark: ET.Element) -> Polygon | None:
    coordinates = placemark.find(".//kml:coordinates", KML_NAMESPACE)
    if coordinates is None or not coordinates.text:
        return None

    points = []
    for coordinate in coordinates.text.strip().split():
        parts = coordinate.split(",")
        if len(parts) >= 2:
            try:
                points.append((float(parts[0]), float(parts[1])))
            except ValueError:
                continue

    if len(points) < 3:
        return None
    polygon = Polygon(points)
    if not polygon.is_valid:
        repaired = polygon.buffer(0)
        if repaired.is_empty or not repaired.is_valid:
            print(f"Geometría inválida omitida: {explain_validity(polygon)}")
            return None
        polygon = repaired
    return polygon


INSERT_SQL = """
INSERT INTO areas_mineras (
    fid, id_registro, fk_area_mi, codigo_unico, fecha_inscripcion, regional, area,
    tipo_area, tipo_actividad, actor_minero, municipio, provincia, departamento,
    departam_1, provincia_, canton_dec,
    certificacion, solicitud, extension, unidad, cantidad_t, cantidad_p,
    cantidad_l, hojas_cartograficas, nombre_hoj, padron, zona_utm, geom
) VALUES (
    %s, LEFT(CAST(%s AS text), 50), LEFT(CAST(%s AS text), 50), LEFT(CAST(%s AS text), 50),
    LEFT(CAST(%s AS text), 50), LEFT(CAST(%s AS text), 100), LEFT(CAST(%s AS text), 200),
    LEFT(CAST(%s AS text), 100), LEFT(CAST(%s AS text), 100), LEFT(CAST(%s AS text), 255),
    %s, %s, LEFT(CAST(%s AS text), 100), LEFT(CAST(%s AS text), 100),
    LEFT(CAST(%s AS text), 100), LEFT(CAST(%s AS text), 100), LEFT(CAST(%s AS text), 100),
    LEFT(CAST(%s AS text), 100), %s, LEFT(CAST(%s AS text), 50), %s, %s, %s,
    LEFT(CAST(%s AS text), 100), LEFT(CAST(%s AS text), 100), LEFT(CAST(%s AS text), 100),
    %s, ST_SetSRID(ST_GeomFromText(%s), 4326)
)
"""


def run_import(kml_path: str = "/app/data/catastro.kml") -> int:
    if not os.path.exists(kml_path):
        print(f"Archivo {kml_path} no encontrado.")
        return 0

    root = ET.parse(kml_path).getroot()
    inserted = 0
    with psycopg2.connect(DB_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute("TRUNCATE areas_mineras RESTART IDENTITY")
            for placemark in root.findall(".//kml:Placemark", KML_NAMESPACE):
                description = placemark.find("kml:description", KML_NAMESPACE)
                polygon = parse_polygon(placemark)
                if description is None or not description.text or polygon is None:
                    continue

                metadata = parse_metadata(description.text)
                cursor.execute(
                    INSERT_SQL,
                    (
                        clean_int(metadata.get("FID")),
                        metadata.get("id_registr"),
                        metadata.get("fk_area_mi"),
                        metadata.get("codigo_uni"),
                        metadata.get("fecha_insc"),
                        metadata.get("regional"),
                        metadata.get("area"),
                        metadata.get("tipo_area_"),
                        metadata.get("tipo_activ"),
                        metadata.get("actor_mine"),
                        metadata.get("municipio"),
                        metadata.get("provincia"),
                        metadata.get("departamen"),
                        metadata.get("departam_1"),
                        metadata.get("provincia_"),
                        metadata.get("canton_dec"),
                        metadata.get("certificac"),
                        metadata.get("solicitud_"),
                        clean_number(metadata.get("extension")),
                        metadata.get("unidad"),
                        clean_int(metadata.get("cantidad_t")),
                        clean_int(metadata.get("cantidad_p")),
                        clean_int(metadata.get("cantidad_l")),
                        metadata.get("hojas_cart"),
                        metadata.get("nombre_hoj"),
                        metadata.get("padron"),
                        clean_int(metadata.get("zona"), default=19),
                        polygon.wkt,
                    ),
                )
                inserted += 1
    print(f"Carga completa: {inserted} registros espaciales insertados.")
    return inserted


if __name__ == "__main__":
    run_import()
