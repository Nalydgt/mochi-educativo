"""Conservative recognition of an explicit spoken arithmetic answer.

Only a complete numeric answer, optionally introduced as an answer, is accepted.
A number mentioned in a question, a story or a protection disclosure is not.
"""
import re
import unicodedata


def normalized(text):
    value = "".join(c for c in unicodedata.normalize("NFD", text.lower()) if not unicodedata.combining(c))
    value = re.sub(r"(?<=[a-z])[-‐‑–](?=[a-z])", " ", value)
    return " ".join(re.sub(r"[.,!¡]", " ", value).split())


def _spanish(n):
    first = ["cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez", "once", "doce", "trece", "catorce", "quince", "dieciseis", "diecisiete", "dieciocho", "diecinueve", "veinte", "veintiuno", "veintidos", "veintitres", "veinticuatro", "veinticinco", "veintiseis", "veintisiete", "veintiocho", "veintinueve"]
    if n < 30:
        return first[n]
    if n == 100:
        return "cien"
    if n > 100:
        return "ciento " + _spanish(n - 100)
    tens = ["", "", "", "treinta", "cuarenta", "cincuenta", "sesenta", "setenta", "ochenta", "noventa"]
    return tens[n // 10] + (" y " + first[n % 10] if n % 10 else "")


def _english(n):
    first = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
    if n < 20:
        return first[n]
    if n >= 100:
        return "one hundred" + (" and " + _english(n - 100) if n > 100 else "")
    return ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"][n // 10] + (" " + first[n % 10] if n % 10 else "")


def _portuguese(n):
    first = ["zero", "um", "dois", "tres", "quatro", "cinco", "seis", "sete", "oito", "nove", "dez", "onze", "doze", "treze", "catorze", "quinze", "dezasseis", "dezassete", "dezoito", "dezanove"]
    if n < 20:
        return first[n]
    if n == 100:
        return "cem"
    if n > 100:
        return "cento e " + _portuguese(n - 100)
    return ["", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta", "oitenta", "noventa"][n // 10] + (" e " + first[n % 10] if n % 10 else "")


_numbers = {normalized(value): number for number in range(145) for value in (_spanish(number), _english(number), _portuguese(number))}
_numbers.update({normalized(_english(number).replace(" and ", " ")): number for number in range(100, 145)})
_numbers.update({"un": 1, "una": 1, "uma": 1, "duas": 2, "quatorze": 14, "dezesseis": 16, "dezessete": 17, "dezenove": 19})
_prefix = re.compile(r"^(?:la respuesta es el numero|la respuesta es|la respuesta|respuesta es|respuesta|el resultado es|el numero es|creo que es|creo que son|creo que hay|pues son|me salen|me da|serian|hay|son|es|the answer is|it is|i think it is|there are|there is|i got|that makes|a resposta e|o resultado e|acho que e|sao|ha|e) ")
_units = re.compile(r" (?:objetos?|manzanas?|peces|pez|coches?(?: de juguete)?|macas?|peixes?|carros?(?: de brincar)?|objects?|apples?|fish|(?:toy )?cars?)(?: en total| ao todo| in total| altogether)?$")


def spoken_answer(text):
    value = normalized(text)
    if "?" in value or "¿" in value or len(value) > 100:
        return None
    value = _prefix.sub("", value, count=1)
    value = _units.sub("", value, count=1)
    value = re.sub(r" (?:en total|ao todo|in total|altogether)$", "", value)
    if re.fullmatch(r"[0-9]{1,3}", value):
        number = int(value)
        return number if number <= 144 else None
    return _numbers.get(value)


def speech_shape(text):
    """Bounded operator diagnostics, without transcript, token values or identifiers."""
    value = normalized(text)
    words = value.split()
    return {"characters": len(text), "words": len(words), "question": "?" in text or "¿" in text,
            "answer_prefix": bool(_prefix.match(value)), "number_word": any(word in _numbers or word.isdigit() for word in words),
            "numeric_match": spoken_answer(text) is not None}
