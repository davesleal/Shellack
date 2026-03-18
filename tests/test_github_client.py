import pytest
from unittest.mock import patch, MagicMock
from tools.github_client import GitHubClient

PROJECTS = {
    "dayist": {"github_repo": "davesleal/Dayist", "platform": "ios"},
}


@pytest.fixture
def client():
    return GitHubClient(token="test-token", projects=PROJECTS)


def test_create_issue_returns_number_and_url(client):
    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"number": 42, "html_url": "https://github.com/davesleal/Dayist/issues/42"}

    with patch("tools.github_client.requests.post", return_value=mock_response):
        result = client.create_issue("dayist", "Login crash", "Details here", "crash")

    assert result["number"] == 42
    assert result["url"] == "https://github.com/davesleal/Dayist/issues/42"


def test_create_issue_returns_none_on_api_error(client):
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.json.return_value = {"message": "Bad credentials"}

    with patch("tools.github_client.requests.post", return_value=mock_response):
        result = client.create_issue("dayist", "Title", "Body", "crash")

    assert result is None


def test_create_issue_returns_none_for_unknown_project(client):
    result = client.create_issue("unknown_project", "Title", "Body", "crash")
    assert result is None


def test_create_issue_applies_correct_labels_for_crash(client):
    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"number": 1, "html_url": "https://github.com/x/y/issues/1"}

    with patch("tools.github_client.requests.post", return_value=mock_response) as mock_post:
        client.create_issue("dayist", "Title", "Body", "crash")
        call_json = mock_post.call_args.kwargs["json"]
        assert "crash" in call_json["labels"]
        assert "bug" in call_json["labels"]
        assert "ios" in call_json["labels"]


def test_close_issue_returns_true_on_success(client):
    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("tools.github_client.requests.patch", return_value=mock_response):
        result = client.close_issue("dayist", 42)

    assert result is True


def test_close_issue_returns_false_on_error(client):
    mock_response = MagicMock()
    mock_response.status_code = 404

    with patch("tools.github_client.requests.patch", return_value=mock_response):
        result = client.close_issue("dayist", 999)

    assert result is False
