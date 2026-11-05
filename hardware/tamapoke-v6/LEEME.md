# TamaPoke V6 · gato y mochi, batería EEMB y antena GPS

Adaptación personal del `TamaPoke.3mf` aportado por el usuario para la Waveshare ESP32-S3-Touch-AMOLED-1.75-G. Conserva la base circular del frontal y sus tres puntos de cierre; añade una forma de gato con orejas continuas y un frontal mochi alternativo. Ambos utilizan el mismo cuerpo, pantalla y dos pulsadores. La trasera nueva es un domo suave, inspirado en la forma redonda de la [referencia Meow Buddy indicada por el usuario](https://makerworld.com/es/models/2235085-esp-vocat-meow-buddy-an-ai-adorable-pet-that-liste?from=search#profileId-2432224), y aloja en tres capas el altavoz, la batería **EEMB LP562438 de 500 mAh, 24,5 × 40 × 5,9 mm**, y la antena GNSS completa. El modelo de Meow Buddy no se ha descargado ni utilizado como fuente de malla.

La trasera alcanza **Ø62 mm**, se estrecha a Ø60 en la unión y termina en un plano central Ø20 para apoyar durante la impresión. Su perfil interior sigue la curva exterior con un desplazamiento normal de 2 mm; los pilares quedan contenidos dentro del domo. El conjunto ocupa Z=−37 a 15 mm, **52 mm de fondo**. Dimensiones exteriores aproximadas: **gato 62 × 69,4 × 52 mm** y **mochi 62 × 62 × 52 mm**. Consultar los valores exportados en `validacion_mecanica.json`. Las piezas originales del receptor Qi, sus retenes y el anillo Magsafe no forman parte del nuevo montaje.

## Archivos y tornillería

Hay **11 STL**. Elegir **01 o 02** como frontal; imprimir **dos unidades del separador 06**. Importar en milímetros, al 100 %, sin escalar el conjunto.

Los proyectos **`TamaPoke_Gato_V6_Impresion.3mf`** y **`TamaPoke_Mochi_V6_Impresion.3mf`** reúnen las ocho piezas que se imprimen para cada alternativa: un frontal, cuerpo, dos bandejas, dos separadores y dos pulsadores. Las tres probetas se entregan aparte. Los proyectos están en milímetros y no incorporan G-code ni un perfil de impresora: seleccionar la máquina, el material y los soportes en el laminador.

| Archivo | Cantidad | Función |
| --- | ---: | --- |
| `01_frontal_gato.stl` | 1, alternativa | Frontal redondo con orejas integradas |
| `02_frontal_mochi.stl` | 1, alternativa | Frontal redondo sin orejas |
| `03_cuerpo_sin_carga_magnetica.stl` | 1 | Cuerpo trasero y pilares de cierre |
| `04_bandeja_bateria_y_GPS.stl` | 1 | Batería por arriba y antena por debajo |
| `05_soporte_altavoz.stl` | 1 | Bandeja superior del altavoz |
| `06_separador_interno_7_7mm.stl` | **2** | Mantienen la distancia entre las dos bandejas |
| `07_pulsador_inferior.stl` | 1 | Botón inferior, visto de frente con las orejas arriba |
| `08_pulsador_superior.stl` | 1 | Botón superior; usar en su posición correspondiente |
| `09_prueba_pantalla.stl` | 1 primero | Probeta del diámetro de alojamiento del cristal |
| `10_prueba_pulsadores.stl` | 1 primero | Probeta del paso Ø3,2 mm |
| `11_prueba_tuerca_M2.stl` | 1 primero | Entrada lateral y hombro de retención de la tuerca |

| Tornillería | Cantidad | Uso |
| --- | ---: | --- |
| M2 × 5 mm | 3 | Placa Waveshare a sus insertos originales |
| M2 × 8 mm | 3 | Cuerpo trasero a los pilotos impresos del frontal |
| M2 × 16 mm | 2 | Apriete del conjunto de bandejas y separadores |
| Arandela M2, **Ø5 exterior, Ø2,2 interior y 0,5 mm de espesor** | 2 | Bajo las cabezas de los M2×16 |
| Tuerca M2 | 2 | Alojamientos de 4,2 mm entre caras, entrada lateral de 4,3 mm |

Las longitudes se miden bajo la cabeza. Utilizar cabezas cilíndricas con hexágono interior de hasta **Ø3,8 mm**; los pozos de cierre tienen Ø4,4 mm. Para llegar a sus cabezas se necesita una llave hexagonal de 1,5 mm con alcance de al menos 30 mm. Los M2×16 están calculados con las arandelas de 0,5 mm indicadas. Si se usan **M2×6 para la placa**, añadir una arandela de 1 mm en cada uno para conservar la penetración prevista del M2×5.

Preparar también una cinta blanda de unos **6 mm de ancho** para la batería y cinta de doble cara de aproximadamente **0,4 mm** para la cara posterior de la PCB de antena. La batería con conector JST PH de paso 2 mm requiere adaptación a la entrada **MX1.25 de dos polos** de Waveshare; no encajan directamente. El diseño reserva 8 × 8 × 6 mm para esa conexión, pero la pieza y sus cables deben comprobarse físicamente. Verificar la polaridad antes de conectar.

## Ajustes que incorpora esta versión

El asiento del cristal mide **Ø49,66 mm**, con 0,35 mm de holgura radial respecto al Ø48,96 del STEP. Se amplía desde Z=10 mm para despejar también los pequeños salientes posteriores del display. La cara frontal del cristal queda en Z=12,9 y el apoyo posterior de sus insertos en Z≈2,5 mm. Los tres pasos M2 se corrigen a Ø2,4 y a las posiciones del STEP: `(0; 20,5)`, `(−13,75; −14,7)` y `(13,75; −14,7)`.

El hueco de botón original se cierra y se abren **los dos pasos Ø3,2 mm sobre los ejes reales del STEP**. Cada pulsador tiene vástago Ø2,5, punta de contacto de **1,6 mm de ancho y 1,0 mm de alto**, y collar interior Ø4,4 mm. El collar limita la extracción contra la guía interior Ø5,4; una cámara Ø5 despeja el collar por dentro. No lleva tornillo de retención. La separación nominal en reposo es de 0,25 mm. El frontal y los pulsadores conservan la geometría del montaje previo; **su barrido completo no se ha repetido al cambiar el domo**. El movimiento hacia dentro de 0,45 mm del diseño previo **no es un tope mecánico de carrera**. El clic, la liberación y la ausencia de precarga deben comprobarse en ambos botones reales.

La antena se dimensiona por su conjunto completo de referencia, **27 × 27 × 6,7 mm**, incluyendo PCB; la cerámica de 25 × 25 mm no representa todo el volumen. Su alojamiento mide 28 × 28 × 7,6 mm y tiene salidas de cable en bordes y esquinas. La cara cerámica apunta hacia la trasera, en dirección −Z, bajo una pared de plástico sin imanes.

| Capa, desde la pantalla hacia atrás | Reserva y posición CAD |
| --- | --- |
| Altavoz | 32,5 × 22,5 × 3,8 mm; centro XY=(1; 1), Z=−8,8 a −5 |
| Batería | 26,5 × 42 × 7,4 mm; centro XY=(1; −2), Z=−17,7 a −10,3 |
| Antena completa | 27 × 27 × 6,7 mm; centro XY=(1; 1), Z=−26,4 a −19,7 |

Son coordenadas del montaje, con Y hacia las orejas y Z hacia la pantalla. Los cuerpos y bandejas se trasladan después a Z=0 para imprimir; los pulsadores se orientan además sobre su vástago. En el cuerpo 03, el plano trasero Z=−37 pasa a ser la base Z=0 del STL. La batería real termina nominalmente en Z=−11,8 y conserva espacio antes del soporte de altavoz. Las dos fijaciones internas están en `(−18,5; 5)` y `(20,5; 5)`. Sus tuercas se cargan lateralmente en Z=−23,2 a −21,3 y apoyan contra hombros continuos de 2 mm, situados **por encima de ellas**, de Z=−21,3 a −19,3. Los M2×16 tiran las tuercas hacia esos hombros; la punta prevista queda en Z=−24,3, antes del final ciego Z=−25.

## Pruebas e impresión

1. Imprimir primero **09, 10 y 11**. El cristal debe pasar por la probeta sin presión; esta comprueba el diámetro, no toda la profundidad de montaje. El vástago de cada botón debe deslizar y la tuerca debe entrar desde el lateral de la probeta 11 hasta quedar bajo su hombro, sin deformarlo. La probeta de tuerca tiene 6 mm de alto, cámara Z=2,1 a 4 y hombro Z=4 a 6.
2. Imprimir **04 y 05 antes del cuerpo completo**. Presentar la batería, la antena con su coaxial y el altavoz real. El altavoz no se ha medido: su referencia procede del rebaje original de 32 × 22 × 3,5 mm. La bandeja 05 es la prueba para confirmar que la unidad disponible cabe, incluidos cables y adhesivo.
3. Como perfil inicial: boquilla de 0,4 mm, capa de 0,20 mm, cuatro perímetros, cinco capas de cierre y 15–20 % de relleno para las carcasas. El cuerpo 03 se entrega con el plano central Ø20 sobre la cama y la abertura hacia arriba: **necesita brim y soportes desde la cama bajo la curva exterior del domo**. Revisar esa primera zona curva en la vista de capas; el plano central no permite imprimir toda la trasera sin soportes. Imprimir los pulsadores macizos y con brim; están exportados con la cara exterior del vástago sobre la cama. Revisar también el techo y los bordes de la bandeja 04: cualquier soporte de su alojamiento GPS debe poder retirarse antes de introducir la antena.
4. Mantener libres los conductos acústicos Ø1,8 mm, pilotos, entradas de tuerca y pozos largos de tornillo. Bloquear soportes dentro de esos pasos cuando el laminador intente rellenarlos. Limpiar rebabas con las piezas sueltas. El paso horizontal del botón en el frontal debe comprobarse además de la probeta; no compensar un atasco escalando toda la carcasa.

## Montaje

1. Con la electrónica desconectada, limpiar las piezas y preparar suavemente los tres pilotos impresos Ø1,8 del frontal con sus M2×8. Retirar después los tornillos y las virutas. Introducir las dos tuercas M2 por los laterales de los pilares del cuerpo 03, **antes de colocar las bandejas**. No introducirlas desde arriba atravesando el hombro.
2. Introducir los pulsadores 07 y 08 **desde el interior del frontal**, con el vástago fino hacia su paso exterior; el collar Ø4,4 queda dentro y no atraviesa el taladro Ø3,2. Presentarlos en sus guías y comprobar que se mueven libres.
3. Introducir la pantalla **desde la cara frontal hacia atrás, con la placa por delante del cristal**. Presentar primero el lado de la microSD y acompañar el movimiento sin forzar conectores ni puntas de botón. El cristal Ø48,96 no puede atravesar desde atrás el estrechamiento original Ø47. Una vez asentado, sujetar desde atrás con tres M2×5, alternando el apriete sobre los insertos metálicos. No utilizar los tornillos para arrastrar un cristal que no ha asentado. Comprobar de nuevo que ambos botones hacen clic y se liberan sin quedar pulsados.
4. Pasar la cinta blanda por las ranuras de la bandeja 04 situadas hacia Y=−19,5. Esta posición conserva el paso de la cinta por fuera del alojamiento GPS. Presentar la antena por debajo de la bandeja, con su PCB hacia el techo y la cerámica hacia la trasera. **Fijar la cara posterior de la PCB con cinta de aproximadamente 0,4 mm; no pegar ni prensar la cara cerámica.**
5. Elegir antes de pegar la antena la salida de coaxial más cercana al conector de la placa. Se puede girar la antena 90° para aprovechar otra esquina. La referencia de cable es de unos 35 mm: comprobar el recorrido completo, incluido el conector, sin tensarlo ni doblarlo contra un borde. La antena no debe quedar suspendida del coaxial o del IPEX.
6. Colocar la batería en la cara superior de 04 y asegurarla con la cinta sin comprimir el pouch. Sus cables salen por el paso previsto hacia la conexión de batería. Presentar la adaptación PH2.0–MX1.25 en su reserva lateral, sin introducir conectores, empalmes ni sobrantes bajo la celda. Mantener la batería desconectada durante el montaje.
7. Sujetar el altavoz real en 05, conservando sus cables y la cara emisora libres. Usar fijación fina solo si queda dentro de la altura disponible de 3,8 mm. No tirar de sus cables para llevarlo a su posición.
8. Apoyar el conjunto batería/GPS sobre los dos pilares del cuerpo 03. Colocar **los dos separadores de 7,7 mm** sobre sus taladros y la bandeja de altavoz encima. Introducir desde arriba los **dos M2×16 con sus arandelas de 0,5 mm**, atravesando bandeja, separador y portabatería hasta las tuercas. Apretar alternadamente hasta que apoyen las piezas rígidas, sin cargar la batería ni la cerámica.
9. Presentar frontal y cuerpo abiertos uno junto al otro. Conectar altavoz y antena; realizar la conexión de batería tras verificar su polaridad. Dejar holgura para abrir el equipo y mantener cables fuera del labio, las tres columnas de cierre y las guías de botones. El conector IPEX se presenta alineado sobre su toma; el coaxial no sirve para tirar de él.
10. Presentar las mitades y colocar los **tres M2×8** por los pozos traseros hasta los pilotos del frontal. Apretar por turnos hasta el contacto de los apoyos en Z=0. La junta exterior de 0,3 mm es intencional; no apretar para eliminarla. Comprobar pantalla, ambos botones, acceso USB, audio, alimentación y recepción GPS con el conjunto cerrado.

Para mantener el interior, abrir los tres tornillos de cierre, desconectar la batería y retirar los dos M2×16. La bandeja de altavoz, los separadores y el conjunto batería/GPS se separan sin tener que romper adhesivos del cuerpo. Mantener identificados los separadores sueltos. El acceso a microSD y el paso de los conectores deben confirmarse con la placa real: el 3MF original no incluía una abertura lateral completa para extraer la tarjeta.

## Comprobaciones y fuentes

Esta edición del **domo redondo utiliza comprobaciones mínimas**, según lo solicitado: revisión de las **11 mallas STL** y espacio de la nueva trasera frente a los frontales, piezas interiores y reservas de batería y antena. `validacion_mecanica.json` identifica este alcance como `quick`; la revisión de los STL figura en `validacion_stl.json`. La lectura de vuelta de las mallas de cada proyecto figura en `validacion_3mf.json`.

Se reutiliza el montaje anterior y se sustituye solo el cuerpo trasero. **No se han repetido la comparación completa con los 666 sólidos del STEP, los barridos de movimiento de botones ni la comprobación completa de tornillería.** Los ensayos y auditorías anteriores del frontal son antecedentes del diseño, no validaciones de esta nueva trasera. Los paquetes de esta edición no presentan el informe antiguo de tornillería ni el plano anterior como resultados actuales. Esta revisión mínima no sustituye una prueba física de montaje.

El STEP corresponde al modelo base 1.75 y puede no representar todos los añadidos de la variante **1.75-G**. Se conserva margen posterior para esos componentes, que deben comprobarse en la placa del usuario. El volumen del altavoz es una referencia del archivo original; la batería, el adaptador, el coaxial y la antena requieren la prueba de sus piezas reales. La comprobación geométrica de espacio para la antena no certifica recepción GPS. Los ojos y coloretes de las vistas son ilustrativos, no piezas impresas ni cambios de firmware.

- [EEMB: LP562438](https://www.eemb.com/product-142), referencia de cuerpo de 24,5 × 40 × 5,9 mm.
- [Waveshare: antena GNSS cerámica completa](https://www.waveshare.com/product/gnss-ceramic-antenna.htm), referencia de PCB, cerámica y cable.
- [Waveshare: documentación de la pantalla y placa](https://docs.waveshare.com/ESP32-S3-Touch-AMOLED-1.75).
- Medidas, variantes y enlaces primarios: `referencias/medidas_bateria_gps.json`.
- Auditoría del 3MF y sus posiciones: `auditoria/original_inspeccion_independiente.json` y `auditoria/original.json`.

Crédito del archivo base: **Jetto Hobby**, título en metadatos **“Pokemon Tamagotchi with Magsafe charging”**, licencia indicada **“Standard Digital File License”**. Esta adaptación conserva el archivo fuente y su atribución para uso personal; no se ha publicado. Las instrucciones y fotografías incluidas dentro del 3MF se han utilizado como datos de referencia para comprender sus piezas.

Para actualizar únicamente el domo, conservar el montaje `tamapoke_v6_montaje.blend`, `actualizar_domo.py`, `generar.py`, `cad_base.py`, `parametros.json` y `validacion_mecanica.json`. Este flujo reutiliza el frontal y los interiores existentes, cambia la trasera y realiza sus comprobaciones mínimas. Desde la carpeta descomprimida, con Blender 5.x y Python con NumPy:

```powershell
cd 'C:\ruta\al\TamaPoke-V6'
& 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe' --background --factory-startup --python actualizar_domo.py
python exportar_3mf.py
```

La regeneración completa mediante `generar.py` utiliza también `auditoria/` y `referencias/` y vuelve a ejecutar comprobaciones más extensas; no es el flujo rápido empleado para esta entrega. Usar las piezas de esta V6 juntas, con uno de sus dos frontales alternativos.
