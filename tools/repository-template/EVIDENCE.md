# Evidencia curada y límites

Este export incluye únicamente previews sintéticas de geometría en
`docs/illustrations/`. Se generan ejecutando el C de las escenas con stubs de
draw descriptors y un render host. No son capturas del firmware instalado.

La herramienta `tools/preview-lesson-scene/preview.py` recorre 432 casos:
factores del 1 al 12 en tres temas. Comprueba que se dibuja el producto completo
hasta 48 objetos, que nunca se dibuja una colección parcial por encima de ese
límite y que se conserva el número de grupos. Su ejecución local requiere
Visual Studio Build Tools/Windows SDK y las dependencias del renderizador host.
La fuente del host difiere del bitmap font de la placa; parte del marco de UI
es ilustrativo, no una emulación completa de controles.

## Comprobaciones del 6 de noviembre de 2026

El operador registró **105 pruebas web y TypeScript correctos**, **105 pruebas
Python del conector** y **8 pruebas del exportador**. Estos resultados se
refieren al código comprobado; la instalación limpia del export debe volver a
ejecutarlos con sus propias dependencias y configuración.

El recorrido de acompañamiento pasó con voz **sintética**, ASR/TTS y API reales:
primero ofreció compartir, después exigió confirmación y finalmente entregó un
aviso mínimo a la familia. El snapshot docente no incluyó ese campo privado.
La limpieza de demostración eliminó un aviso y un destinatario, con cero
registros de prueba restantes. Se conservan aquí sólo esos recuentos; no UUID,
audio, transcripciones, credenciales ni datos de estudiantes.

La QA de producción comprobó navegación docente/familiar, formulario de grupos,
ajustes y acompañamiento, foco y móvil de 375 px, sin errores JavaScript ni
timeouts observados. Fue una revisión sin escritura: no guardó configuraciones,
grupos, calificaciones ni mensajes. No acredita nuevas acciones persistentes.

El extractor real de documentos recuperó texto y número de página de un PDF
sintético creado en memoria bajo Node 22.14. Esa prueba básica no amplía el
soporte declarado por `unpdf` 2.1.0: el setup nuevo requiere Node 24.

Ninguna de estas comprobaciones acredita un recorrido acústico por micrófono
físico, eficacia de detección o una prueba completa de los controles de 0.15.0.

## Qué se puede reproducir sin datos del operador

La ampliación 0.16 pasó 117 pruebas del conector, 48 de herramientas y siete
grupos contra Postgres real con rollback. Dos turnos escritos con el modelo
real devolvieron respuestas completas sin audio. El recorrido de acompañamiento
por texto verificó oferta, confirmación, aviso mínimo familiar y exclusión del
profesor; el aviso ficticio se eliminó y quedaron cero filas asociadas. La
compilación ESP-IDF de 0.16 cabe en la partición de 4 MiB. Estas comprobaciones
no acreditan instalación ni interacción táctil en una placa.

- Pruebas frontend y TypeScript mediante `npm test` y `npx tsc --noEmit` en `web/`.
- Pruebas del conector con fixtures generadas en memoria o directorios temporales.
- Compilación ESP-IDF con versiones declaradas y recursos de arte incluidos.
- Inspección estática de permisos, contratos, límites y deduplicación.

## Qué no demuestra esta evidencia

No acredita una validación educativa con menores, eficacia de detección de acoso,
sincronía acústica de un hardware distinto, fluidez física, calidad de micrófono,
autonomía, instalación de una versión concreta ni una DB vacía reproducida.
Las pruebas físicas y Postgres del operador usan alumnos ficticios y recursos
privados; sus grabaciones, credenciales, respuestas y volcados no se exportan.

Para evaluar voz, volumen, NVS, trabajo sin red y accesibilidad, ejecuta una
prueba controlada en tu propia placa y conserva la distinción entre simulación,
servicio con WAV sintético y entrada real por micrófono. No publiques audio o
conversaciones de menores como prueba técnica.
