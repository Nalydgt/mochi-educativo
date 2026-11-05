# Mochi · gato redondo V4

Carcasa para la Waveshare ESP32-S3-Touch-AMOLED-1.75 y la batería 955565 de la foto: **65 × 55 × 9,5 mm, 3,7 V, 5000 mAh según su etiqueta**. La cabeza y las dos orejas se generan como una superficie continua y se imprimen juntas en el frontal. La tapa cierra con cuatro tornillos, tuercas cautivas, nervios de refuerzo y apoyos definidos.

Las cotas estáticas de pantalla, insertos, conectores y botones proceden del STEP oficial. El ancho nominal del cuerpo es 108 mm y el fondo 54 mm; las dimensiones exteriores finales, incluida la altura de las orejas, se registran en `validacion_mecanica.json`.

## Piezas y tornillería

Importar los STL en **milímetros, al 100 %**, como piezas independientes. La numeración es intencional: esta versión contiene ocho STL.

| STL | Cantidad | Función |
| --- | ---: | --- |
| `01_frontal_gato.stl` | 1 | Cabeza, orejas, guías de botones y alojamientos de tuercas |
| `02_tapa_trasera.stl` | 1 | Cierre, labio de alineación, bandeja y guías de accesorios |
| `03_soporte_waveshare.stl` | 1 | Retención de la placa sobre sus tres insertos metálicos |
| `06_prueba_pantalla.stl` | 1 primero | Comprobar asiento y ventana sin imprimir toda la carcasa |
| `07_pulsador_inferior.stl` | 1 | Botón inferior, visto de frente con las orejas arriba |
| `08_pulsador_superior.stl` | 1 | Botón superior; no intercambiar con el inferior |
| `09_prueba_guia_botones.stl` | 1 primero | Comprobar la holgura del vástago cuadrado |
| `10_prueba_tuercas.stl` | 1 primero | Probar entradas laterales M3/M2 y sus hombros continuos de 2 mm |

| Tornillería | Cantidad | Destino y alojamiento |
| --- | ---: | --- |
| M3 × 25 mm, cabeza cilíndrica con hexágono interior | 4 | Cierre de tapa; cabeza de hasta Ø6,8 mm |
| Tuerca M3 | 4 | Hexágonos cautivos de **5,8 mm entre caras** |
| M2 × 4 mm | 3 | Soporte a los insertos metálicos originales de la placa |
| M2 × 6 mm | 3 | Soporte a los pilares del frontal |
| Tuerca M2 | 3 | Hexágonos cautivos de **4,2 mm entre caras** |
| M2 × 4 mm, cabeza cilíndrica **Ø3,8 × 2 mm** | 2 | Retención transversal de los pulsadores |

Las longitudes de tornillo se miden bajo la cabeza y están calculadas sin arandelas adicionales. Los 5,8 y 4,2 mm de la tabla corresponden a los huecos impresos, no al tamaño nominal de las tuercas. Para los dos tornillos de los botones hay que respetar la cabeza indicada: forma parte de su tope de extracción. Preparar su rosca en el piloto Ø1,7 del pulsador **antes de montar la electrónica**; después retirar el tornillo para introducir el pulsador.

Se necesitan también una cinta blanda de hasta 8 mm para la batería y fijación blanda para los accesorios. La batería declara PH-2.0 y la placa utiliza MX1.25: prever el adaptador correspondiente y comprobar su polaridad antes de conectarlo.

## Cotas que gobiernan el ajuste

| Interfaz | Cota del diseño |
| --- | --- |
| Cristal / asiento | Ø48,96 / Ø49,66 mm: **0,35 mm radial** |
| Área activa / ventana | Ø44,16 / Ø45 mm |
| Reborde frontal | 1,3 mm |
| Frontal del cristal a plano posterior de los insertos | **10,399996 mm**, obtenido del STEP |
| Pasos de montaje M2 / M3 | Ø2,4 / Ø3,4 mm |
| Despeje de los postes metálicos OEM en el frontal | Ø4,2 mm |
| Apoyo de las torres de cierre | Ambas mitades en **Z=27 mm** |
| Hombro de retención M3 | Continuo, 2 mm: **Z=27 a 29 mm** |
| Cámara lateral M3 | **Z=29 a 31,8 mm**; la tuerca apoya en Z=29 |
| Hombro de retención M2 del soporte | Continuo, 2 mm: **Z≈42,30 a 44,30 mm** |
| Cámara lateral M2 del soporte | **Z≈44,30 a 46,20 mm**; la tuerca apoya en Z≈44,30 |
| Punta de tornillo M3×25 / M2×6 del soporte | **Z=34,4 / Z≈46,30 mm**, respectivamente |
| Separación perimetral exterior | 0,3 mm intencionales |
| Reserva de batería | 67 × 57 × 11,5 mm; 1 mm por lado y 2 mm por encima de la celda nominal |

