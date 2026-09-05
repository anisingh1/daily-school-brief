from datetime import datetime, timedelta


def test_parse_jsonl_skips_blank_and_invalid_lines():
    from fetch_whatsapp import parse_jsonl

    text = '{"a": 1}\n\n not json \n{"b": 2}\n'
    result = parse_jsonl(text)
    assert result == [{"a": 1}, {"b": 2}]


def test_filter_recent_includes_message_within_window():
    from fetch_whatsapp import filter_recent

    now = datetime.now().astimezone()
    recent = (now - timedelta(hours=1)).isoformat()
    messages = [{"timestamp": recent, "sender": "A", "text": "hi"}]
    result = filter_recent(messages, lookback_hours=36)
    assert len(result) == 1


def test_filter_recent_excludes_message_before_cutoff():
    from fetch_whatsapp import filter_recent

    now = datetime.now().astimezone()
    old = (now - timedelta(hours=40)).isoformat()
    messages = [{"timestamp": old, "sender": "A", "text": "hi"}]
    result = filter_recent(messages, lookback_hours=36)
    assert result == []


def test_filter_recent_skips_entries_without_timestamp():
    from fetch_whatsapp import filter_recent

    messages = [{"sender": "A", "text": "no timestamp field"}]
    result = filter_recent(messages, lookback_hours=36)
    assert result == []


def test_filter_recent_includes_naive_timestamp_within_window():
    from fetch_whatsapp import filter_recent

    # No .astimezone(): produces a naive (no UTC offset) ISO string, which is
    # plausibly what the phone-side automation actually emits. This exercises
    # the "if ts.tzinfo is None" branch that tz-aware timestamps never hit.
    recent_naive = (datetime.now() - timedelta(hours=1)).isoformat()
    messages = [{"timestamp": recent_naive, "sender": "A", "text": "hi"}]
    result = filter_recent(messages, lookback_hours=36)
    assert len(result) == 1


def test_filter_recent_sorts_chronologically_not_lexicographically():
    from fetch_whatsapp import filter_recent

    # Non-zero-padded hour/minute/second: "9:5:0" sorts *after* "10:00:00"
    # lexicographically, even though it is chronologically earlier (09:05:00
    # < 10:00:00). This would fail if filter_recent sorted by the raw
    # timestamp string instead of the parsed datetime. Both timestamps use
    # "today" (same date as now) and the local UTC offset so they fall
    # inside the lookback window regardless of the current time of day.
    now = datetime.now().astimezone()
    date_str = now.strftime("%Y-%m-%d")
    offset = now.strftime("%z")
    offset_str = f"{offset[:3]}:{offset[3:]}" if offset else ""
    earlier = f"{date_str}T9:5:0{offset_str}"
    later = f"{date_str}T10:00:00{offset_str}"
    assert earlier > later  # sanity check: lexicographic order is reversed

    messages = [
        {"timestamp": later, "sender": "A", "text": "second"},
        {"timestamp": earlier, "sender": "B", "text": "first"},
    ]
    result = filter_recent(messages, lookback_hours=24)
    assert [m["text"] for m in result] == ["first", "second"]


def test_filter_recent_skips_entry_with_overflow_timestamp():
    from fetch_whatsapp import filter_recent

    messages = [{"timestamp": "99999999999999999999", "sender": "A", "text": "bad"}]
    result = filter_recent(messages, lookback_hours=36)
    assert result == []


def test_filter_recent_uses_explicit_cutoff_over_lookback_hours():
    from fetch_whatsapp import filter_recent

    cutoff = datetime(2026, 9, 4, 12, 0, 0).astimezone()
    just_after = (cutoff + timedelta(minutes=1)).isoformat()
    just_before = (cutoff - timedelta(minutes=1)).isoformat()
    messages = [
        {"timestamp": just_after, "sender": "A", "text": "in"},
        {"timestamp": just_before, "sender": "A", "text": "out"},
    ]
    # lookback_hours=1000 would normally include both if it were used -
    # confirming cutoff, not lookback_hours, governs the result.
    result = filter_recent(messages, lookback_hours=1000, cutoff=cutoff)
    assert [m["text"] for m in result] == ["in"]
