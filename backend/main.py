import os
import uuid
from datetime import datetime, timedelta, timezone

import psycopg2
from fastapi import Depends, FastAPI, HTTPException, Query, status, Request, File, UploadFile
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from psycopg2.extras import RealDictCursor

from import_kml import run_import

app = FastAPI(title="Catastro Minero - API Corporativa", version="2.0.0")

origins = [item.strip() for item in os.getenv("CORS_ORIGINS", "http://localhost:8080,http://localhost:8081").split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgrespassword@db:5432/catastro_minero")
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-this-secret-in-production")
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "catastro2026")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")
password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

FIELDS = [
    "fid", "id_registro", "fk_area_mi", "codigo_unico", "fecha_inscripcion",
    "regional", "area", "tipo_area", "tipo_actividad", "actor_minero",
    "municipio", "provincia", "departamento", "departam_1", "provincia_",
    "canton_dec", "certificacion", "solicitud", "extension", "unidad",
    "cantidad_t", "cantidad_p", "cantidad_l", "hojas_cartograficas", "nombre_hoj",
    "padron", "zona_utm"
]
TABULAR_FIELDS = [
    "id", "codigo_unico", "fecha_inscripcion", "regional", "area", "tipo_area",
    "tipo_actividad", "actor_minero", "municipio", "provincia", "departamento",
    "certificacion", "solicitud", "extension", "unidad"
]


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "user"


class UserUpdateRole(BaseModel):
    role: str


class UserUpdateStatus(BaseModel):
    is_active: bool


class UserUpdatePassword(BaseModel):
    password: str


class ChangeOwnPassword(BaseModel):
    old_password: str
    new_password: str


class LoginJSON(BaseModel):
    username: str
    password: str


@app.on_event("startup")
def sync_admin_user():
    if not ADMIN_USER or not ADMIN_PASSWORD:
        return
    try:
        pw_hash = password_context.hash(ADMIN_PASSWORD)
        with psycopg2.connect(DB_URL) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT id FROM usuarios WHERE username = %s", (ADMIN_USER,))
                row = cursor.fetchone()
                if row:
                    cursor.execute(
                        "UPDATE usuarios SET password_hash = %s, role = 'admin', is_active = TRUE WHERE id = %s",
                        (pw_hash, row["id"])
                    )
                else:
                    cursor.execute(
                        "INSERT INTO usuarios (username, password_hash, role, is_active) VALUES (%s, %s, 'admin', TRUE)",
                        (ADMIN_USER, pw_hash)
                    )
                # Create GIST spatial indexes if not exist
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_areas_mineras_geom ON areas_mineras USING GIST (geom);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_divisiones_politicas_geom ON divisiones_politicas USING GIST (geom);")
            conn.commit()
        print(f"Usuario admin '{ADMIN_USER}' y los índices GIST PostGIS han sido verificados.")
    except Exception as e:
        print(f"Error en startup: {e}")


def get_db():
    connection = psycopg2.connect(DB_URL)
    try:
        yield connection
    finally:
        connection.close()


def current_user(token: str = Depends(oauth2_scheme)):
    error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido o expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    concurrent_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Sesión cerrada por inicio en otro dispositivo",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        username = payload.get("sub")
        role = payload.get("role")
        sess_uuid = payload.get("session_uuid")
        if not username or role not in ("admin", "user"):
            raise error

        with psycopg2.connect(DB_URL) as connection:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT is_active, session_uuid FROM usuarios WHERE username = %s", (username,))
                row = cursor.fetchone()
                if not row or not row["is_active"]:
                    raise error
                if row["session_uuid"] and sess_uuid and row["session_uuid"] != sess_uuid:
                    raise concurrent_error

        return payload
    except JWTError as exc:
        raise error from exc


