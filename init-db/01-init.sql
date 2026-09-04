CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS areas_mineras (
    id SERIAL PRIMARY KEY,
    fid INTEGER,
    id_registro VARCHAR(50),
    fk_area_mi VARCHAR(50),
    codigo_unico VARCHAR(50),
    fecha_inscripcion VARCHAR(50),
    regional VARCHAR(100),
    area VARCHAR(200),
    tipo_area VARCHAR(100),
    tipo_actividad VARCHAR(100),
    actor_minero VARCHAR(255),
    municipio TEXT,
    provincia TEXT,
    departamento VARCHAR(100),
    departam_1 VARCHAR(100),
    provincia_ VARCHAR(100),
    canton_dec VARCHAR(100),
    certificacion VARCHAR(100),
    solicitud VARCHAR(100),
    extension NUMERIC(12, 4),
    unidad VARCHAR(50),
    cantidad_t INTEGER DEFAULT 0,
    cantidad_p INTEGER DEFAULT 0,
    cantidad_l INTEGER DEFAULT 0,
    hojas_cartograficas VARCHAR(100),
    nombre_hoj VARCHAR(100),
    padron VARCHAR(100),
    zona_utm INTEGER,
    geom GEOMETRY(Geometry, 4326) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_areas_geom ON areas_mineras USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_areas_actor ON areas_mineras (actor_minero);
CREATE INDEX IF NOT EXISTS idx_areas_extension ON areas_mineras (extension);
CREATE INDEX IF NOT EXISTS idx_areas_tipo ON areas_mineras (tipo_area);

ALTER TABLE areas_mineras
    ADD COLUMN IF NOT EXISTS fk_area_mi VARCHAR(50),
    ADD COLUMN IF NOT EXISTS departam_1 VARCHAR(100),
    ADD COLUMN IF NOT EXISTS provincia_ VARCHAR(100),
    ADD COLUMN IF NOT EXISTS canton_dec VARCHAR(100),
    ADD COLUMN IF NOT EXISTS nombre_hoj VARCHAR(100);

CREATE TABLE IF NOT EXISTS divisiones_politicas (
    id SERIAL PRIMARY KEY,
    nivel VARCHAR(20),
    nombre VARCHAR(150),
    codigo_ine VARCHAR(20),
    departamento VARCHAR(100),
    geom GEOMETRY(MultiPolygon, 4326)
);
CREATE INDEX IF NOT EXISTS idx_div_politica_geom ON divisiones_politicas USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_div_politica_nivel ON divisiones_politicas (nivel);

CREATE TABLE IF NOT EXISTS poblaciones (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(150),
    tipo VARCHAR(50),
    municipio VARCHAR(100),
    departamento VARCHAR(100),
    poblacion INTEGER DEFAULT 0,
    geom GEOMETRY(Point, 4326)
);
CREATE INDEX IF NOT EXISTS idx_poblaciones_geom ON poblaciones USING GIST (geom);
