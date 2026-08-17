"""Calendar logic of a quarterly lesson — run with `python3 test_lesson.py`.

A lesson is dated by "data_sabato", the Sabbath it is DISCUSSED on; its six
daily sections (Domenica…Venerdì) are studied during the week leading up to
that Sabbath. Both rules below got this backwards at some point, so they are
the two worth guarding.
"""
from datetime import date

from core.lesson import LessonSet, day_date, flatten_domande

SAT = "2026-08-22"  # a Saturday
LESSON = {
    "numero_lezione": 8,
    "data_sabato": SAT,
    "giorni": [{"giorno": g, "titolo_giorno": g, "domande": [{"testo": "?"}]}
               for g in ("Domenica", "Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì")],
}


def test_days_fall_in_the_week_before_the_sabbath():
    doms = flatten_domande(LESSON)
    got = [day_date(LESSON, d) for d in doms]
    assert got == [date(2026, 8, 16), date(2026, 8, 17), date(2026, 8, 18),
                   date(2026, 8, 19), date(2026, 8, 20), date(2026, 8, 21)], got
    assert got[0].weekday() == 6, "Domenica must land on a Sunday"
    assert all(d < date(2026, 8, 22) for d in got), "every day precedes its Sabbath"


def test_lesson_is_current_for_its_whole_week():
    ls = LessonSet([LESSON, {"numero_lezione": 9, "data_sabato": "2026-08-29"}])
    for day, expected in ((date(2026, 8, 16), 8),   # Sunday → this week's lesson
                          (date(2026, 8, 18), 8),   # midweek
                          (date(2026, 8, 22), 8),   # the Sabbath itself
                          (date(2026, 8, 23), 9)):  # next Sunday → next lesson
        found = ls.find_for(day)
        assert found and found["numero_lezione"] == expected, (day, found)
    assert ls.find_for(date(2026, 8, 15)) is None   # outside both weeks
    assert ls.find_for(date(2026, 12, 25)) is None


if __name__ == "__main__":
    test_days_fall_in_the_week_before_the_sabbath()
    test_lesson_is_current_for_its_whole_week()
    print("ok")
