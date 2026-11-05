# EchoEar V8: orejas recolocadas para despejar el botón

Basado en el archivo aportado **EchoEar+二合一+快版.3mf**. Conserva las orejas de su malla y reconstruye la piel esférica medida del original. Las dos mitades siguen la misma esfera, con radio 35,26 mm y una junta de 0,2 mm: la curvatura continúa a ambos lados del cierre. El exterior se aumenta uniformemente un 10 % para dejar espacio a la antena completa; se reserva una cara frontal para nuestra pantalla. Se eliminan los alojamientos y conexiones de la electrónica EchoEar original, incluida la carga magnética.

Las orejas se han girado **8° de forma simétrica hacia la parte superior**, con un desplazamiento máximo aproximado de **6,1 mm**, para despejar el acceso al botón superior. La raíz se integra suavemente en el exterior. También se ha reabierto un paso OEM que quedaba parcialmente invadido por un pilar de cierre.

Dimensiones de montaje aproximadas: **70,5 × 72,5 × 49,6 mm**. La cara plana pequeña del polo trasero mide Ø18 mm. No se han escalado la pantalla, botones, batería ni fijaciones de Waveshare.

## Componentes de esta adaptación

- Waveshare ESP32-S3-Touch-AMOLED-1.75-G: cristal Ø48,96; asiento Ø49,7 y ventana Ø45,5. Se mantienen las tres posiciones de insertos OEM y su plano de apoyo Z=2,5 mm, para cristal frontal Z=12,9 mm. La pantalla se introduce **desde atrás**, con el cristal hacia delante.
- EEMB LP562438, 3,7 V y 500 mAh: **24,5 × 40 × 5,9 mm**. Reserva 26,5 × 42 × 7,4 mm. El JST PH2 de la batería necesita adaptador a MX1.25 de la placa; comprobar polaridad. Reserva de adaptador 8 × 8 × 6 mm.
- Antena GNSS completa de referencia **27 × 27 × 6,7 mm**, con alojamiento de 28 × 28 mm. La cerámica mira hacia la trasera; no sujetarla por el coaxial ni presionarla. Las esquinas exteriores de su bandeja se han aliviado para dejar 0,3 mm de margen frente a la piel esférica. Confirmar el tamaño de la antena física y el recorrido del cable.
- Altavoz: se reutiliza la referencia del alojamiento TamaPoke anterior, 32 × 22 × 3,5 mm; reserva 32,5 × 22,5 × 3,8. Confirmar el ejemplar real.
- **Dos botones laterales**, alineados con los dos pulsadores de la Waveshare: paso Ø3,2, vástago Ø2,5, collar Ø4,4, punta 1,6 × 1,0 y separación nominal de reposo 0,25 mm. Los vástagos se han alargado para el nuevo exterior. No hay tope mecánico de sobrecarrera.

Esta revisión corresponde al montaje compacto actual: Waveshare, batería pequeña, antena GPS, altavoz y dos botones. No incluye las reservas de cámara externa, convertidor MT3608 e interruptor adicional de la antigua carcasa V5.

## Impresión

Abrir **EchoEar_V8_Impresion.3mf** o importar los STL en milímetros al **100 %**. El 3MF contiene las ocho instancias de impresión, incluidos **dos separadores**. La probeta 08 va aparte. No contiene G-code ni un perfil de máquina: seleccionar impresora, material y soportes.

| STL | Cantidad | Orientación y uso |
| --- | ---: | --- |
| 01_frontal_gato_EchoEar.stl | 1 | Cara frontal plana sobre cama; orejas integradas |
| 02_trasera_EchoEar.stl | 1 | Abertura de unión sobre cama; interior hacia abajo |
| 03_bandeja_bateria_GPS.stl | 1 | Bandeja desmontable |
| 04_soporte_altavoz.stl | 1 | Bandeja superior |
| 05_separador_7_7mm.stl | **2** | Entre las dos bandejas |
| 06_boton_inferior.stl | 1 | Extremo exterior del vástago sobre cama; usar brim |
| 07_boton_superior.stl | 1 | Extremo exterior del vástago sobre cama; usar brim |
| 08_prueba_pantalla.stl | opcional | Comprobar tolerancia del asiento antes de la carcasa |