def require_admin(user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Se requiere rol admin")
    return user


def filters_for(q, unidad, min_ext, max_ext, departamento=None, municipio=None, force_filter=True):
    if min_ext is not None and max_ext is not None and min_ext > max_ext:
        raise HTTPException(status_code=422, detail="min_ext no puede ser mayor que max_ext")

    if force_filter and not q and not unidad and min_ext is None and max_ext is None and not departamento and not municipio:
        return "1=0", []

    clauses, params = ["1=1"], []
    if q:
        wildcard = f"%{q}%"
        clauses.append("(actor_minero ILIKE %s OR codigo_unico ILIKE %s OR area ILIKE %s OR padron ILIKE %s)")
        params.extend([wildcard] * 4)
    if unidad:
        clauses.append("unidad = %s")
        params.append(unidad)
    if min_ext is not None:
        clauses.append("extension >= %s")
        params.append(min_ext)
    if max_ext is not None:
        clauses.append("extension <= %s")
        params.append(max_ext)
    if departamento:
        clauses.append("departamento ILIKE %s")
        params.append(f"%{departamento}%")
    if municipio:
        clauses.append("municipio ILIKE %s")
        params.append(f"%{municipio}%")
    return " AND ".join(clauses), params


@app.get("/health")
def health():
    return {"status": "ok"}


def do_login(username: str, password_raw: str):
    sess_uuid = str(uuid.uuid4())
    with psycopg2.connect(DB_URL) as connection:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                "SELECT id, username, password_hash, role FROM usuarios WHERE username = %s AND is_active = TRUE",
                (username,)
            )
            user = cursor.fetchone()
            if not user or not password_context.verify(password_raw, user["password_hash"]):
                raise HTTPException(status_code=400, detail="Credenciales incorrectas o usuario inactivo")
            cursor.execute("UPDATE usuarios SET session_uuid = %s WHERE id = %s", (sess_uuid, user["id"]))
        connection.commit()

    expires = datetime.now(timezone.utc) + timedelta(hours=12)
    token = jwt.encode(
        {"sub": user["username"], "role": user["role"], "session_uuid": sess_uuid, "exp": expires},
        SECRET_KEY,
        algorithm="HS256"
    )
    return {"access_token": token, "token_type": "bearer", "role": user["role"], "username": user["username"]}


@app.post("/api/auth/token")
def login_token(form_data: OAuth2PasswordRequestForm = Depends()):
    return do_login(form_data.username, form_data.password)


@app.post("/api/auth/login")
async def login_alias(request: Request):
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        body = await request.json()
        u = body.get("username", "")
        p = body.get("password", "")
    else:
        form = await request.form()
        u = form.get("username", "")
        p = form.get("password", "")
    return do_login(u, p)


@app.get("/api/auth/me")
def auth_me(user=Depends(current_user)):
    return {"username": user["sub"], "role": user["role"]}


@app.post("/api/auth/change-password")
def change_own_password(payload: ChangeOwnPassword, user=Depends(current_user), conn=Depends(get_db)):
    username = user["sub"]
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=422, detail="La nueva contraseña debe tener al menos 8 caracteres")
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute("SELECT id, password_hash FROM usuarios WHERE username = %s", (username,))
        row = cursor.fetchone()
        if not row or not password_context.verify(payload.old_password, row["password_hash"]):
            raise HTTPException(status_code=400, detail="La contraseña actual es incorrecta")
        new_hash = password_context.hash(payload.new_password)
        cursor.execute("UPDATE usuarios SET password_hash = %s WHERE id = %s", (new_hash, row["id"]))
    conn.commit()
    return {"message": "Contraseña cambiada exitosamente"}


# --- Reference Dropdowns Endpoint ---

@app.get("/api/reference/locations")
def get_locations(_: str = Depends(current_user), conn=Depends(get_db)):
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute("SELECT DISTINCT departamento FROM divisiones_politicas WHERE departamento IS NOT NULL AND departamento != '' ORDER BY departamento")
        deps = [r["departamento"] for r in cursor.fetchall()]
        cursor.execute("SELECT nombre AS municipio, departamento FROM divisiones_politicas WHERE nivel = 'municipio' ORDER BY departamento, nombre")
        muns = cursor.fetchall()
        return {"departamentos": deps, "municipios": muns}


