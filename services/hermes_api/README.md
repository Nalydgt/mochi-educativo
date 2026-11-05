# Cancelación de peticiones HTTP de Hermes

Parche pequeño del servidor Hermes instalado, separado del proveedor de memoria.
Las peticiones no progresivas a `chat/completions` y `responses`, sin
`Idempotency-Key`, vigilaban únicamente el final del agente. Al cerrar la
pasarela su conexión por tiempo agotado, el agente podía seguir usando el modelo.

El parche vincula cada una de esas peticiones a su propia conexión, conserva una
referencia a su propio agente y utiliza la interrupción fuerte y limpieza selectiva
que Hermes ya aplica al desconectarse SSE. Mantiene vivo el propietario del
trabajador hasta que este termine; una segunda cancelación del handler no pierde
la tarea de limpieza. No interrumpe otros agentes ni reinicia modelos.

Las solicitudes con `Idempotency-Key` conservan el cómputo compartido y protegido
de Hermes: otro suscriptor o un reintento puede necesitar el resultado de una
acción. El formato final, la memoria y las rutas progresivas se conservan.

`patch.py` exige el SHA256 y los tres contextos exactos del archivo revisado de
la imagen instalada `nousresearch/hermes-agent:v2026.9.24`. Un cambio de imagen
requiere volver a revisar el código. La preparación no modifica el original:

```powershell
python services/hermes_api/patch.py prepare .runtime/hermes-api-upstream/api_server_openai_routes.py --output .runtime/hermes-api-candidate.py
uv run --project gateway --extra test python -m pytest services/hermes_api -q
```

Para aplicarlo en el contenedor, colocar juntos `patch.py` y
`disconnect_guard.py`, y ejecutar `patch.py apply` sobre
`/opt/hermes/gateway/platforms/api_server_openai_routes.py`, con `--backup` en un
directorio nuevo del volumen privado `/opt/data`. Comprueba y respalda el archivo
antes de sustituirlo atómicamente, manteniendo sus permisos y propietario.
El comando nunca reinicia servicios. La activación del proceso API se coordina
por separado, una vez hayan terminado sus peticiones activas.

La instalación vigente conserva los cuatro archivos `sitecustomize.py`,
`runtime_hook.py`, `patch.py` y `disconnect_guard.py` en
`/opt/data/mochi-api-runtime-v1`, dentro del volumen persistente. La variable
adicional de catálogo `PYTHONPATH` antepone ese directorio y conserva cualquier
valor previo. `loaded/` debe ser escribible por el UID/GID del servicio.

El cargador interviene únicamente al importar
`gateway.platforms.api_server_openai_routes`: comprueba el hash de la fuente,
compila el parche en memoria y descarta el bytecode antiguo. No modifica la
imagen. Una imagen futura no revisada falla al importar ese módulo, en lugar de
servir sin la corrección. Cada carga correcta deja un marcador numérico de PID,
tiempo de arranque y hash efectivo en `loaded/`. Para comprobar el servidor hay
que contrastar el marcador con el PID vivo de `/health/detailed` y su tiempo de
arranque; un marcador de un intérprete de diagnóstico no demuestra activación.

La recreación real del catálogo confirmó fuente original `4930c2b5…a0f1159`
y código efectivo `44f7886c…45557ccd` en el nuevo proceso API. No se cambiaron
imagen, volúmenes, redes ni otros valores del catálogo. Para recuperar el
comportamiento previo, retirar solamente este prefijo de `PYTHONPATH` y recrear
el contenedor; conservar la base actual y los demás valores de configuración.

La pasarela intermedia del modelo también debe cancelar su solicitud HTTPX al
perder al cliente mientras espera cabeceras o el JSON completo. Esa corrección
está en `services/local_model/router.py`; interrumpir solo al agente Hermes no
libera una solicitud que dicha pasarela deja pendiente.

El parche no proporciona un control retroactivo para una petición antigua sin
identificador de ejecución.
