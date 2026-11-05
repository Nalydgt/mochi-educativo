export type Lesson = {
  id: string;
  world: string;
  title: string;
  intro: string;
  goal: string;
  minutes: number;
  level: string;
  progress: number;
  activity: "pizza" | "quiz";
  hints: string[];
  quiz?: { q: string; options: string[]; answer: number; explain: string }[];
};

export type World = {
  id: string;
  name: string;
  blurb: string;
  color: string;
  available: boolean;
};

export const worlds: World[] = [
  {
    id: "matematicas",
    name: "Reino de las Matemáticas",
    blurb: "Fracciones, formas, balanzas y gráficos que se tocan.",
    color: "bg-sunburst",
    available: true,
  },
  {
    id: "naturaleza",
    name: "Laboratorio de la Naturaleza",
    blurb: "El cuerpo humano, el sistema solar y el ciclo del agua.",
    color: "bg-mint",
    available: true,
  },
  {
    id: "palabras",
    name: "Biblioteca de las Palabras",
    blurb: "Historias interactivas y el detective de palabras.",
    color: "bg-lavender",
    available: false,
  },
  {
    id: "historia",
    name: "Mundo de la Historia y la Geografía",
    blurb: "Mapas, líneas temporales y una ciudad romana.",
    color: "bg-ember",
    available: false,
  },
];

export const lessons: Lesson[] = [
  {
    id: "pizzeria",
    world: "matematicas",
    title: "La pizzería de Peluqo",
    minutes: 10,
    level: "9–12 años",
    progress: 60,
    activity: "pizza",
    intro:
      "Ha llegado un pedido a la pizzería: un cliente quiere 3/4 de pizza. ¿Le ayudas a servirlo?",
    goal: "Entender qué significa una fracción como partes iguales de un todo.",
    hints: [
      "La pizza está dividida en 4 trozos iguales.",
      "El número de abajo (4) dice en cuántas partes se divide.",
      "El número de arriba (3) dice cuántas partes sirves.",
    ],
  },
  {
    id: "balanza",
    world: "matematicas",
    title: "La balanza de la igualdad",
    minutes: 12,
    level: "12–14 años",
    progress: 0,
    activity: "quiz",
    intro: "Una balanza tiene x + 3 manzanas a un lado y 7 al otro. Está equilibrada.",
    goal: "Resolver ecuaciones sencillas manteniendo el equilibrio.",
    hints: [
      "Lo que quites de un lado, quítalo del otro.",
      "Prueba a quitar 3 manzanas de cada lado.",
    ],
    quiz: [
      {
        q: "Si x + 3 = 7, ¿cuánto vale x?",
        options: ["3", "4", "10"],
        answer: 1,
        explain: "Quitando 3 de cada lado queda x = 4.",
      },
      {
        q: "Si 2x = 10, ¿cuánto vale x?",
        options: ["5", "8", "20"],
        answer: 0,
        explain: "Dividimos ambos lados entre 2: x = 5.",
      },
    ],
  },
  {
    id: "formas",
    world: "matematicas",
    title: "Taller de formas",
    minutes: 8,
    level: "6–9 años",
    progress: 100,
    activity: "quiz",
    intro: "Peluqo construye una casa con figuras. ¿Le ayudas a contarlas?",
    goal: "Reconocer polígonos por su número de lados.",
    hints: [
      "Cuenta los lados con el dedo.",
      "Un triángulo tiene tantos lados como su nombre indica.",
    ],
    quiz: [
      {
        q: "¿Cuántos lados tiene un hexágono?",
        options: ["5", "6", "8"],
        answer: 1,
        explain: "Hexa significa seis.",
      },
      {
        q: "¿Qué figura tiene 4 lados iguales y 4 ángulos rectos?",
        options: ["Rombo", "Cuadrado", "Trapecio"],
        answer: 1,
        explain: "El cuadrado tiene lados y ángulos iguales.",
      },
    ],
  },
  {
    id: "graficos",
    world: "matematicas",
    title: "El mercado de los gráficos",
    minutes: 10,
    level: "10–12 años",
    progress: 20,
    activity: "quiz",
    intro: "En el mercado se vendieron 12 manzanas, 8 peras y 4 plátanos.",
    goal: "Leer e interpretar un gráfico de barras.",
    hints: ["La barra más alta es la fruta más vendida.", "Suma todas las barras para el total."],
    quiz: [
      {
        q: "¿Cuántas frutas se vendieron en total?",
        options: ["20", "24", "28"],
        answer: 1,
        explain: "12 + 8 + 4 = 24.",
      },
    ],
  },
  {
    id: "cuerpo",
    world: "naturaleza",
    title: "Viaje por el cuerpo humano",
    minutes: 15,
    level: "9–12 años",
    progress: 40,
    activity: "quiz",
    intro: "Peluqo encoge y entra en el cuerpo. Primera parada: el corazón.",
    goal: "Conocer la función de los órganos principales.",
    hints: ["Piensa en qué órgano late.", "Los pulmones se llenan de aire."],
    quiz: [
      {
        q: "¿Qué órgano bombea la sangre?",
        options: ["Pulmones", "Corazón", "Estómago"],
        answer: 1,
        explain: "El corazón impulsa la sangre por todo el cuerpo.",
      },
      {
        q: "¿Dónde entra el oxígeno a la sangre?",
        options: ["En los pulmones", "En el hígado", "En los riñones"],
        answer: 0,
        explain: "En los alvéolos de los pulmones.",
      },
    ],
  },
  {
    id: "sistema-solar",
    world: "naturaleza",
    title: "Paseo por el sistema solar",
    minutes: 12,
    level: "8–12 años",
    progress: 0,
    activity: "quiz",
    intro: "Subimos al cohete de Peluqo y salimos de la Tierra.",
    goal: "Ordenar los planetas y conocer sus características.",
    hints: ["Mercurio es el más cercano al Sol.", "Júpiter es el gigante."],
    quiz: [
      {
        q: "¿Cuál es el planeta más grande?",
        options: ["Saturno", "Júpiter", "Neptuno"],
        answer: 1,
        explain: "Júpiter es el mayor del sistema solar.",
      },
      {
        q: "¿Qué planeta está más cerca del Sol?",
        options: ["Venus", "Mercurio", "Marte"],
        answer: 1,
        explain: "Mercurio es el primero.",
      },
    ],
  },
  {
    id: "agua",
    world: "naturaleza",
    title: "El ciclo del agua",
    minutes: 9,
    level: "8–11 años",
    progress: 0,
    activity: "quiz",
    intro: "Una gota sale del mar y empieza un largo viaje.",
    goal: "Describir evaporación, condensación y precipitación.",
    hints: [
      "El calor convierte el agua en vapor.",
      "Las nubes se forman cuando el vapor se enfría.",
    ],
    quiz: [
      {
        q: "¿Cómo se llama el paso de líquido a vapor?",
        options: ["Condensación", "Evaporación", "Precipitación"],
        answer: 1,
        explain: "Con el calor, el agua se evapora.",
      },
    ],
  },
];

