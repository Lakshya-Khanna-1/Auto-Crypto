from unittest import mock

import httpx
import pytest

from tradecore.ailayer.client import generate_response


@pytest.mark.asyncio
async def test_generate_response_success():
    mock_resp = mock.Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"response": "Mocked AI Response Text"}

    with mock.patch("httpx.AsyncClient.post", new_callable=mock.AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        res = await generate_response("mock-fast-model", "Test Prompt")
        assert res == "Mocked AI Response Text"
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert kwargs["json"]["model"] == "mock-fast-model"
        assert kwargs["json"]["prompt"] == "Test Prompt"


@pytest.mark.asyncio
async def test_generate_response_timeout():
    with mock.patch("httpx.AsyncClient.post", new_callable=mock.AsyncMock) as mock_post:
        mock_post.side_effect = httpx.TimeoutException("Connection Timeout")
        res = await generate_response("mock-fast-model", "Test Prompt")
        assert res is None


@pytest.mark.asyncio
async def test_generate_response_http_error():
    mock_resp = mock.Mock()
    mock_resp.status_code = 500
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500 Server Error", request=mock.Mock(), response=mock_resp
    )

    with mock.patch("httpx.AsyncClient.post", new_callable=mock.AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        res = await generate_response("mock-fast-model", "Test Prompt")
        assert res is None
