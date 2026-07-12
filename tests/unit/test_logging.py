import json
import logging

from tradecore.core.logging import JsonFormatter


def test_json_formatter():
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="log verification success",
        args=(),
        exc_info=None,
    )
    result = formatter.format(record)
    parsed = json.loads(result)

    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "test_logger"
    assert parsed["message"] == "log verification success"
    assert "timestamp" in parsed
    assert parsed["module"] == "test"
    assert parsed["line_no"] == 10
