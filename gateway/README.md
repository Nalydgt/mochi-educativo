# Pasarela de voz

FastAPI con autenticación Bearer para todos los endpoints. `/v1/chat` conserva
JSON `text` y `emotion`; `/v1/turn` recibe PCM16 mono a 16 kHz y devuelve ese
mismo formato. `X-Mochi-Stream: pcm16` negocia entrega progresiva por frases.
Las cabeceras existentes de emoción, frecuencia, GPS y caché se conservan.
`X-Mochi-Audio-Cache: bypass` exige síntesis nueva para los diagnósticos; también
admite el proveedor ElevenLabs y consume su cuota.

`X-Mochi-Turn-ID` es optativo para clientes anteriores. Un reintento debe usar
el mismo ID y grabación/contexto. No vuelve a ejecutar herramientas: reutiliza
la respuesta registrada o devuelve 409 si el resultado es incierto. El servidor
asigna un ID a clientes antiguos y lo devuelve en esa cabecera. `/v1/chat`
también admite `exchange_id`. `X-Mochi-Route` identifica fast, hermes o local.

`/health`, clima, `/v1/say`, preparación por nombre y OTA mantienen sus rutas.
`/v1/diagnostics/latency` solo guarda duraciones numéricas en RAM.
ElevenLabs utiliza las mismas rutas de voz que el resto de proveedores.

La configuración se documenta en `.env.example`. El instalador usa requisitos
con hashes y un entorno nuevo en `/data/gateway-runtime`, sin las dependencias
retiradas; el anterior se conserva para recuperación. La precarga nativa solo
carga Whisper. La síntesis aprobada se atiende en el servicio NAS separado.
El extra `diagnostics` instala Piper únicamente cuando se pide expresamente.

Las pruebas se ejecutan desde la raíz con:
`uv run --project gateway --extra test python -m pytest gateway services -q`.
Incluyen dobles de los servicios de voz y del proveedor Hermes: no requieren
pesos, recursos privados ni una instalación de Hermes.

## Voz ElevenLabs

El proveedor `elevenlabs` conserva el protocolo PCM16 mono de 16 kHz y mantiene
Hermes, reconocimiento y memoria en el NAS. `ELEVENLABS_API_KEY_FILE` permite
montar la clave como un archivo secreto, sin incluirla en la placa. La caché
separa el clon, el modelo, la revisión de muestras y sus ajustes.

La preparación y activación conservan configuración y datos existentes:
[instrucciones y medidas reales](../docs/ELEVENLABS-Y-OTA.md).
