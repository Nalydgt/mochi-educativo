from asr_metrics import word_errors


def test_asr_metrics_equate_written_cardinals_accents_case_and_punctuation():
    assert word_errors('¿Cuánto es diecisiete más veintiséis?', 'CUANTO es 17 más 26.') == {
        'errors': 0, 'reference_words': 5, 'exact_normalized': True}


def test_asr_metrics_preserve_meaning_changing_numbers_and_decimal_operators():
    assert word_errors('nueve por siete', '9.7')['errors'] > 0
    assert word_errors('diecisiete más veintiséis', '17 más 25')['errors'] == 1


def test_asr_metrics_report_actual_word_loss_and_insertions():
    assert word_errors('rime con ventana', 'rime y conventara')['errors'] == 2
    assert word_errors('un nombre', 'un pequeño nombre')['errors'] == 1
