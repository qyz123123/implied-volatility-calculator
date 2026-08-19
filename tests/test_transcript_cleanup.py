from transcript_cleanup import clean_paragraph


def test_cleanup_is_idempotent_for_forward_looking_term():
    once = clean_paragraph("forward looking estimates")
    twice = clean_paragraph(once)
    assert once == "Forward-looking estimates"
    assert twice == once


def test_cleanup_corrects_worked_example_numbers():
    assert clean_paragraph("zero point nine percent") == "0.09 percent"
    assert clean_paragraph("eight points, even") == "$8.70"
    assert clean_paragraph("one point five percent dividend yield") == (
        "1.05 percent dividend yield"
    )
