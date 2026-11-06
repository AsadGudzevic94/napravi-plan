from planer.izvoz import preslovi


def test_formule_i_pismo():
    assert preslovi("Функције у = x2 и у = x3.", "ćirilica") == "Функције y = x² и y = x³."
    assert preslovi("Функције у = x2 и у = x3.", "latinica") == "Funkcije y = x² i y = x³."
    assert preslovi("log2 x, x^2 + y^(n+1), sqrt(x), a <= b", "ćirilica") == "log₂ x, x² + yⁿ⁺¹, √x, a ≤ b"
    assert preslovi("Rešavanje x2 - 5x + 6 = 0", "ćirilica") == "Решавање x² - 5x + 6 = 0"


def test_obican_tekst_ostaje():
    assert preslovi("2. razred, nivo B2, PG 7/2023", "latinica") == "2. razred, nivo B2, PG 7/2023"
    assert preslovi("a u školi s drugom", "ćirilica") == "а у школи с другом"
