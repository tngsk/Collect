import json
import sys
from unittest.mock import MagicMock

# Mock dependencies that are not installed
sys.modules["pandas"] = MagicMock()
sys.modules["plotly"] = MagicMock()
sys.modules["plotly.express"] = MagicMock()
sys.modules["fastapi"] = MagicMock()
sys.modules["fastapi.responses"] = MagicMock()
sys.modules["pydantic"] = MagicMock()

import main


def test_save_data_appends_to_file(tmp_path, monkeypatch):
    # Create a temporary file path
    temp_file = tmp_path / "test_data.jsonl"

    # Monkeypatch main.DATA_FILE to use the temporary file
    monkeypatch.setattr(main, "DATA_FILE", str(temp_file))

    data1 = {"user": "alice", "score": 10}
    main.save_data(data1)

    assert temp_file.exists()
    with open(temp_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
        assert len(lines) == 1
        assert json.loads(lines[0]) == data1

    data2 = {"user": "bob", "score": 20}
    main.save_data(data2)

    with open(temp_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
        assert len(lines) == 2
        assert json.loads(lines[0]) == data1
        assert json.loads(lines[1]) == data2


def test_save_data_preserves_existing_content(tmp_path, monkeypatch):
    temp_file = tmp_path / "existing_data.jsonl"
    existing_content = '{"user": "ghost", "score": 0}\n'
    temp_file.write_text(existing_content, encoding="utf-8")

    monkeypatch.setattr(main, "DATA_FILE", str(temp_file))

    new_data = {"user": "newbie", "score": 5}
    main.save_data(new_data)

    with open(temp_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
        assert len(lines) == 2
        assert lines[0] == existing_content
        assert json.loads(lines[1]) == new_data
