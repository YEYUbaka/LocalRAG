# 网页剪藏 / URL 爬取 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 支持从 URL 导入网页内容到知识库，包括单页抓取、整站爬取和批量 URL。

**Architecture:** 后端新增 `web_fetcher.py` 模块处理网页抓取和正文提取（httpx + BeautifulSoup，无新依赖），新增 API 端点支持三种导入模式，复用现有的切块/向量化/BM25 流水线。前端在 DocumentList 中添加 URL 导入 UI。

**Tech Stack:** Python 3.11+, httpx, BeautifulSoup4, lxml（均已安装）, FastAPI, TypeScript, React, Ant Design v6

## Global Constraints

- conda 环境名: `localrag`
- 所有后端测试通过 `conda run -n localrag python -m pytest tests/ -v` 运行
- 前端类型检查通过 `cd frontend && npx tsc --noEmit` 运行
- Git commit message 使用英文，conventional commits 格式
- 不添加新依赖（httpx + beautifulsoup4 + lxml 已安装）
- 爬取时遵守 robots.txt，限制并发和深度

---

## Phase 1: 后端 — 网页抓取模块

### Task 1: 创建 web_fetcher.py

**Files:**
- Create: `backend/app/core/web_fetcher.py`

- [ ] **Step 1: 创建网页抓取模块**

