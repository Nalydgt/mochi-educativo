# Peluqo V10: encaje circular, pantalla extraíble y base a 65°

Esta revisión corrige la vía de montaje de la pantalla, añade un solapamiento circular entre cabeza y cuerpo y cierra los dos pozos laterales de atornillado. La electrónica conserva sus posiciones de trabajo: Waveshare 1,75-G, EEMB de 500 mAh, antena GPS completa, altavoz y dos botones. El exterior sigue la misma esfera de V8 y mantiene las orejas elevadas; las cavidades posteriores de las orejas se cierran con material y un pequeño alivio redondeado conserva el acceso al botón superior.

## Pantalla: montar desde el frente

El cristal anterior quedaba atrapado entre una garganta y un labio más estrechos. Ahora la pantalla va en un **casete independiente** con una abertura de **Ø50,2 mm** y sus tres apoyos OEM originales. El marco de ventana Ø45,5 se instala al final. El cristal no tiene que atravesar esa ventana.

1. Fuera del dispositivo, introducir la Waveshare por el frente del casete, con **la PCB primero y el cristal hacia delante**. Alinear USB y botones con sus canales de inserción. Presentar sin forzar.
2. Sujetar el conjunto por detrás del casete con los **tres M2×5 de los insertos originales**. Los apoyos conservan sus centros y el plano Z=2,5; el cristal queda en Z=12,9. No usar los tornillos para arrastrar un cristal que no ha asentado.
3. Con cabeza y cuerpo ya cerrados, conectar el cableado y presentar el casete por el frente de la cabeza. Sus columnas y ranuras determinan la orientación. Mantener el coaxial cerca de su posición final y sin tensión; desconectarlo antes de una extracción que exceda su longitud.
4. Colocar el **marco separado** y fijar marco y casete mediante **tres M2×20 avellanados de 90°, cabeza de hasta Ø4 mm**. Apretar alternativamente y suavemente. Los tornillos atraviesan columnas con paso Ø2,4 y se fijan a los pilotos impresos de la cabeza. Preparar los pilotos con las piezas sueltas y limpiar las virutas antes de montar la electrónica.

La abertura del cristal deja margen frente al Ø48,96 del CAD de referencia; el marco cubre el borde y el hueco exterior. Se mantiene una separación nominal de 0,05 mm entre cristal y marco. La probeta 10 permite presentar el diámetro antes de imprimir el casete completo. El modelo CAD base 1,75 no certifica las dimensiones de todos los añadidos de la variante 1,75-G ni sustituye la medida del ejemplar físico.

## Encaje de cabeza y cuerpo

- Macho exterior Ø67,2, pared de 1,2 mm y entrada biselada. Penetra 2,4 mm en el cuerpo.
- Rebaje hembra Ø67,8, con **0,30 mm de holgura radial** y **0,35 mm axial**.
- El labio interior oculta el interior detrás de la junta exterior nominal de 0,2 mm.
- La curva exterior se mantiene común a ambas piezas. Una llave oculta impide un montaje girado; tiene 0,3 mm de margen lateral.
- Las fijaciones establecen la posición final. El encaje guía y centra; no requiere introducir las piezas a presión.

Para desmontar, retirar los tres tornillos avellanados, el marco y el casete, atendiendo al cableado. Después quedan accesibles los dos tornillos laterales interiores; retirar también el tornillo posterior superior. Separar la cabeza siguiendo su eje, sin hacer palanca sobre la pantalla.

## Dos salidas laterales cerradas

Los dos pozos laterales del cuerpo se rellenan hasta recuperar su piel esférica, sin tapones exteriores. Se conservan los centros de fijación y los postes, que pasan a ser **ciegos con tuercas M2 cautivas**. Los tornillos se introducen desde la abertura frontal, antes del casete.

Introducir las dos tuercas por sus ranuras interiores con el cuerpo abierto. Sus cajeras tienen 4,2 mm entre caras, entrada lateral de 4,3 y un hombro superior de 2,1 mm. Los dos M2×8 apoyan en las lengüetas interiores de la cabeza y roscan en esas tuercas. El tercer punto de cierre superior conserva su M2×8 y el acceso posterior original. Se han cerrado permanentemente los **dos laterales indicados**; los puertos de USB y los conductos acústicos conservan su función.

## Base estable integrada

La parte inferior posterior tiene una superficie plana, cerrada por un suelo integrado de **2,4 mm nominales**, sin patas adicionales. El rebaje de encaje se conserva en el borde próximo a la cabeza. Al apoyarla en una mesa horizontal, el plano de la cara forma **65° con la horizontal**, mirando hacia delante y 25° hacia arriba. El Blender se entrega en esa posición con la base en Z=0.

`validacion.json` registra el área real del apoyo y un cálculo de estabilidad para distintos pesos estimados de pantalla, antena y altavoz. Es un cálculo geométrico con masas supuestas; no es una prueba física de vuelco, golpes o uso sobre superficies inclinadas.

