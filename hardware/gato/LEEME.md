# Carcasa gato para Mochi · v1

Modelo propio para la Waveshare ESP32-S3-Touch-AMOLED-1.75-G y la batería de la foto del usuario: **955565, 65 × 55 × 9,5 mm, 3,7 V, 5000 mAh según la etiqueta**.

Dimensiones exteriores montada: **94 × 104,85 × 48 mm** (ancho × alto con orejas × fondo). Pared principal de 2,4 mm. Pantalla circular como cara, orejas con insertos opcionales, tapa desmontable y soporte interior de la placa.

## Archivos

| Archivo | Cantidad | Uso |
| --- | --- | --- |
| `stl/01_frontal_gato.stl` | 1 | Frontal, orejas y pilares de fijación |
| `stl/02_tapa_trasera.stl` | 1 | Tapa, encaje, bandeja de batería y guías |
| `stl/03_soporte_waveshare.stl` | 1 | Sujeción de la placa mediante sus tres insertos M2 |
| `stl/04_oreja_izquierda.stl` | 1, opcional | Inserto decorativo |
| `stl/05_oreja_derecha.stl` | 1, opcional | Inserto decorativo |
| `stl/06_prueba_pantalla.stl` | 1, primero | Comprobar el asiento antes de imprimir el cuerpo |
| `gato_montaje.blend` | — | Modelo editable montado, con referencias de componentes |
| `parametros.json`, `generar.py` | — | Cotas y generador para Blender 5.x |
| `validacion.json`, `validacion_stl.json` | — | Interferencias nominales y revisión independiente de STL |
| `vistas/` | — | Imágenes renderizadas de la geometría real |

Los STL son binarios y están en **milímetros**. Cada pieza está apoyada en Z=0. Importar como piezas independientes al 100 %. La orientación inicial del frontal es con el plano de unión abajo. El STL del soporte se imprime plano. Los insertos de oreja se imprimen aparte y se pegan; no necesitan AMS.

## Componentes y espacio interior

| Elemento | Datos usados | Estado |
| --- | --- | --- |
| Pantalla / placa | Cristal Ø48,96 mm; PCB Ø46 mm; ventana Ø45 mm | Diámetros del plano oficial |
| Asiento del cristal | Ø49,66 mm; holgura radial 0,35 mm; reborde frontal 1,3 mm | Incluido en la pieza de prueba |
| Fijaciones de placa | Tres M2; coordenadas en vista trasera (0;20,5), (−13,75;−14,7), (13,75;−14,7) | Del plano; comprobar revisión física |
| Plano de los insertos | 10,4 mm detrás del frontal del cristal | Hipótesis a verificar: el plano da el espesor total, no todas las alturas individuales |
| Batería 955565 | 65 × 55 × 9,5 mm | De la foto del usuario |
| Reserva para la batería | 67 × 57 × 11,5 mm; base Z=5,6 mm | 1 mm por lado y 2 mm por encima; sin prensar la bolsa |
| Antena GPS | 25 × 25 × 4 mm, cerámica mirando hacia arriba | Reserva provisional: medidas del ejemplar no documentadas en el proyecto |
| Altavoz | Ø28 × 7 mm, salida por el lateral | Reserva provisional: medidas del ejemplar no documentadas en el proyecto |
| Adaptador de batería | Reserva de 8 × 16 × 7 mm y paso de cables | PH-2.0 de la foto hacia MX1.25 de la placa |

El ESP32, el LC76G GPS y los dos micrófonos están en la placa; no requieren alojamientos para módulos independientes. La antena GNSS es externa. Las reservas de antena y altavoz no suponen que esos sean los tamaños reales de los accesorios del usuario. Las guías admiten fijación con espuma o cinta; el altavoz previsto necesita un calzo blando bajo su borde inferior.

La placa se monta sin la carcasa redonda comercial. La variante B con caja de Ø51 mm no entra en este asiento de cristal Ø49,66 mm.

## Impresión y montaje

