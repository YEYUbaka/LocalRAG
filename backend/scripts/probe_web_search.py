"""探测火山方舟 web_search 联网能力是否可用（B 方案可行性验证）。

直接用 OpenAI SDK 调 Responses API + web_search tool，
确认当前 API key 权限、模型支持、是否已开通联网内容插件。

用法（在 backend 目录下）：
    conda run -n localrag --no-capture-output python scripts/probe_web_search.py
"""

import sys
import json
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv(BACKEND_DIR.parent / ".env")

from app.config import settings


def probe():
    print("=" * 60)
    print("火山方舟 Web Search 联网能力探测")
    print("=" * 60)
    print(f"  base_url : {settings.llm_base_url}")
    print(f"  model    : {settings.llm_model_name}")
    print(f"  api_key  : {settings.llm_api_key[:14]}...")
    print()

    try:
        from openai import OpenAI
    except ImportError:
        print("[FAIL] 未安装 openai 包")
        return

    client = OpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
    )

    # 测试 1：天气问题（墨迹天气源）
    print(">>> 测试 1：今天武汉天气怎么样？（sources 含 moji）")
    try:
        response = client.responses.create(
            model=settings.llm_model_name,
            input=[{"role": "user", "content": "今天武汉天气怎么样？"}],
            tools=[{
                "type": "web_search",
                "max_keyword": 2,
                "sources": ["moji"],
            }],
        )
        print("  [OK] 调用成功")
        # 提取回答文本
        output_text = ""
        try:
            output_text = response.output_text
        except Exception:
            # 兜底：从 output 里取 message 内容
            for item in getattr(response, "output", []):
                if getattr(item, "type", "") == "message":
                    for c in getattr(item, "content", []):
                        output_text += getattr(c, "text", "")
        print("  --- 回答 ---")
        for line in output_text.splitlines():
            print(f"    {line}")
        # 用量
        usage = getattr(response, "usage", None)
        if usage:
            print(f"  --- 用量 ---")
            print(f"    tool_usage: {getattr(usage, 'tool_usage', None)}")
            print(f"    tool_usage_details: {getattr(usage, 'tool_usage_details', None)}")
    except Exception as e:
        print(f"  [FAIL] 调用失败: {type(e).__name__}: {e}")
        # 尝试提取更有用的错误信息
        import traceback
        tb = traceback.format_exc()
        if "400" in str(e) or "permission" in str(e).lower() or "开通" in str(e):
            print("  >>> 提示：可能未在火山方舟控制台「服务组件库」开通「联网内容插件」")

    print()

    # 测试 2：新闻类问题
    print(">>> 测试 2：今天有什么热点新闻？（默认全网源）")
    try:
        response = client.responses.create(
            model=settings.llm_model_name,
            input=[{"role": "user", "content": "今天有什么热点新闻？"}],
            tools=[{"type": "web_search", "max_keyword": 2}],
        )
        print("  [OK] 调用成功")
        output_text = getattr(response, "output_text", "") or ""
        print("  --- 回答（前300字）---")
        print(f"    {output_text[:300]}...")
    except Exception as e:
        print(f"  [FAIL] 调用失败: {type(e).__name__}: {e}")


if __name__ == "__main__":
    probe()
