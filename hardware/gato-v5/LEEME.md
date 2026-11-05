# Mochi · gato redondo V5 con cámara frontal

Carcasa para Waveshare ESP32-S3-Touch-AMOLED-1.75, batería 955565, diymore ESP32-S3-CAM N16R8 con OV2640, elevador MT3608 e interruptor SS12D00. **La cámara y la pantalla miran hacia delante**, en dirección +Z. La cámara ocupa la frente redondeada, sobre la pantalla; la cabeza y las orejas forman una pieza continua. Tanto la bandeja de batería como la del MT3608 son desmontables: se instala el elevador antes de cerrar su espacio con la batería. El interruptor ocupa una cassette accesible desde atrás.

El cuerpo nominal mide 118 × 118 mm en XY y 78 mm de fondo, de Z=−18 a 60. El adaptador óptico alcanza Z=63,2 y la cassette trasera Z=−19,6. La altura con orejas y las dimensiones finales de las piezas están en `validacion_mecanica.json`. La batería conserva las medidas de la foto: **65 × 55 × 9,5 mm, 3,7 V y 5000 mAh según su etiqueta**.

Pantalla, insertos y botones se sitúan con el STEP oficial de Waveshare. Las reservas de cámara, MT3608 e interruptor se basan en referencias comerciales y holguras de diseño: **no son réplicas medidas de los tres módulos del usuario**. Sus bandejas y cassette permiten probar y ajustar esas interfaces por separado. La procedencia de cada cota está en `referencias/componentes_medidas.json`.

## Piezas y tornillería

Importar en milímetros, al 100 %, como piezas independientes. Hay **15 STL**; el adaptador óptico ciego es una alternativa al perforado, no una pieza adicional del montaje.

| STL | Uso |
| --- | --- |
| `01_frontal_gato.stl` | Cabeza, orejas, frente de cámara, guías de botones y tuercas |
| `02_tapa_trasera.stl` | Cierre, anclajes de bandejas, apoyos de accesorios y ventilación |
| `03_soporte_waveshare.stl` | Retención de la pantalla sobre sus tres insertos |
| `06_prueba_pantalla.stl` | Prueba de asiento y ventana |
| `07_pulsador_inferior.stl` | Botón inferior, visto de frente con las orejas arriba |
| `08_pulsador_superior.stl` | Botón superior; no intercambiar con el inferior |
| `09_prueba_guia_botones.stl` | Prueba del vástago cuadrado |
| `10_prueba_tuercas.stl` | Prueba de entrada lateral y hombros M3/M2 de 2 mm |
| `11_bandeja_camara_frontal.stl` | Marco ajustable y desmontable para la cámara |
| `12_adaptador_objetivo_20mm.stl` | Adaptador óptico con abertura Ø20 mm |
| `13_adaptador_objetivo_ciego.stl` | Alternativa sin perforar para adaptar la óptica real |
| `14_bandeja_MT3608.stl` | Soporte desmontable del elevador, con pasos de cinta |
| `15_cassette_SS12D00.stl` | Placa trasera extraíble y cuna del interruptor |
| `16_retenedor_SS12D00.stl` | Retenedor del cuerpo; deja libres las patillas |
| `17_bandeja_bateria.stl` | Bandeja extraíble; permite montar y mantener el MT3608 situado debajo |

| Tornillería | Cantidad | Destino |
| --- | ---: | --- |
| M3 × 45 mm, cabeza cilíndrica con hexágono interior, hasta Ø6,8 mm | 4 | Cierre de la tapa |
| Tuerca M3, hueco impreso de 5,8 mm entre caras | 4 | Cierre, carga lateral |
| M2 × 4 mm | 3 | Soporte a los insertos metálicos originales Waveshare |
| M2 × 6 mm | 3 | Soporte Waveshare a las tuercas del frontal |
| M2 × 4 mm, cabeza **Ø3,8 × 2 mm** | 2 | Retención transversal de los pulsadores |
| M2 × 8 mm y arandela de 0,5 mm, Ø exterior 6 mm | 2 + 2 | Correderas de la bandeja de cámara |
| M2 × 4 mm | 2 | Adaptador óptico a pilotos impresos Ø1,7 mm |
| M2 × 6 mm | 2 | Bandeja MT3608 a sus tuercas |
| M2 × 8 mm | 2 | Cassette a las tuercas de la tapa |
| M2 × 6 mm | 2 | Retenedor del interruptor a pilotos impresos Ø1,7 mm |
| M2 × 6 mm | 3 | Bandeja de batería a las tuercas de la tapa |
| Tuerca M2, hueco impreso de 4,2 mm entre caras | 12 | Waveshare 3, cámara 2, MT3608 2, cassette 2, batería 3 |