Las tuercas se cargan por ranuras laterales orientadas al interior, enteramente por encima del hombro de 2 mm. En el plano de unión solo queda el paso del tornillo: Ø3,4 para M3 y Ø2,4 para M2. Al apretar, la tuerca tira contra ese hombro del frontal y transmite la fuerza al apoyo de la otra pieza. Así el cierre comprime ambas mitades y el soporte queda sujeto a la carcasa. La probeta 10 reproduce esta construcción; comprobar que las tuercas entran por el lateral sin abrir ni deformar el plástico.
El soporte conserva los tres puntos originales de la placa: `(0; 20,5)`, `(−13,75; −14,7)` y `(13,75; −14,7)`. Sus tres fijaciones a la carcasa están en `(-5; 29)`, `(-25,5; -13,8)` y `(16; -24,8)`, separados de los pasos de conectores y botones. Son coordenadas CAD en milímetros, con Y hacia las orejas y Z hacia la pantalla; no reflejar el montaje tomando una fotografía trasera como plantilla.

Los botones siguen las posiciones y los ejes inclinados reales del STEP. Cada vástago cuadrado mide **3,6 mm** y su paso guiado **4,2 mm** entre caras, con una holgura nominal de 0,3 mm por cara. El exterior de la guía es redondo, **Ø8,6 mm**; el paso interior conserva la forma cuadrada para limitar el giro. La guía empieza a 4,8 mm de la cara del interruptor y el centro del tornillo transversal está a 2,9 mm, medidos hacia el exterior sobre el eje de pulsación. La cabeza exterior mide Ø10 mm y la punta de contacto Ø1,6 mm.

