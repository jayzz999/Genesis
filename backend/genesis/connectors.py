"""Permission-gated real connector adapters.

Every adapter in this module either performs a real scoped side effect after an
Module 8 permission grant validates, or fails with a configuration error. It does
not return artificial success for unavailable external systems.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from typing import Optional
from uuid import uuid4

import httpx

from . import approvals
from backend.shared.config import settings

_BASE = Path(os.getenv("GENESIS_CONNECTOR_STORAGE", "connectors")).resolve()
_MAX_RESPONSE_CHARS = 20_000

ADAPTERS = {
    "external_api": {
        "id": "external_api",
        "name": "HTTP API",
        "permission": "external_api",
        "action_type": "external_api",
        "default_scope": "https://api.example.com",
        "description": "Performs a real outbound HTTP request to an allowlisted endpoint.",
        "real_side_effect": "http_request",
        "requires": ["GENESIS_CONNECTOR_HTTP_ALLOWLIST"],
    },
    "send_message": {
        "id": "send_message",
        "name": "Webhook Message Sender",
        "permission": "send_message",
        "action_type": "send_message",
        "default_scope": "webhook-message",
        "description": "Sends a real message to GENESIS_MESSAGE_WEBHOOK_URL or GENESIS_SLACK_WEBHOOK_URL.",
        "real_side_effect": "webhook_message",
        "requires": ["GENESIS_MESSAGE_WEBHOOK_URL or GENESIS_SLACK_WEBHOOK_URL"],
    },
    "slack_webhook_message": {
        "id": "slack_webhook_message",
        "name": "Slack Webhook Message",
        "permission": "send_message",
        "action_type": "send_message",
        "default_scope": "slack-webhook",
        "description": "Sends a real Slack incoming-webhook message after approval.",
        "real_side_effect": "slack_webhook_message",
        "requires": ["GENESIS_SLACK_WEBHOOK_URL", "GENESIS_CONNECTOR_WEBHOOK_ALLOWLIST"],
    },
    "github_create_issue": {
        "id": "github_create_issue",
        "name": "GitHub Create Issue",
        "permission": "external_api",
        "action_type": "external_api",
        "default_scope": "owner/repo",
        "description": "Creates a real GitHub issue in an allowlisted repository.",
        "real_side_effect": "github_issue_create",
        "requires": ["GITHUB_TOKEN or GENESIS_GITHUB_TOKEN", "GENESIS_GITHUB_REPOSITORIES"],
    },
    "github_issue_comment": {
        "id": "github_issue_comment",
        "name": "GitHub Issue Comment",
        "permission": "external_api",
        "action_type": "external_api",
        "default_scope": "owner/repo#1",
        "description": "Posts a real GitHub issue comment in an allowlisted repository.",
        "real_side_effect": "github_issue_comment",
        "requires": ["GITHUB_TOKEN or GENESIS_GITHUB_TOKEN", "GENESIS_GITHUB_REPOSITORIES"],
    },
    "deploy_change": {
        "id": "deploy_change",
        "name": "Deployment Webhook",
        "permission": "deploy_change",
        "action_type": "deploy_change",
        "default_scope": "staging",
        "description": "Triggers a real deployment webhook configured in GENESIS_DEPLOY_WEBHOOK_URL.",
        "real_side_effect": "deployment_webhook",
        "requires": ["GENESIS_DEPLOY_WEBHOOK_URL"],
    },
    "file_upload": {
        "id": "file_upload",
        "name": "Controlled File Upload",
        "permission": "file_upload",
        "action_type": "file_upload",
        "default_scope": "local-artifacts",
        "description": "Writes a real artifact to the controlled local artifact store.",
        "real_side_effect": "local_file_write",
    },
    "browser_submit": {
        "id": "browser_submit",
        "name": "Browser Submit",
        "permission": "browser_submit",
        "action_type": "browser_submit",
        "default_scope": "browser-automation",
        "description": "Requires a configured browser automation executor; disabled by default.",
        "real_side_effect": "browser_form_submit",
        "requires": ["GENESIS_BROWSER_CONNECTOR_ENABLED=1", "GENESIS_BROWSER_CONNECTOR_WEBHOOK_URL"],
    },
    "local_artifact_write": {
        "id": "local_artifact_write",
        "name": "Local Artifact Writer",
        "permission": "file_upload",
        "action_type": "file_upload",
        "default_scope": "local-artifacts",
        "description": "Writes a real local artifact inside the controlled connector artifact store.",
        "real_side_effect": "local_file_write",
    },
}


def _now() -> str:
    return datetime.utcnow().isoformat()


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _run_path(run_id: str) -> Path:
    return _BASE / f"{run_id}.json"


def _artifact_dir() -> Path:
    return _BASE / "artifacts"


def _artifact_path(filename: str) -> Path:
    raw_name = (filename or "artifact.txt").strip().replace("\\", "/").split("/")[-1]
    safe = "".join(ch for ch in raw_name if ch.isalnum() or ch in ("-", "_", ".")).strip("._")
    if not safe:
        safe = "artifact.txt"
    if len(safe) > 120:
        safe = safe[:120]
    path = (_artifact_dir() / safe).resolve()
    base = _artifact_dir().resolve()
    if base not in path.parents and path != base:
        raise ValueError("artifact path must stay inside connector artifact storage")
    return path


def _save_run(run: dict) -> dict:
    run["updated_at"] = _now()
    _atomic_write_text(_run_path(run["id"]), json.dumps(run, indent=2, default=str))
    return run


def list_adapters() -> list[dict]:
    configuration = connector_configuration()
    by_id = {item["adapter_id"]: item for item in configuration["adapters"]}
    return [
        {
            **adapter,
            "configured": by_id.get(adapter["id"], {}).get("configured", False),
            "missing": by_id.get(adapter["id"], {}).get("missing", []),
        }
        for adapter in ADAPTERS.values()
    ]


def get_adapter(adapter_id: str) -> Optional[dict]:
    return ADAPTERS.get(adapter_id)


def get_run(run_id: str) -> Optional[dict]:
    path = _run_path(run_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_runs(limit: int = 50) -> list[dict]:
    if not _BASE.exists():
        return []
    runs = []
    for path in _BASE.glob("conn_*.json"):
        run = get_run(path.stem)
        if run:
            runs.append(run)
    runs.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return runs[: max(1, min(int(limit), 200))]


def list_artifacts(limit: int = 50) -> list[dict]:
    artifact_dir = _artifact_dir()
    if not artifact_dir.exists():
        return []
    items = []
    for path in artifact_dir.glob("*"):
        if path.is_file():
            stat = path.stat()
            items.append({
                "filename": path.name,
                "path": str(path),
                "bytes": stat.st_size,
                "updated_at": datetime.utcfromtimestamp(stat.st_mtime).isoformat(),
            })
    items.sort(key=lambda item: item["updated_at"], reverse=True)
    return items[: max(1, min(int(limit), 200))]


def _write_local_artifact(payload: dict, scope: str) -> dict:
    filename = str(payload.get("filename") or f"genesis-{uuid4().hex[:8]}.txt")
    content = str(payload.get("content") or "")
    if len(content.encode("utf-8")) > 256_000:
        raise ValueError("artifact content exceeds 256KB limit")
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    artifact_path = _artifact_path(filename)
    body = content
    if metadata:
        body = f"{content}\n\n--- metadata ---\n{json.dumps(metadata, indent=2, sort_keys=True)}\n"
    _atomic_write_text(artifact_path, body)
    return {
        "filename": artifact_path.name,
        "path": str(artifact_path),
        "bytes": artifact_path.stat().st_size,
        "scope": scope,
        "write_state": "written",
    }


def _csv_env(name: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, "").split(",") if item.strip()]


def _is_allowed_url(url: str, *, allowlist_env: str = "GENESIS_CONNECTOR_HTTP_ALLOWLIST") -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    allowlist = _csv_env(allowlist_env)
    if "*" in allowlist:
        return not settings.is_production
    hostname = parsed.hostname.lower()
    normalized = url.lower()
    for item in allowlist:
        allowed = item.lower().rstrip("/")
        if allowed.startswith("http://") or allowed.startswith("https://"):
            if normalized.startswith(allowed):
                return True
        elif hostname == allowed or hostname.endswith("." + allowed):
            return True
    return False


def _safe_headers(headers: dict | None) -> dict:
    if not isinstance(headers, dict):
        return {}
    blocked = {"host", "content-length", "connection"}
    return {
        str(k): str(v)
        for k, v in headers.items()
        if str(k).lower() not in blocked
    }


def _body_preview(response: httpx.Response) -> dict:
    text = response.text[:_MAX_RESPONSE_CHARS]
    try:
        parsed = response.json()
    except Exception:
        parsed = None
    return {
        "status_code": response.status_code,
        "content_type": response.headers.get("content-type", ""),
        "body_preview": parsed if parsed is not None else text,
        "truncated": len(response.text) > _MAX_RESPONSE_CHARS,
    }


def _probe_result(
    adapter_id: str,
    *,
    scope: str,
    configured: bool,
    allowed: bool,
    live_checked: bool = False,
    checks: Optional[list[dict]] = None,
    details: Optional[dict] = None,
) -> dict:
    status = "pass" if configured and allowed else "fail"
    return {
        "adapter_id": adapter_id,
        "scope": scope,
        "status": status,
        "configured": configured,
        "allowed": allowed,
        "live_checked": live_checked,
        "fake_success_allowed": False,
        "checks": checks or [],
        "details": details or {},
        "updated_at": _now(),
    }


def _config_for(adapter_id: str) -> dict:
    configuration = connector_configuration()
    for item in configuration["adapters"]:
        if item["adapter_id"] == adapter_id:
            return item
    return {"adapter_id": adapter_id, "configured": False, "missing": ["unknown adapter"]}


def _check(name: str, ok: bool, message: str, **extra) -> dict:
    return {"name": name, "ok": ok, "message": message, **extra}


def probe_adapter(
    *,
    adapter_id: str,
    scope: str | None = None,
    live: bool = False,
) -> dict:
    """Safely check whether a connector can be used.

    Default probes do not perform external side effects. GitHub live probes use a
    read-only repository endpoint. Slack live probes intentionally stay disabled
    here because an incoming-webhook check must post a real message; use the
    normal approval-gated connector run for that.
    """
    adapter = get_adapter(adapter_id)
    if not adapter:
        raise ValueError(f"unknown connector adapter: {adapter_id}")
    scope = (scope or adapter["default_scope"]).strip() or adapter["default_scope"]
    config = _config_for(adapter_id)
    configured = bool(config.get("configured"))
    checks = [
        _check(
            "server_configuration",
            configured,
            "required environment is present" if configured else "missing required environment",
            missing=config.get("missing", []),
        )
    ]
    details: dict = {
        "real_side_effect": adapter.get("real_side_effect"),
        "permission": adapter["permission"],
        "action_type": adapter["action_type"],
    }
    allowed = configured
    live_checked = False

    if adapter_id == "external_api":
        endpoint = scope
        url_allowed = _is_allowed_url(endpoint)
        checks.append(_check(
            "allowlist",
            url_allowed,
            "endpoint is allowlisted" if url_allowed else "endpoint is not in GENESIS_CONNECTOR_HTTP_ALLOWLIST",
            endpoint=endpoint,
        ))
        allowed = configured and url_allowed
        if live and allowed:
            with httpx.Client(timeout=10, follow_redirects=False) as client:
                response = client.request("GET", endpoint)
            live_checked = True
            details["live_response"] = _body_preview(response)

    elif adapter_id in {"send_message", "slack_webhook_message"}:
        webhook_url = (
            os.getenv("GENESIS_SLACK_WEBHOOK_URL")
            if adapter_id == "slack_webhook_message"
            else os.getenv("GENESIS_MESSAGE_WEBHOOK_URL") or os.getenv("GENESIS_SLACK_WEBHOOK_URL")
        )
        if webhook_url:
            webhook_allowed = _is_allowed_url(webhook_url, allowlist_env="GENESIS_CONNECTOR_WEBHOOK_ALLOWLIST")
            checks.append(_check(
                "allowlist",
                webhook_allowed,
                "webhook URL is allowlisted" if webhook_allowed else "webhook URL is not in GENESIS_CONNECTOR_WEBHOOK_ALLOWLIST",
            ))
            details["webhook_host"] = urlparse(webhook_url).hostname
            allowed = configured and webhook_allowed
        else:
            checks.append(_check("allowlist", False, "webhook URL is not configured"))
            allowed = False
        if live:
            checks.append(_check(
                "live_probe",
                False,
                "Slack/webhook live probes would post a real message; run the permission-gated connector instead",
            ))

    elif adapter_id in {"github_create_issue", "github_issue_comment"}:
        try:
            repo, issue_number = _parse_github_scope(scope)
            repo_allowed = _github_repo_allowed(repo)
            checks.append(_check(
                "repository_allowlist",
                repo_allowed,
                "repository is allowlisted" if repo_allowed else "repository is not in GENESIS_GITHUB_REPOSITORIES",
                repo=repo,
            ))
            allowed = configured and repo_allowed
            details["repo"] = repo
            if issue_number:
                details["issue_number"] = issue_number
            if live and allowed:
                endpoint = f"https://api.github.com/repos/{repo}"
                with httpx.Client(timeout=15, follow_redirects=False) as client:
                    response = client.request("GET", endpoint, headers=_github_headers())
                live_checked = True
                details["live_response"] = _body_preview(response)
        except Exception as exc:
            checks.append(_check("scope", False, str(exc)))
            allowed = False

    elif adapter_id == "deploy_change":
        deploy_url = os.getenv("GENESIS_DEPLOY_WEBHOOK_URL")
        if deploy_url:
            deploy_allowed = _is_allowed_url(deploy_url, allowlist_env="GENESIS_CONNECTOR_DEPLOY_ALLOWLIST")
            checks.append(_check(
                "allowlist",
                deploy_allowed,
                "deployment webhook is allowlisted" if deploy_allowed else "deployment webhook is not in GENESIS_CONNECTOR_DEPLOY_ALLOWLIST",
            ))
            details["webhook_host"] = urlparse(deploy_url).hostname
            allowed = configured and deploy_allowed
        else:
            checks.append(_check("allowlist", False, "deployment webhook URL is not configured"))
            allowed = False

    elif adapter_id == "browser_submit":
        executor_url = os.getenv("GENESIS_BROWSER_CONNECTOR_WEBHOOK_URL")
        if executor_url:
            browser_allowed = _is_allowed_url(executor_url, allowlist_env="GENESIS_CONNECTOR_BROWSER_ALLOWLIST")
            checks.append(_check(
                "allowlist",
                browser_allowed,
                "browser executor is allowlisted" if browser_allowed else "browser executor is not in GENESIS_CONNECTOR_BROWSER_ALLOWLIST",
            ))
            details["executor_host"] = urlparse(executor_url).hostname
            allowed = configured and browser_allowed
        else:
            checks.append(_check("allowlist", False, "browser executor URL is not configured"))
            allowed = False

    elif adapter_id in {"file_upload", "local_artifact_write"}:
        artifact_dir = _artifact_dir()
        checks.append(_check("artifact_store", True, "controlled artifact store is available", path=str(artifact_dir)))
        allowed = True

    return _probe_result(
        adapter_id,
        scope=scope,
        configured=configured,
        allowed=allowed,
        live_checked=live_checked,
        checks=checks,
        details=details,
    )


def _run_http_api(payload: dict, scope: str) -> dict:
    endpoint = str(payload.get("endpoint") or scope).strip()
    if not _is_allowed_url(endpoint):
        raise PermissionError("endpoint is not in GENESIS_CONNECTOR_HTTP_ALLOWLIST")
    method = str(payload.get("method") or "GET").upper()
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        raise ValueError("HTTP method must be GET, POST, PUT, PATCH, or DELETE")
    timeout = max(1.0, min(float(payload.get("timeout_s") or 20), 60.0))
    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        response = client.request(
            method,
            endpoint,
            headers=_safe_headers(payload.get("headers")),
            params=payload.get("params") if isinstance(payload.get("params"), dict) else None,
            json=payload.get("json", payload.get("body")) if method != "GET" else None,
        )
    return {
        "endpoint": endpoint,
        "method": method,
        **_body_preview(response),
    }


def _run_webhook_message(payload: dict, scope: str) -> dict:
    webhook_url = os.getenv("GENESIS_MESSAGE_WEBHOOK_URL") or os.getenv("GENESIS_SLACK_WEBHOOK_URL")
    if not webhook_url:
        raise RuntimeError("GENESIS_MESSAGE_WEBHOOK_URL or GENESIS_SLACK_WEBHOOK_URL is required")
    if not _is_allowed_url(webhook_url, allowlist_env="GENESIS_CONNECTOR_WEBHOOK_ALLOWLIST"):
        raise PermissionError("message webhook is not in GENESIS_CONNECTOR_WEBHOOK_ALLOWLIST")
    message = str(payload.get("message") or payload.get("text") or "").strip()
    if not message:
        raise ValueError("message is required")
    body = {"text": message, "scope": scope, "metadata": payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}}
    with httpx.Client(timeout=20, follow_redirects=False) as client:
        response = client.post(webhook_url, json=body)
    return {"webhook": webhook_url, "scope": scope, "message_bytes": len(message.encode("utf-8")), **_body_preview(response)}


def _run_slack_webhook_message(payload: dict, scope: str) -> dict:
    webhook_url = os.getenv("GENESIS_SLACK_WEBHOOK_URL")
    if not webhook_url:
        raise RuntimeError("GENESIS_SLACK_WEBHOOK_URL is required")
    if not _is_allowed_url(webhook_url, allowlist_env="GENESIS_CONNECTOR_WEBHOOK_ALLOWLIST"):
        raise PermissionError("Slack webhook is not in GENESIS_CONNECTOR_WEBHOOK_ALLOWLIST")
    text = str(payload.get("text") or payload.get("message") or "").strip()
    if not text:
        raise ValueError("text or message is required")
    body = {"text": text}
    if isinstance(payload.get("blocks"), list):
        body["blocks"] = payload["blocks"]
    with httpx.Client(timeout=20, follow_redirects=False) as client:
        response = client.post(webhook_url, json=body)
    return {"scope": scope, "message_bytes": len(text.encode("utf-8")), **_body_preview(response)}


def _parse_github_scope(scope: str) -> tuple[str, Optional[int]]:
    raw = (scope or "").strip()
    issue_number = None
    if "#" in raw:
        raw, number_text = raw.split("#", 1)
        issue_number = int(number_text.strip())
    parts = [part.strip() for part in raw.split("/") if part.strip()]
    if len(parts) != 2:
        raise ValueError("GitHub scope must be owner/repo or owner/repo#issue")
    return f"{parts[0]}/{parts[1]}", issue_number


def _github_repo_allowed(repo: str) -> bool:
    allowed = _csv_env("GENESIS_GITHUB_REPOSITORIES")
    repo_l = repo.lower()
    if "*" in allowed:
        return not settings.is_production
    return repo_l in {item.lower() for item in allowed}


def _github_token() -> str:
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GENESIS_GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN or GENESIS_GITHUB_TOKEN is required")
    return token


def _github_headers() -> dict:
    return {
        "Authorization": f"Bearer {_github_token()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Genesis-Connector/1.0",
    }


def _run_github_create_issue(payload: dict, scope: str) -> dict:
    repo, _issue = _parse_github_scope(scope)
    if not _github_repo_allowed(repo):
        raise PermissionError("GitHub repository is not in GENESIS_GITHUB_REPOSITORIES")
    title = str(payload.get("title") or "").strip()
    if not title:
        raise ValueError("title is required")
    body = {
        "title": title,
        "body": str(payload.get("body") or ""),
    }
    if isinstance(payload.get("labels"), list):
        body["labels"] = [str(item) for item in payload["labels"]]
    if isinstance(payload.get("assignees"), list):
        body["assignees"] = [str(item) for item in payload["assignees"]]
    endpoint = f"https://api.github.com/repos/{repo}/issues"
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        response = client.post(endpoint, headers=_github_headers(), json=body)
    preview = _body_preview(response)
    created = preview.get("body_preview") if isinstance(preview.get("body_preview"), dict) else {}
    return {
        "repo": repo,
        "endpoint": endpoint,
        "status_code": response.status_code,
        "number": created.get("number"),
        "html_url": created.get("html_url"),
        "content_type": preview.get("content_type"),
        "body_preview": created if response.status_code >= 400 else {"number": created.get("number"), "html_url": created.get("html_url"), "title": created.get("title")},
    }


def _run_github_issue_comment(payload: dict, scope: str) -> dict:
    repo, issue_number = _parse_github_scope(scope)
    issue_number = int(payload.get("issue_number") or issue_number or 0)
    if issue_number <= 0:
        raise ValueError("issue_number is required")
    if not _github_repo_allowed(repo):
        raise PermissionError("GitHub repository is not in GENESIS_GITHUB_REPOSITORIES")
    body_text = str(payload.get("body") or payload.get("comment") or "").strip()
    if not body_text:
        raise ValueError("body or comment is required")
    endpoint = f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments"
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        response = client.post(endpoint, headers=_github_headers(), json={"body": body_text})
    preview = _body_preview(response)
    created = preview.get("body_preview") if isinstance(preview.get("body_preview"), dict) else {}
    return {
        "repo": repo,
        "issue_number": issue_number,
        "endpoint": endpoint,
        "status_code": response.status_code,
        "html_url": created.get("html_url"),
        "content_type": preview.get("content_type"),
        "body_preview": created if response.status_code >= 400 else {"html_url": created.get("html_url"), "id": created.get("id")},
    }


def _run_deployment_webhook(payload: dict, scope: str) -> dict:
    deploy_url = os.getenv("GENESIS_DEPLOY_WEBHOOK_URL")
    if not deploy_url:
        raise RuntimeError("GENESIS_DEPLOY_WEBHOOK_URL is required")
    if not _is_allowed_url(deploy_url, allowlist_env="GENESIS_CONNECTOR_DEPLOY_ALLOWLIST"):
        raise PermissionError("deployment webhook is not in GENESIS_CONNECTOR_DEPLOY_ALLOWLIST")
    body = {
        "environment": scope,
        "version": payload.get("version"),
        "change": payload.get("change"),
        "metadata": payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
    }
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        response = client.post(deploy_url, json=body)
    return {"environment": scope, "webhook": deploy_url, **_body_preview(response)}


def _run_browser_submit(payload: dict, scope: str) -> dict:
    if os.getenv("GENESIS_BROWSER_CONNECTOR_ENABLED", "").lower() not in {"1", "true", "yes", "on"}:
        raise RuntimeError("GENESIS_BROWSER_CONNECTOR_ENABLED=1 is required")
    executor_url = os.getenv("GENESIS_BROWSER_CONNECTOR_WEBHOOK_URL")
    if not executor_url:
        raise RuntimeError("GENESIS_BROWSER_CONNECTOR_WEBHOOK_URL is required")
    if not _is_allowed_url(executor_url, allowlist_env="GENESIS_CONNECTOR_BROWSER_ALLOWLIST"):
        raise PermissionError("browser executor is not in GENESIS_CONNECTOR_BROWSER_ALLOWLIST")
    body = {
        "scope": scope,
        "url": payload.get("url"),
        "form": payload.get("form"),
        "fields": payload.get("fields") if isinstance(payload.get("fields"), dict) else {},
        "submit": payload.get("submit", True),
    }
    with httpx.Client(timeout=60, follow_redirects=False) as client:
        response = client.post(executor_url, json=body)
    return {"executor": executor_url, "scope": scope, **_body_preview(response)}


def _execute_adapter(adapter_id: str, payload: dict, scope: str) -> dict:
    if adapter_id in {"local_artifact_write", "file_upload"}:
        return _write_local_artifact(payload, scope)
    if adapter_id == "external_api":
        return _run_http_api(payload, scope)
    if adapter_id == "send_message":
        return _run_webhook_message(payload, scope)
    if adapter_id == "slack_webhook_message":
        return _run_slack_webhook_message(payload, scope)
    if adapter_id == "github_create_issue":
        return _run_github_create_issue(payload, scope)
    if adapter_id == "github_issue_comment":
        return _run_github_issue_comment(payload, scope)
    if adapter_id == "deploy_change":
        return _run_deployment_webhook(payload, scope)
    if adapter_id == "browser_submit":
        return _run_browser_submit(payload, scope)
    raise ValueError(f"no executor registered for connector adapter: {adapter_id}")


def run_adapter(
    *,
    adapter_id: str,
    grant_id: str,
    scope: str | None = None,
    actor: str = "genesis_connector",
    payload: Optional[dict] = None,
) -> dict:
    adapter = get_adapter(adapter_id)
    if not adapter:
        raise ValueError(f"unknown connector adapter: {adapter_id}")

    payload = payload if isinstance(payload, dict) else {}
    scope = (scope or adapter["default_scope"]).strip() or adapter["default_scope"]
    now = _now()
    run = {
        "id": f"conn_{uuid4().hex[:12]}",
        "adapter": adapter,
        "grant_id": grant_id,
        "scope": scope,
        "actor": (actor or "genesis_connector")[:120],
        "payload": payload,
        "status": "pending",
        "created_at": now,
        "updated_at": now,
        "permission_check": None,
        "result": None,
    }

    check = approvals.validate_grant(
        grant_id,
        permission=adapter["permission"],
        action_type=adapter["action_type"],
        scope=scope,
        consume=True,
        actor=actor,
    )
    run["permission_check"] = check
    if not check.get("ok"):
        run["status"] = "blocked"
        run["result"] = {
            "ok": False,
            "blocked": True,
            "reason": check.get("reason"),
            "message": "Connector adapter blocked by Module 9 permission enforcement.",
        }
        return _save_run(run)

    try:
        output = _execute_adapter(adapter_id, payload, scope)
        run["status"] = "complete"
        run["result"] = {
            "ok": True,
            "simulated": False,
            "adapter_id": adapter_id,
            "permission": adapter["permission"],
            "scope": scope,
            "output": output,
            "message": "Connector performed a real permission-gated side effect.",
        }
    except Exception as exc:
        run["status"] = "failed"
        run["result"] = {
            "ok": False,
            "blocked": False,
            "reason": "connector_execution_failed",
            "error": str(exc),
            "message": "Connector passed permission validation but no fake fallback was used.",
        }
    return _save_run(run)


def summary() -> dict:
    runs = list_runs(limit=200)
    counts = {}
    for run in runs:
        counts[run.get("status", "unknown")] = counts.get(run.get("status", "unknown"), 0) + 1
    return {
        "adapters": len(ADAPTERS),
        "runs": len(runs),
        "complete": counts.get("complete", 0),
        "blocked": counts.get("blocked", 0),
        "failed": counts.get("failed", 0),
        "simulation_only": False,
        "fake_success_allowed": False,
        "local_artifacts": len(list_artifacts(limit=200)),
    }


def _configured_status(adapter_id: str, required: list[str]) -> dict:
    missing = []
    for item in required:
        if " or " in item:
            options = [part.strip() for part in item.split(" or ")]
            if not any(os.getenv(option) for option in options):
                missing.append(item)
        elif "=" in item:
            key, expected = item.split("=", 1)
            if os.getenv(key, "") != expected:
                missing.append(item)
        elif not os.getenv(item):
            missing.append(item)
    return {"adapter_id": adapter_id, "configured": not missing, "missing": missing}


def connector_configuration() -> dict:
    adapters = []
    for adapter in ADAPTERS.values():
        required = adapter.get("requires", [])
        status = _configured_status(adapter["id"], required)
        adapters.append({
            "adapter_id": adapter["id"],
            "name": adapter["name"],
            "configured": status["configured"],
            "missing": status["missing"],
            "real_side_effect": adapter.get("real_side_effect"),
            "permission": adapter["permission"],
            "action_type": adapter["action_type"],
        })
    return {
        "version": "genesis-real-connector-configuration-v1",
        "fake_success_allowed": False,
        "configured": sum(1 for item in adapters if item["configured"]),
        "total": len(adapters),
        "adapters": adapters,
        "notes": [
            "Secrets are not returned by this endpoint.",
            "Unconfigured real connectors fail closed after permission validation.",
        ],
        "updated_at": _now(),
    }
