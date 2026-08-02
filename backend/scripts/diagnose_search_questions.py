"""诊断脚本：实测系统对「今天武汉天气怎么样」这类搜索/实时类问题的真实行为。

回答两个问题：
  1. 之前的「相关性阈值修复」是否生效 —— sources 是否已正确过滤为空、不再硬塞不相关来源。
  2. 能否给出今天实时天气 —— 预期不能（系统无任何联网搜索能力），本脚本给出结构化证据。

用法（在 backend 目录下）：
    conda run -n localrag --no-capture-output python scripts/diagnose_search_questions.py

脚本只读：不向 DB 写入 conversation / user / assistant message，只发起真实的 LLM 推理调用。
"""

import asyncio
import json
import sys
import warnings
from pathlib import Path

# 静默第三方 deprecation 噪声
warnings.filterwarnings("ignore")

# 确保 backend/ 在 sys.path（从 scripts/ 运行时，父目录的 app 包需要可见）
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# 加载 .env（与 main.py 一致）
from dotenv import load_dotenv
load_dotenv(BACKEND_DIR.parent / ".env")

# ---- 复用 main.py 的初始化：建表 + 迁移 + 重建 BM25 索引，忠实反映真实运行时 ----
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models import Base
import app.main as _main  # noqa: F401  触发 migrate_db(engine) 的副作用

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

try:
    from app.core.bm25_search import rebuild_from_db, _corpus as _bm25_corpus
    rebuild_from_db(SessionLocal)
except Exception as e:
    print(f"[WARN] BM25 索引重建失败（诊断仍可继续，但 BM25 召回将为空）：{e}")
    _bm25_corpus = []

from app.core.vectorstore import hybrid_search, get_collection
from app.core.prompts import build_rag_prompt, _get_general_prompt, RAG_SYSTEM_PROMPT
from app.services.llm_service import get_chat_model
from app.services.query_rewrite import rewrite_query


# ============ 配置 ============

# 拒答/卡壳关键词 —— 命中说明旧的「回答不上」bug 仍有残留
REFUSAL_KEYWORDS = ["知识库未包含", "未找到相关", "知识库中未", "我没有相关", "根据提供的知识库"]
# 实时性暗示关键词 —— 命中说明 LLM 承认给不出实时数据（预期命中）
REALTIME_HINT_KEYWORDS = ["无法获取", "实时", "无法联网", "没有联网", "建议查询", "建议您查询",
                          "我无法访问", "无法提供实时", "联网查询"]
# 具体天气数据特征（数字 + 温度单位）—— 用于人工判断是否编造数据
WEATHER_NUM_PATTERN = "℃"  # 进一步正则在扫描函数里用

TEST_QUESTIONS = [
    {"category": "对照·知识库内", "question": "什么是 RAG 技术？",
     "expect_sources": "非空", "expect_prompt": "RAG"},
    {"category": "重点·实时类", "question": "今天武汉天气怎么样？",
     "expect_sources": "空", "expect_prompt": "通用"},
    {"category": "重点·实时类", "question": "现在外面下雨吗？",
     "expect_sources": "空", "expect_prompt": "通用"},
    {"category": "通用闲聊", "question": "用一句话解释量子计算",
     "expect_sources": "空", "expect_prompt": "通用"},
]


# ============ 工具函数 ============

def banner(title: str) -> str:
    line = "=" * 70
    return f"\n{line}\n{title}\n{line}"


def which_prompt(question: str, sources: list[dict]) -> str:
    """判断 build_rag_prompt 会走哪条分支（不实际调用，靠 sources 是否为空推断，与代码逻辑一致）。"""
    return "通用聊天" if not sources else "RAG知识库"


def scan_answer(answer: str) -> dict:
    """对 LLM 回答做关键词扫描。"""
    return {
        "拒答词命中": [k for k in REFUSAL_KEYWORDS if k in answer],
        "实时性暗示命中": [k for k in REALTIME_HINT_KEYWORDS if k in answer],
        "含温度数据(℃)": "℃" in answer or "°C" in answer,
    }


async def stream_answer(messages) -> str:
    """复用 rag_service 的流式生成方式，但不写 DB、不发 SSE。"""
    model = get_chat_model()
    chunks = []
    async for chunk in model.astream(messages):
        content = chunk.content
        if content:
            chunks.append(content)
    return "".join(chunks)


