import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.asyncio
async def test_web_search_returns_results():
    """正常搜索应返回 title/url/snippet 列表"""
    from app.services.web_search_service import web_search

    mock_results = [
        {"title": "武汉天气", "href": "https://weather.com/wuhan", "body": "今天晴天 25℃"},
    ]

    with patch("app.services.web_search_service.DDGS") as mock_ddgs:
        instance = mock_ddgs.return_value
        instance.text.return_value = mock_results
        results = await web_search("今天武汉天气")

    assert len(results) == 1
    assert results[0]["title"] == "武汉天气"
    assert results[0]["url"] == "https://weather.com/wuhan"
    assert results[0]["snippet"] == "今天晴天 25℃"


@pytest.mark.asyncio
async def test_web_search_returns_empty_on_error():
    """搜索失败时返回空列表，不抛异常"""
    from app.services.web_search_service import web_search

    with patch("app.services.web_search_service.DDGS") as mock_ddgs:
        instance = mock_ddgs.return_value
        instance.text.side_effect = Exception("rate limited")
        results = await web_search("test query")

    assert results == []


@pytest.mark.asyncio
async def test_web_search_respects_max_results():
    """max_results 参数应限制返回数量"""
    from app.services.web_search_service import web_search

    mock_results = [{"title": f"result {i}", "href": f"https://example.com/{i}", "body": f"snippet {i}"} for i in range(10)]

    with patch("app.services.web_search_service.DDGS") as mock_ddgs:
        instance = mock_ddgs.return_value
        instance.text.return_value = mock_results
        results = await web_search("test", max_results=3)

    assert len(results) == 3