En el tope exterior de reposo se prevén **0,30 mm de separación** entre punta e interruptor; el tope interior limita el desplazamiento de la pieza impresa a **0,50 mm**. La depresión nominal resultante es **0,20 mm**. Como referencia del modelo TS24CA, [Shouhan especifica una carrera de 0,20 ± 0,05 mm](https://www.sohantech.com/ts24ca-24mm-momentary-tact-switch-smd-push-button-switch-product/); el diseño coincide con su valor central. El STEP solo representa la posición estática. **La identidad del interruptor montado, las tolerancias de impresión, el clic y la liberación deben comprobarse físicamente; la referencia del fabricante no certifica por sí sola el mecanismo impreso ni autoriza sobre recorrido adicional.**

## Impresión y montaje

1. **Imprimir primero las pruebas 06, 09 y 10.** El cristal debe entrar sin presión lateral, el vástago debe deslizar libremente y las tuercas deben entrar lateralmente hasta sus hexágonos conservando intactos los hombros de 2 mm. No lijar el vástago hasta perder la forma cuadrada. Corregir la compensación de la impresora si hace falta; no escalar toda la carcasa, porque alteraría las posiciones de los tornillos.
2. Como perfil inicial: boquilla de 0,4 mm, capa de 0,20 mm, cuatro perímetros, cinco capas superior/inferior y 15–20 % de relleno para las carcasas. Imprimir los pulsadores macizos. PETG es una opción para las piezas de uso; PLA permite comprobar el primer ajuste. Revisar soportes en alojamientos y voladizos. Añadir bloqueadores de soporte en el interior de los conductos acústicos de Ø1,8 mm para que no quede material atrapado; revisar esas capas en el laminador y conservar libre el canal curvado. Los STL están colocados en Z=0; los pulsadores se exportan con la cara exterior de la cabeza sobre la cama y la punta hacia arriba.
3. Retirar rebabas y soportes con las piezas sueltas. Comprobar guías, pasos de tornillo, bolsillos de tuercas, canal de la cinta y conductos acústicos. Preparar la rosca de los M2 transversales fuera del dispositivo y volver a retirarlos.
4. **Cargar las cuatro tuercas M3 y las tres M2 por sus ranuras laterales, antes de montar la placa o el soporte.** Deslizarlas hasta los hexágonos, por encima de los hombros continuos; no introducirlas desde el plano de unión. Con la placa sin alimentación, montar la pantalla sin la carcasa comercial redonda. Presentar el cristal desde el interior, con la pantalla orientada hacia su ventana.
5. Colocar el soporte 03 sobre los tres insertos metálicos originales. Presentar los tres **M2 × 4** de la placa y los tres **M2 × 6** que entran en las tuercas cautivas del frontal. Apretar poco a poco, alternando puntos, hasta apoyar. El soporte debe asentar sobre sus referencias sin tirar del cristal ni flexionar la placa.
6. **Montar ahora los pulsadores desde fuera.** Usar el inferior y superior en sus respectivas guías. El taladro transversal debe quedar paralelo al plano de la placa, tangente al contorno, no dirigido hacia la pantalla o la tapa. Las cabezas de ambos M2 de retención quedan en el lado orientado hacia abajo, según las referencias metálicas del modelo de montaje. Introducir cada M2 × 4 por la cavidad trasera, con llave acodada. No dejar tornillos sobresalientes distintos de la longitud prevista.
7. Comprobar con el conjunto aún abierto el deslizamiento y el retorno de ambos pulsadores. No usar el tornillo transversal para ajustar la carrera. El tope exterior y el interior los define la geometría. La prueba física debe confirmar el clic y la liberación del interruptor sin atasco ni precarga.
8. Sujetar la batería con la cinta blanda, conservando su holgura y la salida de cables. Fijar antena y altavoz en sus reservas. Mantener los cables fuera de guías, torres, topes y labio de cierre.
9. Presentar la tapa y colocar los cuatro **M3 × 25**. Apretar en cruz hasta el contacto de los apoyos: las tuercas deben cargar los hombros del frontal y los topes deben apoyar en Z=27, sin deformar el plástico. La junta exterior de 0,3 mm es intencional: no apretar para eliminarla.
10. Comprobar acceso a USB-C y microSD, funcionamiento de ambos botones, carga, voz y recepción GPS con la carcasa cerrada. El ensayo cerrado confirma aspectos que el modelo geométrico no determina, como el comportamiento acústico.

## Validación y alcance

La referencia digital contiene **666 sólidos** del STEP oficial. El informe mecánico consultado registra **925 comprobaciones**. Estas contrastan las piezas con los sólidos de referencia, la reserva de batería y el movimiento conjunto de cada pulsador y su M2 transversal a 0, 0,25 y 0,50 mm, con giros de −10°, 0° y +10°. Incluye alivio del soporte alrededor de la cabeza de retención y una región de contacto del capuchón móvil del interruptor. Los registros de carga de las tuercas recogen los hombros continuos de 2 mm y sus cámaras laterales; no son bolsillos abiertos en el plano de unión. La región de contacto del botón no sustituye la prueba física de su carrera.

Los resultados de la ejecución se registran en `validacion_mecanica.json`. La revisión independiente de los archivos exportados se registra en `validacion_stl.json`: cierre de malla, orientación, componentes, triángulos, dimensiones y huellas SHA-256. La aprobación geométrica de una ejecución debe comprobarse en estos informes y en las huellas de los STL incluidos. Esta guía describe el montaje y sus cotas; no constituye un ensayo físico.

El STEP utilizado corresponde al **modelo base ESP32-S3-Touch-AMOLED-1.75**. Permite contrastar las interfaces representadas; no certifica por sí solo todos los volúmenes adicionales de la variante **1.75-G**. La revisión física debe incluir la placa G concreta y sus componentes añadidos.

Los micrófonos del STEP están simplificados y no incluyen su abertura acústica real. Las cámaras se sitúan según las superficies y orientación del capuchón: exterior de 5,6 × 4,8 mm, cámara interior de 4,0 × 3,2 mm y separación nominal de 0,4 mm al capuchón. Los conductos tienen diámetro interior de 1,8 mm y codo curvado. Su rendimiento requiere comprobar la entrada de voz en el conjunto real. La reserva de antena externa **25 × 25 × 4 mm** y la de altavoz **Ø28 × 7 mm** siguen siendo provisionales: no proceden de medir los accesorios del usuario.

Las cotas estáticas verificadas en el modelo no eliminan las tolerancias de impresión, la necesidad de las piezas de prueba ni la comprobación de la carrera de los botones. Los ojos y coloretes de las vistas son una ilustración; no se imprimen ni modifican el firmware.

## Fuentes y regeneración

- [Documentación de Waveshare](https://docs.waveshare.com/ESP32-S3-Touch-AMOLED-1.75).
- [Recursos mecánicos oficiales](https://docs.waveshare.com/ESP32-S3-Touch-AMOLED-1.75/Resources-And-Documents).
- [Referencia del fabricante para la carrera del TS24CA](https://www.sohantech.com/ts24ca-24mm-momentary-tact-switch-smd-push-button-switch-product/).
- Medidas y transformación: `auditoria/step_measurements_independent.json`.
- Sólidos y malla de referencia: `auditoria/step_parts.json` y `referencias/step_mesh_native.npz`.
- Batería: foto del usuario conservada en las referencias del proyecto.

Para regenerar hay que conservar `generar.py`, `cad_base.py`, `parametros.json`, `auditoria/` y `referencias/step_mesh_native.npz`. La regeneración normal utiliza esta malla incluida y no necesita volver a importar el STEP. El original está en `referencias/waveshare-ESP32-S3-Touch-AMOLED-1_75.stp`.

Con Blender 5.x y Python con NumPy para la comprobación independiente, abrir PowerShell y cambiar a la carpeta descomprimida que contiene `generar.py`. Adaptar únicamente la ruta de `cd` al lugar de extracción:

```powershell
cd 'C:\ruta\al\paquete-V4'
& 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe' --background --factory-startup --python generar.py
python validar_stl.py
```

La opción `-- --no-render` omite las imágenes. Las versiones anteriores quedan en sus carpetas; montar las piezas V4 juntas y no mezclar sus soportes o pulsadores con otros paquetes.