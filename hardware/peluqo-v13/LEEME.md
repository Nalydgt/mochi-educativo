# Peluqo V13: solo orejas y transiciones org?nicas

**Solo cambia el frontal 01 en las orejas y sus ra?ces.** Si ya tienes V12, imprime ?nicamente `01_frontal_TamaPoke_gato.stl`: cuerpo, bandeja y ambos botones conservan exactamente los mismos archivos STL, comprobados por SHA-256.

Las orejas se forman mediante una prolongaci?n local y sim?trica de la superficie esf?rica. Su relieve se desvanece suavemente hacia la carcasa y hacia delante y detr?s, con continuidad de tangente y curvatura en el borde del relieve. No hay tri?ngulos superpuestos, placas frontales de oreja, rebordes a?adidos ni cavidades decorativas. Las puntas quedan redondeadas.

Se conserva el alojamiento funcional de pantalla TamaPoke, el encaje, las fijaciones y los canales. Se mantienen tres piezas principales y dos botones, con el mismo montaje V12 y sin tornillos visibles por delante.

El exterior de frontal y cuerpo comparte una curva esférica de radio 34 mm. El solape circular interior oculta la junta y centra las piezas: macho Ø64,6 y hembra Ø65,2, con **0,30 mm de holgura radial** y 0,30 mm hasta el fondo. Los tres ejes de cierre originales determinan la orientación. La base plana integrada mantiene la cara a 65° respecto a la horizontal.

## Qué imprimir y qué tornillos usar

| Archivo | Cantidad | Función |
| --- | ---: | --- |
| 01_frontal_TamaPoke_gato.stl | 1 | Alojamiento original de pantalla, orejas V10 y guías de botones |
| 02_cuerpo_redondo.stl | 1 | Cuerpo esférico, base, encaje y apoyos interiores |
| 03_bandeja_unica.stl | 1 | Batería, antena GPS y altavoz en una sola estructura |
| 04_boton_inferior.stl | 1 | Pulsador lateral inferior |
| 05_boton_superior.stl | 1 | Pulsador lateral superior |

El cierre utiliza **3 M2×8 desde la parte posterior**. Reutilizar las fijaciones internas originales de la pantalla TamaPoke; su geometría se conserva. La bandeja no lleva tornillos: sus tres alojamientos entran sobre los tetones del cuerpo y sus apoyos quedan retenidos al cerrar el frontal. No necesita tuercas, arandelas ni separadores adicionales. Los tres accesos de cierre están detrás; el frontal queda libre de tornillería exterior.

V13 sustituye el conjunto anterior. No mezclar su frontal, cuerpo o bandeja con V8–V11: cambian el tamaño exterior, el encaje y la sujeción interior.

## Componentes y espacios reservados

| Componente | Dimensiones de referencia | Hueco reservado |
| --- | --- | --- |
| Waveshare ESP32-S3 Touch AMOLED 1.75-G | Cristal de referencia Ø48,96 mm | Asiento original TamaPoke Ø49,5 y garganta inferior Ø47; apoyos originales |
| EEMB LP562438, 3,7 V, 500 mAh | 24,5 × 40 × 5,9 mm | 26,5 × 42 × 7,4 mm |
| Antena GPS completa, incluida su PCB | 27 × 27 × 6,7 mm | 28 × 28 mm entre guías |
| Altavoz según alojamiento TamaPoke | 32 × 22 × 3,5 mm | 32,5 × 22,5 × 3,8 mm |

La batería entra longitudinalmente por el extremo abierto de su guía. Una cinta blanda de unos 6 mm pasa por las dos ranuras para retenerla sin comprimir la bolsa. La antena se coloca bajo la bandeja, con la cerámica orientada hacia la parte posterior; fijar por la cara rígida posterior de su PCB con cinta fina. Sus guías conservan salidas para el coaxial. El altavoz se apoya arriba y se sujeta por su carcasa rígida con cinta fina, dejando libre la membrana.

