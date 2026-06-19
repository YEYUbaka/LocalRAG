"""Test web content fetcher — pure function tests, no mocking needed."""

from app.core.web_fetcher import _extract_text_from_html, _is_same_domain, _normalize_url


# ---------------------------------------------------------------------------
# _extract_text_from_html
# ---------------------------------------------------------------------------


def test_extract_text_basic():
    """基本 HTML 正文提取"""
    html = """
    <html>
    <head><title>测试页面</title></head>
    <body>
        <nav>导航内容不应该出现</nav>
        <article>
            <h1>文章标题</h1>
            <p>这是一段正文内容，需要足够长才能通过过滤阈值检查。</p>
            <p>这是第二段正文，同样需要一定的长度来保证提取成功。</p>
        </article>
        <footer>页脚内容不应该出现</footer>
    </body>
    </html>
    """
    title, text = _extract_text_from_html(html, "https://example.com")
    assert title == "测试页面"
    assert "正文内容" in text
    assert "导航内容" not in text
    assert "页脚内容" not in text


def test_extract_text_removes_scripts_and_styles():
    """应移除 script/style 标签内容"""
    html = """
    <html><body>
        <script>var x = 1; alert('hello');</script>
        <style>.body { color: red; font-size: 14px; }</style>
        <p>这是正文内容，需要足够长才能通过过滤阈值的检查。</p>
        <p>这是另一段正文内容，用于确保文本长度足够。</p>
    </body></html>
    """
    _, text = _extract_text_from_html(html, "https://example.com")
    assert "var x" not in text
    assert "color: red" not in text
    assert "正文内容" in text


def test_extract_text_removes_nav_footer_header():
    """应移除 nav/footer/header/aside/form 等非正文标签"""
    html = """
    <html><body>
        <header>页面头部导航区域</header>
        <nav>侧边导航菜单内容</nav>
        <aside>侧边栏广告和推荐</aside>
        <form><input type="text"/></form>
        <main>
            <p>这是主要正文内容，需要足够长才能通过过滤阈值的检查。</p>
            <p>这是主要正文的第二段，用于保证文本长度。</p>
        </main>
        <footer>版权信息和底部链接</footer>
    </body></html>
    """
    _, text = _extract_text_from_html(html, "https://example.com")
    assert "页面头部" not in text
    assert "侧边导航" not in text
    assert "侧边栏广告" not in text
    assert "主要正文内容" in text
    assert "版权信息" not in text


def test_extract_text_prefers_article_over_body():
    """优先使用 article 标签作为内容根"""
    html = """
    <html><body>
        <div>页面外围杂乱内容不应被提取</div>
        <article>
            <h2>文章标题在此</h2>
            <p>这是文章正文内容，需要足够长才能通过过滤阈值的检查。</p>
            <p>这是文章的第二段正文，用于保证文本长度足够。</p>
        </article>
        <div>页面底部杂乱内容不应被提取</div>
    </body></html>
    """
    _, text = _extract_text_from_html(html, "https://example.com")
    assert "文章正文内容" in text
    # article 优先，外围 div 不应出现
    assert "外围杂乱内容" not in text
    assert "底部杂乱内容" not in text


def test_extract_text_prefers_main_tag():
    """main 标签作为次优先内容根"""
    html = """
    <html><body>
        <div>无关外围内容不应该被提取出来</div>
        <main>
            <p>这是主要内容区域，需要足够长才能通过过滤阈值的检查。</p>
            <p>这是主要内容的第二段，保证文本长度足够通过过滤。</p>
        </main>
        <div>无关底部内容不应该被提取出来</div>
    </body></html>
    """
    _, text = _extract_text_from_html(html, "https://example.com")
    assert "主要内容区域" in text
    assert "无关外围内容" not in text


def test_extract_text_title_missing():
    """没有 title 标签时返回空字符串"""
    html = """
    <html><body>
        <p>这是没有标题的页面正文内容，需要足够长才能通过过滤阈值的检查。</p>
        <p>这是第二段正文，用于保证文本长度足够通过过滤检查。</p>
    </body></html>
    """
    title, text = _extract_text_from_html(html, "https://example.com")
    assert title == ""
    assert "没有标题" in text


def test_extract_text_cleans_excessive_newlines():
    """连续多个空行应压缩为两个"""
    html = """
    <html><body>
        <p>第一段内容在此。</p>
        <p>第二段内容在此。</p>
        <p>第三段内容在此。</p>
        <p>第四段内容在此。</p>
        <p>第五段内容在此。</p>
    </body></html>
    """
    _, text = _extract_text_from_html(html, "https://example.com")
    # 不应出现 3 个以上连续换行
    assert "\n\n\n" not in text


# ---------------------------------------------------------------------------
# _is_same_domain
# ---------------------------------------------------------------------------


def test_is_same_domain_identical():
    """相同域名"""
    assert _is_same_domain("https://example.com/page1", "https://example.com/page2")


def test_is_same_domain_different():
    """不同域名"""
    assert not _is_same_domain("https://example.com", "https://other.com")


def test_is_same_domain_subdomain():
    """子域名不算同域名"""
    assert not _is_same_domain("https://example.com", "https://blog.example.com")


def test_is_same_domain_empty_netloc():
    """无效 URL（空 netloc）返回 False"""
    assert not _is_same_domain("https://example.com", "not-a-url")


def test_is_same_domain_with_port():
    """带端口号的域名比较"""
    assert _is_same_domain("https://example.com:8080/a", "https://example.com:8080/b")
    assert not _is_same_domain("https://example.com:8080", "https://example.com:9090")


# ---------------------------------------------------------------------------
# _normalize_url
# ---------------------------------------------------------------------------


def test_normalize_relative_path():
    """相对路径转绝对路径"""
    result = _normalize_url("/about", "https://example.com/page")
    assert result == "https://example.com/about"


def test_normalize_absolute_url():
    """绝对 URL 保持不变（去掉 fragment）"""
    result = _normalize_url("https://other.com/page", "https://example.com")
    assert result == "https://other.com/page"


def test_normalize_javascript_void():
    """javascript: 协议返回原值（urljoin 不会过滤，但实际使用中由调用方处理）"""
    result = _normalize_url("javascript:void(0)", "https://example.com")
    # urljoin 会保留 javascript: 协议
    assert result is not None


def test_normalize_removes_fragment():
    """应去掉 URL 中的 fragment（#...）"""
    result = _normalize_url("https://example.com/page#section1", "https://example.com")
    assert "#" not in result
    assert result == "https://example.com/page"


def test_normalize_relative_with_fragment():
    """相对路径 + fragment：转绝对并去掉 fragment"""
    result = _normalize_url("/docs#intro", "https://example.com/page")
    assert result == "https://example.com/docs"
    assert "#" not in result


def test_normalize_preserves_query():
    """应保留 query 参数"""
    result = _normalize_url("/search?q=test&page=1", "https://example.com")
    assert "q=test" in result
    assert "page=1" in result