Las longitudes se miden bajo la cabeza. Las arandelas de 0,5 mm se usan **solo en los dos tornillos de la cámara**, donde están incluidas en el cálculo. No sustituir los M3×45 por los M3×25 de V4. Los tamaños entre caras corresponden a los huecos impresos. Preparar las roscas en plástico con las piezas sueltas, retirar las virutas y volver a sacar los tornillos antes de introducir electrónica.

Se necesita cinta blanda de hasta 8 mm para la batería y cinta estrecha o sujeción aislante para las bandejas de los módulos. La batería declara PH-2.0 y Waveshare utiliza MX1.25: prever el adaptador y comprobar la polaridad antes de conectarlo. Esta guía define el montaje mecánico; el cableado, la corriente admisible del interruptor concreto y el ajuste de salida del MT3608 se comprueban en el circuito real.

## Cotas y distribución

Las coordenadas siguientes son del montaje CAD antes de trasladar cada STL a la cama. X es horizontal, Y apunta hacia las orejas y Z hacia la pantalla. No reflejar el montaje a partir de una fotografía trasera.

| Interfaz | Cota de V5 |
| --- | --- |
| Cristal / asiento | Ø48,96 / Ø49,66 mm: 0,35 mm radial |
| Área activa / ventana | Ø44,16 / Ø45 mm; reborde frontal 1,3 mm |
| Frontal del cristal | Z=58,7 mm |
| Cristal a plano posterior de insertos | 10,399996 mm, medido en el STEP |
| Soporte Waveshare | Z≈46,30 a 48,30 mm |
| Pasos de montaje M2 / M3 | Ø2,4 / Ø3,4 mm |
| Apoyo de las dos mitades | Z=27 mm; junta cosmética exterior de 0,3 mm |
| Hombro y cámara lateral M3 | Hombro Z=27 a 29; cámara Z=29 a 31,8 mm |
| Asiento y punta del M3×45 | Z=−8,6 / 36,4 mm |
| Hombro M2 del soporte Waveshare | Z≈48,30 a 50,30 mm; cámara hasta 52,20 mm |
| Reserva de batería | 67 × 57 × 11,5 mm, centro XY=(0; −5), base Z=12 mm |
| Bandeja desmontable de batería | 71 × 61 mm; suelo Z=10 a 12, apoyos de la tapa hasta Z=10 mm |
| Frente de cámara | Envolvente redondeada 58 × 39 mm, Z=44 a 61,6 mm |
| Reserva de cámara | 48 × 29 × 31 mm, centro XY=(0; 44), Z=27,4 a 58,4 mm |
| Bandeja de cámara | Z=45 a 47,4 mm; ajuste horizontal de −3 a +3 mm |
| Marco de cámara | Exterior 46 × 33; hueco 38,8 × 25,8 mm |
| Adaptador óptico | 36 × 28 mm, abertura Ø20; cuello Ø22,8 en paso Ø23,4 mm |
| Reserva del MT3608 | 38 × 20 × 17 mm, centro XY=(0; −5), Z=−9 a 8 mm |
| Hueco de su bandeja | 38,6 × 20,6 mm: 0,3 mm por lado respecto a la reserva |
| Separación elevador / bandeja de batería | 2 mm entre Z=8 y la cara inferior Z=10 mm |
| Cassette del interruptor | 32 × 24 mm, centro XY=(32; −5), Z=−19,6 a −18 mm |
| Bolsillo SS12D00 | 9,5 × 5 × 4,5 mm, Z=−16,2 a −11,7 mm |
| Paso del mando | 6,6 × 3 mm; desplazamiento nominal horizontal de 2 mm |

