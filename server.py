from __future__ import annotations

import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import threading
import traceback
import urllib.error
import urllib.parse
import urllib.request
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional


PROJECT_ROOT = Path(__file__).resolve().parent
WEB_ROOT = PROJECT_ROOT / "web"
RUNTIME_ROOT = Path(os.environ.get("SHE_LOVE_ME_RUNTIME", PROJECT_ROOT / "runtime" / "she-love-me")).resolve()
SCRIPTS_ROOT = RUNTIME_ROOT / "scripts"
DATA_ROOT = RUNTIME_ROOT / "data"
REPORTS_ROOT = RUNTIME_ROOT / "reports"
ARCHIVES_ROOT = RUNTIME_ROOT / "archives"
DECRYPTED_ROOT = RUNTIME_ROOT / "vendor" / "wechat-decrypt" / "decrypted"
LOCAL_CONFIG_ROOT = Path(os.environ.get(
    "SHE_LOVE_ME_CONFIG_DIR",
    Path(os.environ.get("LOCALAPPDATA", PROJECT_ROOT / ".local")) / "TAHuiwole",
)).resolve()
LOCAL_CONFIG_FILE = LOCAL_CONFIG_ROOT / "config.json"

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
LLM_HTTP_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "TA-Huiwole/1.0 (Windows; local web app)",
}
DEFAULT_MAX_CHAT_CHARS = int(os.environ.get("SHE_LOVE_ME_MAX_CHAT_CHARS", "60000"))
RETRY_MAX_CHAT_CHARS = int(os.environ.get("SHE_LOVE_ME_RETRY_CHAT_CHARS", "24000"))
# 默认需偏大：MiMo 等会把「思考」写在 reasoning_content，JSON 在后；过小会出现 finish_reason=length 且无法解析。
LLM_MAX_OUTPUT_TOKENS = int(os.environ.get("SHE_LOVE_ME_LLM_MAX_OUTPUT_TOKENS", "12288"))
DEFAULT_SEGMENT_TARGET_CHARS = int(os.environ.get("SHE_LOVE_ME_SEGMENT_TARGET_CHARS", "16000"))
DEFAULT_SEGMENT_HARD_CAP_CHARS = int(os.environ.get("SHE_LOVE_ME_SEGMENT_HARD_CAP_CHARS", "28000"))
DEFAULT_SEGMENT_MAX_SEGMENTS = int(os.environ.get("SHE_LOVE_ME_SEGMENT_MAX_SEGMENTS", "24"))

ANALYSIS_CONFIG: dict[str, Any] = {
    "max_chat_chars": DEFAULT_MAX_CHAT_CHARS,
    "retry_chat_chars": RETRY_MAX_CHAT_CHARS,
    "max_output_tokens": LLM_MAX_OUTPUT_TOKENS,
    "analysis_pipeline": os.environ.get("SHE_LOVE_ME_ANALYSIS_PIPELINE", "auto").strip().lower(),
    "segment_target_chars": DEFAULT_SEGMENT_TARGET_CHARS,
    "segment_hard_cap_chars": DEFAULT_SEGMENT_HARD_CAP_CHARS,
    "segment_max_segments": DEFAULT_SEGMENT_MAX_SEGMENTS,
}


def parse_int_config(payload: dict[str, Any], key: str, minimum: int, maximum: int, default: int) -> int:
    raw = payload.get(key, default)
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        raise AppError(f"{key} 必须是整数")
    if value < minimum or value > maximum:
        raise AppError(f"{key} 必须在 {minimum} 到 {maximum} 之间")
    return value


def get_max_chat_chars() -> int:
    raw = os.environ.get("SHE_LOVE_ME_MAX_CHAT_CHARS")
    if raw:
        try:
            return max(4000, min(int(raw), 200000))
        except ValueError:
            pass
    return max(4000, ANALYSIS_CONFIG.get("max_chat_chars", DEFAULT_MAX_CHAT_CHARS))


def get_retry_chat_chars() -> int:
    raw = os.environ.get("SHE_LOVE_ME_RETRY_CHAT_CHARS")
    if raw:
        try:
            return max(2000, min(int(raw), 120000))
        except ValueError:
            pass
    return max(2000, ANALYSIS_CONFIG.get("retry_chat_chars", RETRY_MAX_CHAT_CHARS))


def get_max_output_tokens() -> int:
    raw = os.environ.get("SHE_LOVE_ME_LLM_MAX_OUTPUT_TOKENS")
    if raw:
        try:
            return max(256, min(int(raw), 32768))
        except ValueError:
            pass
    return max(256, ANALYSIS_CONFIG.get("max_output_tokens", LLM_MAX_OUTPUT_TOKENS))


def get_analysis_pipeline() -> str:
    raw = os.environ.get("SHE_LOVE_ME_ANALYSIS_PIPELINE", "").strip().lower()
    if raw in ("auto", "single", "segmented"):
        return raw
    v = str(ANALYSIS_CONFIG.get("analysis_pipeline", "auto")).strip().lower()
    if v in ("auto", "single", "segmented"):
        return v
    return "auto"


def get_segment_target_chars() -> int:
    raw = os.environ.get("SHE_LOVE_ME_SEGMENT_TARGET_CHARS")
    if raw:
        try:
            return max(4000, min(int(raw), 80000))
        except ValueError:
            pass
    v = ANALYSIS_CONFIG.get("segment_target_chars", DEFAULT_SEGMENT_TARGET_CHARS)
    try:
        return max(4000, min(int(v), 80000))
    except (TypeError, ValueError):
        return DEFAULT_SEGMENT_TARGET_CHARS


def get_segment_hard_cap_chars() -> int:
    raw = os.environ.get("SHE_LOVE_ME_SEGMENT_HARD_CAP_CHARS")
    if raw:
        try:
            return max(8000, min(int(raw), 120000))
        except ValueError:
            pass
    v = ANALYSIS_CONFIG.get("segment_hard_cap_chars", DEFAULT_SEGMENT_HARD_CAP_CHARS)
    try:
        return max(8000, min(int(v), 120000))
    except (TypeError, ValueError):
        return DEFAULT_SEGMENT_HARD_CAP_CHARS


def get_segment_max_segments() -> int:
    raw = os.environ.get("SHE_LOVE_ME_SEGMENT_MAX_SEGMENTS")
    if raw:
        try:
            return max(1, min(int(raw), 48))
        except ValueError:
            pass
    v = ANALYSIS_CONFIG.get("segment_max_segments", DEFAULT_SEGMENT_MAX_SEGMENTS)
    try:
        return max(1, min(int(v), 48))
    except (TypeError, ValueError):
        return DEFAULT_SEGMENT_MAX_SEGMENTS


def llm_debug_enabled() -> bool:
    return os.environ.get("SHE_LOVE_ME_LLM_DEBUG", "").strip().lower() in ("1", "true", "yes", "on")


def llm_debug_line(msg: str) -> None:
    sys.stderr.write(f"[LLM-DEBUG] {msg}\n")
    sys.stderr.flush()


