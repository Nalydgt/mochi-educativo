import type { Activity, Mission } from "../src/lib/education/schema";
// Explicit teacher-reviewed test content, never presented as generated AI output.
export function reviewedMission(chunkId: string, page: number | null): Mission {
  const refs = [{ chunkId, page }];
  const question = (
    id: string,
    title: string,
    instruction: string,
    choices: string[],
    correct: number,
    competency: string,
  ): Activity => ({
    id,
    type: "question",
    title,
    instruction,
    competency,
    asset: "fish",
    choices: choices.map((label, i) => ({ id: String(i), label })),
    pieces: [],
    answer: { choice: String(correct) },
    hints: [
      "Compara cómo respira y cómo se desarrolla.",
      "Busca la característica que define a cada grupo.",
    ],
    explanation:
      "Compara las características descritas en el material para justificar tu clasificación.",
    sources: refs,
  });
  return {
    title: "La expedición de los vertebrados",
    intro:
      "Un pez, una rana y un delfín esconden pistas sobre sus cuerpos. Vamos a investigar cómo se clasifican y cómo respiran.",
    ageBand: "9–12",
    diagnostic: [
      question(
        "d1",
        "El primer descubrimiento",
        "Una rana adulta tiene piel húmeda. ¿A qué grupo pertenece?",
        ["Anfibios", "Aves", "Mamíferos"],
        0,
        "Clasificar vertebrados",
      ),
      question(
        "d2",
        "Vida bajo el agua",
        "¿Qué estructura utiliza principalmente la trucha para obtener oxígeno del agua?",
        ["Pulmones", "Branquias", "Plumas"],
        1,
        "Relacionar respiración y estructura",
      ),
    ],
    practice: [
      {
        id: "p1",
        type: "classification",
        title: "El campamento de los animales",
        instruction: "Coloca cada animal en su grupo comparando las características de su cuerpo.",
        competency: "Clasificar vertebrados",
        asset: "fish",
        choices: [
          { id: "m", label: "Mamíferos" },
          { id: "a", label: "Aves" },
          { id: "p", label: "Peces" },
        ],
        pieces: [
          { id: "delfin", label: "Delfín", asset: "dolphin" },
          { id: "gorrion", label: "Gorrión", asset: "bird" },
          { id: "trucha", label: "Trucha", asset: "fish" },
        ],
        answer: { delfin: "m", gorrion: "a", trucha: "p" },
        hints: [
          "Vivir en el agua no convierte a un animal en pez.",
          "El delfín respira con pulmones y alimenta a sus crías con leche.",
        ],
        explanation:
          "Delfín: mamífero. Gorrión: ave. Trucha: pez. El lugar donde viven no es suficiente para clasificarlos.",
        sources: refs,
      },
      {
        id: "p2",
        type: "anatomy",
        title: "El laboratorio del pez",
        instruction: "Coloca las etiquetas en las zonas señaladas del pez: ojos, branquias y cola.",
        competency: "Relacionar respiración y estructura",
        asset: "fish",
        choices: [
          { id: "head", label: "Cabeza", x: 81, y: 42 },
          { id: "gill", label: "Detrás de la cabeza", x: 70, y: 54 },
          { id: "tail", label: "Extremo posterior", x: 12, y: 50 },
        ],
        pieces: [
          { id: "eyes", label: "Ojos" },
          { id: "gills", label: "Branquias" },
          { id: "caudal", label: "Cola" },
        ],
        answer: { eyes: "head", gills: "gill", caudal: "tail" },
        hints: [
          "Los ojos permiten percibir el entorno y están en la cabeza.",
          "Las branquias están detrás de la cabeza; la cola está en el extremo posterior.",
        ],
        explanation:
          "Los ojos están en la cabeza. Las branquias obtienen oxígeno del agua. La cola contribuye al impulso.",
        sources: refs,
      },
      question(
        "p3",
        "Cambiar para crecer",
        "Al convertirse en rana adulta, ¿cómo cambia la respiración del renacuajo?",
        [
          "La rana adulta utiliza pulmones y también su piel",
          "La rana adulta desarrolla plumas",
          "La rana adulta deja de necesitar oxígeno",
        ],
        0,
        "Relacionar respiración y estructura",
      ),
    ],
    final: [
      question(
        "f1",
        "Un visitante del océano",
        "Un animal acuático respira aire con pulmones y sus crías toman leche. ¿Qué grupo explicaría estos rasgos?",
        ["Peces", "Mamíferos", "Anfibios"],
        1,
        "Clasificar vertebrados",
      ),
      question(
        "f2",
        "Un cuerpo preparado",
        "Si un pez no pudiera utilizar sus branquias, ¿qué función se vería afectada directamente?",
        ["Obtener oxígeno disuelto en el agua", "Fabricar leche", "Producir plumas"],
        0,
        "Relacionar respiración y estructura",
      ),
    ],
    retention: [
      question(
        "r1",
        "Otra pista para clasificar",
        "¿Qué característica del gato permite relacionarlo con el delfín?",
        [
          "Ambos tienen plumas",
          "Ambos alimentan a sus crías con leche",
          "Ambos respiran por branquias",
        ],
        1,
        "Clasificar vertebrados",
      ),
      question(
        "r2",
        "Recordar y aplicar",
        "¿Por qué debe subir a la superficie un delfín?",
        [
          "Porque necesita tomar aire para sus pulmones",
          "Porque no pertenece a los vertebrados",
          "Porque sus plumas se secan al sol",
        ],
        0,
        "Relacionar respiración y estructura",
      ),
    ],
  };
}
