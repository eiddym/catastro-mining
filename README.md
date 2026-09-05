# Catastro Mining - Visor Satelital de Concesiones y Áreas Mineras

Visor satelital e interactivo de áreas y derechos mineros en Bolivia desarrollado con PostgreSQL/PostGIS, FastAPI (Python), MapLibre GL JS y Nginx.

## 🚀 Puesta en Marcha y Despliegue

### Requisitos Previos
- Docker (v20+)
- Docker Compose (v2+)

### Levantar el Stack de Servicios (Despliegue Cero-Configuración)

1. Configurar variables de entorno iniciales:
   ```bash
   cp .env.example .env
   ```

2. Iniciar todos los contenedores:
   ```bash
   docker compose up -d --build
   ```

> [!NOTE]
> **Poblado Automático Inicial**: Al desplegar el proyecto por primera vez, el backend de FastAPI detectará la base de datos y cargará **automáticamente** en segundo plano todas las capas espaciales incluidas en el repositorio (`data/`):
> - **Departamentos y Municipios**: 343 municipios de Bolivia y 9 departamentos autoderivados.
> - **Comunidades y Lugares Poblados**: 20.650 puntos de poblaciones.
> - **Catastro Minero Inicial**: 16.324 polígonos de concesiones mineras.

### 🌐 Puertos y Servicios Disponibles

- **Visor Web (Frontend)**: [http://localhost:8081](http://localhost:8081)
- **API Backend / Swagger Docs**: [http://localhost:8001/docs](http://localhost:8001/docs) *(ó [http://localhost:8081/api/docs](http://localhost:8081/api/docs))*
- **Salud del Stack**: [http://localhost:8081/health](http://localhost:8081/health)
- **Base de Datos PostGIS**: `localhost:5432`

---

## 🔄 Actualización Periódica del Catastro Minero (KML Mensual)

A partir de la puesta en marcha inicial del sistema, **toda actualización periódica del catastro minero (KML mensual) se debe realizar exclusivamente desde el Panel de Administración Web**:

1. Ingresar al visor en [http://localhost:8081](http://localhost:8081) (o la URL de tu servidor).
2. Iniciar sesión con credenciales de administrador (`admin` / `catastro2026`).
3. Abrir el **Panel Admin** desde el botón ubicado en la barra superior.
4. En el apartado **Actualizar Catastro Minero (KML Mensual)**:
   - Hacer clic en **Seleccionar archivo** y adjuntar el archivo `.kml` actualizado (ej. `doc.kml` o `catastro.kml`, soporta hasta 500 MB).
   - Presionar el botón **CARGAR E IMPORTAR KML**.
5. El sistema procesará el KML, actualizará los polígonos en PostGIS y refrescará el visor automáticamente.

---

## 🛠️ Comandos de Mantenimiento Avanzado (Opcionales por CLI)

*(No requeridos para el uso normal. Solo útiles si deseas re-ejecutar scripts manualmente por línea de comandos)*:

- **Re-importar Departamentos y Municipios**:
  ```bash
  docker compose exec backend python import_reference.py
  ```

- **Re-importar Comunidades y Poblaciones**:
  ```bash
  docker compose exec backend python import_populated_places.py
  ```

- **Re-importar Catastro Minero KML por CLI**:
  ```bash
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
| `POST` | `/api/admin/upload-kml` | Ingesta masiva de archivo KML de catastro minero (Panel Admin). |

---

## 🗄️ Reinicialización de la Base de Datos

Si necesitas limpiar la base de datos y recrear las tablas desde cero:

```bash
docker compose down -v
docker compose up -d --build
```
*(Al reiniciar, el sistema volverá a auto-poblar automáticamente todas las capas desde `data/`)*.


