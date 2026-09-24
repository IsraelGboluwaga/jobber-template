from __future__ import annotations

from src.score import coverage_score, cv_to_text, extract_jd_terms

# --- extract_jd_terms -------------------------------------------------------

def test_extract_jd_terms_finds_single_word_lexicon_terms():
    terms = extract_jd_terms("We use Python and Kubernetes extensively.")
    assert "python" in terms
    assert "kubernetes" in terms


def test_extract_jd_terms_finds_multiword_phrases():
    terms = extract_jd_terms("Strong background in system design and distributed systems.")
    assert "system design" in terms
    assert "distributed systems" in terms


def test_extract_jd_terms_falls_back_to_salient_nouns_when_no_lexicon_hit():
    terms = extract_jd_terms("We are excited about this wonderful opportunity for growth.")
    assert terms  # never empty when there's any text, avoids divide-by-zero
    assert "the" not in terms and "and" not in terms


def test_extract_jd_terms_empty_for_empty_text():
    assert extract_jd_terms("") == set()


# --- coverage_score ----------------------------------------------------------

def test_coverage_score_full_match():
    jd = "Requires Python and Kubernetes."
    cv = "Extensive experience with Python and Kubernetes."
    assert coverage_score(cv, jd) == 100


def test_coverage_score_partial_match():
    jd = "Requires Python and Kubernetes."
    cv = "Extensive experience with Python only."
    assert coverage_score(cv, jd) == 50


def test_coverage_score_no_match():
    jd = "Requires Python and Kubernetes."
    cv = "Experience with Ruby and Rails."
    assert coverage_score(cv, jd) == 0


def test_coverage_score_zero_when_jd_has_no_terms():
    assert coverage_score("anything", "") == 0


# --- cv_to_text ----------------------------------------------------------------

def test_cv_to_text_flattens_all_sections():
    cv = {
        "summary": "Backend engineer.",
        "skills": ["Python", "Go"],
        "experience": [
            {"title": "Senior Engineer", "company": "Acme",
             "highlights": ["Did a thing"], "stack": ["Python"]},
        ],
        "education": [{"degree": "B.Sc. Computer Science"}],
    }
    text = cv_to_text(cv)

    for expected in ("Backend engineer.", "Python", "Go", "Senior Engineer",
                      "Acme", "Did a thing", "B.Sc. Computer Science"):
        assert expected in text


def test_cv_to_text_skips_empty_fields():
    cv = {"summary": "", "skills": [], "experience": [], "education": []}
    assert cv_to_text(cv) == ""