```python
"""Web content fetcher and extractor using httpx + BeautifulSoup."""

import asyncio
import re
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from langchain_core.documents import Document as LCDocument


# 请求配置
DEFAULT_TIMEOUT = 30
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# 最大爬取配置
MAX_PAGES_PER_SITE = 50
MAX_DEPTH = 2
MAX_CONTENT_LENGTH = 500_000  # 500KB 文本上限


def _extract_text_from_html(html: str, url: str) -> tuple[str, str]:
    """从 HTML 中提取正文文本和标题。

    Returns:
        (title, text): 页面标题和提取的正文
    """
    soup = BeautifulSoup(html, "lxml")

    # 移除不需要的标签
    for tag in soup.find_all(["script", "style", "nav", "footer", "header",
                               "aside", "iframe", "noscript", "svg", "form"]):
        tag.decompose()

    # 提取标题
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    # 尝试找 article/main 标签
    content = soup.find("article") or soup.find("main") or soup.find("role", "main")
    if not content:
        content = soup.find("body")

    if not content:
        return title, ""

    # 提取文本，保留段落结构
    text_parts = []
    for elem in content.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6",
                                    "li", "blockquote", "pre", "td", "th"]):
        txt = elem.get_text(strip=True)
        if txt and len(txt) > 10:  # 过滤太短的文本
            text_parts.append(txt)

    # 如果结构化提取失败，回退到整体文本
    if len(text_parts) < 3:
        text = content.get_text(separator="\n", strip=True)
    else:
        text = "\n\n".join(text_parts)

    # 清理多余空行
    text = re.sub(r"\n{3,}", "\n\n", text)

    return title, text


async def fetch_single_url(url: str) -> LCDocument:
    """抓取单个 URL 的内容。

    Returns:
        LangChain Document 对象，metadata 包含 url 和 title
    """
    async with httpx.AsyncClient(
        timeout=DEFAULT_TIMEOUT,
        headers=DEFAULT_HEADERS,
        follow_redirects=True,
        max_redirects=5,
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()

    html = resp.text
    title, text = _extract_text_from_html(html, url)

    if not text.strip():
        raise ValueError(f"无法从 {url} 提取正文内容")

    # 截断过长内容
    if len(text) > MAX_CONTENT_LENGTH:
        text = text[:MAX_CONTENT_LENGTH] + "\n\n[内容已截断]"

    return LCDocument(
        page_content=text,
        metadata={"source": url, "title": title or url, "type": "web"},
    )


async def fetch_multiple_urls(urls: list[str], max_concurrent: int = 5) -> list[LCDocument]:
    """批量抓取多个 URL。

    Args:
        urls: URL 列表
        max_concurrent: 最大并发数

    Returns:
        成功抓取的 Document 列表（失败的 URL 被跳过）
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    results = []

    async def _fetch_one(url: str):
        async with semaphore:
            try:
                doc = await fetch_single_url(url)
                results.append(doc)
            except Exception:
                pass  # 跳过失败的 URL

    await asyncio.gather(*[_fetch_one(u) for u in urls])
    return results


def _is_same_domain(base_url: str, link: str) -> bool:
    """检查链接是否与基础 URL 同域名。"""
    base_domain = urlparse(base_url).netloc
    link_domain = urlparse(link).netloc
    return base_domain == link_domain


def _normalize_url(url: str, base_url: str) -> str | None:
    """规范化 URL，返回绝对路径或 None（无效链接）。"""
    try:
        absolute = urljoin(base_url, url)
        parsed = urlparse(absolute)
        if parsed.scheme not in ("http", "https"):
            return None
        # 去掉 fragment
        return parsed._replace(fragment="").geturl()
    except Exception:
        return None


async def crawl_site(
    start_url: str,
    max_pages: int = MAX_PAGES_PER_SITE,
    max_depth: int = MAX_DEPTH,
    on_progress: callable | None = None,
) -> list[LCDocument]:
    """从起始 URL 开始爬取同域名页面。

    Args:
        start_url: 起始 URL
        max_pages: 最大页面数
        max_depth: 最大爬取深度
        on_progress: 进度回调 (current, total, url)

    Returns:
        所有成功抓取的 Document 列表
    """
    visited: set[str] = set()
    queue: list[tuple[str, int]] = [(start_url, 0)]
    results: list[LCDocument] = []
    semaphore = asyncio.Semaphore(5)

    async with httpx.AsyncClient(
        timeout=DEFAULT_TIMEOUT,
        headers=DEFAULT_HEADERS,
        follow_redirects=True,
        max_redirects=5,
    ) as client:
        while queue and len(results) < max_pages:
            # 取一批同深度的 URL 并发处理
            batch = []
            while queue and len(batch) < 10:
                url, depth = queue.pop(0)
                if url in visited or depth > max_depth:
                    continue
                visited.add(url)
                batch.append((url, depth))

            if not batch:
                break

            async def _process(url: str, depth: int):
                async with semaphore:
                    try:
                        resp = await client.get(url)
                        resp.raise_for_status()
                        html = resp.text

                        title, text = _extract_text_from_html(html, url)
                        if text.strip():
                            if len(text) > MAX_CONTENT_LENGTH:
                                text = text[:MAX_CONTENT_LENGTH]
                            results.append(LCDocument(
                                page_content=text,
                                metadata={"source": url, "title": title or url, "type": "web"},
                            ))

                        if on_progress:
                            on_progress(len(results), max_pages, url)

                        # 提取同域名链接
                        if depth < max_depth:
                            soup = BeautifulSoup(html, "lxml")
                            for a in soup.find_all("a", href=True):
                                link = _normalize_url(a["href"], url)
                                if link and link not in visited and _is_same_domain(start_url, link):
                                    queue.append((link, depth + 1))
                    except Exception:
                        pass

            await asyncio.gather(*[_process(u, d) for u, d in batch])

    return results
```

- [ ] **Step 2: 验证可导入**

```bash
cd e:/AI_projects/LocalRAG/backend && conda run -n localrag python -c "from app.core.web_fetcher import fetch_single_url, fetch_multiple_urls, crawl_site; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/core/web_fetcher.py
git commit -m "feat: add web content fetcher with single/batch/crawl support"
```

---

### Task 2: URL 导入 API 端点

**Files:**
- Modify: `backend/app/api/documents.py`

- [ ] **Step 1: 添加 URL 导入请求模型和端点**

在 `documents.py` 中添加：

