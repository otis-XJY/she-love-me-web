from __future__ import annotations

import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import traceback
import urllib.error
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
WEB_ROOT = PROJECT_ROOT / "web"
RUNTIME_ROOT = Path(os.environ.get("SHE_LOVE_ME_RUNTIME", PROJECT_ROOT / "runtime" / "she-love-me")).resolve()
SCRIPTS_ROOT = RUNTIME_ROOT / "scripts"
DATA_ROOT = RUNTIME_ROOT / "data"
REPORTS_ROOT = RUNTIME_ROOT / "reports"
ARCHIVES_ROOT = RUNTIME_ROOT / "archives"
DECRYPTED_ROOT = RUNTIME_ROOT / "vendor" / "wechat-decrypt" / "decrypted"

HOST = os.environ.get("SHE_LOVE_ME_HOST", "127.0.0.1")
PORT = int(os.environ.get("SHE_LOVE_ME_PORT", "8765"))
LLM_CONFIG: dict[str, str] = {
    "provider": os.environ.get("SHE_LOVE_ME_LLM_PROVIDER", "openai"),
    "base_url": os.environ.get("SHE_LOVE_ME_LLM_BASE_URL", "https://api.openai.com/v1"),
    "api_key": os.environ.get("SHE_LOVE_ME_LLM_API_KEY", ""),
    "model": os.environ.get("SHE_LOVE_ME_LLM_MODEL", "gpt-4.1"),
}

PROVIDER_DEFAULTS = {
    "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-4.1"},
    "anthropic": {"base_url": "https://api.anthropic.com/v1", "model": "claude-3-5-sonnet-latest"},
    "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta", "model": "gemini-1.5-pro"},
}


class AppError(Exception):
    def __init__(self, message: str, status: int = 400, details: Any | None = None):
        super().__init__(message)
        self.status = status
        self.details = details


def ensure_dirs() -> None:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    REPORTS_ROOT.mkdir(parents=True, exist_ok=True)
    ARCHIVES_ROOT.mkdir(parents=True, exist_ok=True)


def script_path(name: str) -> Path:
    path = SCRIPTS_ROOT / name
    if not path.exists():
        raise AppError(f"缺少脚本: {path}", 500)
    return path