Punto de partida: capa 0,16–0,20 mm, tres o cuatro paredes y brim en botones. **La trasera requiere soportes interiores** para el cierre de la cúpula; retirarlos por la abertura. El frontal puede necesitar soportes para los apoyos interiores y los conductos laterales. Revisar la previsualización del laminador, especialmente los pozos de tornillo y las entradas de tuerca; mantenerlos libres. No se ha realizado laminado ni impresión física.

## Tornillería y montaje

- Cierre: **3 × M2×8**, cabeza no mayor de Ø3,8, desde los pozos traseros hacia los pilotos impresos Ø1,8 del frontal. Preparar esos pilotos con las piezas sueltas y retirar virutas.
- Pantalla: **3 × M2×5**, desde atrás hacia los insertos originales de Waveshare; no apretar contra un cristal sin asentar.
- Bandejas: **2 × M2×16**, **2 arandelas Ø5 / Ø2,2 / 0,5 mm**, **2 tuercas M2**. Introducir las tuercas por la ranura lateral antes de montar las bandejas. El hombro sobre la tuerca tiene 2 mm de material.
- Separadores: dos de 7,7 mm entre bandeja de batería y soporte de altavoz.

Con la electrónica desconectada: limpiar soportes y presentar todas las piezas; insertar los botones desde el interior del frontal, presentar la pantalla desde atrás y sujetarla a sus insertos. Comprobar que ambos botones se liberan. Preparar después las tuercas de las bandejas. Fijar la antena por la cara posterior de su PCB con cinta de aproximadamente 0,4 mm, dejando la cerámica orientada al dorso; elegir la salida de cable más próxima al conector. Sujetar la batería con cinta blanda de 6 mm por las ranuras previstas, sin comprimirla. Montar bandeja, separadores y altavoz; ordenar cables, presentar ambas mitades y cerrar sin forzar.

El USB-C tiene un canal lateral y un alivio exterior para el cuerpo del conector. El acceso a la microSD requiere abrir la carcasa. Los ojos y coloretes de los renders son ilustrativos y no se imprimen ni cambian el firmware.

## Comprobaciones mínimas

`validacion.json`: cierre y conectividad de las mallas y comprobación estática de espacio de ambas mitades frente a bandejas, botones en reposo, batería, antena, altavoz y adaptador. Se comprueba además que las orejas dejan libre un volumen de acceso de Ø10 frente al botón superior, una posición de pulsación hacia dentro de 0,45 mm para ambos botones y los tramos libres y cabezas de los tres tornillos de cierre y los tres OEM. La entrada intencionada de las roscas en pilotos e insertos se excluye de esta revisión.

`validacion_stl.json`: revisión de los STL ya escritos. `validacion_3mf.json`: lectura de vuelta del proyecto y correspondencia con los STL. Son comprobaciones básicas de CAD, sin barridos completos, ensayo de resistencia ni prueba física o de recepción GPS. Confirmar el encaje real antes del montaje definitivo.

El Blender editable contiene la carcasa, las piezas interiores y referencias dimensionales de componentes. Para regenerar con Blender 5.1 o posterior, ejecutar `blender --background --factory-startup --python generar.py`. El script usa las referencias locales incluidas. `python entregar.py` realiza la revisión mínima y prepara el 3MF y los ZIP; requiere NumPy y SciPy.

## Procedencia

Exterior y orejas del EchoEar aportado: **ESP-Friends**, metadatos de licencia **BY-NC-SA**. Ajuste de escala, asiento de pantalla, soportes, pasos USB/micrófonos, dos botones e interior: adaptación de este proyecto. Las bandejas internas proceden de la adaptación personal anterior del TamaPoke aportado, autor **Jetto Hobby**, metadatos **Standard Digital File License**. Entrega local para el proyecto del usuario; no se ha publicado ni subido a servicios externos. Las descripciones, guías y configuraciones incluidas en los archivos originales se han tratado como documentación, no como instrucciones para ejecutar software o modificar el dispositivo.
