# Catastro Mining

Visor satelital de áreas mineras con PostgreSQL/PostGIS, API FastAPI e ingestor KML.

## Puesta en marcha

Requisitos: Docker y Docker Compose.

```bash
cp .env.example .env
docker compose up -d --build
```

Coloca el archivo KML como `data/catastro.kml` y ejecuta la carga:

```bash
docker compose exec backend python import_kml.py
```

Servicios:

- Visor: http://localhost:8080
- API / Swagger: http://localhost:8000/docs
- Salud del stack: http://localhost:8080/health
- PostgreSQL: `localhost:5432`

La base de datos se inicializa automáticamente en el primer arranque. Para reinicializarla desde cero, elimina el volumen `catastro-mining_pgdata` cuando no necesites conservar los datos.

## Acceso y consultas

El visor solicita autenticación antes de consultar datos. Con la configuración de ejemplo, usa `admin` / `catastro2026`; en producción define `JWT_SECRET_KEY`, `ADMIN_USER` y `ADMIN_PASSWORD` en `.env`.

- `POST /api/auth/token`: obtiene el token JWT mediante `username` y `password` form-encoded.
- `GET /api/areas`: GeoJSON con los 27 atributos descriptivos del KML.
- `GET /api/areas/tabular`: resultados planos para la vista de lista.
- `GET /api/areas/metrics`: total, extensión acumulada y cantidad de actores.

Las consultas protegidas requieren `Authorization: Bearer <token>`.

## Capas de referencia

Coloca `departamentos.geojson` y `poblaciones.geojson` en `data/`. Los archivos deben estar en EPSG:4326. Cárgalos después de obtener un token de base de datos con:

```bash
API_PORT=8001 WEB_PORT=8081 POSTGRES_PORT=5434 docker compose exec -T backend ogr2ogr -f PostgreSQL \
	PG:"host=db user=postgres password=postgrespassword dbname=catastro_minero" \
	/app/data/departamentos.geojson -nln divisiones_politicas -append -t_srs EPSG:4326

API_PORT=8001 WEB_PORT=8081 POSTGRES_PORT=5434 docker compose exec -T backend ogr2ogr -f PostgreSQL \
	PG:"host=db user=postgres password=postgrespassword dbname=catastro_minero" \
	/app/data/poblaciones.geojson -nln poblaciones -append -t_srs EPSG:4326
```

Los endpoints protegidos son `GET /api/capas/departamentos` y `GET /api/capas/poblaciones?min_pob=0`. El visor activa ambas capas por defecto y permite ocultarlas desde el panel del mapa.

La fuente municipal 2024 se descarga desde Lab TecnoSocial y se carga con:

```bash
curl -fL -o data/municipios_bolivia_2024.geojson \
	https://lab-tecnosocial.github.io/municipios-bolivia-2024/municipios_bolivia_2024.geojson
API_PORT=8001 WEB_PORT=8081 POSTGRES_PORT=5434 docker compose exec -T backend python import_reference.py
```

El importador conserva `idep`, `iprov` e `imun` como `codigo_ine`, normaliza polígonos a `MultiPolygon`, carga las 343 unidades municipales y deriva los 9 límites departamentales mediante `ST_Union`. Las poblaciones requieren una fuente de puntos independiente.

### Lugares poblados KML

El archivo `data/populated_places.kml` aporta puntos de lugares poblados. Se ignoran sus polígonos residenciales y se cargan únicamente sus 20.650 elementos `Point`:

```bash
API_PORT=8001 WEB_PORT=8081 POSTGRES_PORT=5434 docker compose exec -T backend python import_populated_places.py
```

El KML usa coordenadas `latitud,longitud`; el importador las normaliza a PostGIS como `longitud,latitud` en EPSG:4326.

Este KML aporta lugares poblados y sirve como capa de puntos de respaldo. Para comunidades del Censo 2024, la fuente recomendada sigue siendo `censosbo`/geoportal del INE; los manzanos urbanos son una capa poligonal distinta.
