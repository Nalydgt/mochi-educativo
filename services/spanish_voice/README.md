# Voz española local: ejecución y ensayos

La **voz femenina 03 aprobada** está restaurada y activa en el NAS.
El usuario ha pedido mantener una voz femenina; ha terminado la prueba de
Piper `es_ES-carlfm-x_low`. El servicio `mochi-fast-voice-trial`, puerto 8775,
está en ejecución y la pasarela selecciona su perfil de cuatro pasos,
`e9924f56a4686f2b4cf0a266c19b4e74ecd056001cb89cdcc8702e2b52169162`.
Se han comprobado salud, identidad del perfil y reproducción desde la placa.
Para reconstruir y seleccionar esta misma receta aprobada:

```powershell
python tools/Deploy-MochiFastVoice.py
python tools/Deploy-Mochi.py stage
```

La configuración aprobada que se conserva es la siguiente.
Conserva el checkpoint Chatterbox V3, referencia española 03,
temperatura 0,5, CFG 0,5, expresión 0,25 y la semilla 4139. No aplica cambio
de tono ni mezcla de voces. La configuración y recursos se identifican por
SHA-256; el caché de la pasarela incluye ese perfil.

`mochi-fast-voice-trial`, puerto 8775, sustituye las operaciones lineales de
T3 por GGML Q8 y conserva su muestreador Torch, S3Gen FP32 y Perth, ahora
con **cuatro pasos de difusión**. El sufijo del nombre procede del ensayo.
Perfil: `e9924f56a4686f2b4cf0a266c19b4e74ecd056001cb89cdcc8702e2b52169162`.
Se corrigió la posición acústica del adaptador nativo y se comprobó su
paridad con Torch. En tres textos, dos PCM coinciden con el anterior hasta
un nivel PCM16; el tercero tiene coseno de forma de onda 0,9896. Whisper
reconoció los seis clips sin errores de palabras. La escucha física sigue
siendo necesaria para validar timbre y pronunciación.

`Deploy-MochiFastVoice.py` verifica recursos, referencia, revisiones y hash
del adaptador. `Deploy-Mochi.py stage` prepara la pasarela con el perfil vigente y
`activate` exige la comparación aceptada antes de seleccionarla. Las voces anteriores
de diez pasos (8772) y Torch FP32 (8767) están detenidas, con recursos y
configuraciones conservados. Hay que arrancar la aplicación antes de volver
a seleccionarla.
El servicio no instala recursos al generar y trabaja sin acceso a Hugging Face.

Antes de anunciar disponibilidad ejecuta una síntesis real de calentamiento
y descarta su resultado. Cada petición vuelve a fijar la semilla aprobada;
el calentamiento no se guarda como respuesta ni cambia el perfil de voz.
`Server-Timing` y el registro de servicio separan los milisegundos de T3 y
del decodificador, sin transcripciones ni grabaciones.

La comparación CPU con `torch.set_flush_denormal(True)` produjo PCM16
idéntico en dos frases, sin mejora de velocidad medida. Se conserva ese modo
para coincidir con el ensayo aprobado; no se atribuye una aceleración al cambio.

## Ensayo de pasos del decodificador

`Deploy-MochiVoiceBenchmark.py --decoder` prepara un ensayo aislado que
reutiliza los mismos tokens T3 y el mismo estado aleatorio del decodificador.
Prueba 10, 8, 6 y 4 pasos y conserva muestras con marca de agua. Su proceso
se pausa durante conversación. No selecciona el resultado automáticamente.

Tres clips de 1,7–1,8 s pasan de aproximadamente 6 s de generación a 4,2 s
con cuatro pasos. El reconocimiento no encuentra errores de palabras; el
coseno del codificador de voz respecto a diez pasos está entre 0,977 y 0,985.
Las formas de onda difieren: estas cifras no equivalen a aprobación de oído.

`Deploy-MochiFastVoice.py` actualiza el servicio
activo `mochi-fast-voice-trial`, puerto 8775. El nombre procede del ensayo
original: ya es producción. Para comparar otra receta se necesita un servicio
aislado distinto; esta orden conserva la selección de la pasarela, pero
recrea el proceso de voz que Mochi utiliza.
El usuario escuchó los clips de `voice-bank/optimizacion-nas/` y confirmó:
«La candidata suena igual de bien». El perfil de cuatro pasos ya es el
seleccionado en la pasarela; la caché está separada de los perfiles anteriores.

Antes de la selección, tres ensayos ASR → Hermes → candidato sin caché obtuvieron primer PCM en
9,276, 7,779 y 9,706 s. Se ejecutaron mediante un diagnóstico dentro del NAS;
no son peticiones desde el micrófono ni incluyen la VPN o el altavoz físico.
Usaban otro modelo de conversación: no acreditan la configuración actual.
Las medidas actuales están en [LATENCIA-NAS.md](../../docs/LATENCIA-NAS.md).
El objetivo físico de menos de diez segundos en Mochi sigue pendiente.

El ensayo del 24 de octubre con espera OpenMP pasiva conservó PCM idéntico,
pero fue más lento en las tres frases. Se restauró la espera original.
`--cpu-wait-policy passive` permite reproducirlo, sin seleccionarlo por defecto.
[Mediciones de CPU y paridad](../../docs/mediciones/20261024-politica-cpu-voz.json).

Las dependencias y licencias están en [ATTRIBUTION.md](ATTRIBUTION.md).