def run_script(name: str, args: list[str], timeout: int = 900) -> dict[str, Any]:
    ensure_dirs()
    cmd = [sys.executable, str(script_path(name)), *args]
    proc = subprocess.run(
        cmd,
        cwd=str(RUNTIME_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    payload = parse_jsonish(proc.stdout)
    result = {
        "command": [Path(cmd[0]).name, name, *args],
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "json": payload,
    }
    if proc.returncode != 0:
        message = ""
        if isinstance(payload, dict):
            message = str(payload.get("error") or payload.get("message") or "")
        raise AppError(message or proc.stderr.strip() or proc.stdout.strip() or f"{name} 执行失败", 500, result)
    return result


def parse_jsonish(text: str) -> Any | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start_candidates = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    if not start_candidates:
        return None
    start = min(start_candidates)
    for end in range(len(text), start, -1):
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            continue
    return None


def read_json(path: Path) -> Any:
    if not path.exists():
        raise AppError(f"文件不存在: {path}", 404)
    return json.loads(path.read_text(encoding="utf-8"))


def latest_report() -> dict[str, str] | None:
    if not REPORTS_ROOT.exists():
        return None
    reports = sorted(REPORTS_ROOT.glob("*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not reports:
        return None
    path = reports[0]
    return {"name": path.name, "url": f"/reports/{path.name}", "path": str(path)}


def list_archives() -> list[dict[str, Any]]:
    ensure_dirs()
    archives: list[dict[str, Any]] = []
    seen_reports: set[str] = set()

    for meta_path in ARCHIVES_ROOT.glob("*/metadata.json"):
        try:
            item = read_json(meta_path)
            if item.get("report_name"):
                seen_reports.add(item["report_name"])
            archives.append(item)
        except Exception:
            continue

    for report in REPORTS_ROOT.glob("*.html"):
        if report.name in seen_reports:
            continue
        stem = report.stem
        contact = re.sub(r"_\d{8}_\d{4}$", "", stem) or stem
        archives.append({
            "id": stem,
            "contact": contact,
            "created_at": datetime.fromtimestamp(report.stat().st_mtime).isoformat(timespec="seconds"),
            "report_name": report.name,
            "report_url": f"/reports/{report.name}",
            "relationship_type": "历史报告",
            "message_count": None,
        })

    archives.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return archives[:24]


def create_archive(report_path: Path) -> dict[str, Any]:
    ensure_dirs()
    messages = read_json(DATA_ROOT / "messages.json") if (DATA_ROOT / "messages.json").exists() else {}
    stats = read_json(DATA_ROOT / "stats.json") if (DATA_ROOT / "stats.json").exists() else {}
    analysis = read_json(DATA_ROOT / "analysis.json") if (DATA_ROOT / "analysis.json").exists() else {}

    contact = messages.get("contact_display") or get_contact_name()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_contact = re.sub(r"[^\w\u4e00-\u9fff\-]+", "_", str(contact)).strip("_") or "contact"
    archive_id = f"{stamp}_{safe_contact}"
    archive_dir = ARCHIVES_ROOT / archive_id
    archive_dir.mkdir(parents=True, exist_ok=True)

    for name in ("messages.json", "stats.json", "analysis.json", "chat_history.txt"):
        src = DATA_ROOT / name
        if src.exists():
            shutil.copy2(src, archive_dir / name)

    metadata = {
        "id": archive_id,
        "contact": contact,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "report_name": report_path.name,
        "report_url": f"/reports/{report_path.name}",
        "relationship_type": analysis.get("relationship_type", "未判定"),
        "relationship_label": analysis.get("relationship_label", ""),
        "message_count": stats.get("basic", {}).get("total_messages"),
        "date_range": stats.get("basic", {}).get("date_range"),
        "scores": stats.get("scores", {}),
    }
    (archive_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


def get_contact_name() -> str:
    messages_path = DATA_ROOT / "messages.json"
    if messages_path.exists():
        try:
            data = read_json(messages_path)
            return data.get("contact_display") or data.get("contact_username") or "对方"
        except Exception:
            pass
    return "对方"


def build_status() -> dict[str, Any]:
    llm_key = LLM_CONFIG.get("api_key", "")
    scripts_ready = all((SCRIPTS_ROOT / name).exists() for name in (
        "setup_check.py",
        "decrypt_wechat.py",
        "list_contacts.py",
        "extract_messages.py",
        "stats_analyzer.py",
        "generate_html_report.py",
    ))
    return {
        "runtime_root": str(RUNTIME_ROOT),
        "python": sys.executable,
        "scripts_ready": scripts_ready,
        "environment_ready": scripts_ready,
        "environment_label": "环境就绪" if scripts_ready else "环境异常",
        "decryptor_present": (RUNTIME_ROOT / "vendor" / "wechat-decrypt").exists(),
        "decrypted_present": DECRYPTED_ROOT.exists(),
        "messages_present": (DATA_ROOT / "messages.json").exists(),
        "stats_present": (DATA_ROOT / "stats.json").exists(),
        "analysis_present": (DATA_ROOT / "analysis.json").exists(),
        "latest_report": latest_report(),
        "archives": list_archives(),
        "llm_configured": bool(llm_key),
        "llm_provider": LLM_CONFIG.get("provider", "openai"),
        "llm_model": LLM_CONFIG.get("model", ""),
        "llm_base_url": LLM_CONFIG.get("base_url", ""),
        "llm_key_hint": f"已设置 · ****{llm_key[-4:]}" if llm_key else "未设置",
    }


def update_llm_config(payload: dict[str, Any]) -> dict[str, str]:
    old_provider = LLM_CONFIG.get("provider", "openai")
    provider = str(payload.get("provider", LLM_CONFIG.get("provider", "openai"))).strip().lower()
    if provider not in PROVIDER_DEFAULTS:
        raise AppError("接口模式只支持 openai、anthropic、gemini")
    base_url = str(payload.get("base_url", "")).strip().rstrip("/")
    model = str(payload.get("model", "")).strip()
    api_key = str(payload.get("api_key", "")).strip()

    provider_changed = provider != old_provider
    LLM_CONFIG["provider"] = provider
    if base_url:
        if not re.match(r"^https?://", base_url):
            raise AppError("BaseURL 必须以 http:// 或 https:// 开头")
        LLM_CONFIG["base_url"] = base_url
    elif provider_changed or not LLM_CONFIG.get("base_url"):
        LLM_CONFIG["base_url"] = PROVIDER_DEFAULTS[provider]["base_url"]
    if model:
        LLM_CONFIG["model"] = model
    elif provider_changed or not LLM_CONFIG.get("model"):
        LLM_CONFIG["model"] = PROVIDER_DEFAULTS[provider]["model"]
    if api_key:
        LLM_CONFIG["api_key"] = api_key

    return {
        "provider": LLM_CONFIG.get("provider", "openai"),
        "base_url": LLM_CONFIG.get("base_url", ""),
        "model": LLM_CONFIG.get("model", ""),
        "key_hint": build_status()["llm_key_hint"],
    }


def discover_wechat() -> dict[str, Any]:
    setup = run_script("setup_check.py", ["--ensure-decryptor"], timeout=1200)
    decrypt = run_script("decrypt_wechat.py", [], timeout=2400)
    contacts = run_script("list_contacts.py", ["--decrypted-dir", str(DECRYPTED_ROOT)], timeout=900)
    return {
        "setup": setup,
        "decrypt": decrypt,
        "contacts": contacts.get("json") or [],
        "status": build_status(),
    }


def summarize_stats(stats: dict[str, Any], contact: str) -> dict[str, Any]:
    basic = stats.get("basic", {})
    scores = stats.get("scores", {})
    initiative = stats.get("initiative", {})
    reply = stats.get("reply_speed", {})
    bombing = stats.get("bombing", {})
    goodnight = stats.get("goodnight", {})
    linguistic = stats.get("linguistic", {})

    my_ratio = basic.get("my_ratio", 0)
    their_ratio = basic.get("their_ratio", 0)
    loved = scores.get("loved_index", 0)
    simp = scores.get("simp_index", 0)
    cold = scores.get("cold_index", 0)
    symmetry = max(1, min(10, 10 - int(abs(my_ratio - their_ratio) * 12)))

    if loved >= 70 and symmetry >= 7:
        relationship_type = "相互喜欢"
        relationship_label = "双向投入明显，关系里有稳定的回应和持续互动。"
    elif simp >= 72 and loved < 45:
        relationship_type = "深陷单恋"
        relationship_label = "你的主动和投入明显高于对方，需要警惕单向消耗。"
    elif cold >= 65:
        relationship_type = "名存实亡"
        relationship_label = "冷淡信号偏高，当前互动质量需要重点复盘。"
    else:
        relationship_type = "暧昧拉锯"
        relationship_label = "双方存在互动基础，但节奏和确认感仍不稳定。"

    trend = "平稳维持"
    daily = stats.get("daily_trend", [])
    if len(daily) >= 14:
        recent = sum(d.get("count", 0) for d in daily[-7:]) / 7
        previous = sum(d.get("count", 0) for d in daily[-14:-7]) / 7
        if previous and recent > previous * 1.25:
            trend = "升温中"
        elif previous and recent < previous * 0.65:
            trend = "逐渐降温"

    danger_warnings = []
    if symmetry <= 3 or (simp >= 78 and loved <= 40):
        danger_warnings.append({
            "type": "单向投入风险",
            "level": "高危",
            "evidence": "主动指数明显高于被爱指数，且双方消息占比/回应节奏不够对称。",
        })
    if bombing.get("my_max_consecutive", 0) >= 20:
        danger_warnings.append({
            "type": "连续追问风险",
            "level": "中危",
            "evidence": f"你最高连续发送 {bombing.get('my_max_consecutive')} 条未等到对方回应。",
        })

    return {
        "relationship_type": relationship_type,
        "relationship_label": relationship_label,
        "relationship_trend": trend,
        "relationship_stage": {
            "stage": "关系观察期" if relationship_type in ("暧昧拉锯", "朋友边界") else "关系维护期",
            "stage_description": f"基于 {basic.get('total_messages', 0)} 条消息的本地统计，当前更接近「{relationship_type}」。",
            "is_situationship": relationship_type == "暧昧拉锯",
            "situationship_evidence": "此版本为统计启发式分析，若需要原话证据，请配置 OpenAI 兼容模型后重新运行深度分析。",
            "stage_risk": "统计结果只能识别互动结构，不能替代对具体语境的人工判断。",
            "advancement_path": "优先观察对方是否稳定主动、是否愿意承接你的情绪，以及现实安排是否能被认真讨论。",
        },
        "emotional_asymmetry": {
            "symmetry_score": symmetry,
            "anchor_person": "me" if my_ratio >= their_ratio else "them",
            "anchor_description": f"消息占比：你 {my_ratio:.1%}，{contact} {their_ratio:.1%}；主动指数 {simp}，被爱指数 {loved}。",
            "conflict_pattern": "需要结合聊天原文判断。当前版本主要依据主动性、回复速度、冷淡回复和连续发送结构推断。",
            "power_dynamics": f"对话发起：你 {initiative.get('my_starts', 0)} 次，对方 {initiative.get('their_starts', 0)} 次。",
            "key_turning_point": {"date": "未定位", "event": "启发式模式未扫描全文转折点。"},
        },
        "sternberg": {
            "passion": max(20, min(95, int(loved * 0.7 + linguistic.get("positive_ratio", {}).get("them", 0.5) * 30))),
            "intimacy": max(20, min(95, int((100 - cold) * 0.55 + symmetry * 4))),
            "commitment": max(15, min(90, int(symmetry * 7 + min(goodnight.get("their_goodnight", 0), 10)))),
            "love_type": "需结合原文确认",
        },
        "gottman": {
            "positive_negative_ratio": round(max(0.5, min(9.9, (100 - cold) / 12)), 1),
            "horsemen_detected": [],
            "risk_level": "低危" if cold < 45 else ("中危" if cold < 70 else "高危"),
            "repair_attempts": {
                "who_initiates": "unknown",
                "method": "启发式模式未做冲突片段抽取",
                "partner_response": "需配置模型或人工查看原文",
                "success_rate": "未知",
            },
        },
        "personality": {
            "user_attachment": "需要全文判断",
            "partner_attachment": "需要全文判断",
            "pursue_distance_cycle": simp > loved + 20,
            "user_communication": "统计显示你在主动维系上更明显" if simp >= loved else "互动投入相对均衡",
            "partner_communication": "统计显示对方回应质量需要结合上下文判断",
            "user_love_language": "待分析",
            "partner_love_language": "待分析",
            "love_language_mismatch": False,
        },
        "personality_portrait": {
            "user": {
                "core_traits": ["主动维系", "需要确定性"],
                "defense_mechanisms": [],
                "core_needs": "关系确认、稳定回应和可持续互动。",
                "needs_behavior_map": [],
                "trust_architecture": "基于统计结果，你更需要关系保持连续，不适合长期悬空。",
                "big_five_sketch": {},
            },
            "partner": {
                "core_traits": ["需结合原文判断"],
                "defense_mechanisms": [],
                "core_needs": "需结合原文判断。",
                "needs_behavior_map": [],
                "trust_architecture": "需结合原文判断。",
                "big_five_sketch": {},
            },
        },
        "language_patterns": {
            "pronoun_we_ratio": f"「我们」次数：你 {linguistic.get('pronoun_we_count', {}).get('me', 0)}，对方 {linguistic.get('pronoun_we_count', {}).get('them', 0)}。",
            "hedging_density": "需结合原文判断",
            "future_orientation": "需结合原文判断",
            "emotional_valence_ratio": "基于词表统计，详细语义需要模型分析。",
            "conditional_density": "需结合原文判断",
            "key_linguistic_finding": "当前为本地启发式结果，适合先生成报告框架。",
        },
        "danger_warnings": danger_warnings,
        "strategist": {
            "core_problem": relationship_label,
            "stop_doing": [{"action": "停止只看单条消息下结论", "reason": "关系判断应看长期主动性、回应质量和冲突修复。", "quote": ""}],
            "start_doing": [{"action": "用稳定行动验证关系", "timing": "未来 2 到 4 周", "reason": "统计只能发现结构，行动才能验证对方投入。", "script": "我想把我们的节奏变得更稳定一点，你也愿意一起试试吗？"}],
            "roadmap": "先用统计报告定位互动结构，再补充模型或人工分析来判断关键原话和转折点。",
            "walkaway_point": {"timeframe": "连续 4 到 6 周", "trigger": "对方持续不回应、不主动、且拒绝任何现实沟通。", "reason": "长期单向投入会让关系变成消耗。"},
        },
        "key_findings": [
            {
                "title": "互动结构已完成本地统计",
                "quote": f"总消息 {basic.get('total_messages', 0)} 条；你 {basic.get('my_messages', 0)} 条，对方 {basic.get('their_messages', 0)} 条。",
                "analysis": "这是报告的事实底座。深层心理判断建议配置模型后生成。",
            }
        ],
        "verdict": relationship_label,
        "simp_description": f"主动指数 {simp}，越高说明你越主动维系。",
        "love_description": f"被爱指数 {loved}，越高说明对方主动和情绪投入越明显。",
    }


def build_llm_prompt(stats: dict[str, Any], contact: str, chat_history: str) -> str:
    schema_hint = summarize_stats(stats, contact)
    return f"""你是关系聊天记录分析助手。请基于统计数据和聊天记录片段，输出严格 JSON，不要 Markdown。

要求：
1. JSON 必须兼容下面 schema 示例中的键。
2. 所有强心理推断必须谨慎，并尽量引用聊天原话。
3. 如果证据不足，写“证据不足”，不要编造。
4. 如果发现严重单向投入、单相思痴迷或情感创伤绑定，danger_warnings 必须高亮。

schema 示例：
{json.dumps(schema_hint, ensure_ascii=False, indent=2)}

统计数据：
{json.dumps(stats, ensure_ascii=False, indent=2)}

聊天记录片段：
{chat_history}
"""


def parse_llm_json(content: str) -> dict[str, Any]:
    parsed = parse_jsonish(content)
    if not isinstance(parsed, dict):
        raise AppError("模型返回内容不是可解析 JSON", 502, content)
    return parsed


def call_llm(prompt: str) -> dict[str, Any]:
    provider = LLM_CONFIG.get("provider", "openai")
    if provider == "anthropic":
        return call_anthropic(prompt)
    if provider == "gemini":
        return call_gemini(prompt)
    return call_openai(prompt)


def call_openai(prompt: str) -> dict[str, Any]:
    base_url = LLM_CONFIG.get("base_url", PROVIDER_DEFAULTS["openai"]["base_url"]).rstrip("/")
    api_key = LLM_CONFIG.get("api_key", "")
    model = LLM_CONFIG.get("model", PROVIDER_DEFAULTS["openai"]["model"])
    if not api_key:
        raise AppError("未配置 API Key，已改用启发式分析。", 400)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你只输出可解析 JSON。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
    }
    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise AppError(f"模型服务返回错误: {exc.code}", 502, detail)
    except Exception as exc:
        raise AppError(f"模型调用失败: {exc}", 502)

    return parse_llm_json(body["choices"][0]["message"]["content"])


def call_anthropic(prompt: str) -> dict[str, Any]:
    base_url = LLM_CONFIG.get("base_url", PROVIDER_DEFAULTS["anthropic"]["base_url"]).rstrip("/")
    api_key = LLM_CONFIG.get("api_key", "")
    model = LLM_CONFIG.get("model", PROVIDER_DEFAULTS["anthropic"]["model"])
    if not api_key:
        raise AppError("未配置 API Key，已改用启发式分析。", 400)

    payload = {
        "model": model,
        "max_tokens": 4096,
        "temperature": 0.4,
        "messages": [{"role": "user", "content": prompt}],
    }
    req = urllib.request.Request(
        f"{base_url}/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise AppError(f"Anthropic 服务返回错误: {exc.code}", 502, detail)
    except Exception as exc:
        raise AppError(f"Anthropic 调用失败: {exc}", 502)

    content_blocks = body.get("content", [])
    text = "\n".join(block.get("text", "") for block in content_blocks if isinstance(block, dict))
    return parse_llm_json(text)


def call_gemini(prompt: str) -> dict[str, Any]:
    base_url = LLM_CONFIG.get("base_url", PROVIDER_DEFAULTS["gemini"]["base_url"]).rstrip("/")
    api_key = LLM_CONFIG.get("api_key", "")
    model = LLM_CONFIG.get("model", PROVIDER_DEFAULTS["gemini"]["model"])
    if not api_key:
        raise AppError("未配置 API Key，已改用启发式分析。", 400)

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.4},
    }
    url = f"{base_url}/models/{model}:generateContent?key={api_key}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise AppError(f"Gemini 服务返回错误: {exc.code}", 502, detail)
    except Exception as exc:
        raise AppError(f"Gemini 调用失败: {exc}", 502)

    candidates = body.get("candidates", [])
    parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
    text = "\n".join(part.get("text", "") for part in parts if isinstance(part, dict))
    return parse_llm_json(text)


def make_analysis(use_llm: bool) -> dict[str, Any]:
    stats = read_json(DATA_ROOT / "stats.json")
    contact = get_contact_name()
    if use_llm:
        chat_path = DATA_ROOT / "chat_history.txt"
        chat = chat_path.read_text(encoding="utf-8", errors="replace") if chat_path.exists() else ""
        max_chars = int(os.environ.get("SHE_LOVE_ME_MAX_CHAT_CHARS", "200000"))
        if len(chat) > max_chars:
            half = max_chars // 2
            chat = chat[:half] + "\n\n...[中间聊天记录已截断]...\n\n" + chat[-half:]
        analysis = call_llm(build_llm_prompt(stats, contact, chat))
        analysis["_analysis_mode"] = "llm"
    else:
        analysis = summarize_stats(stats, contact)
        analysis["_analysis_mode"] = "heuristic"
    (DATA_ROOT / "analysis.json").write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
    return analysis


def safe_report_name(name: str) -> bool:
    return bool(re.fullmatch(r"[\w\u4e00-\u9fff .\-()（）]+\.html", name))


class Handler(BaseHTTPRequestHandler):
    server_version = "SheLoveMeWeb/1.0"

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        try:
            if self.path == "/api/status":
                self.send_json(build_status())
                return
            if self.path.startswith("/reports/"):
                name = urllib.request.url2pathname(self.path[len("/reports/"):])
                if not safe_report_name(name):
                    raise AppError("非法报告路径", 400)
                self.send_file(REPORTS_ROOT / name)
                return
            path = self.path.split("?", 1)[0]
            if path == "/":
                path = "/index.html"
            self.send_file(WEB_ROOT / path.lstrip("/"))
        except AppError as exc:
            self.send_json({"error": str(exc), "details": exc.details}, exc.status)
        except Exception:
            self.send_json({"error": "服务器内部错误", "details": traceback.format_exc()}, 500)

    def do_POST(self) -> None:
        try:
            body = self.read_body()
            if self.path == "/api/setup":
                result = run_script("setup_check.py", ["--ensure-decryptor"], timeout=1200)
                self.send_json({"ok": True, "result": result, "status": build_status()})
                return
            if self.path == "/api/config":
                config = update_llm_config(body)
                self.send_json({"ok": True, "config": config, "status": build_status()})
                return
            if self.path == "/api/decrypt":
                result = run_script("decrypt_wechat.py", [], timeout=2400)
                self.send_json({"ok": True, "result": result, "status": build_status()})
                return
            if self.path == "/api/discover":
                self.send_json({"ok": True, **discover_wechat()})
                return
            if self.path == "/api/contacts":
                result = run_script("list_contacts.py", ["--decrypted-dir", str(DECRYPTED_ROOT)], timeout=900)
                self.send_json({"ok": True, "contacts": result["json"] or [], "result": result})
                return
            if self.path == "/api/extract":
                contact = str(body.get("contact", "")).strip()
                if not contact:
                    raise AppError("请选择联系人")
                result = run_script("extract_messages.py", [
                    "--decrypted-dir", str(DECRYPTED_ROOT),
                    "--contact", contact,
                    "--output", str(DATA_ROOT / "messages.json"),
                ], timeout=1200)
                self.send_json({"ok": True, "result": result, "messages": read_json(DATA_ROOT / "messages.json")})
                return
            if self.path == "/api/stats":
                result = run_script("stats_analyzer.py", [
                    "--input", str(DATA_ROOT / "messages.json"),
                    "--output", str(DATA_ROOT / "stats.json"),
                ], timeout=1200)
                self.send_json({"ok": True, "result": result, "stats": read_json(DATA_ROOT / "stats.json")})
                return
            if self.path == "/api/analyze":
                analysis = make_analysis(bool(body.get("use_llm")))
                self.send_json({"ok": True, "analysis": analysis, "status": build_status()})
                return
            if self.path == "/api/report":
                contact = get_contact_name()
                result = run_script("generate_html_report.py", [
                    "--stats", str(DATA_ROOT / "stats.json"),
                    "--analysis", str(DATA_ROOT / "analysis.json"),
                    "--contact", contact,
                    "--output", str(REPORTS_ROOT),
                ], timeout=900)
                report_path = Path((result.get("json") or {}).get("path", ""))
                report = {"path": str(report_path), "name": report_path.name, "url": f"/reports/{report_path.name}"}
                archive = create_archive(report_path) if report_path.exists() else None
                self.send_json({"ok": True, "result": result, "report": report, "archive": archive, "status": build_status()})
                return
            raise AppError("未知接口", 404)
        except AppError as exc:
            self.send_json({"error": str(exc), "details": exc.details}, exc.status)
        except subprocess.TimeoutExpired as exc:
            self.send_json({"error": "命令执行超时", "details": str(exc)}, 504)
        except Exception:
            self.send_json({"error": "服务器内部错误", "details": traceback.format_exc()}, 500)

    def read_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if not length:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw) if raw else {}

    def send_json(self, payload: Any, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_file(self, path: Path) -> None:
        path = path.resolve()
        allowed_roots = (WEB_ROOT.resolve(), REPORTS_ROOT.resolve())
        if not any(str(path).startswith(str(root)) for root in allowed_roots):
            raise AppError("非法文件路径", 403)
        if not path.exists() or not path.is_file():
            raise AppError("文件不存在", 404)
        content = path.read_bytes()
        mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        if path.suffix == ".js":
            mime = "text/javascript"
        self.send_response(200)
        self.send_cors_headers()
        self.send_header("Content-Type", f"{mime}; charset=utf-8" if mime.startswith("text/") else mime)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, fmt: str, *args: Any) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{stamp}] {self.address_string()} {fmt % args}")


def main() -> None:
    ensure_dirs()
    print(f"Runtime: {RUNTIME_ROOT}")
    print(f"Open: http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
