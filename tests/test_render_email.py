from render_email import render_brief_html


def _base_data(**overrides):
    data = {
        "date": "2026-09-05",
        "warnings": [],
        "aviraj_highlight": None,
        "homework": [],
        "agenda": [],
        "dress_code": None,
        "reminders": [],
    }
    data.update(overrides)
    return data


def test_render_includes_homework_section_when_present():
    html = render_brief_html(_base_data(homework=["Read pages 10-12"]))
    assert "Homework" in html
    assert "Read pages 10-12" in html


def test_render_omits_empty_sections():
    html = render_brief_html(_base_data(agenda=["Skill Analysis day"]))
    assert "Homework" not in html
    assert "Dress Code" not in html
    assert "Skill Analysis day" in html


def test_render_shows_nothing_new_message_when_all_empty():
    html = render_brief_html(_base_data())
    assert "Nothing new" in html


def test_render_includes_warnings_banner():
    html = render_brief_html(_base_data(warnings=["WhatsApp fetch failed"]))
    assert "WhatsApp fetch failed" in html


def test_render_includes_aviraj_highlight():
    html = render_brief_html(
        _base_data(aviraj_highlight="Aviraj is presenting show and tell tomorrow")
    )
    assert "Aviraj is presenting show and tell tomorrow" in html


def test_render_includes_dress_code_section_when_present():
    html = render_brief_html(
        _base_data(dress_code="Swimming dress (Tuesday is swim day)")
    )
    assert "Dress Code" in html
    assert "Swimming dress (Tuesday is swim day)" in html


def test_render_escapes_html_special_characters():
    html = render_brief_html(_base_data(homework=["Read <Chapter 3> & write notes"]))
    assert "<Chapter 3>" not in html
    assert "&lt;Chapter 3&gt;" in html