# --- Módulo 4: PostGIS Spatial Intersects Validation Endpoint ---

@app.get("/api/areas/{area_id}/validacion-espacial")
def validacion_espacial(area_id: int, _: str = Depends(current_user), conn=Depends(get_db)):
    query = """
    SELECT a.id, a.codigo_unico, a.departamento AS depto_declarado, a.municipio AS mun_declarado,
           d.nombre AS depto_real, m.nombre AS mun_real
    FROM areas_mineras a
    LEFT JOIN divisiones_politicas d ON (d.nivel = 'departamento' OR d.nivel IS NULL) AND ST_Intersects(a.geom, d.geom)
    LEFT JOIN divisiones_politicas m ON m.nivel = 'municipio' AND ST_Intersects(a.geom, m.geom)
    WHERE a.id = %s
    LIMIT 1;
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(query, (area_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Área minera no encontrada")

        depto_dec = (row["depto_declarado"] or "").strip().upper()
        depto_real = (row["depto_real"] or "").strip().upper()
        mun_dec = (row["mun_declarado"] or "").strip().upper()
        mun_real = (row["mun_real"] or "").strip().upper()

        coincide_depto = (depto_dec == depto_real) if depto_real else False
        coincide_mun = (mun_dec == mun_real) if mun_real else False

        return {
            "id": row["id"],
            "codigo_unico": row["codigo_unico"],
            "depto_declarado": row["depto_declarado"],
            "mun_declarado": row["mun_declarado"],
            "depto_real": row["depto_real"] or "Fuera de límite / No intercepta",
            "mun_real": row["mun_real"] or "Fuera de límite / No intercepta",
            "coincide_departamento": coincide_depto,
            "coincide_municipio": coincide_mun,
            "coincidencia_global": coincide_depto and coincide_mun
        }


# --- Admin User Management Endpoints ---

@app.get("/api/admin/users")
def list_users(_: dict = Depends(require_admin), conn=Depends(get_db)):
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute("SELECT id, username, role, is_active, created_at FROM usuarios ORDER BY id ASC")
        return cursor.fetchall()


@app.post("/api/admin/users", status_code=201)
def create_user(user_data: UserCreate, _: dict = Depends(require_admin), conn=Depends(get_db)):
    if user_data.role not in ("admin", "user"):
        raise HTTPException(status_code=422, detail="El rol debe ser admin o user")
    if len(user_data.username.strip()) < 3 or len(user_data.password) < 8:
        raise HTTPException(status_code=422, detail="Usuario mínimo de 3 caracteres y contraseña mínima de 8")
    password_hash = password_context.hash(user_data.password)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                "INSERT INTO usuarios (username, password_hash, role) VALUES (%s, %s, %s) RETURNING id, username, role, is_active, created_at",
                (user_data.username.strip(), password_hash, user_data.role)
            )
            created = cursor.fetchone()
        conn.commit()
        return created
    except psycopg2.errors.UniqueViolation as exc:
        conn.rollback()
        raise HTTPException(status_code=409, detail="El usuario ya existe") from exc


@app.put("/api/admin/users/{user_id}/role")
def update_user_role(user_id: int, payload: UserUpdateRole, _: dict = Depends(require_admin), conn=Depends(get_db)):
    if payload.role not in ("admin", "user"):
        raise HTTPException(status_code=422, detail="Rol inválido. Debe ser admin o user")
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            "UPDATE usuarios SET role = %s WHERE id = %s RETURNING id, username, role, is_active, created_at",
            (payload.role, user_id)
        )
        updated = cursor.fetchone()
        if not updated:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
    conn.commit()
    return updated


@app.patch("/api/admin/users/{user_id}/status")
def update_user_status(user_id: int, payload: UserUpdateStatus, admin_user: dict = Depends(require_admin), conn=Depends(get_db)):
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute("SELECT username FROM usuarios WHERE id = %s", (user_id,))
        target = cursor.fetchone()
        if not target:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        if target["username"] == admin_user["sub"] and not payload.is_active:
            raise HTTPException(status_code=400, detail="No puedes desactivar tu propio usuario en sesión")
        cursor.execute(
            "UPDATE usuarios SET is_active = %s WHERE id = %s RETURNING id, username, role, is_active, created_at",
            (payload.is_active, user_id)
        )
        updated = cursor.fetchone()
    conn.commit()
    return updated


@app.put("/api/admin/users/{user_id}/password")
def update_user_password(user_id: int, payload: UserUpdatePassword, _: dict = Depends(require_admin), conn=Depends(get_db)):
    if len(payload.password) < 8:
        raise HTTPException(status_code=422, detail="La contraseña debe contener al menos 8 caracteres")
    new_hash = password_context.hash(payload.password)
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            "UPDATE usuarios SET password_hash = %s WHERE id = %s RETURNING id, username, role, is_active",
            (new_hash, user_id)
        )
        updated = cursor.fetchone()
        if not updated:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
    conn.commit()
    return {"message": "Contraseña actualizada exitosamente", "id": updated["id"], "username": updated["username"]}


@app.delete("/api/admin/users/{user_id}")
def delete_user(user_id: int, admin_user: dict = Depends(require_admin), conn=Depends(get_db)):
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute("SELECT username FROM usuarios WHERE id = %s", (user_id,))
        target = cursor.fetchone()
        if not target:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        if target["username"] == admin_user["sub"]:
            raise HTTPException(status_code=400, detail="No puedes eliminar tu propio usuario en sesión")
        cursor.execute("DELETE FROM usuarios WHERE id = %s", (user_id,))
    conn.commit()
    return {"message": f"Usuario {target['username']} eliminado exitosamente"}


@app.post("/api/admin/upload-kml")
async def upload_kml(
    file: UploadFile = File(...),
    _: dict = Depends(require_admin)
):
    if not file.filename.lower().endswith(('.kml', '.xml')):
        raise HTTPException(status_code=400, detail="El archivo debe tener extensión .kml o .xml")

    temp_path = f"/tmp/upload_{uuid.uuid4().hex}_{file.filename}"
    try:
        content = await file.read()
        with open(temp_path, "wb") as f:
            f.write(content)

        count = run_import(temp_path)

        return {
            "message": f"Archivo {file.filename} importado exitosamente.",
            "poligono_count": count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error procesando KML: {str(e)}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


# --- Mining & Geospatial Endpoints ---

@app.get("/api/areas")
def get_areas(
    q: str | None = None,
    unidad: str | None = None,
    min_ext: float | None = Query(None, ge=0),
    max_ext: float | None = Query(None, ge=0),
    departamento: str | None = None,
    municipio: str | None = None,
    todas: bool = False,
    limit: int = Query(2000, ge=1, le=50000),
    _: str = Depends(current_user),
    conn=Depends(get_db)
):
    force_filter = not todas and limit <= 5000
    where, params = filters_for(q, unidad, min_ext, max_ext, departamento, municipio, force_filter=force_filter)
    properties = ", ".join(f"'{field}', {field}" for field in FIELDS)
    query = f"SELECT jsonb_build_object('type','FeatureCollection','features',COALESCE(jsonb_agg(feature),'[]'::jsonb)) AS geojson FROM (SELECT jsonb_build_object('type','Feature','id',id,'geometry',ST_AsGeoJSON(geom)::jsonb,'properties',jsonb_build_object({properties})) AS feature FROM areas_mineras WHERE {where} ORDER BY id LIMIT %s) results"
    params.append(limit)
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(query, params)
        return cursor.fetchone()["geojson"]


@app.get("/api/areas/tabular")
def get_areas_tabular(
    q: str | None = None,
    unidad: str | None = None,
    min_ext: float | None = Query(None, ge=0),
    max_ext: float | None = Query(None, ge=0),
    departamento: str | None = None,
    municipio: str | None = None,
    todas: bool = False,
    limit: int = Query(500, ge=1, le=50000),
    _: str = Depends(current_user),
    conn=Depends(get_db)
):
    force_filter = not todas and limit <= 5000
    where, params = filters_for(q, unidad, min_ext, max_ext, departamento, municipio, force_filter=force_filter)
    params.append(limit)
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(f"SELECT {', '.join(TABULAR_FIELDS)} FROM areas_mineras WHERE {where} ORDER BY extension DESC NULLS LAST, id LIMIT %s", params)
        return cursor.fetchall()


@app.get("/api/areas/metrics")
def get_metrics(
    q: str | None = None,
    unidad: str | None = None,
    min_ext: float | None = Query(None, ge=0),
    max_ext: float | None = Query(None, ge=0),
    departamento: str | None = None,
    municipio: str | None = None,
    todas: bool = False,
    limit: int = Query(2000, ge=1, le=50000),
    _: str = Depends(current_user),
    conn=Depends(get_db)
):
    force_filter = not todas and limit <= 5000
    where, params = filters_for(q, unidad, min_ext, max_ext, departamento, municipio, force_filter=force_filter)
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(f"SELECT COUNT(*) AS total, COALESCE(SUM(extension), 0) AS extension_total, COUNT(DISTINCT actor_minero) AS actores FROM areas_mineras WHERE {where}", params)
        return cursor.fetchone()


@app.get("/api/agrupado-apm")
def get_agrupado_apm(
    min_ext: float = Query(1000, ge=0),
    max_ext: float = Query(8000, ge=0),
    unidad: str = "CUADRICULA",
    _: str = Depends(current_user),
    conn=Depends(get_db)
):
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute("SELECT actor_minero, COUNT(*) AS total_concesiones, SUM(extension) AS extension_total, unidad FROM areas_mineras WHERE unidad = %s AND extension BETWEEN %s AND %s GROUP BY actor_minero, unidad ORDER BY extension_total DESC", (unidad, min_ext, max_ext))
        return cursor.fetchall()


@app.get("/api/capas/departamentos")
def get_departamentos(_: str = Depends(current_user), conn=Depends(get_db)):
    query = """
    SELECT jsonb_build_object(
        'type', 'FeatureCollection',
        'features', COALESCE(jsonb_agg(jsonb_build_object(
            'type', 'Feature', 'id', id,
            'geometry', ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom, 0.005))::jsonb,
            'properties', jsonb_build_object('nombre', nombre, 'nivel', nivel,
                'codigo_ine', codigo_ine, 'departamento', departamento)
        )), '[]'::jsonb)
    ) AS geojson
    FROM divisiones_politicas
    WHERE nivel = 'departamento' OR nivel IS NULL
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(query)
        return cursor.fetchone()["geojson"]


