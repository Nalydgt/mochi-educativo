# Detector de nombre: estado de validación

La infraestructura local de microWakeWord está integrada, pero no hay un
modelo `Mochi` aprobado ni activo en la placa. BOOT conserva la conversación
manual y la ventana de continuación de ocho segundos.

El candidato v9 detectó 4 de 36 clips positivos y aceptó erróneamente 3 de
57 negativos de la evaluación sintética. No se instala. No se reduce el
umbral para convertir ese resultado en una aceptación.

`check_stream_parity.py` compara el modelo Keras con la conversión INT8 en
ventanas idénticas. La diferencia media observada fue 0,00154; ambos rechazaban
las mismas palabras. `check_dataset_generalization.py` añade un diagnóstico
de solo lectura y muestreo fijo: 64/64 palabras aisladas de entrenamiento
aceptadas frente a 0/64 de una voz española de validación. Esto evidencia
sobreajuste; no acredita un fallo de memoria ni del micrófono.

v10 reduce las identidades suplementarias entrenadas en inglés de 96 a 16
y da peso ocho a cada una de siete identidades españolas. Estas siguen
contando como siete voces, no como 56 hablantes nuevos. La voz `carlfm`
permanece en validación; la argentina `daniela-high`, no expuesta en los
ensayos previos, queda reservada para la prueba final. Las voces ya expuestas
por versiones anteriores pueden usarse en entrenamiento, pero no se vuelven
a presentar como evaluación independiente. No se reutilizan datasets o
modelos de otra versión de la preparación.

El trabajo v10 `719ed16f52f34df58eb2a06aea99086a` terminó rechazado: **33/36** detecciones y **4/57** falsas activaciones. La aceptación de palabra aislada en validación fue 0,0625 con umbral 0,5. Mejora el reconocimiento sintético frente a v9, pero sigue sin cumplir los criterios. El trabajador está libre y el detector permanece inactivo.

El entrenador permanece aislado: dos CPU, 8 GiB, un trabajo simultáneo y
pausa durante conversación. El historial y la identidad de Hermes son
independientes del nombre. `Deploy-MochiLab.py` incluye la revisión de código
en la configuración para que un cambio del trabajador sí recree el servicio.

El candidato solo pasa a descargable si supera la evaluación sintética.
La descarga valida manifiesto, integridad y compatibilidad; después exige
la prueba guiada de placa. Las 38/40 detecciones a cada distancia, falsas
activaciones, ruido de paseo y bloqueo de la propia voz siguen pendientes.