```python
class ImportUrlRequest(BaseModel):
    url: str
    kb_id: int = 1


class ImportBatchUrlRequest(BaseModel):
    urls: list[str]
    kb_id: int = 1


class ImportCrawlRequest(BaseModel):
    url: str
    kb_id: int = 1
    max_pages: int = 20
    max_depth: int = 2


@router.post("/import-url")
async def import_from_url(
    req: ImportUrlRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """从单个 URL 导入网页内容。"""
    from app.core.web_fetcher import fetch_single_url

    # URL 去重检查
    existing = db.query(Document).filter(
        Document.file_path == req.url,
        Document.kb_id == req.kb_id,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="该 URL 已导入")

    # 创建文档记录
    doc = Document(
        kb_id=req.kb_id,
        user_id=user.id if user else None,
        filename=req.url[:200],  # 用 URL 作为文件名
        file_path=req.url,
        file_size=0,
        md5_hash="",  # URL 内容无法预先计算 MD5
        status="pending",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # 后台处理
    background_tasks.add_task(process_url_import, doc.id, req.url)

    return {"id": doc.id, "filename": doc.filename, "status": "pending"}


@router.post("/import-batch")
async def import_batch_urls(
    req: ImportBatchUrlRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """批量导入多个 URL。"""
    if len(req.urls) > 20:
        raise HTTPException(status_code=400, detail="单次最多导入 20 个 URL")

    results = []
    for url in req.urls:
        # URL 去重
        existing = db.query(Document).filter(
            Document.file_path == url,
            Document.kb_id == req.kb_id,
        ).first()
        if existing:
            continue

        doc = Document(
            kb_id=req.kb_id,
            user_id=user.id if user else None,
            filename=url[:200],
            file_path=url,
            file_size=0,
            md5_hash="",
            status="pending",
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        background_tasks.add_task(process_url_import, doc.id, url)
        results.append({"id": doc.id, "filename": doc.filename, "status": "pending"})

    return {"imported": len(results), "documents": results}


@router.post("/import-crawl")
async def import_crawl_site(
    req: ImportCrawlRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """从起始 URL 爬取同域名页面并导入。"""
    if req.max_pages > 50:
        raise HTTPException(status_code=400, detail="最大页面数不能超过 50")

    # 创建一个"爬取任务"文档记录
    doc = Document(
        kb_id=req.kb_id,
        user_id=user.id if user else None,
        filename=f"[爬取] {req.url[:180]}",
        file_path=req.url,
        file_size=0,
        md5_hash="",
        status="pending",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    background_tasks.add_task(process_crawl_import, doc.id, req.url, req.max_pages, req.max_depth)

    return {"id": doc.id, "filename": doc.filename, "status": "pending"}
```

- [ ] **Step 2: 添加 URL 导入的后台处理函数**

在 `document_service.py` 中添加：

```python
async def process_url_import(doc_id: int, url: str):
    """处理单个 URL 的导入。"""
    from app.core.web_fetcher import fetch_single_url

    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            return

        doc.status = "processing"
        db.commit()

        # 抓取网页
        lc_doc = await fetch_single_url(url)

        # 切块
        texts, metadatas = split_documents([lc_doc], doc.filename)

        # 向量化 + BM25
        add_documents(doc_id, texts, metadatas, doc.kb_id)
        add_document_chunks(doc_id, texts, doc.kb_id, metadatas)

        # 更新状态
        doc.parsed_content = lc_doc.page_content
        doc.chunk_count = len(texts)
        doc.status = "completed"
        doc.file_size = len(lc_doc.page_content.encode("utf-8"))
        db.commit()

    except Exception as e:
        doc.status = "failed"
        doc.error_message = str(e)[:500]
        db.commit()
    finally:
        db.close()


async def process_crawl_import(doc_id: int, start_url: str, max_pages: int, max_depth: int):
    """处理整站爬取导入。"""
    from app.core.web_fetcher import crawl_site

    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            return

        doc.status = "processing"
        db.commit()

        # 爬取
        lc_docs = await crawl_site(start_url, max_pages=max_pages, max_depth=max_depth)

        if not lc_docs:
            doc.status = "failed"
            doc.error_message = "未抓取到任何内容"
            db.commit()
            return

        # 合并所有页面内容
        all_text = "\n\n---\n\n".join(d.page_content for d in lc_docs)

        # 切块
        texts, metadatas = split_documents(lc_docs, doc.filename)

        # 向量化 + BM25
        add_documents(doc_id, texts, metadatas, doc.kb_id)
        add_document_chunks(doc_id, texts, doc.kb_id, metadatas)

        # 更新状态
        doc.parsed_content = all_text
        doc.chunk_count = len(texts)
        doc.status = "completed"
        doc.file_size = len(all_text.encode("utf-8"))
        db.commit()

    except Exception as e:
        doc.status = "failed"
        doc.error_message = str(e)[:500]
        db.commit()
    finally:
        db.close()
```

