# MOCHI educativo conectado

Fuentes de un prototipo privado para uso personal y demostraciones. Versión
declarada por el firmware al exportar: **0.16.0-mochi-product**. Esto identifica
el código, no acredita qué versión está instalada en una placa.

El niño practica en un Mochi físico con pantalla circular de 466 × 466. La web
es un espacio adulto: [panel docente](https://peluqo-mundos.vercel.app/expedicion)
y [panel familiar](https://peluqo-mundos.vercel.app/familia). Los enlaces requieren
cuentas autorizadas; el repositorio no incluye sus credenciales.

## Qué contiene

La revisión 0.16 incorpora **Escribir** como alternativa opcional en el Mochi.
Permite conversar por texto sin micrófono ni síntesis de voz. La voz sigue
siendo el modo principal. El firmware se ha compilado; su instalación y prueba
táctil están pendientes. El servicio de texto está desplegado y verificado.

- `firmware/`: ESP32-S3, LVGL, voz/I2S, conectividad, preferencias, escenas y
  motor de multiplicaciones descargadas. Conserva Coucou por elección del
  propietario para uso personal y demostraciones.
- `web/`: aplicación adulta React/TanStack, contratos de API, pruebas y SQL.
- `services/peluqo_education/`: conector ASR, tutor, voz y señales familiares.
- `gateway/` y los demás `services/`: componentes del modo personal y servicios
  de voz/memoria, separados del flujo educativo.
- `tools/`: preparación, diagnósticos y exportador; `hardware/`: fuentes CAD y
  geometría seleccionada; `licenses/`: atribuciones y condiciones de terceros.
- `config/asr-small.json`: versiones y hashes del ASR, sin sus pesos;
  `profiles/mochi/`: personalidad fuente del modo personal, sin memorias.

No se incluyen cuentas, PIN, claves, `.env` privados, historial, audios,
grabaciones, pesos de modelos, bases de datos, builds ni paquetes instalados.
Los ejemplos de interfaz son geometría sintética y se identifican como tal.

## Comenzar

Lee [la guía del monorepo](docs/GUIA_MONOREPO.md),
[la preparación técnica](docs/SETUP.md) y
[el orden y los límites de las migraciones](docs/MIGRATIONS.md).
[Estado y pendientes](docs/ESTADO_PRODUCTO.md) conserva el alcance del producto;
[COUCOU.md](COUCOU.md) explica controles, recursos y procedencia del personaje.

```powershell
cd web
npm ci
npm test
npx tsc --noEmit
```

La web necesita un proyecto Supabase propio y configuración privada. Los SQL
son incrementales; aún no se ha validado un bootstrap completo de una base vacía.
El conector de voz requiere servicios y recursos del operador. El ESP32 no
ejecuta un LLM. Una actividad debe descargarse antes de practicar sin red.

## Verificación y alcance

[Evidencia curada](docs/EVIDENCIA.md) distingue pruebas de código, preview de
geometría y validación física. Los números de pruebas cambian con el código;
ejecuta las órdenes y conserva tu propio resultado. No se publican resultados
de alumnos ni conversaciones como evidencia.

Los reconocimientos son participación interna: 10 por práctica con revisión
docente compartida, 20 extra por integrante cuando se revisa todo el lote del
equipo y 5 por ayuda voluntaria confirmada. No son notas ni clasificaciones.
Los avisos de acompañamiento son privados para familiares destinatarios:
requieren opt-in y confirmación del menor, y no contienen audio ni transcripción.
No acreditan un diagnóstico ni un sistema infalible de detección.

## Licencias y uso

**Este repositorio no se licencia íntegramente bajo MIT.** Consulta
[las condiciones de terceros](licenses/README.md) y [el alcance personal](USO_PERSONAL.md).
La licencia MIT del código Coucou no concede una licencia general sobre su
personaje, nombre, expresiones, animaciones ni sonidos. Mantén el repositorio
privado y revisa los derechos antes de cualquier distribución distinta.

`REPOSITORY_MANIFEST.json` registra archivos, hashes y ajustes de disposición.
Los hashes se calculan sobre el texto normalizado a LF que se exporta; los
binarios conservan sus bytes originales.
`SECRET_SCAN.json` contiene sólo rutas, reglas y recuentos, nunca los valores
que compara. El exportador no ejecuta Git, no despliega y no altera las fuentes.
