"""Approved narration matches the firmware's three illustrated counting scenes."""


def counting_story(a: int, b: int, step: int, language: str = "es") -> str:
    theme = step % 3
    if language == "en":
        groups = [("basket", "baskets", "apple", "apples"), ("pond", "ponds", "fish", "fish"), ("box", "boxes", "toy car", "toy cars")][theme]
        group = groups[0] if a == 1 else groups[1]
        item = groups[2] if b == 1 else groups[3]
        return f"We have {a} {group}, with {b} {item} in each one. How many {groups[3]} are there altogether?"
    if language == "pt":
        groups = [("cesto", "cestos", "maçã", "maçãs"), ("lago", "lagos", "peixe", "peixes"), ("caixa", "caixas", "carro de brincar", "carros de brincar")][theme]
        group = groups[0] if a == 1 else groups[1]
        item = groups[2] if b == 1 else groups[3]
        return f"Temos {a} {group}, com {b} {item} em cada um. Quantos objetos há ao todo?"
    groups = [("cesta", "cestas", "manzana", "manzanas", "manzanas"), ("estanque", "estanques", "pez", "peces", "peces"), ("caja", "cajas", "coche de juguete", "coches de juguete", "coches")][theme]
    group = groups[0] if a == 1 else groups[1]
    item = groups[2] if b == 1 else groups[3]
    question = "¿Cuántas manzanas hay en total?" if theme == 0 else f"¿Cuántos {groups[4]} hay en total?"
    return f"Tenemos {a} {group}, con {b} {item} en cada {'una' if theme != 1 else 'uno'}. {question}"


def question_narration(a: int, b: int, step: int, language: str = "es") -> str:
    invitation = {"es": "¡Vamos a explorar! Enséñame a contar.", "en": "Let's explore! Teach me to count.", "pt": "Vamos explorar! Ensina-me a contar."}[language]
    answer = {"es": "Mantén pulsado el botón para responder.", "en": "Hold the button to answer.", "pt": "Mantém o botão premido para responder."}[language]
    return f"{invitation} {counting_story(a, b, step, language)} {answer}"
