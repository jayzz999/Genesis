"""Continuous Perception Loop — the heartbeat that makes organisms truly alive.

Without this module, an organism only thinks when a human pokes it. With it,
each organism gets its own asyncio task that:

  1. Polls registered `perception_sources` (HTTP endpoints) at an interval.
  2. Receives webhook deliveries via the `/webhook/{token}` route.
  3. Dreams during idle stretches (no perceptions for `idle_dream_after_s`).

The heartbeat is the difference between a "workflow that ran once" and a
digital organism that lives.

Each organism's perception_sources is a list of dicts. Supported shapes:

    {"kind": "interval",  "type": "tick",       "interval_s": 30, "payload": {...}}
    {"kind": "http_poll", "type": "rss_check",  "url": "https://...", "interval_s": 120,
     "method": "GET", "headers": {...}}
    {"kind": "github_repo","type": "repo_maintainer_signal", "repo": "owner/repo",
     "interval_s": 300}
    {"kind": "webhook",   "type": "github_event","token": "wh_..."}  # token auto-generated

The lifecycle manager runs as a single background asyncio task. It scans
organisms every few seconds, spawns missing per-organism heartbeats, and
cancels those whose organisms have died.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import secrets
from datetime import datetime, timedelta
from typing import Any

import httpx

from . import connectors, dreams, events, nervous_system, runtime, store
from .types import OrganismState

logger = logging.getLogger("genesis.lifecycle")


# In-memory: organism_id -> asyncio.Task running its heartbeat
_heartbeats: dict[str, asyncio.Task] = {}
# Webhook token -> (organism_id, source_index)
_webhook_index: dict[str, tuple[str, int]] = {}
# Last activity timestamp per organism (for idle-dream)
_last_active: dict[str, datetime] = {}
# Last time each organism checked its society message inbox
_last_msg_check: dict[str, datetime] = {}

# Minimum seconds between society message-inbox checks per organism.
# Prevents a broadcast to N organisms from triggering N simultaneous LLM calls.
_MSG_CHECK_INTERVAL_S: int = int(os.getenv("GENESIS_MSG_CHECK_INTERVAL_S", "30"))

_supervisor_task: asyncio.Task | None = None
_enabled = os.getenv("GENESIS_LIFECYCLE", "1") not in ("0", "false", "no")


# ── Public API ────────────────────────────────────────────────────────

def start() -> None:
    """Idempotent: start the supervisor that spawns/reaps heartbeats."""
    global _supervisor_task
    if not _enabled:
        logger.info("[Lifecycle] disabled via GENESIS_LIFECYCLE=0")
        return
    if _supervisor_task and not _supervisor_task.done():
        return
    _supervisor_task = asyncio.create_task(_supervisor_loop(), name="genesis_supervisor")
    logger.info("[Lifecycle] supervisor started")


async def stop() -> None:
    """Cancel everything cleanly. Call on app shutdown."""
    global _supervisor_task
    if _supervisor_task:
        _supervisor_task.cancel()
        _supervisor_task = None
    for t in list(_heartbeats.values()):
        t.cancel()
    _heartbeats.clear()
    _webhook_index.clear()


def status() -> dict:
    """Snapshot for the UI / debugging."""
    return {
        "enabled": _enabled,
        "supervisor_running": bool(_supervisor_task and not _supervisor_task.done()),
        "alive_organisms": list(_heartbeats.keys()),
        "webhooks": [
            {"token": tok, "organism_id": oid, "source_index": idx}
            for tok, (oid, idx) in _webhook_index.items()
        ],
        "last_active": {oid: ts.isoformat() for oid, ts in _last_active.items()},
    }


def issue_webhook_token(organism_id: str, source_index: int) -> str:
    """Mint a webhook token bound to an organism + source index."""
    token = f"wh_{secrets.token_urlsafe(12)}"
    _webhook_index[token] = (organism_id, source_index)
    return token


async def deliver_webhook(token: str, body: dict) -> dict:
    """Called by the FastAPI route — feeds the body into the organism as a perception."""
    if token not in _webhook_index:
        raise KeyError(f"unknown webhook token: {token}")
    organism_id, source_index = _webhook_index[token]
    org = store.load_organism(organism_id)
    if not org:
        raise KeyError(f"organism for token gone: {organism_id}")
    source = (org.perception_sources or [{}])[source_index] if source_index < len(org.perception_sources) else {}
    perception = {
        "type": source.get("type", "webhook"),
        "source": "webhook",
        "payload": body,
    }
    decision = await runtime.perceive(
        organism_id, perception, event_callback=events.make_callback(),
    )
    _last_active[organism_id] = datetime.utcnow()
    return {"decision_id": decision.id, "action": decision.action}


# ── Supervisor ────────────────────────────────────────────────────────

async def _supervisor_loop() -> None:
    """Every few seconds, ensure each living organism has a heartbeat task."""
    try:
        while True:
            try:
                await _reconcile()
            except Exception as e:
                logger.error(f"[Supervisor] reconcile failed: {e}")
            await asyncio.sleep(5)
    except asyncio.CancelledError:
        return


async def _reconcile() -> None:
    organisms = [
        o for o in store.list_organisms()
        if o.state not in (OrganismState.DYING, OrganismState.DEAD)
    ]
    alive_ids = {o.id for o in organisms}

    # Reap heartbeats for organisms that no longer exist
    for oid in list(_heartbeats.keys()):
        if oid not in alive_ids or _heartbeats[oid].done():
            _heartbeats[oid].cancel()
            del _heartbeats[oid]
            # also drop webhook tokens
            for tok in [t for t, (o, _) in _webhook_index.items() if o == oid]:
                del _webhook_index[tok]

    # Spawn missing heartbeats and ensure webhook tokens exist
    for org in organisms:
        # Auto-mint webhook tokens for any webhook source that lacks one
        dirty = False
        for i, src in enumerate(org.perception_sources or []):
            if src.get("kind") == "webhook" and not src.get("token"):
                src["token"] = issue_webhook_token(org.id, i)
                dirty = True
            elif src.get("kind") == "webhook" and src.get("token"):
                _webhook_index.setdefault(src["token"], (org.id, i))
        if dirty:
            store.save_organism(org)

        if org.id not in _heartbeats:
            t = asyncio.create_task(_heartbeat(org.id, startup_jitter=True), name=f"hb_{org.id}")
            _heartbeats[org.id] = t
            _last_active.setdefault(org.id, datetime.utcnow())


# ── Per-organism heartbeat ────────────────────────────────────────────

async def _heartbeat(organism_id: str, startup_jitter: bool = False) -> None:
    """One async loop per organism. Drives interval ticks, polls, and idle dreaming."""
    logger.info(f"[Heartbeat] {organism_id} starting")
    # Spread newly spawned organisms over a 10s window so they don't all
    # fire their first perception at the exact same moment.
    if startup_jitter:
        await asyncio.sleep(random.uniform(0, 10))

    # Per-source last-fired timestamps
    last_fired: dict[int, datetime] = {}

    try:
        while True:
            org = store.load_organism(organism_id)
            if not org:
                logger.info(f"[Heartbeat] {organism_id} organism gone, stopping")
                return
            if org.state in (OrganismState.DYING, OrganismState.DEAD):
                logger.info(f"[Heartbeat] {organism_id} state={org.state}, stopping")
                return

            now = datetime.utcnow()
            sources = org.perception_sources or []

            try:
                ns_state = nervous_system.tick(organism_id, {"type": "heartbeat"})
                await events.emit("organism.nervous_tick", {
                    "organism_id": organism_id,
                    "nervous_system": {
                        "phase": ns_state.get("phase"),
                        "mood": ns_state.get("mood"),
                        "needs": ns_state.get("needs", [])[:3],
                        "intentions": ns_state.get("intentions", [])[:3],
                    },
                })
            except Exception as e:
                logger.warning(f"[Heartbeat] {organism_id} nervous system tick failed: {e}")

            for i, src in enumerate(sources):
                kind = src.get("kind")
                interval_s = int(src.get("interval_s", 60))
                last = last_fired.get(i)
                if last and (now - last).total_seconds() < interval_s:
                    continue

                try:
                    if kind == "interval":
                        await _fire_interval(organism_id, src)
                        last_fired[i] = now
                        _last_active[organism_id] = now
                    elif kind == "http_poll":
                        await _fire_http_poll(organism_id, src)
                        last_fired[i] = now
                        _last_active[organism_id] = now
                    elif kind == "github_repo":
                        await _fire_github_repo(organism_id, src)
                        last_fired[i] = now
                        _last_active[organism_id] = now
                    # webhook sources fire externally; nothing to poll here
                except Exception as e:
                    logger.warning(f"[Heartbeat] {organism_id} source {i} ({kind}) failed: {e}")
                    last_fired[i] = now  # back off till next tick

            # Phase 5C: Check for unread society messages — throttled to avoid
            # N organisms all hitting the LLM simultaneously after a broadcast.
            last_check = _last_msg_check.get(organism_id)
            if not last_check or (now - last_check).total_seconds() >= _MSG_CHECK_INTERVAL_S:
                try:
                    await _check_messages(organism_id)
                    _last_msg_check[organism_id] = datetime.utcnow()
                except Exception as e:
                    logger.warning(f"[Heartbeat] {organism_id} message check failed: {e}")
                    _last_msg_check[organism_id] = datetime.utcnow()  # back off

            # Idle dreaming — skipped entirely when GENESIS_DREAMING=0
            from backend.shared.config import settings as _settings
            if _settings.GENESIS_DREAMING:
                idle_after = _settings.GENESIS_IDLE_DREAM_AFTER_S
                last_active = _last_active.get(organism_id, org.born_at)
                if (now - last_active).total_seconds() > idle_after:
                    try:
                        logger.info(f"[Heartbeat] {organism_id} idle → dreaming")
                        await dreams.imagine(
                            organism_id,
                            n=org.dream_budget_per_cycle,
                            event_callback=events.make_callback(),
                        )
                        _last_active[organism_id] = datetime.utcnow()
                    except Exception as e:
                        logger.warning(f"[Heartbeat] {organism_id} dreaming failed: {e}")

            # Jitter prevents all organisms from waking at the same moment
            # when many are alive simultaneously. Demo organisms can opt into
            # a 1s source interval, so keep that path responsive.
            has_fast_source = any(
                int(src.get("interval_s", 60)) <= 1
                for src in sources
                if src.get("kind") in {"interval", "http_poll", "github_repo"}
            )
            await asyncio.sleep(1 if has_fast_source else 2 + random.uniform(0, 3))

    except asyncio.CancelledError:
        logger.info(f"[Heartbeat] {organism_id} cancelled")
        return
    except Exception as e:
        logger.exception(f"[Heartbeat] {organism_id} crashed: {e}")


# ── Source drivers ────────────────────────────────────────────────────

async def _fire_interval(organism_id: str, src: dict) -> None:
    perception = {
        "type": src.get("type", "tick"),
        "source": "interval",
        "payload": src.get("payload", {}),
        "ts": datetime.utcnow().isoformat(),
    }
    await runtime.perceive(
        organism_id, perception, event_callback=events.make_callback(),
    )


async def _fire_github_repo(organism_id: str, src: dict) -> None:
    repo = str(src.get("repo") or "").strip()
    probe_adapter = str(src.get("read_probe") or "github_create_issue")
    if repo:
        probe = await asyncio.to_thread(
            connectors.probe_adapter,
            adapter_id=probe_adapter,
            scope=repo,
            live=True,
        )
    else:
        probe = {
            "status": "fail",
            "checks": [{"name": "repository", "ok": False, "detail": "repo is not configured"}],
        }

    perception = {
        "type": src.get("type", "repo_maintainer_signal"),
        "source": "github_repo",
        "repo": repo,
        "payload": {
            **(src.get("payload") or {}),
            "repo": repo,
            "probe": probe,
            "write_connectors": src.get("write_connectors", []),
            "requires_approval": bool(src.get("requires_approval", True)),
            "no_fake_activity": bool(src.get("no_fake_activity", True)),
        },
        "ts": datetime.utcnow().isoformat(),
    }
    await runtime.perceive(
        organism_id, perception, event_callback=events.make_callback(),
    )


async def _fire_http_poll(organism_id: str, src: dict) -> None:
    url = src["url"]
    method = src.get("method", "GET").upper()
    headers = src.get("headers") or {}
    async with httpx.AsyncClient(timeout=20) as cx:
        r = await cx.request(method, url, headers=headers)
    try:
        body: Any = r.json()
    except Exception:
        body = r.text
        
    # Truncate string representations to prevent context bloat
    body_str = str(body)
    if len(body_str) > 4000:
        body = body_str[:4000] + "... (truncated)"
        
    perception = {
        "type": src.get("type", "http_poll"),
        "source": "http_poll",
        "url": url,
        "status": r.status_code,
        "body": body,
        "ts": datetime.utcnow().isoformat(),
    }
    await runtime.perceive(
        organism_id, perception, event_callback=events.make_callback(),
    )


async def _check_messages(organism_id: str) -> None:
    from . import society
    msgs = store.load_messages(organism_id, unread_only=True)
    if not msgs:
        return
    for msg in msgs:
        perception = {
            "type": "incoming_message",
            "source": "society",
            "sender_id": msg.sender_id,
            "message_type": msg.message_type,
            "payload": msg.content,
        }
        await runtime.perceive(
            organism_id, perception, event_callback=events.make_callback(),
        )
        society.mark_read(organism_id, [msg.id])
        _last_active[organism_id] = datetime.utcnow()
