# Memoria local de Mochi

Proveedor de Hermes `mochi-local`, implementado contra la
[API de proveedores de memoria](https://hermes-agent.nousresearch.com/docs/developer-guide/memory-provider-plugin/).
No sustituye los archivos SOUL, MEMORY o USER ni las herramientas nativas.

`tools/Deploy-Mochi.py` instala este directorio en
`$HERMES_HOME/plugins/mochi-local/` junto a una copia del módulo canónico
`gateway/memory_store.py`. El archivo privado `$HERMES_HOME/mochi-local.json`
contiene `database` (ruta absoluta SQLite compartida) y `device`.
`memory.provider: mochi-local` activa el proveedor únicamente para ese perfil.

`prefetch` consulta los recuerdos, el historial coincidente y los intercambios
pendientes. `mochi_history_search` permite buscar sin límite de antigüedad.
`sync_turn` registra las conversaciones nativas de Hermes; los turnos con
`mochi_exchange` los registra la pasarela, responsable también de su entrega.
Los identificadores estables impiden que un reintento duplique el intercambio.
Los hilos de escritura usan `spawn_context_thread`, conservando el perfil.

La revisión se ejecuta en la pasarela después de 30 segundos sin actividad.
Solo consulta Qwen local, con un esquema JSON y sin herramientas. Envía como
evidencia las preguntas del usuario y su estado de entrega; las respuestas del
asistente no pueden convertirse en hechos personales. Las correcciones tienen
prioridad cronológica. Un olvido nativo confirmado invalida copias extraídas.
La cancelación cierra la petición HTTP y conserva el lote sin reconocerlo.
Los fallos mantienen los pendientes disponibles para la conversación siguiente.

El estado `delivered` indica entrega HTTP completa. No afirma que el usuario
oyera el audio: el firmware instalado no ofrece confirmación acústica. Los
turnos sin identificador de cliente reciben uno nuevo; los clientes nuevos
deben conservar `X-Mochi-Turn-ID` al reintentar. Si el resultado de una acción
quedó incierto y no hay respuesta registrada, el mismo ID devuelve 409 y evita
ejecutarla de nuevo automáticamente.