async def diagnose_one(item: dict) -> dict:
    """对单个问题跑完整诊断（检索层 + 生成层）。"""
    question = item["question"]
    result = {"item": item, "rewrites": [], "sources": [], "prompt_type": "", "answer": "", "scan": {}}

    # ---- Layer 1：检索层 ----
    # 复现 rag_query 的多查询逻辑
    if settings.query_rewrite_enabled:
        queries = await rewrite_query(question)
    else:
        queries = [question]
    result["rewrites"] = queries

    all_sources = []
    seen_ids: set[str] = set()
    for q in queries:
        for r in hybrid_search(q, kb_id=None):
            if r["id"] not in seen_ids:
                seen_ids.add(r["id"])
                all_sources.append(r)
    sources = all_sources[:settings.rerank_top_k]
    result["sources"] = sources
    result["prompt_type"] = which_prompt(question, sources)

    # ---- Layer 2：生成层（直接调模型，绕开 DB）----
    from app.services.rag_service import build_messages
    messages = build_messages(question, sources, history=[])
    answer = await stream_answer(messages)
    result["answer"] = answer
    result["scan"] = scan_answer(answer)
    return result


# ============ Layer 0：环境前置检查 ============

def print_env_check() -> bool:
    print(banner("Layer 0：环境前置检查"))
    print(f"  LLM base_url     : {settings.llm_base_url}")
    print(f"  LLM model        : {settings.llm_model_name}")
    print(f"  similarity_threshold (向量距离上限, 越小越严) : {settings.similarity_threshold}")
    print(f"  rerank_threshold  (rerank 分数下限, 越大越严) : {settings.rerank_threshold}")
    print(f"  rerank_enabled    : {settings.rerank_enabled}")
    print(f"  hybrid_search     : {settings.hybrid_search}")
    print(f"  query_rewrite     : {settings.query_rewrite_enabled}")
    print(f"  retrieval_top_k   : {settings.retrieval_top_k}")
    print(f"  rerank_top_k      : {settings.rerank_top_k}")

    # 向量库规模
    try:
        coll = get_collection()
        vec_count = coll.count()
    except Exception as e:
        vec_count = f"<读取失败: {e}>"
    bm25_count = len(_bm25_corpus) if isinstance(_bm25_corpus, list) else 0
    print(f"  ChromaDB 向量数   : {vec_count}")
    print(f"  BM25 语料片段数   : {bm25_count}")

    # 模型/数据缺失判断
    ok = True
    if isinstance(vec_count, int) and vec_count == 0 and bm25_count == 0:
        print("\n  [FAIL] 知识库为空（向量库与 BM25 均无数据）。")
        print("         请先在系统里上传 test_docs/ 中的文档并等待解析完成，再跑本脚本。")
        ok = False
    if not settings.llm_api_key:
        print("\n  [FAIL] 未配置 LLM API Key，无法发起生成层验证。")
        ok = False
    if ok:
        print("\n  [OK] 环境就绪，继续诊断。")
    return ok


# ============ 主流程 ============

def print_one_result(r: dict, idx: int):
    item = r["item"]
    print(banner(f"#{idx} [{item['category']}] {item['question']}"))
    print(f"  期望 sources: {item['expect_sources']}  |  期望 prompt: {item['expect_prompt']}")

    print("\n  -- 查询改写变体 --")
    for i, q in enumerate(r["rewrites"], 1):
        print(f"    [{i}] {q}")

    srcs = r["sources"]
    print(f"\n  -- 检索结果：过滤后召回 {len(srcs)} 个片段 --")
    if srcs:
        for i, s in enumerate(srcs, 1):
            rs = s.get("rerank_score")
            rs_str = f"{rs:.4f}" if isinstance(rs, (int, float)) else "N/A"
            meta = s.get("metadata", {})
            fn = meta.get("filename", "未知文件")
            print(f"    [{i}] rerank_score={rs_str}  (阈值={settings.rerank_threshold})  《{fn}》")
            print(f"        片段预览: {s.get('document', '')[:60].replace(chr(10), ' ')}...")
    else:
        print("    (空 —— 弱相关结果已被 rerank 阈值过滤，符合预期)")

    pt = r["prompt_type"]
    print(f"\n  -- 触发 prompt 类型：{pt} --")
    if "通用" in pt:
        print("    → 走 _get_general_prompt()：LLM 像普通 AI 聊天，不提「知识库」、不说「未找到」")

    print("\n  -- LLM 实际回答 --")
    answer = r["answer"] or "(空)"
    for line in answer.splitlines():
        print(f"    {line}")

    sc = r["scan"]
    print("\n  -- 回答扫描 --")
    print(f"    拒答词命中      : {sc['拒答词命中'] or '无'}")
    print(f"    实时性暗示命中  : {sc['实时性暗示命中'] or '无'}")
    print(f"    含温度数据(℃)  : {sc['含温度数据(℃)']}")