1. Imprimir primero `06_prueba_pantalla.stl`. Probar sin forzar el cristal y comprobar que la ventana deja libre la zona activa y el borde táctil.
2. Para el prototipo: boquilla de 0,4 mm, capa de 0,20 mm, 4 perímetros, 5 capas superior/inferior y relleno 15–20 %. PETG o PLA para la prueba. El perfil final depende de la impresora y el material.
3. Revisar en el laminador los voladizos del frontal, los alojamientos de tuerca y los accesos laterales. Usar soportes localizados donde los marque el laminador. En la tapa, conservar libre el canal de la cinta bajo la bandeja; los nervios reducen los puentes, pero conviene inspeccionar esas capas. No se incluye un G-code universal.
4. Introducir cuatro tuercas M3 en los huecos hexagonales del frontal, abiertos desde el plano de unión. La tapa usa cuatro tornillos **M3 × 25 mm** de cabeza cilíndrica de hasta Ø6,8 mm; el asiento tiene 6 mm de profundidad desde Z=0.
5. Colocar el cristal desde el interior. Presentar el soporte a los tres insertos originales. La altura del soporte debe comprobarse antes de apretar: nunca usar los tornillos para tirar del cristal contra la carcasa. La profundidad efectiva de rosca debe permitir elegir los M2 de la placa; unos M2 × 4 mm son una referencia inicial, sujetos a esa comprobación.
6. Atornillar las tres lengüetas exteriores del soporte a los pilares impresos. Piloto Ø1,7 mm; tornillos M2 × 6 mm como punto inicial. Roscar suavemente antes de montar la electrónica. No dejar las puntas tocar pantalla ni PCB.
7. Instalar batería con cinta blanda de hasta 8 mm de ancho por las ranuras centrales y una fijación suave. Dejar holgura a la bolsa y a los cables. No poner tornillos, tuercas ni puntas sobre la celda.
8. Colocar la antena con su cara de recepción hacia el techo del gato; fijar el altavoz frente a la rejilla lateral y mantener despejados los accesos a micrófonos, USB, microSD y botones. Mantener la batería fuera de esos recorridos.
9. La batería de la foto declara **PH-2.0**, mientras la placa usa **MX1.25**. Utilizar un adaptador adecuado y comprobar con un multímetro positivo y negativo antes de conectarla; las denominaciones de conector no garantizan el orden de los cables. Este diseño mecánico no configura la corriente de carga.
10. Cerrar a mano, comprobar que el labio entra libre y apretar en cruz sin deformar la tapa. Probar audio, recepción GPS, carga y acceso a controles en el conjunto real.

## Qué está comprobado

El generador comprueba una sola componente conexa y volumen positivo por STL, bordes cerrados y ausencia de triángulos degenerados. Un segundo script vuelve a leer los STL exportados y comprueba bordes, orientación, caras duplicadas, componentes, dimensiones y colocación sobre la cama. Además se comprueban 22 pares de volúmenes del montaje, incluyendo batería con holgura, carcasa, soporte, cristal, PCB, antena, altavoz y reserva del adaptador. El umbral de interferencia es 0,02 mm³ para el ruido numérico.

**Esta v1 es un prototipo de ajuste.** Falta contrastar en el ejemplar físico el plano de los insertos, alturas de los componentes de la PCB, tamaños reales de antena y altavoz y alineación de todos los accesos. Los centros en Z de USB, microSD, micrófonos y botones se han estimado a partir del plano y de las fotografías oficiales; están separados en el generador para poder corregirlos. La lectura del STEP oficial no se ha usado para certificar esos centros. La comprobación digital no es una prueba de montaje ni de funcionamiento acústico o RF.

Los ojos de las vistas son una ilustración de la pantalla. No son piezas para imprimir ni una modificación del firmware de Mochi.

## Regenerar

Desde PowerShell, con Blender 5.x:

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe' --background --factory-startup --python 'hardware\gato\generar.py'
python hardware\gato\validar_stl.py
```

La opción `-- --no-render` omite las imágenes. Python para la comprobación independiente necesita NumPy. El generador usa la API de Blender y no requiere complementos. El JSON centraliza las cotas principales; para cambios de distribución o conectores también hay que editar las operaciones correspondientes de `generar.py`.

## Fuentes

- Documentación y plano oficial: https://docs.waveshare.com/ESP32-S3-Touch-AMOLED-1.75
- Recursos mecánicos oficiales: https://docs.waveshare.com/ESP32-S3-Touch-AMOLED-1.75/Resources-And-Documents
- Batería: `referencias/bateria-955565.jpg`, foto aportada por el usuario.
- Inspiración elegida por el usuario: https://makerworld.com/es/models/2235085-esp-vocat-meow-buddy-an-ai-adorable-pet-that-liste

MakerWorld bloqueó la descarga con su verificación de acceso. La geometría se ha construido desde cero: no se ha importado ni modificado el STL de ese autor. El segundo enlace de mochi quedó descartado cuando el usuario eligió gato.