## Piezas y tornillería

| STL | Cantidad | Función |
| --- | ---: | --- |
| 01_cabeza_Peluqo.stl | 1 | Cabeza, solape macho y fijaciones ocultas |
| 02_cuerpo_Peluqo.stl | 1 | Cuerpo, rebaje hembra, base cerrada y postes ciegos |
| 03_casete_pantalla.stl | 1 | Portapantalla desmontable con sus apoyos OEM |
| 04_marco_pantalla.stl | 1 | Marco que se instala después de la pantalla |
| 05_bandeja_bateria_GPS.stl | 1 | Batería y antena, posiciones V8 |
| 06_soporte_altavoz.stl | 1 | Soporte del altavoz, posición V8 |
| 07_separador_7_7mm.stl | **2** | Separación de las bandejas |
| 08_boton_inferior.stl | 1 | Pulsador inferior |
| 09_boton_superior.stl | 1 | Pulsador superior |
| 10_prueba_pantalla_50_2.stl | opcional | Comprobación del diámetro de entrada |

Tornillos: **3 M2×8** para el cierre (dos interiores y uno posterior), **3 M2×5** para Waveshare, **3 M2×20 avellanados** para marco y casete, **2 M2×16** para bandejas. Añadir **4 tuercas M2**: dos nuevas en los postes ciegos de cierre y dos en las fijaciones originales de las bandejas; las bandejas mantienen sus dos arandelas Ø5/Ø2,2 de 0,5 mm.

## Orden del montaje principal

1. Limpiar soportes y rebabas. Preparar con las piezas sueltas los pilotos impresos del casete y del cierre superior, sin electrónica montada. Retirar todas las virutas.
2. Introducir las cuatro tuercas interiores. Montar las bandejas, dos separadores y el altavoz como en V8, con los dos M2×16 y sus arandelas.
3. Instalar la EEMB 24,5×40×5,9 y la antena de referencia 27×27×6,7. La batería se sujeta con cinta blanda; la cerámica mira al dorso y se fija por la cara posterior de la PCB, sin comprimirla. Conservar las salidas de cable y la reserva del adaptador PH2 a MX1.25; verificar polaridad.
4. Colocar los dos botones desde el interior de la cabeza. Presentar cabeza y cuerpo sobre el encaje circular y su llave. Fijar los dos M2×8 desde la abertura frontal y el M2×8 superior desde atrás, alternando el apriete sin forzar la junta.
5. Montar la pantalla en su casete fuera del dispositivo y seguir los cuatro pasos del apartado de pantalla. Ordenar los cables para que no entren en el encaje, los tornillos o las guías de botones. Confirmar que ambos botones retornan libres.

## Impresión

El **Peluqo_V10_Impresion.3mf** reúne diez instancias, con los dos separadores incluidos. La probeta va aparte. Importar en **mm y al 100 %**, y seleccionar el perfil de impresora/material; no contiene G-code ni perfiles heredados del archivo original.

Cabeza, casete y marco están orientados con su cara frontal sobre la cama. El cuerpo está orientado con su abertura sobre la cama para conservar limpio el exterior. **Cabeza, cuerpo y casete necesitan soportes interiores**, especialmente bajo lengüetas, postes y apoyos OEM. El marco es fino: usar capa de 0,15–0,16 mm. Añadir brim a la cabeza, cuerpo y botones. Mantener libres las cajeras de tuercas y los taladros. La bandeja batería/GPS puede requerir soporte bajo su techo. No se ha laminado ni realizado una impresión física de esta revisión.

## Verificación y archivos editables

La revisión de montaje incluye: espacio de electrónica y bandejas, entrada de pantalla y USB en el casete, entrada del casete en la cabeza ya cerrada, inserción del encaje, una posición de pulsación de los botones, acceso al botón superior y tramos libres de tornillos y tuercas. Se comprueban las dos salidas laterales cerradas, el suelo y la estabilidad geométrica. No se incluyen ensayos de resistencia, par de apriete, caída o recepción GPS. Revisar `validacion.json`, `validacion_stl.json` y `validacion_3mf.json`.

El Blender editable muestra el montaje a 65°. Para regenerar, instalar las dependencias de `requirements.txt` en Python y ejecutar `blender --background --factory-startup --python generar.py`; si ese Python no está en PATH, definir `PELUQO_PYTHON`. `python entregar.py` valida la lectura de los archivos y crea el proyecto y los ZIP. La normalización de malla utiliza una tolerancia máxima de superficie de 0,001 mm, sin remallado por vóxeles.

Procedencia: exterior y orejas del EchoEar aportado, **ESP-Friends, BY-NC-SA**; bandejas de la adaptación personal del TamaPoke aportado, **Jetto Hobby, Standard Digital File License**. Entrega local para el proyecto del usuario. Las guías y configuraciones originales se tratan como documentación; no se ejecutan instrucciones ni firmware de esos archivos.