Las tuercas entran por ranuras laterales antes de instalar los módulos. Los hombros continuos de 2 mm soportan la fuerza de apriete: la tuerca no puede salir hacia la cabeza del tornillo. La probeta 10 reproduce este principio. En la cámara, el hombro está en Z=47,4 a 49,4 y la cámara de tuerca en 49,4 a 51,3 mm. En el MT3608 está por encima de la tuerca, de Z=−13 a −11; la cámara ocupa −14,9 a −13 mm. En la cassette está entre Z=−15,6 y −13,6; su cámara ocupa −13,6 a −11,7 mm. Para la bandeja de batería, los hombros quedan **sobre las tuercas**, en Z=8 a 10, y sus cámaras en Z=6,1 a 8 mm; los M2×6 entran desde arriba, con asiento Z=12 y punta Z=6 mm. Respetar el sentido de montaje y no abrir esos hombros al retirar soportes.

Waveshare conserva sus insertos originales en `(0; 20,5)`, `(−13,75; −14,7)` y `(13,75; −14,7)`. Los anclajes de su soporte a la carcasa son ahora `(−24; 23)`, `(−25,5; −13,8)` y `(16; −24,8)`: **el anclaje superior cambió para despejar la cámara**. Las correderas de cámara se fijan en `(−29,5; 44)` y `(29,5; 44)`; la bandeja MT3608 en `(0; −23)` y `(0; 13)`; y la bandeja de batería en `(−37; −13)`, `(38; 0)` y `(12; 28)`, separados de la torre M3 y del paso de cinta.

