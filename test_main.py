import sys
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

# 1. Mock dependencies before importing main
# We must mock them because they are not installed in the environment
# and uv run fails due to lack of internet access.
def mock_decorator(*args, **kwargs):
    def wrapper(func):
        return func
    return wrapper

mock_fastapi = MagicMock()
mock_app = MagicMock()
mock_app.get = mock_decorator
mock_app.post = mock_decorator
mock_fastapi.FastAPI.return_value = mock_app

sys.modules["fastapi"] = mock_fastapi
sys.modules["fastapi.responses"] = MagicMock()

mock_pydantic = MagicMock()
class MockBaseModel:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
    def dict(self):
        return self.__dict__
mock_pydantic.BaseModel = MockBaseModel
sys.modules["pydantic"] = mock_pydantic

sys.modules["pandas"] = MagicMock()
sys.modules["plotly"] = MagicMock()
sys.modules["plotly.express"] = MagicMock()

# 2. Import main
import main

def test_submit_response_ignored_in_waiting_phase():
    # Setup: Set phase to WAITING
    main.state.current_phase = main.AllowedPhase.WAITING
    data = main.SubmitData(client_id="test_client", response="A", rt=100)

    # Execute
    result = asyncio.run(main.submit_response(data))

    # Verify
    assert result == {"status": "ignored", "reason": "not in evaluate phase"}

def test_submit_response_ok_in_evaluate_phase():
    # Setup: Set phase to EVALUATE_Q1
    main.state.current_phase = main.AllowedPhase.EVALUATE_Q1
    data = main.SubmitData(client_id="test_client", response="A", rt=100)

    # We mock save_data to avoid side effects on data.jsonl
    with patch("main.save_data") as mock_save,          patch("main.update_screen", new_callable=AsyncMock) as mock_update:

        # Execute
        result = asyncio.run(main.submit_response(data))

        # Verify
        assert result == {"status": "ok"}
        mock_save.assert_called_once_with({
            "client_id": "test_client",
            "phase": "EVALUATE_Q1",
            "response": "A",
            "rt": 100,
        })
        mock_update.assert_called_once()

def test_submit_response_ignored_in_show_result_phase():
    # Setup: Set phase to SHOW_RESULT_Q1
    main.state.current_phase = main.AllowedPhase.SHOW_RESULT_Q1
    data = main.SubmitData(client_id="test_client", response="A", rt=100)

    # Execute
    result = asyncio.run(main.submit_response(data))

    # Verify
    assert result == {"status": "ignored", "reason": "not in evaluate phase"}
