# Catastro Mining - Visor Satelital de Concesiones y Áreas Mineras

Visor satelital e interactivo de áreas y derechos mineros en Bolivia desarrollado con PostgreSQL/PostGIS, FastAPI (Python), MapLibre GL JS y Nginx.

## 🚀 Puesta en Marcha

### Requisitos Previos
- Docker (v20+)
- Docker Compose (v2+)

### Levantar el Stack de Servicios

1. Configurar variables de entorno iniciales:
   ```bash
   cp .env.example .env
   ```

2. Iniciar todos los contenedores:
   ```bash
   docker compose up -d --build
   ```

### 🌐 Puertos y Servicios Disponibles

- **Visor Web (Frontend)**: [http://localhost:8081](http://localhost:8081)
- **API Backend / Swagger Docs**: [http://localhost:8001/docs](http://localhost:8001/docs) *(ó [http://localhost:8081/api/docs](http://localhost:8081/api/docs))*
- **Salud del Stack**: [http://localhost:8081/health](http://localhost:8081/health)
- **Base de Datos PostGIS**: `localhost:5432`

---

## 🗺️ Poblado de Datos en el Mapa

El sistema cuenta con scripts integrados para la ingesta y preparación de las capas espaciales (**Departamentos**, **Municipios**, **Lugares Poblados** y **Concesiones Mineras**).

### 1. Departamentos y Municipios (Límites Político-Administrativos)

Carga los **343 municipios** de Bolivia e infiere automáticamente los **9 departamentos** mediante agregación espacial (`ST_Union`).

- **Fuente de datos**: `data/municipios_bolivia_2024.geojson` *(descargado de Lab TecnoSocial / GeoINE)*
- **Comando de carga**:
  ```bash
  docker compose exec backend python import_reference.py
  ```
- *(Opcional)* Si requieres descargar nuevamente la fuente GeoJSON oficial:
  ```bash
  curl -fL -o data/municipios_bolivia_2024.geojson https://lab-tecnosocial.github.io/municipios-bolivia-2024/municipios_bolivia_2024.geojson
  ```

### 2. Lugares Poblados y Comunidades (Capa de Puntos)

Ingesta **20.650 puntos** de comunidades, pueblos y ciudades en todo el territorio boliviano, registrando coordenadas WGS84 en la tabla PostGIS `poblaciones`.

- **Fuente de datos**: `data/populated_places.kml`
- **Comando de carga**:
  ```bash
  docker compose exec backend python import_populated_places.py
  ```

### 3. Catastro Minero (Polígonos y Concesiones Mineras)

Carga los **16.324 polígonos** de concesiones y solicitudes de derechos mineros con sus 27 atributos descriptivos.

- **Fuente de datos**: `data/catastro.kml` o `data/doc.kml`

Existen dos opciones para realizar la carga:

#### Opción A: Vía Línea de Comandos (Recomendado para la primera instalación)
```bash
docker compose exec backend python import_kml.py
```

#### Opción B: Desde el Panel de Administración Web
1. Ingresar al visor en [http://localhost:8081](http://localhost:8081).
2. Iniciar sesión como administrador (`admin` / `catastro2026`).
3. Abrir el **Panel Admin** desde el botón ubicado en la barra superior.
4. Seleccionar la opción **Cargar KML Actualizado**, adjuntar el archivo `.kml` (soporta archivos de hasta 500 MB) y presionar **Procesar y Cargar KML**.

---

### ⚡ Secuencia Completa de Poblado Inicial (Ejecución en un solo paso)

Para poblar la base de datos completamente desde cero con todas las capas espaciales:

```bash
docker compose exec backend python import_reference.py
docker compose exec backend python import_populated_places.py
docker compose exec backend python import_kml.py
```

---

## 🔑 Autenticación y Seguridad

El acceso al visor y a la API requiere autenticación JWT.

- **Credenciales por defecto**: `admin` / `catastro2026`.
- **Control Anticoncurrencia de Sesiones**: Solo se permite una sesión activa simultánea por usuario; al iniciar sesión en un dispositivo nuevo, los tokens anteriores quedan invalidados automáticamente.
- **Configuración de Producción**: Para un entorno de producción, define en el archivo `.env`:
  ```env
  JWT_SECRET_KEY=clave_secreta_super_segura
  ADMIN_USER=tu_usuario_admin
  ADMIN_PASSWORD=tu_contrasena_segura
  ```

---

## 🛰️ Endpoints Principales de la API

| Método | Endpoint | Descripción |
| :--- | :--- | :--- |
| `POST` | `/api/auth/login` | Autenticación de usuarios y obtención de token JWT. |
| `GET` | `/api/areas` | GeoJSON optimizado de polígonos mineros con atributos para data-driven styling. |
| `GET` | `/api/capas/departamentos` | GeoJSON con límites poligonales de los 9 departamentos. |
| `GET` | `/api/capas/poblaciones` | GeoJSON con los 20.650 puntos de poblaciones. |
| `GET` | `/api/reference/locations` | Listado jerárquico de departamentos y municipios para filtros dinámicos. |
| `GET` | `/api/seprec/buscar` | Consulta integrada en vivo de empresas registradas en SEPREC. |
| `GET` | `/api/seprec/detalle` | Ficha técnica completa de empresas SEPREC por NIT o Matrícula. |
| `POST` | `/api/admin/upload-kml` | Ingesta masiva de archivo KML de catastro minero (Admin). |

---

## 🗄️ Reinicialización de la Base de Datos

Si necesitas limpiar la base de datos y recrear las tablas desde cero:

```bash
docker compose down -v
docker compose up -d --build
```
Posteriormente, ejecuta la secuencia de poblado inicial descrita arriba.

