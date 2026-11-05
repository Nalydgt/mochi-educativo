-- Restore the starter catalogue from src/data/peluqo.ts in the new hosted project.
-- Existing lessons and activities keep their IDs and content.
INSERT INTO public.subjects (slug, name, description, color, display_order) VALUES
  ('matematicas', 'Reino de las Matemáticas', 'Fracciones, formas, balanzas y gráficos que se tocan.', 'sunburst', 1),
  ('naturaleza', 'Laboratorio de la Naturaleza', 'El cuerpo humano, el sistema solar y el ciclo del agua.', 'mint', 2),
  ('palabras', 'Biblioteca de las Palabras', 'Historias interactivas y el detective de palabras.', 'lavender', 3),
  ('historia', 'Mundo de la Historia y la Geografía', 'Mapas, líneas temporales y una ciudad romana.', 'ember', 4)
ON CONFLICT (slug) DO NOTHING;

WITH seed (subject_slug, slug, title, position) AS (VALUES
  ('matematicas', 'fracciones', 'Fracciones', 1),
  ('matematicas', 'ecuaciones', 'Ecuaciones', 2),
  ('matematicas', 'geometria', 'Geometría', 3),
  ('matematicas', 'datos', 'Datos y gráficos', 4),
  ('naturaleza', 'cuerpo-humano', 'Cuerpo humano', 5),
  ('naturaleza', 'astronomia', 'Astronomía', 6),
  ('naturaleza', 'agua', 'El agua', 7),
  ('palabras', 'lectura', 'Lectura', 8),
  ('historia', 'historia-geografia', 'Historia y geografía', 9)
)
INSERT INTO public.topics (subject_id, slug, title, display_order)
SELECT subject.id, seed.slug, seed.title, seed.position
FROM seed JOIN public.subjects subject ON subject.slug = seed.subject_slug
ON CONFLICT (subject_id, slug) DO NOTHING;

