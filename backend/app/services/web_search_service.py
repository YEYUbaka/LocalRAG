"""联网搜索服务，使用 DuckDuckGo 作为搜索引擎。"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from duckduckgo_search import DDGS

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)


def _search_sync(query: str, max_results: int = 5) -> list[dict]:
    """同步搜索，在线程池中运行。"""
    ddgs = DDGS()
    results = ddgs.text(query, region="cn-zh", max_results=max_results)
    return [
        {
            "title": r.get("title", ""),
            "url": r.get("href", ""),
            "snippet": r.get("body", ""),
        }
        for r in results[:max_results]
    ]


async def web_search(query: str, max_results: int = 5) -> list[dict]:
    """异步搜索接口。

    Args:
        query: 搜索查询
        max_results: 最大返回结果数

    Returns:
        [{"title": str, "url": str, "snippet": str}, ...]
        搜索失败时返回空列表。
    """
    try:
        loop = asyncio.get_event_loop()
        results = await asyncio.wait_for(
            loop.run_in_executor(_executor, _search_sync, query, max_results),
            timeout=10.0,
        )
        return results
    except asyncio.TimeoutError:
        logger.warning(f"Web search timed out for query: {query}")
        return []
    except Exception as e:
        logger.warning(f"Web search failed for query '{query}': {e}")
        return []