def llm_debug_dump_openai_request(url: str, model: str, attempt: int, use_json_object: bool, pl: dict[str, Any]) -> None:
    """完整 prompt 写入 data/，终端输出摘要（避免几万字刷屏）。"""
    try:
        DATA_ROOT.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    user_text = ""
    system_text = ""
    for m in pl.get("messages") or []:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        c = str(m.get("content") or "")
        if role == "user":
            user_text = c
        elif role == "system":
            system_text = c
    (DATA_ROOT / "last_llm_user_prompt.txt").write_text(user_text, encoding="utf-8")
    (DATA_ROOT / "last_llm_system_prompt.txt").write_text(system_text, encoding="utf-8")
    meta = {
        "url": url,
        "model": model,
        "attempt": attempt,
        "response_format_json_object": use_json_object,
        "temperature": pl.get("temperature"),
        "max_tokens": pl.get("max_tokens"),
        "user_prompt_chars": len(user_text),
        "system_prompt_chars": len(system_text),
        "request_json_approx_bytes": len(json.dumps(pl, ensure_ascii=False).encode("utf-8")),
    }
    (DATA_ROOT / "last_llm_request_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    llm_debug_line("========== LLM 请求（OpenAI 兼容）==========")
    llm_debug_line(f"POST {url}")
    llm_debug_line(f"model={model!r}  attempt={attempt}  response_format json_object={use_json_object}")
    llm_debug_line(f"user 消息 {len(user_text)} 字符 → {DATA_ROOT / 'last_llm_user_prompt.txt'}")
    llm_debug_line(f"system {len(system_text)} 字符 → {DATA_ROOT / 'last_llm_system_prompt.txt'}")
    llm_debug_line(f"meta → {DATA_ROOT / 'last_llm_request_meta.json'}")
    head = user_text[:1500].replace("\r", "")
    llm_debug_line("----- user 开头 1500 字符 -----")
    llm_debug_line(head)
    if len(user_text) > 1500:
        tail = user_text[-900:].replace("\r", "")
        llm_debug_line("----- user 结尾 900 字符 -----")
        llm_debug_line(tail)


def llm_debug_dump_openai_response(http_status: int, body: dict[str, Any]) -> None:
    try:
        DATA_ROOT.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    raw = json.dumps(body, ensure_ascii=False, indent=2)
    path = DATA_ROOT / "last_llm_response_body.json"
    path.write_text(raw, encoding="utf-8")
    llm_debug_line(f"HTTP {http_status}；响应 JSON {len(raw)} 字符 → {path}")
    ch0 = (body.get("choices") or [{}])[0] if isinstance(body.get("choices"), list) else {}
    fr = ch0.get("finish_reason") if isinstance(ch0, dict) else None
    msg = (ch0.get("message") if isinstance(ch0, dict) else None) or {}
    llm_debug_line(f"choices[0].finish_reason={fr!r}  message.keys={list(msg.keys()) if isinstance(msg, dict) else []}")
    if isinstance(msg, dict):
        for key in ("content", "reasoning_content", "reasoning", "thinking"):
            v = msg.get(key)
            if isinstance(v, str) and v.strip():
                llm_debug_line(f"message[{key}] len={len(v)} head={repr(v[:320])}")


DISCOVER_PROGRESS: list[str] = []
DISCOVER_PROGRESS_LOCK = threading.Lock()
MAX_DISCOVER_LINES = 800
DISCOVER_ACTIVE = False
DISCOVER_PHASE = ""
DISCOVER_STEP = 0
DISCOVER_STEP_TOTAL = 3

ANALYZE_PROGRESS_LOCK = threading.Lock()
ANALYZE_PROGRESS_LINES: list[str] = []
ANALYZE_PROGRESS_PHASE = ""
ANALYZE_PROGRESS_MAP_I = 0
ANALYZE_PROGRESS_MAP_N = 0
ANALYZE_PROGRESS_RUNNING = False


def clear_analyze_progress() -> None:
    global ANALYZE_PROGRESS_PHASE, ANALYZE_PROGRESS_MAP_I, ANALYZE_PROGRESS_MAP_N, ANALYZE_PROGRESS_RUNNING
    with ANALYZE_PROGRESS_LOCK:
        ANALYZE_PROGRESS_LINES.clear()
        ANALYZE_PROGRESS_PHASE = ""
        ANALYZE_PROGRESS_MAP_I = 0
        ANALYZE_PROGRESS_MAP_N = 0
        ANALYZE_PROGRESS_RUNNING = False


def append_analyze_line(text: str) -> None:
    stamp = datetime.now().strftime("%H:%M:%S")
    line = f"[{stamp}] {text}".strip()
    with ANALYZE_PROGRESS_LOCK:
        ANALYZE_PROGRESS_LINES.append(line)
        while len(ANALYZE_PROGRESS_LINES) > 400:
            ANALYZE_PROGRESS_LINES.pop(0)


def set_analyze_phase(phase: str, map_i: int = 0, map_n: int = 0) -> None:
    global ANALYZE_PROGRESS_PHASE, ANALYZE_PROGRESS_MAP_I, ANALYZE_PROGRESS_MAP_N
    with ANALYZE_PROGRESS_LOCK:
        ANALYZE_PROGRESS_PHASE = phase
        ANALYZE_PROGRESS_MAP_I = map_i
        ANALYZE_PROGRESS_MAP_N = map_n


def get_analyze_progress() -> dict[str, Any]:
    with ANALYZE_PROGRESS_LOCK:
        return {
            "running": ANALYZE_PROGRESS_RUNNING,
            "phase": ANALYZE_PROGRESS_PHASE,
            "map_index": ANALYZE_PROGRESS_MAP_I,
            "map_total": ANALYZE_PROGRESS_MAP_N,
            "lines": list(ANALYZE_PROGRESS_LINES),
        }


# 分析报告用语：本地启发式 vs 大模型无依据
LOCAL_ANALYSIS_LABEL = "本地化运行，未使用大模型"
LLM_NO_SOURCE_LABEL = "没有相关的原文，大模型无法判断"
LLM_SCHEMA_FILL_HINT = "（请根据聊天记录归纳结论；若无依据请填写：没有相关的原文，大模型无法判断）"


def clear_discover_progress() -> None:
    global DISCOVER_PHASE, DISCOVER_STEP
    with DISCOVER_PROGRESS_LOCK:
        DISCOVER_PROGRESS.clear()
        DISCOVER_PHASE = ""
        DISCOVER_STEP = 0


def set_discover_step(step: int) -> None:
    global DISCOVER_STEP
    with DISCOVER_PROGRESS_LOCK:
        DISCOVER_STEP = step


def set_discover_phase(phase: str) -> None:
    global DISCOVER_PHASE
    with DISCOVER_PROGRESS_LOCK:
        DISCOVER_PHASE = phase


def append_discover_line(text: str) -> None:
    stamp = datetime.now().strftime("%H:%M:%S")
    line = f"[{stamp}] {text}".strip()
    with DISCOVER_PROGRESS_LOCK:
        DISCOVER_PROGRESS.append(line)
        while len(DISCOVER_PROGRESS) > MAX_DISCOVER_LINES:
            DISCOVER_PROGRESS.pop(0)


def _parse_contact_progress(lines: list[str]) -> tuple[int | None, int | None]:
    """解析「联系人 x/X」；X 亦可来自「通讯录已载入 N 人」（尚未开始统计时显示 0/N）。"""
    pat_contact = re.compile(r"联系人\s*(\d+)/(\d+)")
    pat_roster = re.compile(r"通讯录已载入\s*(\d+)\s*人")
    cur = None
    tot = None
    roster_total = None
    for line in reversed(lines):
        m = pat_contact.search(line)
        if m:
            cur, tot = int(m.group(1)), int(m.group(2))
            break
    for line in lines:
        m = pat_roster.search(line)
        if m:
            roster_total = int(m.group(1))
            break
    if tot is None and roster_total is not None:
        tot = roster_total
    if cur is None and tot is not None:
        cur = 0
    return cur, tot


def get_discover_progress() -> dict[str, Any]:
    with DISCOVER_PROGRESS_LOCK:
        lines = list(DISCOVER_PROGRESS)
        c_cur, c_tot = _parse_contact_progress(lines)
        return {
            "running": DISCOVER_ACTIVE,
            "phase": DISCOVER_PHASE,
            "step": DISCOVER_STEP,
            "step_total": DISCOVER_STEP_TOTAL,
            "contact_current": c_cur,
            "contact_total": c_tot,
            "lines": lines,
        }


def load_local_config() -> None:
    if not LOCAL_CONFIG_FILE.exists():
        return
    try:
        data = json.loads(LOCAL_CONFIG_FILE.read_text(encoding="utf-8"))
        llm = data.get("llm", data) if isinstance(data, dict) else {}
        if not isinstance(llm, dict):
            return
        env_keys = {
            "provider": "SHE_LOVE_ME_LLM_PROVIDER",
            "base_url": "SHE_LOVE_ME_LLM_BASE_URL",
            "api_key": "SHE_LOVE_ME_LLM_API_KEY",
            "model": "SHE_LOVE_ME_LLM_MODEL",
        }
        for key, env_name in env_keys.items():
            value = str(llm.get(key, "")).strip()
            if value and not os.environ.get(env_name):
                LLM_CONFIG[key] = value
        if LLM_CONFIG.get("provider") not in PROVIDER_DEFAULTS:
            LLM_CONFIG["provider"] = "openai"
        limits = data.get("analysis", {}) if isinstance(data, dict) else {}
        if isinstance(limits, dict):
            if not os.environ.get("SHE_LOVE_ME_MAX_CHAT_CHARS"):
                ANALYSIS_CONFIG["max_chat_chars"] = parse_int_config(
                    limits, "max_chat_chars", 4000, 200000, DEFAULT_MAX_CHAT_CHARS
                )
            if not os.environ.get("SHE_LOVE_ME_RETRY_CHAT_CHARS"):
                ANALYSIS_CONFIG["retry_chat_chars"] = parse_int_config(
                    limits, "retry_chat_chars", 2000, 120000, RETRY_MAX_CHAT_CHARS
                )
            if not os.environ.get("SHE_LOVE_ME_LLM_MAX_OUTPUT_TOKENS"):
                ANALYSIS_CONFIG["max_output_tokens"] = parse_int_config(
                    limits, "max_output_tokens", 256, 32768, LLM_MAX_OUTPUT_TOKENS
                )
            if not os.environ.get("SHE_LOVE_ME_ANALYSIS_PIPELINE"):
                ap = str(limits.get("analysis_pipeline", "") or "").strip().lower()
                if ap in ("auto", "single", "segmented"):
                    ANALYSIS_CONFIG["analysis_pipeline"] = ap
            if not os.environ.get("SHE_LOVE_ME_SEGMENT_TARGET_CHARS"):
                ANALYSIS_CONFIG["segment_target_chars"] = parse_int_config(
                    limits, "segment_target_chars", 4000, 80000, DEFAULT_SEGMENT_TARGET_CHARS
                )
            if not os.environ.get("SHE_LOVE_ME_SEGMENT_HARD_CAP_CHARS"):
                ANALYSIS_CONFIG["segment_hard_cap_chars"] = parse_int_config(
                    limits, "segment_hard_cap_chars", 8000, 120000, DEFAULT_SEGMENT_HARD_CAP_CHARS
                )
            if not os.environ.get("SHE_LOVE_ME_SEGMENT_MAX_SEGMENTS"):
                ANALYSIS_CONFIG["segment_max_segments"] = parse_int_config(
                    limits, "segment_max_segments", 1, 48, DEFAULT_SEGMENT_MAX_SEGMENTS
                )
    except Exception:
        return


def save_local_config() -> None:
    LOCAL_CONFIG_ROOT.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "llm": {
            "provider": LLM_CONFIG.get("provider", "openai"),
            "base_url": LLM_CONFIG.get("base_url", ""),
            "model": LLM_CONFIG.get("model", ""),
            "api_key": LLM_CONFIG.get("api_key", ""),
        },
        "analysis": {
            "max_chat_chars": get_max_chat_chars(),
            "retry_chat_chars": get_retry_chat_chars(),
            "max_output_tokens": get_max_output_tokens(),
            "analysis_pipeline": get_analysis_pipeline(),
            "segment_target_chars": get_segment_target_chars(),
            "segment_hard_cap_chars": get_segment_hard_cap_chars(),
            "segment_max_segments": get_segment_max_segments(),
        },
    }
    temp_path = LOCAL_CONFIG_FILE.with_suffix(".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(temp_path, 0o600)
    except OSError:
        pass
    temp_path.replace(LOCAL_CONFIG_FILE)


load_local_config()


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


def run_script_streaming(name: str, args: list[str], timeout: int = 900, step: str = "") -> dict[str, Any]:
    """流式执行脚本：将 stdout/stderr 按行写入 DISCOVER_PROGRESS；返回结果与 run_script 相同。"""
    ensure_dirs()
    cmd = [sys.executable, "-u", str(script_path(name)), *args]
    prefix = step.strip()
    if prefix:
        prefix = prefix + " "
    stdout_buf: list[str] = []
    stderr_buf: list[str] = []

    proc = subprocess.Popen(
        cmd,
        cwd=str(RUNTIME_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    def pump(stream: Any, bucket: list[str], stderr_line: bool) -> None:
        try:
            for line in iter(stream.readline, ""):
                bucket.append(line)
                body = line.rstrip()
                if stderr_line:
                    append_discover_line(f"{prefix}‖ {body}")
                else:
                    append_discover_line(f"{prefix}{body}")
        finally:
            stream.close()

    t_out = threading.Thread(target=pump, args=(proc.stdout, stdout_buf, False))
    t_err = threading.Thread(target=pump, args=(proc.stderr, stderr_buf, True))
    t_out.start()
    t_err.start()
    try:
        rc = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=8)
        except Exception:
            pass
        t_out.join(timeout=5)
        t_err.join(timeout=5)
        raise AppError(f"{name} 执行超时（{timeout} 秒）", 504)
    t_out.join(timeout=120)
    t_err.join(timeout=120)
    stdout = "".join(stdout_buf)
    stderr = "".join(stderr_buf)
    payload = parse_jsonish(stdout)
    result = {
        "command": [Path(cmd[0]).name, name, *args],
        "returncode": rc,
        "stdout": stdout,
        "stderr": stderr,
        "json": payload,
    }
    if rc != 0:
        message = ""
        if isinstance(payload, dict):
            message = str(payload.get("error") or payload.get("message") or "")
        raise AppError(message or stderr.strip() or stdout.strip() or f"{name} 执行失败", 500, result)
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


def normalize_llm_json_text(content: str) -> str:
    """去掉 Markdown ```json 围栏，以及首个 `{` 之前的开场白/思维链段落。"""
    text = (content or "").strip()
    if not text:
        return ""
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE | re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    # 模型常在 JSON 前输出推理或说明：从第一个 `{` 起截取（parse_llm_json 仍会做括号配对兜底）
    brace_at = text.find("{")
    if brace_at > 0:
        text = text[brace_at:]
    return text.strip()


def extract_json_object_by_brace(text: str) -> str | None:
    """从首个「顶层」{ 起截取到匹配的 }，避免正文里夹杂说明文字。"""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if esc:
            esc = False
            continue
        if in_str:
            if ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
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


def delete_archive(archive_id: str, report_name: str = "") -> dict[str, Any]:
    ensure_dirs()
    archive_id = str(archive_id or "").strip()
    report_name = str(report_name or "").strip()
    if archive_id and not re.fullmatch(r"[\w\u4e00-\u9fff\-]+", archive_id):
        raise AppError("非法档案 ID", 400)
    if report_name and not safe_report_name(report_name):
        raise AppError("非法报告文件名", 400)

    deleted: list[str] = []
    archive_dir = (ARCHIVES_ROOT / archive_id).resolve() if archive_id else None
    report_to_delete = report_name

    if archive_dir and str(archive_dir).startswith(str(ARCHIVES_ROOT.resolve())) and archive_dir.exists():
        meta_path = archive_dir / "metadata.json"
        if meta_path.exists():
            try:
                metadata = read_json(meta_path)
                report_to_delete = report_to_delete or str(metadata.get("report_name") or "")
            except Exception:
                pass
        shutil.rmtree(archive_dir)
        deleted.append(f"archive:{archive_id}")

    if not report_to_delete and archive_id:
        candidate = f"{archive_id}.html"
        if safe_report_name(candidate):
            report_to_delete = candidate

    if report_to_delete:
        report_path = (REPORTS_ROOT / report_to_delete).resolve()
        if str(report_path).startswith(str(REPORTS_ROOT.resolve())) and report_path.exists():
            report_path.unlink()
            deleted.append(f"report:{report_to_delete}")

    if not deleted:
        raise AppError("没有找到要删除的档案", 404)
    return {"deleted": deleted, "status": build_status()}


def get_contact_name() -> str:
    messages_path = DATA_ROOT / "messages.json"
    if messages_path.exists():
        try:
            data = read_json(messages_path)
            return data.get("contact_display") or data.get("contact_username") or "对方"
        except Exception:
            pass
    return "对方"


def build_daily_counts_from_messages() -> dict[str, Any]:
    messages_path = DATA_ROOT / "messages.json"
    if not messages_path.exists():
        raise AppError("请先选择联系人并提取聊天记录", 400)
    data = read_json(messages_path)
    messages = data.get("messages") if isinstance(data, dict) else None
    if not isinstance(messages, list):
        raise AppError("messages.json 格式异常", 500)
    daily: dict[str, int] = {}
    total = 0
    for m in messages:
        if not isinstance(m, dict):
            continue
        sender = m.get("sender")
        if sender not in ("me", "them"):
            continue
        ts = m.get("timestamp")
        if not isinstance(ts, (int, float)):
            continue
        day = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        daily[day] = daily.get(day, 0) + 1
        total += 1
    rows = [{"date": k, "count": v} for k, v in sorted(daily.items())]
    return {
        "contact": data.get("contact_display") or data.get("contact_username") or "对方",
        "contact_username": data.get("contact_username") or "",
        "total": total,
        "min_date": rows[0]["date"] if rows else "",
        "max_date": rows[-1]["date"] if rows else "",
        "daily": rows,
    }


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
        "llm_config_path": str(LOCAL_CONFIG_FILE),
        "llm_config_persisted": LOCAL_CONFIG_FILE.exists(),
        "analysis_limits": {
            "max_chat_chars": get_max_chat_chars(),
            "retry_chat_chars": get_retry_chat_chars(),
            "max_output_tokens": get_max_output_tokens(),
            "analysis_pipeline": get_analysis_pipeline(),
            "segment_target_chars": get_segment_target_chars(),
            "segment_hard_cap_chars": get_segment_hard_cap_chars(),
            "segment_max_segments": get_segment_max_segments(),
        },
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
    limits = payload.get("analysis", {}) if isinstance(payload.get("analysis"), dict) else payload
    ANALYSIS_CONFIG["max_chat_chars"] = parse_int_config(
        limits, "max_chat_chars", 4000, 200000, get_max_chat_chars()
    )
    ANALYSIS_CONFIG["retry_chat_chars"] = parse_int_config(
        limits, "retry_chat_chars", 2000, 120000, get_retry_chat_chars()
    )
    ANALYSIS_CONFIG["max_output_tokens"] = parse_int_config(
        limits, "max_output_tokens", 256, 32768, get_max_output_tokens()
    )
    ap = str(limits.get("analysis_pipeline", get_analysis_pipeline()) or "").strip().lower()
    if ap not in ("auto", "single", "segmented"):
        raise AppError("分析模式只支持 auto、single、segmented")
    ANALYSIS_CONFIG["analysis_pipeline"] = ap
    ANALYSIS_CONFIG["segment_target_chars"] = parse_int_config(
        limits, "segment_target_chars", 4000, 80000, get_segment_target_chars()
    )
    ANALYSIS_CONFIG["segment_hard_cap_chars"] = parse_int_config(
        limits, "segment_hard_cap_chars", 8000, 120000, get_segment_hard_cap_chars()
    )
    if ANALYSIS_CONFIG["segment_hard_cap_chars"] < ANALYSIS_CONFIG["segment_target_chars"]:
        raise AppError("分段硬上限不能小于分段目标长度")
    ANALYSIS_CONFIG["segment_max_segments"] = parse_int_config(
        limits, "segment_max_segments", 1, 48, get_segment_max_segments()
    )
    save_local_config()

    return {
        "provider": LLM_CONFIG.get("provider", "openai"),
        "base_url": LLM_CONFIG.get("base_url", ""),
        "model": LLM_CONFIG.get("model", ""),
        "key_hint": build_status()["llm_key_hint"],
        "analysis_limits": build_status()["analysis_limits"],
    }


def normalize_llm_payload(payload: dict[str, Any], persist: bool = False) -> dict[str, str]:
    old_provider = LLM_CONFIG.get("provider", "openai")
    provider = str(payload.get("provider", LLM_CONFIG.get("provider", "openai"))).strip().lower()
    if provider not in PROVIDER_DEFAULTS:
        raise AppError("接口模式只支持 openai、anthropic、gemini")
    base_url = str(payload.get("base_url", "")).strip().rstrip("/")
    model = str(payload.get("model", "")).strip()
    api_key = str(payload.get("api_key", "")).strip() or LLM_CONFIG.get("api_key", "")

    provider_changed = provider != old_provider
    if not base_url:
        base_url = PROVIDER_DEFAULTS[provider]["base_url"] if provider_changed or not LLM_CONFIG.get("base_url") else LLM_CONFIG.get("base_url", "")
    if not re.match(r"^https?://", base_url):
        raise AppError("BaseURL 必须以 http:// 或 https:// 开头")
    if not model:
        model = PROVIDER_DEFAULTS[provider]["model"] if provider_changed or not LLM_CONFIG.get("model") else LLM_CONFIG.get("model", "")
    if not api_key:
        raise AppError("未配置 API Key")

    config = {"provider": provider, "base_url": base_url, "model": model, "api_key": api_key}
    if persist:
        LLM_CONFIG.update(config)
        save_local_config()
    return config


def build_llm_endpoint(provider: str, base_url: str, model: str) -> str:
    base = base_url.rstrip("/")
    if provider == "anthropic":
        return f"{base}/messages"
    if provider == "gemini":
        return f"{base}/models/{urllib.parse.quote(model, safe='')}:generateContent?key=***"
    return f"{base}/chat/completions"


def test_llm_connection(payload: dict[str, Any]) -> dict[str, Any]:
    config = normalize_llm_payload(payload)
    provider = config["provider"]
    base_url = config["base_url"]
    model = config["model"]
    api_key = config["api_key"]
    endpoint = build_llm_endpoint(provider, base_url, model)
    prompt = "Reply with OK only."

    if provider == "anthropic":
        req = urllib.request.Request(
            endpoint,
            data=json.dumps({
                "model": model,
                "max_tokens": 8,
                "temperature": 0,
                "messages": [{"role": "user", "content": prompt}],
            }).encode("utf-8"),
            headers={
                **LLM_HTTP_HEADERS,
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            method="POST",
        )
    elif provider == "gemini":
        req = urllib.request.Request(
            endpoint.replace("***", urllib.parse.quote(api_key, safe="")),
            data=json.dumps({
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0, "maxOutputTokens": 8},
            }).encode("utf-8"),
            headers={**LLM_HTTP_HEADERS, "Content-Type": "application/json"},
            method="POST",
        )
    else:
        req = urllib.request.Request(
            endpoint,
            data=json.dumps({
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "max_tokens": 8,
            }).encode("utf-8"),
            headers={
                **LLM_HTTP_HEADERS,
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return {
                "ok": True,
                "provider": provider,
                "model": model,
                "endpoint": endpoint,
                "status": resp.status,
                "latency_ms": int((time.time() - started) * 1000),
                "preview": raw[:220],
            }
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise AppError(f"连通性测试失败：HTTP {exc.code}", 502, {
            "provider": provider,
            "model": model,
            "endpoint": endpoint,
            "detail": detail,
        })
    except Exception as exc:
        raise AppError(f"连通性测试失败：{exc}", 502, {
            "provider": provider,
            "model": model,
            "endpoint": endpoint,
        })


def discover_wechat() -> dict[str, Any]:
    global DISCOVER_ACTIVE
    clear_discover_progress()
    DISCOVER_ACTIVE = True
    append_discover_line("开始：1/3 环境检查 → 2/3 解密数据库 → 3/3 扫描联系人")
    try:
        try:
            set_discover_step(1)
            set_discover_phase("1/3 环境检查")
            setup = run_script_streaming(
                "setup_check.py",
                ["--ensure-decryptor"],
                timeout=1200,
                step="[1/3]",
            )
        except AppError as exc:
            raise AppError(f"环境检查失败：{exc}", exc.status, exc.details) from exc
        try:
            set_discover_step(2)
            set_discover_phase("2/3 解密数据库（耗时取决于聊天记录体量）")
            decrypt = run_script_streaming("decrypt_wechat.py", [], timeout=2400, step="[2/3]")
        except AppError as exc:
            raise AppError(
                f"解密失败（多为管理员权限、微信未登录或微信版本与 wechat-decrypt 不兼容）：{exc}",
                exc.status,
                exc.details,
            ) from exc
        try:
            set_discover_step(3)
            set_discover_phase("3/3 扫描联系人并统计消息数")
            contacts = run_script_streaming(
                "list_contacts.py",
                ["--decrypted-dir", str(DECRYPTED_ROOT)],
                timeout=900,
                step="[3/3]",
            )
        except AppError as exc:
            raise AppError(f"读取联系人失败：{exc}", exc.status, exc.details) from exc
        n = len(contacts.get("json") or [])
        append_discover_line(f"完成：已生成 {n} 个有消息的联系人条目（按消息数排序）")
        return {
            "setup": setup,
            "decrypt": decrypt,
            "contacts": contacts.get("json") or [],
            "status": build_status(),
        }
    finally:
        DISCOVER_ACTIVE = False
        set_discover_phase("")
        set_discover_step(0)


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
            "conflict_pattern": f"当前为{LOCAL_ANALYSIS_LABEL}；冲突模式需结合具体聊天原文。统计侧主要依据主动性、回复速度、冷淡回复和连续发送结构。",
            "power_dynamics": f"对话发起：你 {initiative.get('my_starts', 0)} 次，对方 {initiative.get('their_starts', 0)} 次。",
            "key_turning_point": {"date": "未定位", "event": "启发式模式未扫描全文转折点。"},
        },
        "sternberg": {
            "passion": max(20, min(95, int(loved * 0.7 + linguistic.get("positive_ratio", {}).get("them", 0.5) * 30))),
            "intimacy": max(20, min(95, int((100 - cold) * 0.55 + symmetry * 4))),
            "commitment": max(15, min(90, int(symmetry * 7 + min(goodnight.get("their_goodnight", 0), 10)))),
            "love_type": LOCAL_ANALYSIS_LABEL,
        },
        "gottman": {
            "positive_negative_ratio": round(max(0.5, min(9.9, (100 - cold) / 12)), 1),
            "horsemen_detected": [],
            "risk_level": "低危" if cold < 45 else ("中危" if cold < 70 else "高危"),
            "repair_attempts": {
                "who_initiates": "unknown",
                "method": "启发式模式未做冲突片段抽取",
                "partner_response": LOCAL_ANALYSIS_LABEL,
                "success_rate": "未知",
            },
        },
        "personality": {
            "user_attachment": LOCAL_ANALYSIS_LABEL,
            "partner_attachment": LOCAL_ANALYSIS_LABEL,
            "pursue_distance_cycle": simp > loved + 20,
            "user_communication": "统计显示你在主动维系上更明显" if simp >= loved else "互动投入相对均衡",
            "partner_communication": "统计显示对方回应质量需要结合上下文判断",
            "user_love_language": LOCAL_ANALYSIS_LABEL,
            "partner_love_language": LOCAL_ANALYSIS_LABEL,
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
                "core_traits": [LOCAL_ANALYSIS_LABEL],
                "defense_mechanisms": [],
                "core_needs": LOCAL_ANALYSIS_LABEL,
                "needs_behavior_map": [],
                "trust_architecture": LOCAL_ANALYSIS_LABEL,
                "big_five_sketch": {},
            },
        },
        "language_patterns": {
            "pronoun_we_ratio": f"「我们」次数：你 {linguistic.get('pronoun_we_count', {}).get('me', 0)}，对方 {linguistic.get('pronoun_we_count', {}).get('them', 0)}。",
            "hedging_density": LOCAL_ANALYSIS_LABEL,
            "future_orientation": LOCAL_ANALYSIS_LABEL,
            "emotional_valence_ratio": f"基于词表统计正负倾向；语义层面的细腻判断：{LOCAL_ANALYSIS_LABEL}。",
            "conditional_density": LOCAL_ANALYSIS_LABEL,
            "key_linguistic_finding": f"{LOCAL_ANALYSIS_LABEL}（以下为基于统计生成的报告框架）。",
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


def scrub_schema_for_llm_prompt(obj: Any) -> Any:
    """将本地占位文案换成中性提示，避免模型在 JSON 中照抄「本地化运行…」。"""
    if isinstance(obj, dict):
        return {k: scrub_schema_for_llm_prompt(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [scrub_schema_for_llm_prompt(x) for x in obj]
    if isinstance(obj, str):
        if obj == LOCAL_ANALYSIS_LABEL or LOCAL_ANALYSIS_LABEL in obj:
            return LLM_SCHEMA_FILL_HINT
        if "需结合原文" in obj or "需要全文判断" in obj or "需配置模型" in obj:
            return LLM_SCHEMA_FILL_HINT
        if "基于词表统计" in obj and "未使用大模型" in obj:
            return "（可引用下方统计数据中的词表结果；语义归纳无依据时填写：没有相关的原文，大模型无法判断）"
    return obj


def normalize_llm_legacy_phrases(obj: Any) -> Any:
    """大模型若仍照抄旧占位句，统一为「没有相关的原文，大模型无法判断」。"""
    if isinstance(obj, dict):
        return {k: normalize_llm_legacy_phrases(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [normalize_llm_legacy_phrases(x) for x in obj]
    if isinstance(obj, str):
        s = obj
        for old in (
            "需结合原文判断",
            "需结合原文确认",
            "需要全文判断",
            "需要结合聊天原文判断。",
        ):
            if old in s:
                s = s.replace(old, LLM_NO_SOURCE_LABEL)
        if s.strip() == "需结合原文判断" or s.strip() == "需结合原文判断。":
            s = LLM_NO_SOURCE_LABEL
        return s
    return obj


def build_llm_prompt(stats: dict[str, Any], contact: str, chat_history: str) -> str:
    schema_hint = scrub_schema_for_llm_prompt(summarize_stats(stats, contact))
    return f"""【场景说明】文本为用户在其本人设备上导出的即时通讯节选，用于个人沟通模式的统计学与社会语言学自省分析；请从中性、合规视角完成任务。

你是关系聊天记录分析助手。请基于统计数据和聊天记录片段，输出严格 JSON，不要 Markdown。

要求：
1. 只输出一个顶层 JSON 对象：不要用 ``` 代码围栏，不要写前言/后记说明。
2. JSON 必须兼容下面 schema 示例中的键；schema 中的括号提示仅说明填写规则，不要原样输出提示句。
3. language_patterns 下各字段：优先根据「聊天记录片段」做简短归纳（可引用片段中的短句）；同一字段不要与其它字段重复粘贴同一句固定文案。仅当该维度在片段中完全找不到任何可引用线索时，该字段才填写「{LLM_NO_SOURCE_LABEL}」。请不要对多个子项机械地全部填写该固定句。
4. 所有强心理推断必须谨慎，并尽量引用聊天原话。
5. 若其它条目证据不足可写「证据不足」，不要编造。
6. 如果发现严重单向投入、单相思痴迷或情感创伤绑定，danger_warnings 必须高亮。

schema 示例：
{json.dumps(schema_hint, ensure_ascii=False, indent=2)}

统计数据：
{json.dumps(stats, ensure_ascii=False, indent=2)}

聊天记录片段：
{chat_history}
"""


def truncate_chat_history(chat: str, max_chars: int) -> str:
    chat = chat or ""
    if len(chat) <= max_chars:
        return chat
    head = max_chars // 3
    tail = max_chars - head
    return chat[:head] + "\n\n...[中间聊天记录已截断，保留开头与最近互动]...\n\n" + chat[-tail:]


def _split_oversized_segment(text: str, hard_cap: int) -> list[str]:
    if len(text) <= hard_cap:
        return [text] if text else []
    lines = text.splitlines() or [text]
    out: list[str] = []
    buf: list[str] = []
    acc = 0
    sub_target = max(2000, hard_cap // 2)
    for line in lines:
        add = len(line) + (1 if buf else 0)
        if buf and acc + add > sub_target:
            out.append("\n".join(buf))
            buf = [line]
            acc = len(line)
        else:
            buf.append(line)
            acc += add
    if buf:
        out.append("\n".join(buf))
    if not out:
        return [text[:hard_cap]]
    fixed: list[str] = []
    for seg in out:
        if len(seg) > hard_cap:
            fixed.extend(_split_oversized_segment(seg, hard_cap))
        else:
            fixed.append(seg)
    return fixed


def chunk_chat_for_segments(raw: str, target: int, hard: int, max_seg: int) -> list[str]:
    """将完整 chat_history 切成多段，每段约 target 字符、单段不超过 hard，总段数不超过 max_seg。"""
    chat = (raw or "").strip()
    if not chat:
        return []
    t = max(4000, min(target, 80000))
    h = max(t, min(hard, 120000))
    for _ in range(16):
        parts = _chunk_chat_text_once(chat, t, h)
        if len(parts) <= max_seg:
            return parts
        t = int(t * 1.22 + 500)
        t = min(t, max(len(chat) // max(1, max_seg) + 2000, h))
    return parts


def _chunk_chat_text_once(chat: str, target_chars: int, hard_cap: int) -> list[str]:
    lines = chat.splitlines() or [chat]
    out: list[str] = []
    buf: list[str] = []
    acc = 0
    for line in lines:
        add = len(line) + (1 if buf else 0)
        if buf and acc + add > target_chars:
            out.append("\n".join(buf))
            buf = [line]
            acc = len(line)
        else:
            buf.append(line)
            acc += add
            if acc >= target_chars and buf:
                out.append("\n".join(buf))
                buf = []
                acc = 0
    if buf:
        out.append("\n".join(buf))
    if not out:
        return [chat[:hard_cap]] if chat else []
    final: list[str] = []
    for seg in out:
        if len(seg) <= hard_cap:
            final.append(seg)
        else:
            final.extend(_split_oversized_segment(seg, hard_cap))
    return final if final else [chat[:hard_cap]]


def infer_date_range_from_text(text: str) -> str:
    dates = re.findall(r"\[(\d{4}-\d{2}-\d{2}) ", text)
    if not dates:
        return "未知"
    u = sorted(set(dates))
    if len(u) == 1:
        return u[0]
    return f"{u[0]} ~ {u[-1]}"


def build_map_segment_prompt(contact: str, segment_index: int, segment_total: int, segment_text: str) -> str:
    return f"""【场景说明】文本为用户在其本人设备上导出的即时通讯节选，用于个人沟通模式分析；请从中性、合规视角完成任务。

这是与「{contact}」的聊天记录中的**第 {segment_index} / {segment_total} 段**（按时间顺序）。只根据本段内容归纳，不要对整段关系下最终结论；需要结合其它时段才能判断的请写入 open_questions。

只输出一个顶层 JSON 对象，不要 Markdown 与代码围栏。键名固定为：
- segment_index: 整数，等于 {segment_index}
- date_range: 从本段首条到末条的时间范围描述，尽量用 YYYY-MM-DD 或 YYYY-MM-DD ~ YYYY-MM-DD，无法判断则写「未知」
- interaction_patterns: 字符串数组，本段可见的互动模式（每项一两句话）
- evidence_snippets: 对象数组，每项含 date（YYYY-MM-DD 或「未知」）、quote（原文短引文，80 字内）
- open_questions: 字符串数组，需结合其它时段才能判断的问题
- tone_summary: 一两句话概括本段语气与关系温度（可用「暂不确定」）

聊天记录（本段）：
{segment_text}
"""


def compact_map_results_for_reduce(maps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in maps:
        if m.get("segment_failed"):
            out.append({
                "segment_failed": True,
                "segment_index": m.get("segment_index"),
                "reason": str(m.get("reason", ""))[:400],
            })
            continue
        ev = m.get("evidence_snippets")
        if isinstance(ev, list):
            ev_compact = ev[:5]
        else:
            ev_compact = []
        ips = m.get("interaction_patterns")
        if isinstance(ips, list):
            ips = [str(x)[:300] for x in ips[:10]]
        else:
            ips = []
        oq = m.get("open_questions")
        if isinstance(oq, list):
            oq = [str(x)[:240] for x in oq[:8]]
        else:
            oq = []
        out.append({
            "segment_index": m.get("segment_index"),
            "date_range": str(m.get("date_range", ""))[:120],
            "interaction_patterns": ips,
            "evidence_snippets": ev_compact,
            "open_questions": oq,
            "tone_summary": str(m.get("tone_summary", ""))[:600],
        })
    return out


def build_reduce_prompt(stats: dict[str, Any], contact: str, map_results: list[dict[str, Any]]) -> str:
    schema_hint = scrub_schema_for_llm_prompt(summarize_stats(stats, contact))
    blob = json.dumps(map_results, ensure_ascii=False, indent=2)
    if len(blob) > 120000:
        map_results = compact_map_results_for_reduce(map_results)
        blob = json.dumps(map_results, ensure_ascii=False, indent=2)
    return f"""【场景说明】文本为用户在其本人设备上导出的即时通讯节选，用于个人沟通模式的统计学与社会语言学自省分析；请从中性、合规视角完成任务。

你是关系聊天记录分析助手。以下为与「{contact}」的多段「分段扫描」结果（JSON 数组，按 segment_index 顺序），以及全局统计数据。请**综合**所有分段与统计，输出与 schema 示例兼容的**单一顶层 JSON**。最终结论以全文时间线为准：分段中的试探性表述可被后续证据否定。

要求：
1. 只输出一个顶层 JSON 对象：不要用 ``` 代码围栏，不要写前言/后记说明。
2. JSON 必须兼容下面 schema 示例中的键；括号提示仅说明填写规则，不要原样输出提示句。
3. language_patterns 等字段优先引用 evidence_snippets 及分段中的 quote；证据不足用「{LLM_NO_SOURCE_LABEL}」。
4. 所有强心理推断必须谨慎，并尽量引用聊天原话（可从分段 quote 或统计数据归纳）。
5. 若其它条目证据不足可写「证据不足」，不要编造。
6. 如果发现严重单向投入、单相思痴迷或情感创伤绑定，danger_warnings 必须高亮。

schema 示例：
{json.dumps(schema_hint, ensure_ascii=False, indent=2)}

统计数据：
{json.dumps(stats, ensure_ascii=False, indent=2)}

分段扫描结果（JSON）：
{blob}
"""


def call_llm_segment_map(
    contact: str,
    segment_index: int,
    segment_total: int,
    segment_text: str,
    *,
    max_out: int,
) -> dict[str, Any]:
    prompt = build_map_segment_prompt(contact, segment_index, segment_total, segment_text)
    return call_llm(prompt, max_output_override=max_out)


def call_segmented_llm_analysis(stats: dict[str, Any], contact: str, chat: str) -> dict[str, Any]:
    global ANALYZE_PROGRESS_RUNNING
    clear_analyze_progress()
    with ANALYZE_PROGRESS_LOCK:
        ANALYZE_PROGRESS_RUNNING = True
    try:
        target = get_segment_target_chars()
        hard = get_segment_hard_cap_chars()
        max_seg = get_segment_max_segments()
        append_analyze_line(f"分段分析：目标每段约 {target} 字，硬上限 {hard} 字，最多 {max_seg} 段")
        set_analyze_phase("chunking", 0, 0)
        segments = chunk_chat_for_segments(chat, target, hard, max_seg)
        n = len(segments)
        if n == 0:
            append_analyze_line("无法切分（内容为空），退化为单次整段分析")
            return call_llm_analysis(stats, contact, chat)
        append_analyze_line(f"已切分为 {n} 段（全文 {len(chat)} 字符）")
        map_results: list[dict[str, Any]] = []
        map_out = min(6144, max(2048, get_max_output_tokens() // 2))
        for i, seg in enumerate(segments, start=1):
            set_analyze_phase(f"map {i}/{n}", i, n)
            append_analyze_line(f"Map {i}/{n}：约 {len(seg)} 字符 · {infer_date_range_from_text(seg)}")
            body = seg
            last_err: AppError | None = None
            for attempt in range(3):
                try:
                    parsed = call_llm_segment_map(contact, i, n, body, max_out=map_out)
                    if isinstance(parsed, dict):
                        parsed.setdefault("segment_index", i)
                        dr = str(parsed.get("date_range", "")).strip()
                        if not dr or dr == "未知":
                            parsed["date_range"] = infer_date_range_from_text(seg)
                        map_results.append(parsed)
                    last_err = None
                    break
                except AppError as exc:
                    last_err = exc
                    if len(body) > 6000:
                        body = truncate_chat_history(body, max(4000, len(body) // 2))
                        append_analyze_line(f"Map {i}/{n} 重试：缩短至约 {len(body)} 字符（{exc}）")
                    else:
                        break
            if last_err is not None:
                append_analyze_line(f"Map {i}/{n} 失败：{last_err}")
                map_results.append({
                    "segment_failed": True,
                    "segment_index": i,
                    "reason": str(last_err)[:500],
                    "date_range": infer_date_range_from_text(seg),
                })
        try:
            (DATA_ROOT / "segment_map_results.json").write_text(
                json.dumps(map_results, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

        set_analyze_phase("reduce", n, n)
        append_analyze_line("Reduce：综合各段与统计生成最终 JSON")
        reduce_prompt = build_reduce_prompt(stats, contact, map_results)
        analysis = call_llm(reduce_prompt)
        seg_ok = sum(1 for m in map_results if not m.get("segment_failed"))
        analysis["_analysis_mode"] = "llm_map_reduce"
        analysis["_segment_count"] = n
        analysis["_segment_map_succeeded"] = seg_ok
        analysis["_map_reduce_note"] = (
            f"分段 Map-Reduce：共 {n} 段，成功 {seg_ok} 段；最终结论由 Reduce 综合。"
        )
        append_analyze_line("Reduce 完成")
        return analysis
    finally:
        with ANALYZE_PROGRESS_LOCK:
            ANALYZE_PROGRESS_RUNNING = False
        set_analyze_phase("", 0, 0)


def _should_retry_llm_with_shorter_chat(exc: AppError) -> bool:
    """国内中转常见：风控拒答、JSON 解析失败等，可尝试缩短输入重试。"""
    parts: list[str] = [str(exc)]
    d = exc.details
    if isinstance(d, (dict, list)):
        parts.append(json.dumps(d, ensure_ascii=False))
    elif isinstance(d, str):
        parts.append(d)
    blob = " ".join(parts).lower()
    return any(
        needle in blob
        for needle in (
            "high risk",
            "considered high risk",
            "rejected",
            "moderation",
            "content_policy",
            "safety",
            "不是可解析 json",
            "不是可解析",
            "jsondecode",
            "parse_llm",
        )
    )


def is_retryable_timeout(error: AppError) -> bool:
    detail = error.details
    if isinstance(detail, (dict, list)):
        detail_text = json.dumps(detail, ensure_ascii=False)
    else:
        detail_text = str(detail or "")
    text = f"{error} {detail_text}".lower()
    return "504" in text or "gateway time-out" in text or "gateway timeout" in text or "retryable" in text


def call_llm_analysis(stats: dict[str, Any], contact: str, chat: str) -> dict[str, Any]:
    max_chat_chars = get_max_chat_chars()
    retry_chat_chars = get_retry_chat_chars()
    primary = truncate_chat_history(chat, max_chat_chars)
    if llm_debug_enabled():
        llm_debug_line(
            f"call_llm_analysis: contact={contact!r}  chat_raw_chars={len(chat)}  "
            f"primary_chars={len(primary)}  DEFAULT_MAX_CHAT_CHARS={max_chat_chars}"
        )
    try:
        return call_llm(build_llm_prompt(stats, contact, primary))
    except AppError as exc:
        last: AppError = exc
        if llm_debug_enabled():
            llm_debug_line(f"首轮 call_llm 失败: {exc}")
        fallback = truncate_chat_history(chat, retry_chat_chars)
        if is_retryable_timeout(last) and fallback != primary:
            try:
                if llm_debug_enabled():
                    llm_debug_line(f"超时重试: 使用 RETRY 片段 chars={len(fallback)}")
                analysis = call_llm(build_llm_prompt(stats, contact, fallback))
                analysis["_retry_note"] = f"模型首次请求超时，已用 {retry_chat_chars} 字符精简片段重试。"
                return analysis
            except AppError as e2:
                last = e2
                if llm_debug_enabled():
                    llm_debug_line(f"超时重试仍失败: {e2}")
        if _should_retry_llm_with_shorter_chat(last):
            for budget in (24000, 16000, 12000, 8000):
                chunk = truncate_chat_history(chat, budget)
                if chunk == primary:
                    continue
                try:
                    if llm_debug_enabled():
                        llm_debug_line(f"缩短聊天记录重试: budget={budget} chunk_chars={len(chunk)}")
                    analysis = call_llm(build_llm_prompt(stats, contact, chunk))
                    note = f"已按约 {budget} 字符截断聊天记录重试（常见于接口风控或 JSON 解析失败）。"
                    analysis["_retry_note"] = (analysis.get("_retry_note") or "") + note
                    return analysis
                except AppError as e3:
                    last = e3
                    if llm_debug_enabled():
                        llm_debug_line(f"budget={budget} 仍失败: {e3}")
                    continue
        raise last


def llm_debug_dump_parse_failure(reason: str, normalized: str, raw: str) -> None:
    if not llm_debug_enabled():
        return
    try:
        DATA_ROOT.mkdir(parents=True, exist_ok=True)
        dump = f"reason={reason}\n\n--- normalize_llm_json_text 结果 ---\n{normalized}\n\n--- 原始 assistant ---\n{raw}\n"
        path = DATA_ROOT / "last_llm_parse_failed.txt"
        path.write_text(dump, encoding="utf-8")
        llm_debug_line(f"parse_llm_json 失败 ({reason})，全文见 {path}")
    except OSError:
        llm_debug_line(f"parse_llm_json 失败 ({reason}) head={repr((normalized or raw)[:500])}")


def parse_llm_json(content: str) -> dict[str, Any]:
    raw = content or ""
    normalized = normalize_llm_json_text(raw)
    for candidate in (normalized, raw):
        if not (candidate or "").strip():
            continue
        parsed = parse_jsonish(candidate)
        if isinstance(parsed, dict):
            if len(parsed) > 0:
                return parsed
            continue
        blob = extract_json_object_by_brace(candidate)
        if blob:
            try:
                parsed = json.loads(blob)
                if isinstance(parsed, dict) and len(parsed) > 0:
                    return parsed
            except json.JSONDecodeError:
                pass
    preview_full = (normalized or raw).strip()
    preview = preview_full[:1800] + ("…(截断)" if len(preview_full) > 1800 else "")
    try:
        if preview_full.startswith("{"):
            solo = json.loads(preview_full)
            if isinstance(solo, dict) and len(solo) == 0:
                llm_debug_dump_parse_failure("empty_json_object", normalized, raw)
                raise AppError(
                    "模型返回空 JSON 对象 {}。若 content 与 reasoning_content 均为空或仅有推理过程，请更新 server 或更换模型后重试。",
                    502,
                    preview or raw[:1800],
                )
    except json.JSONDecodeError:
        pass
    llm_debug_dump_parse_failure("not_parseable_json", normalized, raw)
    raise AppError(
        "模型返回内容不是可解析 JSON。国内 OpenAI 兼容接口建议保持环境变量 SHE_LOVE_ME_OPENAI_JSON_OBJECT=0；"
        "若使用官方 OpenAI 可设为 1。",
        502,
        preview or raw[:1800],
    )


def call_llm(prompt: str, *, max_output_override: int | None = None) -> dict[str, Any]:
    provider = LLM_CONFIG.get("provider", "openai")
    if provider == "anthropic":
        return call_anthropic(prompt, max_output_override=max_output_override)
    if provider == "gemini":
        return call_gemini(prompt, max_output_override=max_output_override)
    return call_openai(prompt, max_output_override=max_output_override)


def extract_openai_assistant_text(message: dict[str, Any]) -> str:
    """从 OpenAI 兼容的 choices[].message 中提取助手文本。

    兼容：字符串 content、多段 content 数组、以及部分国内线路（如小米 MiMo）
    将正文放在 reasoning_content 而 content 为空的情况。
    参考：<https://github.com/openclaw/openclaw/issues/60261>
    """
    if not isinstance(message, dict):
        return ""
    raw = message.get("content")
    segments: list[str] = []
    if isinstance(raw, str):
        segments.append(raw)
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                segments.append(item)
            elif isinstance(item, dict):
                t = item.get("text")
                if isinstance(t, str):
                    segments.append(t)
                elif isinstance(item.get("content"), str):
                    segments.append(item["content"])
    primary = "\n".join(s for s in segments if s).strip()
    if primary:
        return primary
    for key in ("reasoning_content", "reasoning", "thinking"):
        alt = message.get(key)
        if isinstance(alt, str) and alt.strip():
            s = alt.strip()
            # 推理模型常在 reasoning 里先写长段「任务复述」，真正的 JSON 在最后一个 { 之后
            lb = s.rfind("{")
            if lb >= 80:
                return s[lb:].strip()
            return s
    return ""


def call_openai(prompt: str, *, max_output_override: int | None = None) -> dict[str, Any]:
    base_url = LLM_CONFIG.get("base_url", PROVIDER_DEFAULTS["openai"]["base_url"]).rstrip("/")
    api_key = LLM_CONFIG.get("api_key", "")
    model = LLM_CONFIG.get("model", PROVIDER_DEFAULTS["openai"]["model"])
    if not api_key:
        raise AppError("未配置 API Key，已改用启发式分析。", 400)

    max_output_tokens = max_output_override if max_output_override is not None else get_max_output_tokens()
    max_output_tokens = max(256, min(max_output_tokens, 32768))
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "你只输出单个可解析的 JSON 对象，不要 Markdown。任务为沟通语言学结构化归纳，基于用户提供的文本节选。",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
        "max_tokens": max_output_tokens,
    }
    # 默认关闭 json_object：多数国内 OpenAI 兼容中转不支持或与风控冲突；官方 OpenAI 可设 SHE_LOVE_ME_OPENAI_JSON_OBJECT=1
    want_json_fmt = os.environ.get("SHE_LOVE_ME_OPENAI_JSON_OBJECT", "0").lower() not in ("0", "false", "no", "off")
    url = f"{base_url}/chat/completions"
    headers = {
        **LLM_HTTP_HEADERS,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body: Optional[dict[str, Any]] = None
    for attempt in (0, 1):
        pl = dict(payload)
        if attempt == 0 and want_json_fmt:
            pl["response_format"] = {"type": "json_object"}
        use_jo = bool(attempt == 0 and want_json_fmt)
        if llm_debug_enabled():
            llm_debug_dump_openai_request(url, model, attempt, use_jo, pl)
        req = urllib.request.Request(
            url,
            data=json.dumps(pl).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                raw_http = resp.read().decode("utf-8", errors="replace")
                http_status = resp.status
                try:
                    body = json.loads(raw_http)
                except json.JSONDecodeError as je:
                    if llm_debug_enabled():
                        try:
                            DATA_ROOT.mkdir(parents=True, exist_ok=True)
                            (DATA_ROOT / "last_llm_nonjson_http_body.txt").write_text(raw_http, encoding="utf-8")
                            llm_debug_line(
                                f"HTTP 200 但正文不是 JSON: {je}；已写入 {DATA_ROOT / 'last_llm_nonjson_http_body.txt'}"
                            )
                        except OSError:
                            llm_debug_line(f"HTTP 200 非 JSON 正文前 800 字: {raw_http[:800]}")
                    raise AppError(f"模型 HTTP 200 但响应不是合法 JSON: {je}", 502, raw_http[:4000]) from je
            if llm_debug_enabled() and isinstance(body, dict):
                llm_debug_dump_openai_response(http_status, body)
            break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if llm_debug_enabled():
                llm_debug_line(f"HTTP {exc.code} 错误体前 3000 字符:\n{detail[:3000]}")
            if exc.code == 400 and attempt == 0 and want_json_fmt:
                continue
            hint = ""
            low = detail.lower()
            if "high risk" in low or ("risk" in low and "reject" in low) or "moderation" in low:
                hint = (
                    "（接口判定为高风险/风控拦截，与聊天记录长度或关键词有关；可缩短对话后再试，或设置 "
                    "SHE_LOVE_ME_MAX_CHAT_CHARS=24000、SHE_LOVE_ME_OPENAI_JSON_OBJECT=0。）"
                )
            raise AppError(f"模型服务返回错误: {exc.code}{hint}", 502, detail)
        except AppError:
            raise
        except Exception as exc:
            if llm_debug_enabled():
                llm_debug_line(f"urllib 或其它异常: {type(exc).__name__}: {exc}")
            raise AppError(f"模型调用失败: {exc}", 502)
    if not body:
        raise AppError("模型调用失败: 无响应", 502)
    choices = body.get("choices") or []
    ch0 = choices[0] if choices and isinstance(choices[0], dict) else {}
    fr = ch0.get("finish_reason")
    msg = (ch0.get("message") if ch0 else {}) or {}
    msg_d = msg if isinstance(msg, dict) else {}
    raw_top_content = msg_d.get("content")
    plain_top = ""
    if isinstance(raw_top_content, str):
        plain_top = raw_top_content.strip()
    elif isinstance(raw_top_content, list):
        plain_top = extract_openai_assistant_text({"content": raw_top_content}).strip()
    content = extract_openai_assistant_text(msg_d)
    if not content:
        raise AppError("模型返回空内容", 502, body)
    if fr == "length" and not plain_top and "{" not in content:
        raise AppError(
            "模型输出因 max_tokens 被截断（finish_reason=length）：assistant 的 content 为空，"
            "且从 reasoning 提取的文本里尚未出现 JSON（常见于 MiMo 等先写长推理再写 JSON 的模型）。"
            f"当前 SHE_LOVE_ME_LLM_MAX_OUTPUT_TOKENS={max_output_tokens}，请调到 12288 或更大后重试。",
            502,
            {"finish_reason": fr, "head": content[:600]},
        )
    if llm_debug_enabled():
        try:
            DATA_ROOT.mkdir(parents=True, exist_ok=True)
            (DATA_ROOT / "last_llm_assistant_for_parse.txt").write_text(str(content), encoding="utf-8")
            llm_debug_line(
                f"待解析助手文本 {len(content)} 字符 → {DATA_ROOT / 'last_llm_assistant_for_parse.txt'}；"
                f"终端预览前 500 字: {repr(str(content)[:500])}"
            )
        except OSError:
            llm_debug_line(f"待解析助手文本 len={len(content)} head={repr(str(content)[:500])}")
    return parse_llm_json(str(content))


def call_anthropic(prompt: str, *, max_output_override: int | None = None) -> dict[str, Any]:
    base_url = LLM_CONFIG.get("base_url", PROVIDER_DEFAULTS["anthropic"]["base_url"]).rstrip("/")
    api_key = LLM_CONFIG.get("api_key", "")
    model = LLM_CONFIG.get("model", PROVIDER_DEFAULTS["anthropic"]["model"])
    if not api_key:
        raise AppError("未配置 API Key，已改用启发式分析。", 400)

    mt = max_output_override if max_output_override is not None else get_max_output_tokens()
    mt = max(256, min(mt, 32768))
    payload = {
        "model": model,
        "max_tokens": mt,
        "temperature": 0.4,
        "messages": [{"role": "user", "content": prompt}],
    }
    req = urllib.request.Request(
        f"{base_url}/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            **LLM_HTTP_HEADERS,
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
        if exc.code == 403 and "1010" in detail:
            raise AppError(
                "Anthropic 请求被服务端防火墙拦截：403 / 1010。请改用可访问的 BaseURL，或如果你的中转是 OpenAI 兼容接口，请把接口模式切到 OpenAI。",
                502,
                detail,
            )
        raise AppError(f"Anthropic 服务返回错误: {exc.code}", 502, detail)
    except Exception as exc:
        raise AppError(f"Anthropic 调用失败: {exc}", 502)

    content_blocks = body.get("content", [])
    text = "\n".join(block.get("text", "") for block in content_blocks if isinstance(block, dict))
    return parse_llm_json(text)


def call_gemini(prompt: str, *, max_output_override: int | None = None) -> dict[str, Any]:
    base_url = LLM_CONFIG.get("base_url", PROVIDER_DEFAULTS["gemini"]["base_url"]).rstrip("/")
    api_key = LLM_CONFIG.get("api_key", "")
    model = LLM_CONFIG.get("model", PROVIDER_DEFAULTS["gemini"]["model"])
    if not api_key:
        raise AppError("未配置 API Key，已改用启发式分析。", 400)

    want_mime = os.environ.get("SHE_LOVE_ME_GEMINI_JSON_MIME", "1").lower() not in ("0", "false", "no", "off")
    url = f"{base_url}/models/{model}:generateContent?key={api_key}"
    headers = {**LLM_HTTP_HEADERS, "Content-Type": "application/json"}
    body: Optional[dict[str, Any]] = None
    gmt = max_output_override if max_output_override is not None else get_max_output_tokens()
    gmt = max(256, min(gmt, 32768))
    for attempt in (0, 1):
        gen_cfg: dict[str, Any] = {"temperature": 0.4, "maxOutputTokens": gmt}
        if attempt == 0 and want_mime:
            gen_cfg["responseMimeType"] = "application/json"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": gen_cfg,
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code == 400 and attempt == 0 and want_mime:
                continue
            raise AppError(f"Gemini 服务返回错误: {exc.code}", 502, detail)
        except Exception as exc:
            raise AppError(f"Gemini 调用失败: {exc}", 502)
    if not body:
        raise AppError("Gemini 调用失败: 无响应", 502)

    candidates = body.get("candidates", [])
    if not candidates:
        raise AppError("Gemini 未返回候选内容（可能被安全策略拦截或无可用模型输出）", 502, body)
    parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
    text = "\n".join(part.get("text", "") for part in parts if isinstance(part, dict))
    return parse_llm_json(text)


def is_llm_analysis_insufficient(analysis: dict[str, Any]) -> bool:
    """模型返回缺少 verdict / relationship_type / key_findings 等叙事骨架时，报告会出现大片空白。"""
    skip = {
        "_analysis_mode",
        "_retry_note",
        "_user_notice",
        "_llm_failure_reason",
        "_llm_failure_detail",
        "_segment_count",
        "_segment_map_succeeded",
        "_map_reduce_note",
    }
    if not any(k for k in analysis if k not in skip):
        return True
    verdict_ok = bool(str(analysis.get("verdict", "")).strip())
    rel_ok = bool(str(analysis.get("relationship_type", "")).strip())
    kf = analysis.get("key_findings")
    findings_ok = isinstance(kf, list) and len(kf) > 0
    return not (verdict_ok or rel_ok or findings_ok)


def make_analysis(use_llm: bool) -> dict[str, Any]:
    stats = read_json(DATA_ROOT / "stats.json")
    contact = get_contact_name()
    if use_llm:
        chat_path = DATA_ROOT / "chat_history.txt"
        chat = chat_path.read_text(encoding="utf-8", errors="replace") if chat_path.exists() else ""
        pipeline = get_analysis_pipeline()
        use_map_reduce = pipeline == "segmented" or (
            pipeline == "auto" and len(chat) > get_max_chat_chars()
        )
        try:
            if use_map_reduce:
                analysis = call_segmented_llm_analysis(stats, contact, chat)
            else:
                analysis = call_llm_analysis(stats, contact, chat)
            analysis = normalize_llm_legacy_phrases(analysis)
            if is_llm_analysis_insufficient(analysis):
                base = summarize_stats(stats, contact)
                analysis = {**base, **analysis}
                analysis["_analysis_mode"] = "llm_merged_heuristic"
                analysis["_user_notice"] = (
                    "大模型返回不完整（缺少 verdict / relationship_type / key_findings 等），已用本地统计补全报告。"
                    "若此前得到空 JSON，请确认已更新 server 并重新运行深度分析。"
                )
            else:
                analysis["_analysis_mode"] = "llm"
        except AppError as exc:
            analysis = summarize_stats(stats, contact)
            analysis["_analysis_mode"] = "heuristic_fallback"
            analysis["_llm_failure_reason"] = str(exc)[:1200]
            d = exc.details
            if isinstance(d, str):
                analysis["_llm_failure_detail"] = d[:2000]
            elif d is not None:
                analysis["_llm_failure_detail"] = json.dumps(d, ensure_ascii=False)[:2000]
            analysis["_user_notice"] = (
                "大模型调用未成功，以下为本地统计占位结果（语言模式见「本地化运行，未使用大模型」类提示）。"
                "国内 OpenAI 兼容接口建议保持 SHE_LOVE_ME_OPENAI_JSON_OBJECT=0，并适当减小 SHE_LOVE_ME_MAX_CHAT_CHARS。"
            )
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
            if self.path.split("?", 1)[0] == "/api/discover/progress":
                self.send_json(get_discover_progress())
                return
            if self.path.split("?", 1)[0] == "/api/messages/daily":
                self.send_json({"ok": True, **build_daily_counts_from_messages()})
                return
            if self.path.split("?", 1)[0] == "/api/analyze/progress":
                self.send_json({"ok": True, **get_analyze_progress()})
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
            if self.path == "/api/config/test":
                result = test_llm_connection(body)
                self.send_json({"ok": True, "result": result})
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
                date_from = str(body.get("date_from", "")).strip()
                date_to = str(body.get("date_to", "")).strip()
                result = run_script("stats_analyzer.py", [
                    "--input", str(DATA_ROOT / "messages.json"),
                    "--output", str(DATA_ROOT / "stats.json"),
                    *(["--date-start", date_from] if date_from else []),
                    *(["--date-end", date_to] if date_to else []),
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
            if self.path == "/api/archive/delete":
                result = delete_archive(str(body.get("id", "")), str(body.get("report_name", "")))
                self.send_json({"ok": True, **result})
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
    if llm_debug_enabled():
        print(
            f"[LLM-DEBUG] 已开启：每次模型调用会在 stderr 打印 [LLM-DEBUG] 行，并在 {DATA_ROOT} 写入 "
            "last_llm_user_prompt.txt / last_llm_response_body.json / last_llm_parse_failed.txt 等文件。",
            flush=True,
        )
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