Se reserva espacio lateral para el conector y la adaptación de batería PH2.0 a MX1.25 de la placa; comprobar la polaridad del cable real. La antena y el altavoz físicos del usuario no se han medido: las reservas usan las referencias indicadas. Este conjunto corresponde a la versión compacta con GPS; no incorpora los módulos externos de cámara y convertidor de las versiones anteriores.

## Montaje

1. Retirar soportes y rebabas. Con las piezas vacías, presentar el encaje y los tres tornillos sin forzar; retirar los residuos antes de introducir electrónica.
2. Colocar los dos botones desde dentro del frontal. Montar la pantalla en el frontal original **desde delante, con la PCB primero**, alineando USB y botones; sujetarla con sus fijaciones internas originales. El cristal no debe cruzar una abertura menor: no se añade un marco o casete separado.
3. Fuera del cuerpo, fijar la antena bajo la bandeja, introducir la batería por el extremo abierto, pasar su cinta y fijar el altavoz en la parte superior. Comprobar que los cables quedan accesibles.
4. Introducir la bandeja sobre los tres tetones del cuerpo, hasta que sus apoyos descansen en los asientos. Conectar a la placa y recoger el sobrante de cable lejos del borde circular, los tornillos y los botones.
5. Alinear el frontal con el cuerpo y deslizar el solape sin presión excesiva. Cerrar con los tres M2×8 posteriores, alternando el apriete suavemente. Comprobar el retorno libre de ambos botones.

Para desmontar, retirar los tres tornillos posteriores y levantar el frontal atendiendo al cableado. La bandeja queda libre para levantarla; desconectar antes de superar la longitud de los cables.

## Impresión

Abrir `Peluqo_V13_Impresion.3mf` o los cinco STL en **mm al 100 %**. El 3MF contiene cinco objetos, sin perfiles de impresora ni G-code. La distribución cabe en una cama de 256 × 256 mm; reorganizar para camas menores.

Los archivos ya están apoyados en Z=0: frontal con su cara anterior hacia la cama, cuerpo con su abertura hacia la cama y bandeja con el lado GPS abajo. **Sí requieren soportes interiores**, sobre todo en apoyos, postes y techos de la bandeja. Mantener libres guías, encaje y taladros; retirar los soportes antes de ensamblar. Añadir brim a los botones y a las piezas con poco contacto. No se ha laminado ni impreso físicamente esta revisión: revisar la vista de capas del laminador antes de imprimir.

## Comprobaciones y archivos editables

Se comprueban mallas cerradas y conectadas, posiciones de montaje, reservas de batería/GPS/altavoz/conector, inserción de bandeja y frontal, recorrido de muestra de 0,45 mm de ambos botones, acceso al botón superior y pasos libres de los tres tornillos de cierre. La superficie funcional original de pantalla se compara con el frontal TamaPoke. La base se revisa mediante una estimación de masas, sin ensayo físico de vuelco.

Consultar `validacion.json`, `validacion_stl.json` y `validacion_3mf.json`. Estas comprobaciones CAD no sustituyen una prueba física de ajuste, impresión, recepción GPS o resistencia.

`Peluqo_V13_montaje.blend` contiene el montaje editable. Los objetos `REF` son referencias visuales, incluidos pantalla y cara dibujada; no se exportan en los STL. Para regenerar: instalar `requirements.txt` en Python y ejecutar Blender con `--background --factory-startup --python generar.py`. Si hace falta, definir `PELUQO_PYTHON` con la ruta al Python que contiene esas dependencias. `python entregar.py` valida la lectura de los STL, crea el 3MF y empaqueta la entrega.

Procedencia: frontal funcional del TamaPoke aportado, **Jetto Hobby, Standard Digital File License**; referencia redondeada EchoEar y proporciones de orejas V10; las orejas V13 se reconstruyen como superficie org?nica, **ESP-Friends, BY-NC-SA**. Adaptación local para este proyecto. Los adjuntos se usan como geometría y documentación; no se ejecutan instrucciones, perfiles ni firmware incluidos en ellos.