export const notebooks = [
  {
    id: "bio",
    title: "Biología 4º ESO — La célula",
    pages: 18,
    topics: 5,
    color: "bg-mint",
    updated: "hace 2 días",
  },
  {
    id: "hist",
    title: "Historia — Revolución industrial",
    pages: 26,
    topics: 7,
    color: "bg-lavender",
    updated: "hace 5 días",
  },
  {
    id: "fis",
    title: "Física — Cinemática",
    pages: 12,
    topics: 4,
    color: "bg-sunburst",
    updated: "ayer",
  },
];

export const detectedTopics = [
  "Teoría celular",
  "Célula procariota y eucariota",
  "Orgánulos y sus funciones",
  "Membrana plasmática",
  "División celular: mitosis",
];

export const mockExam = [
  {
    q: "Según tus apuntes, ¿qué orgánulo produce la energía de la célula?",
    options: ["Ribosoma", "Mitocondria", "Aparato de Golgi"],
    answer: 1,
    source: "Pág. 7",
  },
  {
    q: "¿Qué diferencia principal tiene una célula procariota?",
    options: ["No tiene núcleo definido", "Tiene cloroplastos", "Es más grande"],
    answer: 0,
    source: "Pág. 4",
  },
  {
    q: "¿En qué fase de la mitosis se separan las cromátidas?",
    options: ["Profase", "Metafase", "Anafase"],
    answer: 2,
    source: "Pág. 15",
  },
];

export const badges = [
  { name: "Pizzero aprendiz", color: "bg-sunburst", got: true },
  { name: "Explorador del cuerpo", color: "bg-mint", got: true },
  { name: "Maestro de formas", color: "bg-lavender", got: true },
  { name: "Astronauta", color: "bg-electric", got: false },
  { name: "Gota viajera", color: "bg-sky", got: false },
  { name: "Equilibrista", color: "bg-ember", got: false },
];

export const reviews = [
  { topic: "Fracciones equivalentes", when: "Hoy" },
  { topic: "Órganos del cuerpo", when: "Mañana" },
  { topic: "Polígonos", when: "En 4 días" },
];

export const children = [
  { name: "Lucía", age: 10, minutes: 35, limit: 45, done: 12, hard: "Fracciones" },
  { name: "Mateo", age: 7, minutes: 15, limit: 30, done: 5, hard: "Lectura" },
];

export const buddyEvents = [
  { t: "10:42", e: "Lección completada: Taller de formas", r: "Baile de celebración" },
  { t: "10:31", e: "Pista solicitada en La pizzería", r: "Gesto de ánimo" },
  { t: "Ayer", e: "Repaso de órganos superado", r: "Ojos de estrella" },
];

export const labProjects = [
  {
    title: "Monta tu Peluqo",
    level: "Inicial",
    desc: "Ensambla la carcasa, la pantalla y el altavoz.",
    color: "bg-sunburst",
  },
  {
    title: "Primer firmware",
    level: "Intermedia",
    desc: "Instala el firmware y conecta el Wi-Fi.",
    color: "bg-mint",
  },
  {
    title: "Sensores y emociones",
    level: "Intermedia",
    desc: "Programa reacciones con el sensor táctil.",
    color: "bg-lavender",
  },
  {
    title: "Conecta la API",
    level: "Avanzada",
    desc: "Recibe eventos educativos en el dispositivo.",
    color: "bg-ember",
  },
];

export const groups = [
  {
    name: "5º B — CEIP Miguel Hernández",
    students: 24,
    assigned: "La pizzería de Peluqo",
    done: 18,
    faq: "¿Por qué 2/4 es igual que 1/2?",
  },
  {
    name: "6º A — CEIP Miguel Hernández",
    students: 22,
    assigned: "Viaje por el cuerpo humano",
    done: 9,
    faq: "¿El corazón está a la izquierda?",
  },
];

export const tutorScript = [
  "Buena pregunta. Antes de responder: ¿qué crees que pasa con la energía cuando la célula la necesita?",
  "Vas bien. Pista: en tus apuntes (pág. 7) hay un orgánulo con forma de judía. ¿Cómo se llama?",
  "Exacto, la mitocondria. ¿Podrías explicarme con tus palabras por qué se la llama la central energética?",
  "Muy bien explicado. Te propongo repasarlo mañana con dos preguntas nuevas.",
];
