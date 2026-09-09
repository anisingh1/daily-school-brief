import base64
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pi_service.generate_brief as generate_brief

IST = ZoneInfo("Asia/Kolkata")


def _envelope(portal_messages=None, whatsapp_messages=None, portal_error=None, whatsapp_error=None):
    return {
        "portal": {"messages": portal_messages or [], "error": portal_error},
        "whatsapp": {"messages": whatsapp_messages or [], "error": whatsapp_error},
    }


def test_generate_brief_short_circuits_when_nothing_to_report():
    now = datetime(2026, 9, 7, 20, 0, tzinfo=IST)  # Monday
    result = generate_brief.generate_brief(_envelope(), now=now)
    assert result == {
        "date": "Tuesday, September 08, 2026",
        "warnings": [],
        "aviraj_highlight": None,
        "classwork": [],
        "homework": [],
        "agenda": [],
        "dress_code": None,
        "reminders": [],
    }


def test_generate_brief_includes_warnings_for_source_errors():
    now = datetime(2026, 9, 7, 20, 0, tzinfo=IST)
    result = generate_brief.generate_brief(
        _envelope(portal_error="RuntimeError: login failed"), now=now
    )
    assert result["warnings"] == ["Couldn't reach school portal: RuntimeError: login failed"]


def test_build_prompt_includes_today_and_tomorrow_labels():
    now = datetime(2026, 9, 7, 20, 0, tzinfo=IST)  # Monday
    prompt = generate_brief.build_prompt(_envelope(portal_messages=[{"id": "1"}]), now)
    assert "Monday, September 07, 2026" in prompt
    assert "Tuesday, September 08, 2026" in prompt


def test_build_prompt_embeds_envelope_messages_as_json():
    now = datetime(2026, 9, 7, 20, 0, tzinfo=IST)
    envelope = _envelope(portal_messages=[{"id": "1", "title": "Homework"}])
    prompt = generate_brief.build_prompt(envelope, now)
    assert "Homework" in prompt
    assert json.dumps({"portal": envelope["portal"]["messages"], "whatsapp": []}, indent=2) in prompt


def test_collect_attachment_blocks_skips_missing_files(tmp_path):
    envelope = _envelope(
        portal_messages=[{"id": "1", "attachments": [{"name": "x", "saved_as": str(tmp_path / "missing.pdf")}]}]
    )
    assert generate_brief._collect_attachment_blocks(envelope) == []


def test_collect_attachment_blocks_encodes_existing_pdf(tmp_path):
    pdf_path = tmp_path / "homework.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake pdf bytes")
    envelope = _envelope(
        whatsapp_messages=[{"timestamp": "x", "attachments": [{"name": "homework.pdf", "saved_as": str(pdf_path)}]}]
    )
    blocks = generate_brief._collect_attachment_blocks(envelope)
    assert len(blocks) == 1
    assert blocks[0]["type"] == "document"
    assert blocks[0]["source"]["media_type"] == "application/pdf"
    decoded = base64.standard_b64decode(blocks[0]["source"]["data"])
    assert decoded == b"%PDF-1.4 fake pdf bytes"
