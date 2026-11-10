from whaat.memory.labels import LABELS, label


def test_every_language_has_the_same_words() -> None:
    assert set(LABELS["hu"]) == set(LABELS["en"])


def test_an_unknown_key_shows_as_the_data_names_it() -> None:
    assert label("en", "dtype.new-kind", "Új fajta") == "Új fajta"
    assert label("hu", "rings.coreFiles", count=4) == "core · 4 fájl"