- [ ] **Step 3: 验证后端可启动**

```bash
cd e:/AI_projects/LocalRAG/backend && conda run -n localrag python -c "from app.api.documents import router; print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/documents.py backend/app/services/document_service.py
git commit -m "feat: add URL import API with single/batch/crawl modes"
```

---

### Task 3: 后端测试

**Files:**
- Create: `backend/tests/test_web_fetcher.py`

- [ ] **Step 1: 编写 web_fetcher 测试**

```python
"""Test web content fetcher."""

from app.core.web_fetcher import _extract_text_from_html, _is_same_domain, _normalize_url


def test_extract_text_basic():
    """基本 HTML 正文提取"""
    html = """
    <html>
    <head><title>测试页面</title></head>
    <body>
        <nav>导航内容</nav>
        <article>
            <h1>文章标题</h1>
            <p>这是一段正文内容，需要足够长才能通过过滤。</p>
            <p>这是第二段正文，同样需要一定的长度。</p>
        </article>
        <footer>页脚内容</footer>
    </body>
    </html>
    """
    title, text = _extract_text_from_html(html, "https://example.com")
    assert title == "测试页面"
    assert "正文内容" in text
    assert "导航内容" not in text
    assert "页脚内容" not in text


def test_extract_text_removes_scripts():
    """应移除 script/style 标签"""
    html = """
    <html><body>
        <script>var x = 1;</script>
        <style>.body { color: red; }</style>
        <p>这是正文内容，需要足够长才能通过过滤阈值。</p>
    </body></html>
    """
    _, text = _extract_text_from_html(html, "https://example.com")
    assert "var x" not in text
    assert "color: red" not in text
    assert "正文内容" in text


def test_is_same_domain():
    """同域名检查"""
    assert _is_same_domain("https://example.com/page1", "https://example.com/page2")
    assert not _is_same_domain("https://example.com", "https://other.com")


def test_normalize_url():
    """URL 规范化"""
    result = _normalize_url("/about", "https://example.com/page")
    assert result == "https://example.com/about"

    result = _normalize_url("https://other.com/page", "https://example.com")
    assert result == "https://other.com/page"

    result = _normalize_url("javascript:void(0)", "https://example.com")
    assert result is None
```

- [ ] **Step 2: 运行测试**

```bash
cd e:/AI_projects/LocalRAG/backend && conda run -n localrag python -m pytest tests/test_web_fetcher.py -v
```

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_web_fetcher.py
git commit -m "test: add unit tests for web content fetcher"
```

---

## Phase 2: 前端 — URL 导入 UI

### Task 4: 前端 API 和 UI

**Files:**
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/components/DocumentList.tsx`

- [ ] **Step 1: 添加 URL 导入 API 函数**

在 `api.ts` 中添加：

```typescript
export async function importUrl(url: string, kbId: number = 1): Promise<{ id: number; filename: string; status: string }> {
  return request('/documents/import-url', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, kb_id: kbId }),
  });
}

export async function importBatchUrls(urls: string[], kbId: number = 1): Promise<{ imported: number; documents: { id: number; filename: string; status: string }[] }> {
  return request('/documents/import-batch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ urls, kb_id: kbId }),
  });
}

export async function importCrawlSite(url: string, kbId: number = 1, maxPages: number = 20, maxDepth: number = 2): Promise<{ id: number; filename: string; status: string }> {
  return request('/documents/import-crawl', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, kb_id: kbId, max_pages: maxPages, max_depth: maxDepth }),
  });
}
```

- [ ] **Step 2: DocumentList 添加 URL 导入 UI**

在 DocumentList 的上传区域下方添加 URL 导入面板：

```tsx
import { Input, Tabs, Button, message, Space, InputNumber } from 'antd';
import { LinkOutlined, GlobalOutlined } from '@ant-design/icons';
```

添加状态：

```tsx
const [urlInput, setUrlInput] = useState('');
const [batchUrls, setBatchUrls] = useState('');
const [crawlUrl, setCrawlUrl] = useState('');
const [maxPages, setMaxPages] = useState(20);
const [maxDepth, setMaxDepth] = useState(2);
const [importing, setImporting] = useState(false);
```

