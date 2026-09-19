# Ejecución y despliegue

## Local

```powershell
docker compose up -d --build
.\.venv\Scripts\python.exe -m pytest -v
npx --yes newman@6.2.1 run "postman/[inst] Lab1.postman_collection.json" -e "postman/[inst][local] Lab1.postman_environment.json"
```

API: http://localhost:8080/api/v1/persons. Documentación: http://localhost:8080/docs.
Detén cualquier Uvicorn local que esté usando el puerto 8080 antes de arrancar Compose.

## GitHub Actions

`Person API CI` ejecuta las pruebas unitarias, construye la imagen Docker, inicia
PostgreSQL y la API, y ejecuta la colección Postman. Solo después de pasar las
pruebas publica esa misma imagen en `ghcr.io/dra6666/lab1-template` con las
etiquetas `latest` y el SHA completo del commit. Los pull requests no publican.
La base de pruebas del runner se elimina al terminar, sin tocar Railway ni la base local.

En un fork puede ser necesario habilitar los workflows desde la pestaña Actions.
El workflow antiguo de Classroom se sustituyó: no escribe calificaciones en la
hoja del profesor ni ejecuta pruebas contra una URL de Heroku vacía.

## Railway: configuración inicial

Esta alternativa a Heroku requiere aceptación del profesor. La compilación se
realiza en GitHub Actions; Railway ejecuta la imagen ya construida.

1. Espera a que `Person API CI` termine correctamente en GitHub.
2. En el perfil de GitHub, abre Packages, el paquete `lab1-template` y sus
   Package settings. Cambia su visibilidad a Public para que Railway pueda
   descargarlo sin credenciales de registro. El repositorio público no implica
   que el paquete sea público automáticamente.
3. Dentro del proyecto Railway que contiene `Postgres`, crea un servicio desde
   **Docker Image** con `ghcr.io/dra6666/lab1-template:latest` y llámalo `api`.
4. En Variables del servicio **api**, añade:

   ```text
   DATABASE_URL=${{Postgres.DATABASE_URL}}
   PORT=8080
   ```

   Usa el nombre exacto del servicio de base de datos en la referencia. No copies
   la contraseña al repositorio. La conexión utiliza la red privada de Railway.
5. Configura el healthcheck en `/api/v1/persons`. Conserva el comando de inicio
   de la imagen y despliega los cambios.
6. En Networking del servicio api, genera un dominio público con puerto 8080.
   Abre `https://TU-DOMINIO/docs` y consulta `/api/v1/persons`.

La base de Railway es independiente de la local: no contendrá las personas
creadas en tu equipo. La tabla se crea automáticamente al iniciar la API.

## Comprobación del despliegue

La API está desplegada en https://lab1-template-production-893a.up.railway.app.
Su documentación está en https://lab1-template-production-893a.up.railway.app/docs.
El entorno Postman `postman/[inst][railway] Lab1.postman_environment.json`
contiene este dominio. Se verificaron las cinco operaciones con Newman.

Ejecuta manualmente `Railway API tests` desde Actions; usa ese dominio por defecto.
Si cambia, puedes configurar `RAILWAY_BASE_URL` en GitHub, Settings > Secrets and
variables > Actions > Variables, con la nueva URL HTTPS, sin `/docs` ni
`/api/v1/persons`. Actualiza también el entorno Postman. La colección crea una
persona de prueba y la elimina al terminar correctamente.

## Actualizaciones

El workflow `Person API CI` despliega automáticamente después de publicar la
imagen probada. Usa `ghcr.io/dra6666/lab1-template:SHA_COMPLETO_DEL_COMMIT`,
configura el healthcheck `/api/v1/persons` y espera a que Railway confirme el
estado SUCCESS del nuevo despliegue. Después comprueba la URL pública y ejecuta
Postman contra Railway. No construye en Railway ni usa Heroku CLI o webhooks.

Configuración inicial en GitHub, Settings > Secrets and variables > Actions:

- Secret `RAILWAY_TOKEN`: token de proyecto Railway para el entorno production,
  creado en Settings > Tokens del proyecto. No uses un token de cuenta.
- Variable opcional `RAILWAY_BASE_URL`: URL HTTPS si cambia el dominio actual.

El entorno se obtiene del token de proyecto y el servicio API se identifica por
el dominio público configurado; no necesitas guardar un ID de servicio. Los pull requests solo ejecutan CI;
el despliegue está limitado a master y nunca cancela otro despliegue en curso.
Si falta configuración o Railway rechaza el despliegue, el job falla explícitamente.
No se informa de éxito basándose únicamente en que responda una versión anterior.

Para volver a ejecutar el flujo completo, usa Actions > Person API CI > Run
workflow en master. `Railway API tests` sigue disponible para comprobar solo la API.
Si falla la versión nueva, revisa los logs en Railway; no se hace rollback
automático. Mantén Trial/Free según el presupuesto elegido; los créditos gratuitos
son limitados y no garantizan disponibilidad permanente.

Referencias:
- https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry
- https://docs.railway.com/services
- https://docs.railway.com/variables/reference

## Northflank (alternativa gratuita)

Railway queda como despliegue manual porque su API devolvio HTTP 403 incluso
con un Project Token. Para evitar pagos, usa Northflank Developer Sandbox y
confirma esta sustitucion con el profesor, ya que el enunciado original menciona
Heroku.

1. Crea un proyecto **Developer Sandbox** en Northflank.
2. Anade un servicio PostgreSQL y espera a que este disponible.
3. Anade un servicio desde el repositorio GitHub `DRA6666/lab1-template`.
   Northflank detectara el `Dockerfile` y construira la imagen.
4. En las variables del servicio API configura `PORT=8080` y asigna
   `DATABASE_URL` al valor de conexion que Northflank muestra para PostgreSQL.
   No guardes esa URL en GitHub porque contiene la contrasena.
5. Expone el puerto 8080 y genera un dominio HTTPS. Comprueba `/docs` y
   `/api/v1/persons`.
6. En GitHub, Settings > Secrets and variables > Actions > Variables, anade
   `NORTHFLANK_BASE_URL` con ese dominio, sin `/docs` ni una ruta API.
7. Ejecuta **Actions > Northflank API tests > Run workflow**. Newman creara y
   eliminara un registro temporal usando las cinco operaciones.

El workflow `Person API CI` ya no intenta desplegar en Railway: ejecuta las 14
pruebas, construye la imagen y la publica en GHCR. Asi un fallo de credenciales
del proveedor no bloquea la integracion continua.