def print_summary(results: list[dict]):
    print(banner("汇总表"))
    header = f"{'#':<3}{'类别':<16}{'sources数':<10}{'prompt':<12}{'拒答词':<8}{'实时暗示':<10}{'含℃'}"
    print(header)
    print("-" * len(header))
    for i, r in enumerate(results, 1):
        sc = r["scan"]
        print(f"{i:<3}{r['item']['category']:<16}"
              f"{len(r['sources']):<10}{r['prompt_type']:<12}"
              f"{'是' if sc['拒答词命中'] else '否':<8}"
              f"{'是' if sc['实时性暗示命中'] else '否':<10}"
              f"{'是' if sc['含温度数据(℃)'] else '否'}")

    print(banner("结论"))
    # 结论 1：卡壳/硬塞问题是否修复
    realtime_results = [r for r in results if "实时" in r["item"]["category"]]
    weather = next((r for r in results if "武汉天气" in r["item"]["question"]), None)

    print("\n[问题1] 天气/实时类问题还会不会「回答不上」（卡壳/硬塞不相关来源）？")
    if weather is not None:
        ws = weather["sources"]
        refusal = weather["scan"]["拒答词命中"]
        if len(ws) == 0 and not refusal:
            print(f"  ✅ 已修复：「今天武汉天气怎么样」检索结果为空（{len(ws)} 个来源），")
            print(f"     且回答未命中任何拒答词。系统切换到通用聊天 prompt 正常作答，不再硬塞来源、不再卡壳。")
        else:
            reasons = []
            if len(ws) > 0:
                scores = [f"{s.get('rerank_score'):.3f}" for s in ws if isinstance(s.get('rerank_score'), (int, float))]
                print(f"  ⚠️  仍有问题：天气问题召回了 {len(ws)} 个来源，rerank 分数 {scores}")
                print(f"     说明阈值过滤未生效，可能阈值偏低或数据特殊。")
            if refusal:
                print(f"  ⚠️  回答中命中拒答词：{refusal}，说明仍会出现「知识库未包含」式卡壳。")

    print("\n[问题2] 能给出「今天武汉实时天气」吗？")
    if weather is not None:
        hint = weather["scan"]["实时性暗示命中"]
        has_temp = weather["scan"]["含温度数据(℃)"]
        print(f"  ❌ 不能。系统架构上没有任何联网搜索 / function calling / tool use 能力，")
        print(f"     LLM 只能用自身参数知识作答。证据：")
        print(f"     - 回答中实时性暗示命中：{hint or '（未明确承认，但仍无真实实时数据）'}")
        print(f"     - 回答中是否出现温度数据：{'是（需人工核实真伪，大概率是泛泛/编造）' if has_temp else '否'}")
        print(f"  💡 如需真实实时天气，必须开发联网能力。建议优先探测当前模型")
        print(f"     ({settings.llm_model_name}) 是否支持火山方舟 web_search tool，再决定方案。")


async def main():
    print(banner("LocalRAG 搜索/实时类问题诊断"))
    print(f"  诊断脚本路径: {Path(__file__).resolve()}")

    if not print_env_check():
        print("\n环境检查未通过，终止诊断。")
        return

    results = []
    for idx, item in enumerate(TEST_QUESTIONS, 1):
        print(f"\n>>> 正在诊断 #{idx}: {item['question']} ...")
        try:
            r = await diagnose_one(item)
        except Exception as e:
            print(f"  [ERROR] 该问题诊断失败：{e}")
            import traceback
            traceback.print_exc()
            r = {"item": item, "rewrites": [], "sources": [], "prompt_type": "<错误>",
                 "answer": f"<诊断失败: {e}>", "scan": {"拒答词命中": [], "实时性暗示命中": [], "含温度数据(℃)": False}}
        results.append(r)
        print_one_result(r, idx)

    print_summary(results)


if __name__ == "__main__":
    asyncio.run(main())
