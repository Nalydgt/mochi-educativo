# Preparación técnica

## Requisitos

- Node.js **24** para la web, npm y Python 3.11.
- ESP-IDF **6.0.1** para firmware. Sus dependencias declaran LVGL 9.5.0 y BSP
  Waveshare 3.0.1 en `firmware/main/idf_component.yml`.
- Un proyecto Supabase propio con Auth y una base configurada según el historial
  incremental. Consulta [MIGRATIONS.md](MIGRATIONS.md) antes de aplicar SQL.

No se incluyen pesos de ASR/LLM/TTS ni referencias de voz. El modo personal y el
conector educativo necesitan sus propios servicios y secretos del operador.

## Web

El lockfile incluye `unpdf` 2.1.0 para extraer materiales PDF en el servidor;
esa versión [declara Node >=24](https://github.com/unjs/unpdf/blob/v2.1.0/package.json).
Usa Node 24 tanto al instalar como al ejecutar el servidor. `npm ci` puede
terminar con una advertencia de engine en Node 22, pero eso no acredita soporte
completo. Una extracción sintética básica funcionó en Node 22.14 durante la
revisión; no sustituye el requisito declarado ni una prueba con PDFs variados.
Esta guía no actualiza automáticamente el NAS o un despliegue existente.

Desde la raíz:

```powershell
Copy-Item web/.env.example web/.env.local
cd web
npm ci
npm test
npx tsc --noEmit
npm run dev
```

Rellena `.env.local` en privado. Las variables `VITE_*` son públicas en el
navegador: no introduzcas claves de servidor en ellas. `PELUQO_DATABASE_URL`,
claves de integración y claves de servicio permanecen sólo en el servidor.
`PELUQO_WEB_ORIGIN` debe coincidir exactamente con el origen que utilices:
`localhost` y `127.0.0.1` son orígenes distintos.

El build se genera con `npm run build`. El servidor Node de Nitro se inicia
con `node .output/server/index.mjs`, con sus variables privadas suministradas
por el entorno. Para Vercel configura `web/` como raíz de proyecto y tus
variables en la plataforma. Este repositorio no enlaza ni publica un proyecto.

## Firmware

Abre una terminal de ESP-IDF 6.0.1 y usa el entorno de esa instalación:

```powershell
idf.py -C firmware build
```

Los archivos `sdkconfig.defaults`, `sdkconfig.ota.defaults`, las tablas de
particiones y `dependencies.lock` están incluidos. `managed_components/` y
los builds se regeneran. Compilar no instala ni modifica NVS. Las operaciones
de flash, particionado o migración OTA requieren el procedimiento de respaldo
de la placa; este exportador no las ejecuta.

`tools/Invoke-Mochi.ps1` es un adaptador del equipo Windows original, con rutas
locales de Espressif y una junction. El comando estándar anterior no depende de
esa disposición. La opción OneWorks permanece como fuente alternativa sin
seleccionarse en el build; la identidad elegida sigue siendo Coucou para uso
personal/demostración, con las atribuciones correspondientes.

## Python y servicios

```powershell
python -m venv .venv
.venv/Scripts/Activate.ps1
python -m pip install -r tools/requirements.txt
python -m pip install -r services/peluqo_education/requirements.txt
python -m pytest services/peluqo_education -q
```

`pytest` puede instalarse en el entorno de desarrollo si todavía no está
disponible. Los otros servicios declaran sus dependencias junto a su código;
`gateway/pyproject.toml` incluye extras para pruebas y voz.

## NAS opcional

El despliegue TrueNAS es una integración del operador, no un requisito para
ejecutar las pruebas de código. Crea `.runtime/` y configura allí identidades,
rutas, claves y destinos de tu instalación. Las herramientas esperan archivos
privados; no se exportan ni se generan credenciales reales en este repositorio.

`config/nas.example.json` es una plantilla genérica, con un dominio `.invalid`
y rutas de ejemplo. Para las herramientas que lo requieran, cópiala a
`.runtime/nas.json` y adapta los campos en privado. Registra la clave pública
del host por un canal fiable; el transporte rechaza hosts desconocidos.

`web/tools/pilot.py` localiza el monorepo padre y `tools/Check-MochiLessonVoice.py`
localiza `web/`. El export corrige exclusivamente esas disposiciones, el
adaptador de placa y la creación de `.runtime` en `web/tools/build-pilot.py`.
Otras referencias históricas se enumeran para revisión, sin cambiar URLs.

Las claves nunca deben almacenarse en Git ni en capturas de diagnóstico. Los
ejemplos `.env.example` contienen marcadores que debes sustituir localmente.