@app.get("/api/capas/municipios")
def get_municipios(_: str = Depends(current_user), conn=Depends(get_db)):
    query = """
    SELECT jsonb_build_object(
        'type', 'FeatureCollection',
        'features', COALESCE(jsonb_agg(jsonb_build_object(
            'type', 'Feature', 'id', id,
            'geometry', ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom, 0.001))::jsonb,
            'properties', jsonb_build_object('nombre', nombre, 'codigo_ine', codigo_ine,
                'departamento', departamento)
        )), '[]'::jsonb)
    ) AS geojson
    FROM divisiones_politicas
    WHERE nivel = 'municipio'
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(query)
        return cursor.fetchone()["geojson"]


@app.get("/api/capas/poblaciones")
def get_poblaciones(min_pob: int = Query(0, ge=0), limit: int = Query(5000, ge=1, le=50000), _: str = Depends(current_user), conn=Depends(get_db)):
    query = """
    SELECT jsonb_build_object(
        'type', 'FeatureCollection',
        'features', COALESCE(jsonb_agg(feature), '[]'::jsonb)
    ) AS geojson
    FROM (
        SELECT jsonb_build_object(
            'type', 'Feature', 'id', id,
            'geometry', ST_AsGeoJSON(geom)::jsonb,
            'properties', jsonb_build_object('nombre', nombre, 'tipo', tipo,
                'municipio', municipio, 'departamento', departamento,
                'poblacion', poblacion)
        ) AS feature
        FROM poblaciones
        WHERE poblacion >= %s
        ORDER BY poblacion DESC, id
        LIMIT %s
    ) results
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(query, (min_pob, limit))
        return cursor.fetchone()["geojson"]