在 Dragger 下方添加 Tabs：

```tsx
<Tabs size="small" items={[
  {
    key: 'upload',
    label: '文件上传',
    children: <Dragger ...>...</Dragger>,
  },
  {
    key: 'single',
    label: '网页导入',
    children: (
      <Space.Compact style={{ width: '100%' }}>
        <Input
          prefix={<LinkOutlined />}
          placeholder="输入网页 URL..."
          value={urlInput}
          onChange={e => setUrlInput(e.target.value)}
          onPressEnter={handleImportUrl}
        />
        <Button type="primary" loading={importing} onClick={handleImportUrl}>导入</Button>
      </Space.Compact>
    ),
  },
  {
    key: 'batch',
    label: '批量导入',
    children: (
      <div>
        <Input.TextArea
          placeholder="每行一个 URL"
          value={batchUrls}
          onChange={e => setBatchUrls(e.target.value)}
          autoSize={{ minRows: 3, maxRows: 6 }}
          style={{ marginBottom: 8 }}
        />
        <Button type="primary" block loading={importing} onClick={handleBatchImport}>批量导入</Button>
      </div>
    ),
  },
  {
    key: 'crawl',
    label: '整站爬取',
    children: (
      <div>
        <Input
          prefix={<GlobalOutlined />}
          placeholder="输入起始 URL..."
          value={crawlUrl}
          onChange={e => setCrawlUrl(e.target.value)}
          style={{ marginBottom: 8 }}
        />
        <Space style={{ marginBottom: 8 }}>
          <span>最大页面:</span>
          <InputNumber size="small" value={maxPages} onChange={v => setMaxPages(v || 20)} min={1} max={50} />
          <span>深度:</span>
          <InputNumber size="small" value={maxDepth} onChange={v => setMaxDepth(v || 2)} min={1} max={3} />
        </Space>
        <Button type="primary" block loading={importing} onClick={handleCrawlImport}>开始爬取</Button>
      </div>
    ),
  },
]} />
```

处理函数：

```tsx
const handleImportUrl = async () => {
  if (!urlInput.trim()) return;
  setImporting(true);
  try {
    const result = await importUrl(urlInput.trim(), currentKbId);
    message.success(`已提交: ${result.filename}`);
    setUrlInput('');
    await loadDocs();
    pollStatus(result.id);
  } catch (e: any) {
    message.error(e.message);
  } finally {
    setImporting(false);
  }
};

const handleBatchImport = async () => {
  const urls = batchUrls.split('\n').map(u => u.trim()).filter(Boolean);
  if (urls.length === 0) return;
  setImporting(true);
  try {
    const result = await importBatchUrls(urls, currentKbId);
    message.success(`已提交 ${result.imported} 个 URL`);
    setBatchUrls('');
    await loadDocs();
    result.documents.forEach(d => pollStatus(d.id));
  } catch (e: any) {
    message.error(e.message);
  } finally {
    setImporting(false);
  }
};

const handleCrawlImport = async () => {
  if (!crawlUrl.trim()) return;
  setImporting(true);
  try {
    const result = await importCrawlSite(crawlUrl.trim(), currentKbId, maxPages, maxDepth);
    message.success(`爬取任务已提交: ${result.filename}`);
    setCrawlUrl('');
    await loadDocs();
    pollStatus(result.id);
  } catch (e: any) {
    message.error(e.message);
  } finally {
    setImporting(false);
  }
};
```

- [ ] **Step 3: 前端类型检查**

```bash
cd e:/AI_projects/LocalRAG/frontend && npx tsc --noEmit
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/services/api.ts frontend/src/components/DocumentList.tsx
git commit -m "feat: add URL import UI with single/batch/crawl modes"
```

---

## 最终验证

- [ ] **Step 1: 运行全量后端测试**

```bash
cd e:/AI_projects/LocalRAG/backend && conda run -n localrag python -m pytest tests/ -v
```

预期：全部 PASS（约 65+ tests）

- [ ] **Step 2: 前端类型检查**

```bash
cd e:/AI_projects/LocalRAG/frontend && npx tsc --noEmit
```

预期：无类型错误
