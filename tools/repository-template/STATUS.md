# Estado y alcance del producto

Revisión curada: 6 de noviembre de 2026. Versión declarada por estas fuentes:
`{{FIRMWARE_VERSION}}`. Este documento distingue implementación, pruebas de
código y comportamiento que todavía debe comprobarse en hardware. No declara
terminado todo el producto por haber compilado o publicado un panel.

## Implementación disponible

| Área | Alcance disponible | Límite de la evidencia |
| --- | --- | --- |
| Web adulta | Paneles docente y familiar, navegación protegida y roles del servidor. | La QA de producción comprobó carga y navegación con cuentas ficticias; no es una auditoría externa. |
| Organización docente | Clases, estudiantes, asignaciones, materiales, calendario y comunicaciones. | Las acciones necesitan una base con el historial instalado y permisos propios. |
| Revisión y notas | Revisión humana, publicación explícita y calificaciones manuales. | Los contadores de práctica y los puntos no sustituyen una evaluación pedagógica. |
| Propuesta por IA | Borrador editable sujeto a revisión y asignación docente. | Requiere el conector del operador; la indisponibilidad no se rellena con un resultado inventado. |
| Cooperación | Equipos supervisados, participación voluntaria, ayuda confirmada y libro privado de puntos 10 + 20 extra + 5. | Los premios se conceden tras revisión publicada; no hay clasificaciones de capacidad. |
| Familia | Consulta limitada a estudiantes vinculados, notas publicadas, mensajes y controles autorizados. | Vínculos y roles se comprueban en servidor; las cuentas no se incluyen. |
| Acompañamiento | Opt-in, confirmación del menor, aviso mínimo para destinatarios familiares y revisión por adulto. | Sin audio ni transcripción en el aviso; no acredita un diagnóstico ni detección infalible. |
| Privacidad | Destinatarios fijados al compartir, retención de 90 días y exclusión de avisos del aprendizaje y los puntos. | Las pruebas SQL usan datos ficticios y rollback; los volcados privados no se exportan. |
| Dispositivo | Jardín, cestas/manzanas, estanques/peces y cajas/coches con conteos completos hasta 48. | La preview host valida geometría; el aspecto y la fluidez se revisan también en la placa. |
| Personaje | Coucou y sus animaciones para el uso personal elegido, con personalización persistida. | El MIT del código no concede derechos generales sobre los recursos; consulta las licencias. |
| Tiempo y sonido | Límite diario, horarios, recordatorio configurable y control de volumen con persistencia existente. | Cambiar ajustes en el servidor no acredita que una placa concreta ya los haya sincronizado. |
| Accesibilidad | Texto completo, prioridad de texto, respuestas táctiles, foco web y navegación móvil. | La configuración no almacena un diagnóstico; falta una evaluación especializada de todo el recorrido. |

Las pruebas de código disponibles incluyen frontend/TypeScript, conector Python
y contratos escolares contra Postgres. Deben volver a ejecutarse en cada
instalación. Consulta [EVIDENCIA.md](EVIDENCIA.md) para el alcance reproducible
sin cuentas, conversaciones ni mediciones privadas.

El 6 de noviembre se comprobó la oferta y confirmación del acompañamiento con
voz sintética y servicios reales, entrega mínima sólo a la familia y exclusión
del snapshot docente. Los registros ficticios se eliminaron después. Esta
prueba de servicio no sustituye el recorrido acústico ni valida su eficacia.

## Trabajo y comprobaciones pendientes

El código 0.16 añade «Escribir» como opción adicional. Sus permisos, contexto
efímero, horarios y avisos familiares se comparten con voz; no requiere ASR/TTS.
Servicio y compilación verificados. El operador instaló 0.16 por OTA firmada
y validó el arranque (`state=2`) y la vista real del PIN. El envío escrito
desde la pantalla táctil sigue pendiente de aceptación.
Los ajustes adultos usan un desplegable; el PIN acepta sólo dígitos y muestra
un teclado negro centrado, conservando la comprobación y el límite de intentos.

- **Más tipos de actividad.** El motor físico actual trabaja multiplicaciones.
  El alcance original también pide respuestas abiertas, explicación oral,
  autocorrección y tareas en papel; necesitan contratos, ejecución y revisión
  propios antes de considerarse cubiertos.
- **Recorrido acústico completo.** Hay captura, reconocimiento y reproducción
  en el servicio, pero completar una pregunta con voz real y avance local debe
  probarse de extremo a extremo en la placa. Un WAV sintético o un HTTP 200 no
  acreditan esa interacción.
- **Cambios físicos recientes.** La secuencia de bajar/subir, silenciar y
  restaurar, la persistencia tras reinicio y los recordatorios deben comprobarse
  con el firmware instalado. La revisión de fuentes no sustituye esa prueba.
- **Uso sin red.** La práctica descargada y el progreso local tienen mecanismos
  de persistencia y sincronización. Cada nuevo tipo de actividad exige su propia
  prueba sin conexión, reinicio y deduplicación al recuperar la red.
- **Protección y acompañamiento.** El funcionamiento técnico necesita un
  protocolo operativo real, responsables adultos y revisión especializada. No
  se afirma eficacia para detectar o resolver situaciones de acoso.
- **Reconstrucción y recuperación.** Aún no se ha validado una base vacía con
  todos los SQL exportados. Tampoco se ofrece como probado un despliegue NAS
  nuevo sin recursos privados. Sigue [MIGRATIONS.md](MIGRATIONS.md) y conserva
  respaldos antes de instalar firmware o modificar infraestructura.
- **Validación del producto completo.** Faltan evaluación educativa con menores,
  pruebas amplias de accesibilidad, autonomía y rendimiento, y costes de la
  instalación elegida. Este repositorio no contiene resultados de alumnos.

El ESP32 ejecuta escenas y lógica guiada. La conversación libre requiere los
servicios del operador; no se describe el motor determinista como un LLM local.
La copia privada conserva código y procedencia, sin conceder derechos nuevos
para una distribución distinta del uso personal y las demostraciones elegidas.