def clean_seprec_query(q: str) -> str:
    if not q:
        return ""
    import re
    s = q.strip()
    patterns = [
        r'\bs\.?\s*r\.?\s*l\.?\b',
        r'\bs\.?\s*a\.?\s*m\.?\b',
        r'\bs\.?\s*a\.?\b',
        r'\br\.?\s*l\.?\b',
        r'\bltda\.?\b',
        r'\bcoop\.?\b',
        r'\bcooperativa\b',
        r'\bsociedad\s+de\s+responsabilidad\s+limitada\b',
        r'\bsociedad\s+anonima\b',
        r'\bsoc\.?\s*anonima\b',
    ]
    cleaned = s
    for pat in patterns:
        cleaned = re.sub(pat, '', cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace('.', ' ').replace(',', ' ').replace('-', ' ').replace('_', ' ').replace('/', ' ')
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    if not cleaned:
        cleaned = s.replace('.', '').replace(',', '').strip()
    return cleaned


@app.get("/api/seprec/buscar")
def buscar_seprec(
    filtro: str = Query(..., description="Texto de búsqueda para empresa en SEPREC"),
    limite: int = Query(10, ge=1, le=100),
    pagina: int = Query(1, ge=1),
    _: str = Depends(current_user)
):
    import urllib.request
    import urllib.parse
    import json

    search_query = clean_seprec_query(filtro)
    if not search_query:
        return {"finalizado": True, "mensaje": "Búsqueda vacía", "datos": {"total": 0, "filas": []}}

    encoded_filtro = urllib.parse.quote(search_query)
    seprec_url = f"https://servicios.seprec.gob.bo/api/empresas/buscarEmpresas?filtro={encoded_filtro}&tipoFiltro=nombre&limite={limite}&pagina={pagina}"

    req = urllib.request.Request(
        seprec_url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw_data = resp.read().decode("utf-8")
            return json.loads(raw_data)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error al comunicar con la API de SEPREC: {str(e)}"
        )


@app.get("/api/seprec/detalle")
def detalle_seprec(
    id_empresa: str = Query(..., description="ID de la empresa en SEPREC"),
    id_establecimiento: str = Query(None, description="ID del establecimiento en SEPREC"),
    _: str = Depends(current_user)
):
    import urllib.request
    import json

    emp_id = id_empresa.strip()
    est_id = (id_establecimiento or emp_id).strip()

    if not emp_id:
        raise HTTPException(status_code=400, detail="El id_empresa es requerido.")

    detail_url = f"https://servicios.seprec.gob.bo/api/empresas/informacionBasicaEmpresa/{emp_id}/establecimiento/{est_id}"

    req = urllib.request.Request(
        detail_url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://consulta.seprec.gob.bo",
            "Referer": "https://consulta.seprec.gob.bo/"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw_data = resp.read().decode("utf-8")
            return json.loads(raw_data)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error al obtener detalle de la empresa desde SEPREC: {str(e)}"
        )


