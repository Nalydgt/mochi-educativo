# Mochi con Coucou: operación y procedencia

La instalación personal conserva el personaje y las animaciones de
[louis-cfm/coucou](https://github.com/louis-cfm/coucou), referencia
`47d1c2da12bf1dce8fb28b825757d497c1e1d88d`. El nombre del dispositivo es Mochi.
El código y los recursos tienen condiciones distintas: conserva
[Coucou-MIT.txt](licenses/Coucou-MIT.txt) y
[Coucou-ASSETS.md](licenses/Coucou-ASSETS.md). Esta adaptación privada para uso
personal y demostraciones no acredita permiso para otra distribución.

## Pantalla y personalización

La adaptación dibuja a tamaño nativo para la pantalla circular de 466 × 466.
Combina capas RGB565 con alfa y objetos LVGL para cara, boca y efectos.
El catálogo conserva estados, expresiones, gestos, disfraces y variantes mini.
La fluidez depende del gesto y debe medirse en la placa; no se promete una
frecuencia constante a partir de una preview.

En el engranaje, **Personalizar Mochi** permite elegir ropa, color, cara y
movimiento. Los cambios se guardan con la ruta de preferencias existente.
La preview de catálogo es temporal y restaura los ajustes al salir.
La boca sigue el audio completado por I2S, se cierra en silencio y acompaña la
reproducción cuando el personaje está visible. Una actividad puede usar toda
la pantalla sin mostrarlo.

El modo educativo abre un jardín de actividades descargadas. La interacción
hablada requiere el servicio conectado; el texto completo y las respuestas
táctiles ofrecen una alternativa. Horarios, recordatorios, acceso adulto y
vínculos pertenecen a sus controles autorizados. Las pruebas de controles,
persistencia, micrófono y audio deben hacerse con una placa propia.

## Regenerar los recursos conservados

Desde la raíz del repositorio:

```powershell
git clone https://github.com/louis-cfm/coucou.git .references/coucou-latest
git -C .references/coucou-latest checkout 47d1c2da12bf1dce8fb28b825757d497c1e1d88d
npm ci --prefix tools/coucou-render
python -m pip install -r tools/coucou-render/requirements.txt
node tools/Render-MochiNative.mjs
python tools/Prepare-MochiNative.py
python tools/Check-MochiPack.py
```

El catálogo y los hashes están en `firmware/assets/mochi/native-catalog.json`
y `firmware/assets/mochi-native/manifest.json`. Regenerar assets no instala
firmware ni cambia NVS. Compilar se describe en [SETUP](docs/SETUP.md).
Las herramientas físicas requieren un puerto disponible y un procedimiento de
respaldo; el exportador nunca las ejecuta.

La alternativa OneWorks permanece como fuente opcional, con su licencia y
procedencia conservadas. No sustituye al renderer seleccionado ni acredita
validación en hardware.
