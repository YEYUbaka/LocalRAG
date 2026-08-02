"""网页内容抓取模块。

支持单页抓取、批量抓取和整站爬取，将网页正文提取为 LangChain Document。
所有网络访问经由 SafeFetcher（SSRF 防护）。
"""

import asyncio
import re
from urllib.parse import urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup
from langchain_core.documents import Document

from app.core.safe_fetcher import FetchError, PublicHttpUrl, SafeFetcher

# 需要移除的标签（非正文内容）
_REMOVE_TAGS = [
    "script", "style", "nav", "footer", "header",
    "aside", "iframe", "noscript", "svg", "form",
]

# 内容截断上限（500KB）
_MAX_CONTENT_LENGTH = 500 * 1024


def _is_same_domain(base_url: str, link: str) -> bool:
    """检查 link 是否与 base_url 同域名。"""
    base_host = urlparse(base_url).netloc
    link_host = urlparse(link).netloc
    return base_host == link_host and link_host != ""


def _normalize_url(url: str, base_url: str) -> str:
    """URL 规范化：相对路径转绝对路径，去掉 fragment。"""
    # 相对路径 → 绝对路径
    absolute = urljoin(base_url, url)
    # 去掉 fragment（#...）
    parsed = urlparse(absolute)
    normalized = urlunparse((parsed.scheme, parsed.netloc, parsed.path,
                             parsed.params, parsed.query, ""))
    return normalized


def _extract_text_from_html(html: str, url: str) -> tuple[str, str]:
    """从 HTML 提取正文文本和标题。

    Returns:
        (title, text) 元组
    """
    soup = BeautifulSoup(html, "lxml")

    # 提取标题
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    # 移除非正文标签
    for tag_name in _REMOVE_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    # 优先找 article / main 标签
    content_root = soup.find("article") or soup.find("main")
    if content_root is None:
        content_root = soup.body or soup

    # 提取文本，用双换行分隔块级元素以保留段落结构
    text = content_root.get_text(separator="\n", strip=True)

    # 清理多余空行（超过 2 个连续换行 → 2 个）
    text = re.sub(r"\n{3,}", "\n\n", text)

    return title, text


async def fetch_single_url(url: str, fetcher: SafeFetcher | None = None) -> Document | None:
    """抓取单个 URL，返回 LangChain Document。

    抓取失败或地址被 SSRF 策略拒绝时返回 None。
    """
    try:
        parsed = PublicHttpUrl.parse(url)
    except FetchError:
        return None

    owned = fetcher is None
    fetcher = fetcher or SafeFetcher()
    try:
        result = await fetcher.fetch(parsed)
        html = result.html
        title, text = _extract_text_from_html(html, result.url)

        # 内容过长时截断
        if len(text.encode("utf-8")) > _MAX_CONTENT_LENGTH:
            text = text[:_MAX_CONTENT_LENGTH]

        if not text.strip():
            return None

        return Document(
            page_content=text,
            metadata={"url": result.url, "title": title, "type": "web"},
        )
    except FetchError:
        return None
    finally:
        if owned:
            await fetcher.aclose()


async def fetch_multiple_urls(
    urls: list[str], max_concurrent: int = 5
) -> list[Document]:
    """批量抓取多个 URL，跳过失败的，返回成功抓取的 Document 列表。"""
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _fetch(url: str) -> Document | None:
        async with semaphore:
            return await fetch_single_url(url)

    results = await asyncio.gather(*[_fetch(u) for u in urls])
    return [doc for doc in results if doc is not None]


async def crawl_site(
    start_url: str, max_pages: int = 50, max_depth: int = 2,
    fetcher: SafeFetcher | None = None,
) -> list[Document]:
    """BFS 整站爬取同域名页面。

    Args:
        start_url: 起始 URL
        max_pages: 最大爬取页面数
        max_depth: 最大爬取深度
        fetcher: 注入的 SafeFetcher（SSRF 防护），不传则自动创建

    Returns:
        所有成功抓取的 Document 列表
    """
    try:
        start_parsed = PublicHttpUrl.parse(start_url)
    except FetchError:
        return []

    semaphore = asyncio.Semaphore(5)
    visited: set[str] = set()
    documents: list[Document] = []
    # BFS 队列: (url, depth)
    queue: list[tuple[PublicHttpUrl, int]] = [(start_parsed, 0)]

    owned = fetcher is None
    fetcher = fetcher or SafeFetcher()
    try:
        while queue and len(documents) < max_pages:
            # 取一批待处理的 URL（最多 10 个并发）
            batch: list[tuple[PublicHttpUrl, int]] = []
            while queue and len(batch) < 10:
                url, depth = queue.pop(0)
                if url.url in visited or depth > max_depth:
                    continue
                visited.add(url.url)
                batch.append((url, depth))

            if not batch:
                break

            async def _fetch_and_extract(
                url: PublicHttpUrl, depth: int
            ) -> tuple[Document | None, list[tuple[PublicHttpUrl, int]]]:
                """抓取页面并提取同域名链接。"""
                async with semaphore:
                    try:
                        result = await fetcher.fetch(url)
                    except FetchError:
                        return None, []

                    html = result.html
                    title, text = _extract_text_from_html(html, result.url)

                    # 提取同域名链接（每个链接重新校验）
                    links: list[tuple[PublicHttpUrl, int]] = []
                    if depth < max_depth:
                        soup = BeautifulSoup(html, "lxml")
                        for a in soup.find_all("a", href=True):
                            href = a["href"]
                            normalized = _normalize_url(href, result.url)
                            if (
                                _is_same_domain(start_parsed.host, normalized)
                                and normalized not in visited
                            ):
                                try:
                                    link_url = PublicHttpUrl.parse(normalized)
                                except FetchError:
                                    continue
                                links.append((link_url, depth + 1))

                    if not text.strip():
                        return None, links

                    # 内容过长时截断
                    if len(text.encode("utf-8")) > _MAX_CONTENT_LENGTH:
                        text = text[:_MAX_CONTENT_LENGTH]

                    doc = Document(
                        page_content=text,
                        metadata={"url": result.url, "title": title, "type": "web"},
                    )
                    return doc, links

            tasks = [_fetch_and_extract(url, depth) for url, depth in batch]
            results = await asyncio.gather(*tasks)

            for doc, new_links in results:
                if doc is not None:
                    documents.append(doc)
                for link_url, link_depth in new_links:
                    if link_url.url not in visited:
                        queue.append((link_url, link_depth))
    finally:
        if owned:
            await fetcher.aclose()

    return documents
