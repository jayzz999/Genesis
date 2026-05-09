"""Module 3 — sandboxed tool-use autonomy.

Organisms can execute small analysis programs without touching the host
workspace. This is not a perfect security boundary, but it is a practical
agent safety layer: subprocess isolation, stripped environment, timeout,
memory limits, limited imports, temporary working directory, and auditable
records for every run.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

_BASE = Path(os.getenv("GENESIS_TOOL_SANDBOX_STORAGE", "tool_runs")).resolve()

DEFAULT_TIMEOUT_S = 8
DEFAULT_MEMORY_MB = 128
MAX_CODE_CHARS = 8000
MAX_STDOUT_CHARS = 6000
MAX_STDERR_CHARS = 3000


RUNNER = r'''
import builtins
import contextlib
import io
import json
import sys

payload = json.loads(sys.stdin.read())
code = payload.get("code", "")
input_data = payload.get("input", {})

allowed_modules = {
    "collections", "datetime", "functools", "itertools", "json", "math",
    "random", "re", "statistics", "string", "textwrap", "time",
}

def limited_import(name, globals=None, locals=None, fromlist=(), level=0):
    root = name.split(".", 1)[0]
    if root not in allowed_modules:
        raise ImportError(f"module '{root}' is not allowed in Genesis sandbox")
    return builtins.__import__(name, globals, locals, fromlist, level)

safe_builtins = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "pow": pow,
    "print": print,
    "range": range,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
    "__import__": limited_import,
}

globals_dict = {
    "__builtins__": safe_builtins,
    "input_data": input_data,
    "result": None,
}

stdout = io.StringIO()
try:
    with contextlib.redirect_stdout(stdout):
        exec(compile(code, "<genesis_sandbox>", "exec"), globals_dict, globals_dict)
    response = {
        "ok": True,
        "result": globals_dict.get("result"),
        "stdout": stdout.getvalue(),
    }
except Exception as exc:
    response = {
        "ok": False,
        "error": f"{type(exc).__name__}: {exc}",
        "stdout": stdout.getvalue(),
    }

print(json.dumps(response, default=str))
'''


def _set_limits(memory_mb: int):
    def apply_limits():
        try:
            import resource
            mem_bytes = int(memory_mb) * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
            resource.setrlimit(resource.RLIMIT_CPU, (DEFAULT_TIMEOUT_S + 1, DEFAULT_TIMEOUT_S + 1))
        except Exception:
            pass
    return apply_limits


def _run_path(run_id: str) -> Path:
    return _BASE / f"{run_id}.json"


def _write_run(run: dict) -> None:
    _BASE.mkdir(parents=True, exist_ok=True)
    _run_path(run["id"]).write_text(json.dumps(run, indent=2, default=str), encoding="utf-8")


def list_runs(limit: int = 50) -> list[dict]:
    if not _BASE.exists():
        return []
    runs = []
    for path in _BASE.glob("tsr_*.json"):
        try:
            runs.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
    runs.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return runs[:limit]


def get_run(run_id: str) -> Optional[dict]:
    path = _run_path(run_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


async def run_python(
    *,
    code: str,
    input_data: Optional[dict] = None,
    organism_id: Optional[str] = None,
    purpose: str = "",
    timeout_s: int = DEFAULT_TIMEOUT_S,
    memory_mb: int = DEFAULT_MEMORY_MB,
) -> dict:
    code = (code or "")[:MAX_CODE_CHARS]
    run_id = f"tsr_{uuid4().hex[:12]}"
    created_at = datetime.utcnow().isoformat()
    input_data = input_data or {}
    timeout_s = max(1, min(int(timeout_s or DEFAULT_TIMEOUT_S), 30))
    memory_mb = max(32, min(int(memory_mb or DEFAULT_MEMORY_MB), 512))

    run = {
        "id": run_id,
        "created_at": created_at,
        "organism_id": organism_id,
        "purpose": purpose[:500],
        "language": "python",
        "timeout_s": timeout_s,
        "memory_mb": memory_mb,
        "code": code,
        "input": input_data,
        "status": "running",
    }
    _write_run(run)

    payload = json.dumps({"code": code, "input": input_data}, default=str)
    with tempfile.TemporaryDirectory(prefix=f"genesis_{run_id}_") as cwd:
        try:
            proc = subprocess.run(
                [sys.executable, "-I", "-c", RUNNER],
                input=payload,
                text=True,
                capture_output=True,
                cwd=cwd,
                env={
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONUNBUFFERED": "1",
                    "NO_PROXY": "*",
                },
                timeout=timeout_s,
                preexec_fn=_set_limits(memory_mb) if sys.platform != "win32" else None,
            )
            raw_stdout = (proc.stdout or "")[:MAX_STDOUT_CHARS]
            raw_stderr = (proc.stderr or "")[:MAX_STDERR_CHARS]
            parsed = {}
            try:
                parsed = json.loads(raw_stdout.strip().splitlines()[-1])
            except Exception:
                parsed = {"ok": False, "error": "sandbox produced non-json output", "stdout": raw_stdout}
            run.update({
                "status": "complete" if parsed.get("ok") else "error",
                "ok": bool(parsed.get("ok")),
                "returncode": proc.returncode,
                "result": parsed.get("result"),
                "stdout": (parsed.get("stdout") or raw_stdout)[:MAX_STDOUT_CHARS],
                "stderr": raw_stderr,
                "error": parsed.get("error"),
                "completed_at": datetime.utcnow().isoformat(),
            })
        except subprocess.TimeoutExpired as exc:
            run.update({
                "status": "timeout",
                "ok": False,
                "stdout": (exc.stdout or "")[:MAX_STDOUT_CHARS] if isinstance(exc.stdout, str) else "",
                "stderr": (exc.stderr or "")[:MAX_STDERR_CHARS] if isinstance(exc.stderr, str) else "",
                "error": f"Timed out after {timeout_s}s",
                "completed_at": datetime.utcnow().isoformat(),
            })
        except Exception as exc:
            run.update({
                "status": "error",
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "completed_at": datetime.utcnow().isoformat(),
            })

    _write_run(run)
    return run