WITH lesson_seed (slug, subject_slug, topic_slug, title, description, level, minutes, scene) AS (VALUES
  ('pizzeria', 'matematicas', 'fracciones', 'La pizzería de Peluqo', 'Entender qué significa una fracción como partes iguales de un todo.', 'Primaria', 10, '{"version":1,"intro":"Ha llegado un pedido a la pizzería: un cliente quiere 3/4 de pizza. ¿Le ayudas a servirlo?","goal":"Entender qué significa una fracción como partes iguales de un todo.","hints":["La pizza está dividida en 4 trozos iguales.","El número de abajo (4) dice en cuántas partes se divide.","El número de arriba (3) dice cuántas partes sirves."]}'::jsonb),
  ('balanza', 'matematicas', 'ecuaciones', 'La balanza de la igualdad', 'Resolver ecuaciones sencillas manteniendo el equilibrio.', 'Secundaria', 12, '{"version":1,"intro":"Una balanza tiene x + 3 manzanas a un lado y 7 al otro. Está equilibrada.","goal":"Resolver ecuaciones sencillas manteniendo el equilibrio.","hints":["Lo que quites de un lado, quítalo del otro.","Prueba a quitar 3 manzanas de cada lado."]}'::jsonb),
  ('formas', 'matematicas', 'geometria', 'Taller de formas', 'Reconocer polígonos por su número de lados.', 'Primaria', 8, '{"version":1,"intro":"Peluqo construye una casa con figuras. ¿Le ayudas a contarlas?","goal":"Reconocer polígonos por su número de lados.","hints":["Cuenta los lados con el dedo.","Un triángulo tiene tantos lados como su nombre indica."]}'::jsonb),
  ('graficos', 'matematicas', 'datos', 'El mercado de los gráficos', 'Leer e interpretar un gráfico de barras.', 'Primaria', 10, '{"version":1,"intro":"En el mercado se vendieron 12 manzanas, 8 peras y 4 plátanos.","goal":"Leer e interpretar un gráfico de barras.","hints":["La barra más alta es la fruta más vendida.","Suma todas las barras para el total."]}'::jsonb),
  ('cuerpo', 'naturaleza', 'cuerpo-humano', 'Viaje por el cuerpo humano', 'Conocer la función de los órganos principales.', 'Primaria', 15, '{"version":1,"intro":"Peluqo encoge y entra en el cuerpo. Primera parada: el corazón.","goal":"Conocer la función de los órganos principales.","hints":["Piensa en qué órgano late.","Los pulmones se llenan de aire."]}'::jsonb),
  ('sistema-solar', 'naturaleza', 'astronomia', 'Paseo por el sistema solar', 'Ordenar los planetas y conocer sus características.', 'Primaria', 12, '{"version":1,"intro":"Subimos al cohete de Peluqo y salimos de la Tierra.","goal":"Ordenar los planetas y conocer sus características.","hints":["Mercurio es el más cercano al Sol.","Júpiter es el gigante."]}'::jsonb),
  ('agua', 'naturaleza', 'agua', 'El ciclo del agua', 'Describir evaporación, condensación y precipitación.', 'Primaria', 9, '{"version":1,"intro":"Una gota sale del mar y empieza un largo viaje.","goal":"Describir evaporación, condensación y precipitación.","hints":["El calor convierte el agua en vapor.","Las nubes se forman cuando el vapor se enfría."]}'::jsonb)
), new_lessons AS (
  INSERT INTO public.lessons (topic_id, slug, title, description, education_level, estimated_minutes, content, status)
  SELECT topic.id, seed.slug, seed.title, seed.description, seed.level, seed.minutes, seed.scene, 'published'
  FROM lesson_seed seed
  JOIN public.subjects subject ON subject.slug = seed.subject_slug
  JOIN public.topics topic ON topic.subject_id = subject.id AND topic.slug = seed.topic_slug
  ON CONFLICT (slug) DO NOTHING
  RETURNING id, slug
), activity_seed (lesson_slug, position, kind, title, instructions, config, answer, explanation) AS (VALUES
  ('pizzeria', 1, 'interactive_fractions', 'Sirve 3/4 de pizza', 'Selecciona tres de las cuatro porciones iguales.', '{"total":4,"target":"3/4"}'::jsonb, '{"selected":3}'::jsonb, 'Tres porciones de un total de cuatro partes iguales representan 3/4.'),
  ('balanza', 1, 'quiz', 'Si x + 3 = 7, ¿cuánto vale x?', 'Elige la opción correcta.', '{"options":["3","4","10"]}'::jsonb, '{"option":1}'::jsonb, 'Quitando 3 de cada lado queda x = 4.'),
  ('balanza', 2, 'quiz', 'Si 2x = 10, ¿cuánto vale x?', 'Elige la opción correcta.', '{"options":["5","8","20"]}'::jsonb, '{"option":0}'::jsonb, 'Dividimos ambos lados entre 2: x = 5.'),
  ('formas', 1, 'quiz', '¿Cuántos lados tiene un hexágono?', 'Elige la opción correcta.', '{"options":["5","6","8"]}'::jsonb, '{"option":1}'::jsonb, 'Hexa significa seis.'),
  ('formas', 2, 'quiz', '¿Qué figura tiene 4 lados iguales y 4 ángulos rectos?', 'Elige la opción correcta.', '{"options":["Rombo","Cuadrado","Trapecio"]}'::jsonb, '{"option":1}'::jsonb, 'El cuadrado tiene lados y ángulos iguales.'),
  ('graficos', 1, 'quiz', '¿Cuántas frutas se vendieron en total?', 'Elige la opción correcta.', '{"options":["20","24","28"]}'::jsonb, '{"option":1}'::jsonb, '12 + 8 + 4 = 24.'),
  ('cuerpo', 1, 'quiz', '¿Qué órgano bombea la sangre?', 'Elige la opción correcta.', '{"options":["Pulmones","Corazón","Estómago"]}'::jsonb, '{"option":1}'::jsonb, 'El corazón impulsa la sangre por todo el cuerpo.'),
  ('cuerpo', 2, 'quiz', '¿Dónde entra el oxígeno a la sangre?', 'Elige la opción correcta.', '{"options":["En los pulmones","En el hígado","En los riñones"]}'::jsonb, '{"option":0}'::jsonb, 'En los alvéolos de los pulmones.'),
  ('sistema-solar', 1, 'quiz', '¿Cuál es el planeta más grande?', 'Elige la opción correcta.', '{"options":["Saturno","Júpiter","Neptuno"]}'::jsonb, '{"option":1}'::jsonb, 'Júpiter es el mayor del sistema solar.'),
  ('sistema-solar', 2, 'quiz', '¿Qué planeta está más cerca del Sol?', 'Elige la opción correcta.', '{"options":["Venus","Mercurio","Marte"]}'::jsonb, '{"option":1}'::jsonb, 'Mercurio es el primero.'),
  ('agua', 1, 'quiz', '¿Cómo se llama el paso de líquido a vapor?', 'Elige la opción correcta.', '{"options":["Condensación","Evaporación","Precipitación"]}'::jsonb, '{"option":1}'::jsonb, 'Con el calor, el agua se evapora.')
), new_activities AS (
  INSERT INTO public.activities (lesson_id, display_order, activity_type, title, instructions, public_config)
  SELECT lesson.id, seed.position, seed.kind, seed.title, seed.instructions, seed.config
  FROM activity_seed seed JOIN new_lessons lesson ON lesson.slug = seed.lesson_slug
  RETURNING id, lesson_id, display_order
)
INSERT INTO public.activity_solutions (activity_id, answer_config, explanation)
SELECT activity.id, seed.answer, seed.explanation
FROM new_activities activity
JOIN new_lessons lesson ON lesson.id = activity.lesson_id
JOIN activity_seed seed ON seed.lesson_slug = lesson.slug AND seed.position = activity.display_order;

WITH badge (lesson_slug, title) AS (VALUES
  ('pizzeria', 'Pizzero aprendiz'),
  ('cuerpo', 'Explorador del cuerpo'),
  ('formas', 'Maestro de formas'),
  ('sistema-solar', 'Astronauta'),
  ('agua', 'Gota viajera'),
  ('balanza', 'Equilibrista')
)
INSERT INTO public.achievements (lesson_id, title)
SELECT lesson.id, badge.title FROM badge JOIN public.lessons lesson ON lesson.slug = badge.lesson_slug
ON CONFLICT (lesson_id) DO NOTHING;