Los pulsadores conservan vástago cuadrado de 3,6 mm, guía interior de 4,2 mm, guía exterior Ø8,6 y cabeza Ø10. La separación nominal en reposo es 0,30 mm y el tope limita el movimiento impreso a 0,50 mm: la depresión nominal del interruptor es 0,20 mm. [Shouhan publica 0,20 ± 0,05 mm para el TS24CA](https://www.sohantech.com/ts24ca-24mm-momentary-tact-switch-smd-push-button-switch-product/). La posición estática del STEP y esa referencia no certifican el clic ni el retorno del mecanismo impreso: comprobar que ambos botones quedan libres y sin precarga.

## Pruebas de ajuste e impresión

1. Imprimir primero las probetas **06, 09 y 10**. El cristal entra sin presión lateral, los vástagos deslizan y las tuercas llegan a sus hexágonos por los laterales sin romper sus hombros. Ajustar la compensación de la impresora; no escalar toda la carcasa.
2. Imprimir **11, 14, 15, 16 y 17 antes de las carcasas completas**. Presentar la cámara real con su flex, conectores y patillas; el MT3608 con su potenciómetro y cables; y el SS12D00 con todo su mando y terminales. Probar la batería y su cinta sobre la bandeja 17. Los soportes no suponen taladros de montaje del fabricante. La pieza 13 permite adaptar una abertura diferente sin modificar el frontal completo.
3. Como punto de partida: boquilla de 0,4 mm, capa de 0,20 mm, cuatro perímetros, cinco capas de cierre y 15–20 % de relleno en carcasas. Imprimir pulsadores macizos. Usar PLA para el primer ajuste o PETG para piezas de uso y revisar el laminado de voladizos, hombros y correderas.
4. Bloquear soportes **dentro de los conductos acústicos Ø1,8 mm** para evitar material atrapado. Conservar libres también las entradas laterales de tuercas y los pilotos ciegos. Los STL se exportan sobre Z=0; los botones apoyan su cabeza exterior en la cama. Los adaptadores ópticos **12 y 13 se exportan con la cara exterior de la brida sobre la cama y el cuello hacia arriba**. Retirar rebabas y comprobar los canales con todas las piezas sueltas.

## Orden de montaje y mantenimiento

1. Con todo desconectado, preparar las roscas impresas de pulsadores, adaptador óptico y retenedor SS12D00. Limpiar las piezas. Introducir las cuatro tuercas M3 y las **doce M2** por sus entradas laterales **antes de instalar las placas y las bandejas**. No introducirlas desde los planos de unión.
2. Empezar por la tapa trasera, dejando fuera la bandeja de batería 17. Preparar el interruptor en la cassette 15 con sus patillas hacia el interior. Comprobar ambos extremos de su recorrido con el mando accesible desde atrás. La referencia de cuerpo de 3,5 mm deja hasta 1 mm bajo el retenedor: si existe juego, ajustar con un calce aislante blando sobre zonas inmóviles del cuerpo, conservando libres mando y contactos. Sujetar el retenedor 16 con dos M2×6 y la cassette a la tapa con dos M2×8. No deformar el cuerpo al apretar.
3. Sujetar el MT3608 a la bandeja 14 con cinta por sus ranuras y montar la bandeja con dos M2×6, **antes de colocar la bandeja de batería**. Mantener componentes, aislante, soldaduras y cables dentro de su reserva; el hueco de 38,6 × 20,6 mm deja 0,3 mm por lado respecto a la reserva. Ajustar eléctricamente el módulo mientras está accesible. La separación de 2 mm bajo la futura bandeja de batería es geométrica y no constituye una validación térmica.
4. Fijar la antena GNSS arriba, centro `(0; 61; 26,5)`, y el altavoz en el lateral izquierdo. Comprobar sus cables y los del elevador. Presentar la bandeja 17 sobre los apoyos Z=10 y sujetarla con **tres M2×6**, en `(−37; −13)`, `(38; 0)` y `(12; 28)`. Sus tuercas deben estar ya cargadas por el lateral bajo los hombros Z=8 a 10. Colocar después la batería sin presión sobre el pouch, pasar la cinta blanda y conservar libre su salida de cable.
5. Preparar la cámara sobre la bandeja 11. La referencia de placa es 40 × 27 mm: sobre el hueco del marco queda un apoyo nominal de solo 0,6 mm por borde. Sujetar únicamente márgenes de PCB libres de componentes con cinta aislante; no comprimir flex, conectores ni óptica. Una base gruesa bajo la placa consume la holgura frontal disponible. Las patillas y cables pasan por el centro abierto.
6. Presentar la cámara desde el interior del frontal y colocar los dos M2×8 con sus arandelas de 0,5 mm. Dejar flojos, ajustar hasta ±3 mm en X y alinear **la lente real** con la abertura frontal. El flex original debe permitir esa orientación sin estirarlo ni plegarlo bruscamente; el CAD no define su longitud ni un anclaje exacto del sensor. Sujetar el sensor por su soporte real, sin apoyar el adaptador sobre el cristal de la lente. Si la configuración concreta no permite la alineación, adaptar primero la bandeja o la pieza 13 antes de cerrar el conjunto.
7. Instalar por fuera el adaptador 12 con dos M2×4, sin arandelas adicionales. La pieza 13 lo sustituye cuando se necesite otro diámetro o posición de abertura. Comprobar imagen, enfoque y que los bordes no recortan el campo de visión. La lente representada en las vistas es ilustrativa. El paso Ø20 no certifica ausencia de viñeteo para cualquier óptica OV2640.
8. Introducir la pantalla desde dentro, sin la carcasa comercial redonda. Montar el soporte 03 con tres M2×4 en los insertos originales y tres M2×6 en los pilares del frontal. Alternar el apriete hasta apoyar sin flexionar la placa ni cargar el cristal. El hueco superior del soporte deja libre la nueva frente de cámara.
9. Introducir los dos pulsadores desde fuera **después de la pantalla**. Sus taladros transversales quedan tangentes a la placa, paralelos a su plano. Montar los M2×4 de retención con llave acodada desde el interior; las cabezas quedan hacia la zona inferior según el modelo de montaje. Comprobar clic, deslizamiento y retorno sin alimentación y después con el equipo abierto. El tornillo transversal no ajusta la carrera.
10. Guiar los cables fuera de guías de botones, torres, labios y correderas, dejando holgura de servicio entre mitades. Presentar la tapa y colocar los cuatro **M3×45**. Apretar en cruz hasta el contacto de sus apoyos en Z=27; la junta cosmética de 0,3 mm debe permanecer. Comprobar cámara, pantalla, ambos botones, interruptor, USB-C, microSD, audio y GPS con el conjunto cerrado.

El USB-C de Waveshare conserva su ventana lateral. **El USB de la placa de cámara no tiene una segunda abertura exterior garantizada**: acceder con la tapa abierta y, si el conector lo exige, retirando su bandeja ajustable con la batería desconectada. Para mantener el MT3608, abrir la tapa, desconectar y retirar la batería, quitar los tres M2×6 de la bandeja 17 y levantarla; quedan accesibles el potenciómetro y los dos tornillos de la bandeja 14. El interruptor se maneja desde su rebaje trasero; para sustituirlo se desconecta su cableado y se retiran cassette y retenedor. No arrancar la cassette hacia fuera con las patillas todavía cableadas.

## Validación y alcance

La referencia Waveshare contiene **666 sólidos** del STEP oficial y conserva la transformación de coordenadas y el ajuste de pantalla. `validacion_mecanica.json` registra las comprobaciones de **esta V5**, incluidas interferencias entre piezas, tornillería expuesta y reservas provisionales, movimiento de cámara de −3/0/+3 mm, mando del interruptor de −1/0/+1 mm y barrido de los pulsadores. `validacion_stl.json` revisa los STL exportados, su cierre, componentes, orientación, dimensiones y huellas SHA-256. Consultar el resultado de la ejecución y las huellas del paquete: el recuento de comprobaciones de V4 no se traslada a esta versión.

El STEP corresponde al modelo base **ESP32-S3-Touch-AMOLED-1.75**; no certifica todos los añadidos de la variante **1.75-G**. Los micrófonos están simplificados sin su abertura real: las cámaras acústicas y conductos se sitúan con sus capuchones, y requieren una prueba de voz real. Las reservas de antena **25 × 25 × 4 mm** y altavoz **Ø28 × 7 mm** también son provisionales.

Para los módulos nuevos no hay CAD oficial del ejemplar concreto. La reserva de cámara incluye alturas supuestas para headers y cableado; la conexión del flex y el eje óptico deben ajustarse físicamente. El [MT3608 comercial de diymore se anuncia de 36 × 17 × 14 mm](https://www.diymore.cc/products/diymore-5mt3608-dc-dc-step-up-power-apply-module-booster-power-converter-booster-module-max-output-28v-2a-for-arduino), y aquí dispone de 38 × 20 × 17 mm; comprobar la placa comprada. El nombre SS12D00 tampoco fija todas sus medidas: [Hengqi indica 8,5 × 3,6 × H](https://www.hq-dz.com/en/products/toggleswitch/ssstraighthandletoggleswitch/524.html), y [Bituo ofrece mandos de 2 a 7 mm](https://www.bituoelec.com/power-slide-switch/). La cassette usa un cuerpo supuesto de 8,5 × 3,6 × 3,5 mm, mando de 3 mm y terminales de 5 mm; medir el sufijo y la geometría reales antes de dar por terminado su ajuste.

Las verificaciones digitales prueban las geometrías representadas; el ajuste impreso, el flex, la liberación de botones, el acceso con cables reales y el comportamiento térmico/acústico se comprueban en el prototipo. Los ojos y coloretes de las vistas son ilustración de pantalla y no se imprimen ni modifican el firmware.

## Fuentes y regeneración

- [Waveshare: documentación y recursos oficiales](https://docs.waveshare.com/ESP32-S3-Touch-AMOLED-1.75/Resources-And-Documents).
- Transformación y medidas independientes: `auditoria/step_measurements_independent.json` y `auditoria/step_parts.json`.
- Cotas, reservas y fuentes de módulos: `parametros.json` y `referencias/componentes_medidas.json`.
- STEP original incluido: `referencias/waveshare-ESP32-S3-Touch-AMOLED-1_75.stp`; malla de referencia: `referencias/step_mesh_native.npz`.
- Batería: `referencias/bateria-955565.jpg`, foto del usuario.

Conservar `generar.py`, `modulos_v5.py`, `cad_base.py`, `parametros.json`, `auditoria/` y `referencias/`. La regeneración normal usa la malla incluida y no necesita reimportar el STEP. Desde PowerShell, cambiar a la carpeta V5 descomprimida y ejecutar con Blender 5.x y Python con NumPy:

```powershell
cd 'C:\ruta\al\paquete-V5'
& 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe' --background --factory-startup --python generar.py
python validar_stl.py
```

`-- --no-render` omite las imágenes. Montar juntas las piezas V5; no mezclar soportes, tapas ni tornillería de V4.
