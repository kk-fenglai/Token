import json
from pathlib import Path

import pytest

from tokenscope.parser import ParseResult, model_family, normalize_cwd, parse_file, project_name

FIXTURE = Path(__file__).parent / "fixtures" / "sample.jsonl"


def test_model_family():
    assert model_family("claude-opus-5") == "opus"
    assert model_family("claude-fable-5") == "fable"
    assert model_family("claude-sonnet-4-6") == "sonnet"
    assert model_family("claude-haiku-4-5-20251001") == "haiku"
    assert model_family("<synthetic>") == "other"
    assert model_family("") == "other"


def test_normalize_cwd():
    assert normalize_cwd("C:\\Users\\alex\\Desktop\\MyApp") == "c:/Users/alex/Desktop/MyApp"
    assert normalize_cwd("/home/alex/myapp/") == "/home/alex/myapp"
    assert project_name("c:/Users/alex/Desktop/MyApp") == "MyApp"


def test_parse_file_streaming_dedupe_last_wins():
    res: ParseResult = parse_file(FIXTURE)
    # fixture: 2 partial lines + 1 final line share msg_A/req_A; msg_B is separate;
    # plus a user line, a malformed line, and an assistant line without usage.
    events = {(e[0], e[1]): e for e in res.events}
    assert len(events) == 2
    final_a = events[("msg_A", "req_A")]
    assert final_a[9] == 562          # output_tokens from the LAST msg_A line
    assert final_a[4] == "opus"
    assert res.error_count == 1       # malformed line
    assert res.skipped_count == 2     # user line + assistant without usage


def test_parse_file_idempotent_shape():
    res1 = parse_file(FIXTURE)
    res2 = parse_file(FIXTURE)
    assert sorted(res1.events) == sorted(res2.events)


@pytest.fixture(autouse=True, scope="session")
def make_fixture():
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        # streaming partials then final for msg_A
        _assistant("msg_A", "req_A", output=10, ts="2026-08-01T02:00:00.000Z"),
        _assistant("msg_A", "req_A", output=200, ts="2026-08-01T02:00:01.000Z"),
        _assistant("msg_A", "req_A", output=562, ts="2026-08-01T02:00:02.000Z"),
        _assistant("msg_B", "req_B", output=42, ts="2026-08-01T03:00:00.000Z"),
        json.dumps({"type": "user", "message": {"role": "user"}, "timestamp": "2026-08-01T02:00:00Z"}),
        "{ this is not json",
        json.dumps({"type": "assistant", "message": {"id": "msg_C", "model": "claude-opus-5"},
                    "timestamp": "2026-08-01T02:00:00Z"}),  # no usage → skipped
    ]
    FIXTURE.write_text("\n".join(lines), encoding="utf-8")


def _assistant(msg_id, req_id, output, ts):
    return json.dumps({
        "type": "assistant",
        "requestId": req_id,
        "timestamp": ts,
        "cwd": "C:\\Users\\alex\\Desktop\\MyApp",
        "session_id": "sess-1",
        "message": {
            "id": msg_id,
            "model": "claude-opus-5",
            "usage": {"input_tokens": 2, "output_tokens": output,
                      "cache_creation_input_tokens": 100, "cache_read_input_tokens": 500},
        },
    })
