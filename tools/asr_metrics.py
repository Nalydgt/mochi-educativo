"""Transparent word-error comparisons for Spanish synthetic ASR diagnostics."""
import re
import unicodedata

_SMALL = ('cero uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce '
          'quince dieciseis diecisiete dieciocho diecinueve veinte veintiuno veintidos veintitres '
          'veinticuatro veinticinco veintiseis veintisiete veintiocho veintinueve').split()
_TENS = ['', '', '', 'treinta', 'cuarenta', 'cincuenta', 'sesenta', 'setenta', 'ochenta', 'noventa']


def cardinal(number):
    """Expand integer spellings, without treating decimal points as multiplication."""
    if number < 30:
        return _SMALL[number]
    if number < 100:
        return _TENS[number // 10] + (' y ' + _SMALL[number % 10] if number % 10 else '')
    return str(number)


def words(text):
    text = ''.join(c for c in unicodedata.normalize('NFD', text.casefold())
                   if unicodedata.category(c) != 'Mn')
    tokens = re.findall(r'\d+(?:[.,]\d+)?|[^\W\d_]+', text)
    normalized = []
    for token in tokens:
        normalized.extend(cardinal(int(token)).split() if token.isdigit() else [token])
    return normalized


def word_errors(reference, hypothesis):
    expected, heard = words(reference), words(hypothesis)
    previous = list(range(len(heard) + 1))
    for i, word in enumerate(expected, 1):
        row = [i]
        for j, other in enumerate(heard, 1):
            row.append(min(row[-1] + 1, previous[j] + 1, previous[j-1] + (word != other)))
        previous = row
    return {'errors': previous[-1], 'reference_words': len(expected),
            'exact_normalized': expected == heard}
