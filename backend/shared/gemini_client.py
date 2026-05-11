"""Centralized Gemini API client for ForgeFlow.

All LLM calls go through this module. Provides:
- generate_json() — for structured JSON responses
- generate_text() — for free-text responses
- generate_with_tools() — agentic tool-calling loop (browse, shell, write, test)
- get_client() — raw Gemini client access
"""

import collections
import json
import logging
import os
import time
from typing import Any, Callable, Coroutine

from google import genai
from google.genai import types

from backend.shared.config import settings

logger = logging.getLogger("forgeflow.gemini")

_client: genai.Client | None = None
_groq_client = None  # lazy-initialised when provider=groq

MAX_TOOL_ROUNDS = 15  # Safety limit for tool-calling loops

# ── Global LLM rate guard ─────────────────────────────────────────────
# Sliding-window counter across ALL organisms. Prevents bursts from
# many simultaneous heartbeats from exhausting provider quotas.
# Set GENESIS_MAX_LLM_CALLS_PER_MIN=0 (default) to disable.

_call_timestamps: collections.deque = collections.deque()
_max_calls_per_min: int = int(os.getenv("GENESIS_MAX_LLM_CALLS_PER_MIN", "0"))


async def _rate_guard() -> None:
    """Block the caller until the sliding-window allows another LLM call.

    Uses a 60-second sliding window. When the window is full the coroutine
    sleeps just long enough for the oldest call to age out, then proceeds.
    Disabled when GENESIS_MAX_LLM_CALLS_PER_MIN=0 (the default).
    """
    if not _max_calls_per_min:
        return

    import asyncio as _asyncio

    while True:
        now = time.monotonic()
        # Prune calls that have aged out of the 60-second window
        while _call_timestamps and now - _call_timestamps[0] > 60:
            _call_timestamps.popleft()

        if len(_call_timestamps) < _max_calls_per_min:
            _call_timestamps.append(now)
            return

        # Wait for the oldest call to fall outside the window
        wait_s = 60.0 - (now - _call_timestamps[0]) + 0.05
        logger.warning(
            f"[LLM rate guard] {len(_call_timestamps)}/{_max_calls_per_min} calls in "
            f"last 60s — waiting {wait_s:.1f}s before next call"
        )
        await _asyncio.sleep(wait_s)


def rate_guard_stats() -> dict:
    """Snapshot of the sliding-window for the /status endpoint."""
    now = time.monotonic()
    recent = sum(1 for t in _call_timestamps if now - t <= 60)
    return {
        "calls_last_60s": recent,
        "limit_per_min": _max_calls_per_min,
        "guard_active": _max_calls_per_min > 0,
    }


def _get_groq_client():
    """Lazy singleton for the Groq async client."""
    global _groq_client
    if _groq_client is None:
        from groq import AsyncGroq
        _groq_client = AsyncGroq(api_key=settings.GROQ_API_KEY)
    return _groq_client


async def _groq_generate_text(
    prompt: str,
    system: str,
    model: str | None = None,
    temperature: float = 0,
    max_tokens: int = 8000,
) -> str:
    """Call Groq (Llama 3.3 70B) — free tier, OpenAI-compatible.

    Retries up to 3 times with exponential backoff on 429 rate-limit errors.
    """
    import asyncio as _asyncio

    client = _get_groq_client()
    # Never send a Gemini model name to Groq
    if model and "gemini" in model:
        model = settings.GROQ_MODEL

    _model = model or settings.GROQ_MODEL
    _messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]

    max_retries = 3
    base_delay = 5.0  # seconds

    for attempt in range(max_retries + 1):
        try:
            response = await client.chat.completions.create(
                model=_model,
                messages=_messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            err_str = str(e).lower()
            is_rate_limit = "429" in err_str or "rate_limit" in err_str or "rate limit" in err_str
            hard_quota = any(token in err_str for token in ("tokens per day", "requests per day", "quota"))
            if is_rate_limit and not hard_quota and attempt < max_retries:
                delay = base_delay * (2 ** attempt)  # 5s, 10s, 20s
                logger.warning(
                    f"[Groq] 429 rate-limit on attempt {attempt + 1}/{max_retries + 1}. "
                    f"Retrying in {delay:.0f}s…"
                )
                await _asyncio.sleep(delay)
            else:
                raise


async def _gemini_generate_text(
    prompt: str,
    system: str,
    model: str | None = None,
    temperature: float = 0,
    max_tokens: int = 8000,
) -> str:
    """Call Gemini with bounded retry on transient quota/server errors."""
    import asyncio as _asyncio

    client = get_client()
    max_retries = 3
    base_delay = float(os.getenv("GENESIS_LLM_RETRY_BASE_DELAY_S", "5"))

    for attempt in range(max_retries + 1):
        try:
            response = await client.aio.models.generate_content(
                model=model or settings.GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                ),
            )
            return response.text or ""
        except Exception as e:
            err_str = str(e).lower()
            retryable = any(
                token in err_str
                for token in ("429", "rate", "quota", "resource exhausted", "503", "unavailable", "deadline")
            )
            hard_quota = any(token in err_str for token in ("requests per day", "free_tier", "resource exhausted"))
            if retryable and not hard_quota and attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    f"[Gemini] transient provider error on attempt {attempt + 1}/{max_retries + 1}. "
                    f"Retrying in {delay:.0f}s..."
                )
                await _asyncio.sleep(delay)
            else:
                raise


def get_client() -> genai.Client:
    """Get or create the singleton Gemini client."""
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client


async def generate_json(
    prompt: str,
    system: str,
    model: str | None = None,
    temperature: float = 0,
    max_tokens: int = 2000,
) -> dict:
    """Call Gemini and return parsed JSON.

    Uses response_mime_type="application/json" to enforce JSON output.
    """
    client = get_client()

    response = await client.aio.models.generate_content(
        model=model or settings.GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            temperature=temperature,
            max_output_tokens=max_tokens,
        ),
    )

    try:
        return json.loads(response.text)
    except (json.JSONDecodeError, AttributeError) as e:
        logger.error(f"Failed to parse Gemini JSON response: {e}")
        logger.debug(f"Raw response: {response.text[:500] if response.text else 'None'}")
        return {}


async def generate_text(
    prompt: str,
    system: str = "",
    model: str | None = None,
    temperature: float = 0,
    max_tokens: int = 8000,
) -> str:
    """Call the configured LLM and return plain text.

    Routes to Groq (free, Llama 3.3 70B) when GENESIS_LLM_PROVIDER=groq,
    otherwise uses Gemini (default, for demo/prod).

    All calls pass through the global rate guard (GENESIS_MAX_LLM_CALLS_PER_MIN).
    """
    provider = settings.GENESIS_LLM_PROVIDER.lower()
    if provider == "mock" or (
        provider == "gemini" and not settings.GEMINI_API_KEY
    ) or (
        provider == "groq" and not settings.GROQ_API_KEY
    ):
        return _mock_generate_text(prompt=prompt, system=system)

    await _rate_guard()

    if provider == "groq":
        return await _groq_generate_text(prompt, system, model, temperature, max_tokens)

    return await _gemini_generate_text(prompt, system, model, temperature, max_tokens)


def _mock_generate_text(prompt: str, system: str = "") -> str:
    """Deterministic local LLM stand-in for demos, tests, and no-key setup.

    It preserves the JSON contracts expected by the runtime, critic, dreamer,
    distiller, and compiler so the product can run end-to-end before API keys
    are configured.
    """
    lower_system = system.lower()
    lower_prompt = prompt.lower()

    if "python mcp server code generator" in lower_system:
        return '''from mcp.server.fastmcp import FastMCP

server = FastMCP("mock_compiled_skill")

@server.tool()
async def apply_skill(context: str = "") -> dict:
    """Apply a locally compiled Genesis skill."""
    return {"ok": True, "summary": context[:500]}

if __name__ == "__main__":
    server.run()
'''

    if "distilling a digital organism" in lower_system:
        return json.dumps({
            "name": "local_distilled_skill",
            "description": "A deterministic skill distilled by the local mock provider.",
            "trigger_patterns": ["task", "test_event"],
            "forbidden_patterns": [],
            "body": (
                "# What this knows\n"
                "- Work from the organism intent and current perception.\n\n"
                "# What worked\n"
                "- Prefer safe, explicit actions with readable reasoning.\n\n"
                "# What failed\n"
                "- Avoid inventing unavailable tools.\n\n"
                "# Patterns observed\n"
                "- Record decisions so later organisms can inherit context.\n"
            ),
        })

    if "plausible-but-not-yet-occurred" in lower_system:
        return json.dumps([
            {"type": "mock_future", "payload": {"case": "common"}},
            {"type": "mock_edge_case", "payload": {"case": "edge"}},
        ])

    if "meta-cognitive critic" in lower_system:
        return json.dumps({
            "reasoning_quality": 0.72,
            "attention_gaps": [],
            "action_efficiency": 0.68,
            "repeated_mistake": False,
            "lesson": "Choose the smallest available action that advances the intent.",
            "knowledge_gaps": [],
            "recommended_strategy": "systematic",
            "strategy_performance_delta": 0.1,
            "confidence": 0.76,
        })

    if "genesis multi-agent debate participant" in lower_system:
        agent_name = "Debate Agent"
        try:
            payload = json.loads(prompt)
            agent_name = payload.get("agent", {}).get("name") or agent_name
            stance = payload.get("agent", {}).get("stance") or "Analyze the topic carefully."
            topic = payload.get("topic") or "the requested topic"
        except Exception:
            stance = "Analyze the topic carefully."
            topic = "the requested topic"
        return json.dumps({
            "recommendation": (
                f"{agent_name} recommends advancing '{topic}' with a narrow, testable implementation "
                f"that honors its role: {stance}"
            ),
            "evidence": [
                "The system already has organisms, memory, tools, and benchmark phases to build on.",
                "A bounded debate loop can be audited and repeated without changing external state.",
            ],
            "risks": [
                "Agents may converge too early without explicit critique.",
                "The synthesis can overstate confidence if proposals are weak.",
            ],
            "tests": [
                "Run a debate through the API and confirm proposals, critiques, and synthesis are persisted.",
                "Verify the browser UI can start a debate and render the audit trail.",
            ],
            "confidence": 0.72,
        })

    if "genesis multi-agent debate critic" in lower_system:
        try:
            payload = json.loads(prompt)
            proposals = payload.get("proposals_to_review") or []
            target = proposals[0] if proposals else {}
        except Exception:
            target = {}
        return json.dumps({
            "target_agent_id": target.get("agent_id"),
            "strongest_point": "The proposal is concrete enough to test.",
            "weakest_point": "It needs sharper acceptance criteria and a clearer rollback path.",
            "revision": "Add measurable success criteria, failure handling, and a browser/API verification step.",
            "score": 0.68,
        })

    if "genesis multi-agent debate synthesis judge" in lower_system:
        try:
            payload = json.loads(prompt)
            topic = payload.get("topic") or "the requested topic"
            proposals = payload.get("scored_proposals") or []
            top = proposals[0] if proposals else {}
        except Exception:
            topic = "the requested topic"
            top = {}
        return json.dumps({
            "decision": (
                f"Proceed with the review-board workflow for '{topic}' as an auditable multi-agent debate room: "
                "independent proposals, adversarial critique, ranked synthesis, and persisted run history."
            ),
            "consensus": [
                "Use multiple specialist perspectives instead of a single response path.",
                "Keep every proposal and critique inspectable.",
                "Validate through API and browser flows.",
            ],
            "dissent": [
                "Confidence should remain bounded until debates are compared against real task outcomes.",
            ],
            "risks": [
                "Synthetic agreement can hide missing evidence.",
                "Too many agents can increase latency and cost.",
            ],
            "next_actions": [
                "Expose debate runs in the UI.",
                "Persist debate conclusions into long-term memory.",
                "Add regression tests around the debate API contract.",
            ],
            "confidence": max(0.65, min(0.82, float(top.get("debate_score", 0.72) or 0.72))),
        })

    if "genesis self-improvement proposer" in lower_system:
        try:
            payload = json.loads(prompt)
            objective = payload.get("objective") or "Improve Genesis safely"
        except Exception:
            objective = "Improve Genesis safely"
        return json.dumps({
            "title": "Strict promotion gate for self-improvement",
            "problem": (
                "Genesis can generate improvement ideas, but without strict gates it could promote "
                "changes before benchmark evidence, regression controls, and rollback plans are clear."
            ),
            "hypothesis": (
                f"For objective '{objective}', requiring benchmark delta, passing checks, safety review, "
                "and rollback evidence before promotion will reduce unsafe regressions."
            ),
            "change_summary": (
                "Evaluate each proposed improvement through deterministic gates before it can be marked "
                "approved for experiment."
            ),
            "expected_metrics": {
                "benchmark_delta": 0.04,
                "regression_risk": 0.18,
            },
            "tests": [
                "Unit contract test for passing and failing gates.",
                "Production build check for the improvement-gates panel.",
                "Browser run confirming visible gate verdicts.",
            ],
            "rollback_plan": "Keep the candidate blocked unless gates pass; rollback by discarding the run record or reverting the candidate branch.",
            "safety_notes": [
                "No autonomous deployment.",
                "Human review remains required after gates pass.",
                "High-risk intents are blocked by deterministic terms.",
            ],
            "confidence": 0.78,
        })

    if "genesis autonomous operator planner" in lower_system:
        try:
            payload = json.loads(prompt)
            tick_count = int(payload.get("operator", {}).get("tick_count") or 0)
            goal = payload.get("operator", {}).get("goal") or "Maintain Genesis"
        except Exception:
            tick_count = 0
            goal = "Maintain Genesis"
        if tick_count % 3 == 0:
            return json.dumps({
                "action": "evaluate_improvement",
                "rationale": "The safest autonomous progress is to evaluate a bounded improvement through strict gates.",
                "args": {
                    "objective": f"Autonomously improve progress toward: {goal}",
                    "evidence": {
                        "benchmark_delta": 0.03,
                        "regression_risk": 0.2,
                        "confidence": 0.72,
                        "checks": {"unit": True, "build": True, "browser": True},
                        "tests": ["operator tick audit", "strict gate evaluation"],
                    },
                },
                "confidence": 0.72,
            })
        return json.dumps({
            "action": "record_checkpoint",
            "rationale": "Record a reversible checkpoint and wait for the next cadence.",
            "args": {},
            "confidence": 0.68,
        })

    action = {"name": "noop", "args": {}}
    reasoning = "Local mock reasoning selected a safe no-op because no external action was required."
    if "declare_done" in lower_prompt and ("done" in lower_prompt or "satisfied" in lower_prompt):
        action = {"name": "declare_done", "args": {"summary": "Completed by local mock provider."}}
        reasoning = "The current perception appears to satisfy the organism intent."
    elif "remember" in lower_prompt:
        action = {"name": "remember", "args": {"pattern": "Use local mock mode for deterministic offline validation."}}
        reasoning = "Recording a durable pattern is the safest useful action for this perception."

    return json.dumps({
        "reasoning": reasoning,
        "action": action,
        "alternatives": [
            {"name": "noop", "args": {}, "why_not": "Less informative than the selected action."},
            {"name": "declare_done", "args": {"summary": "Not yet confirmed."}, "why_not": "Intent completion is not explicit."},
        ],
    })


async def generate_with_tools(
    prompt: str,
    system: str,
    tools_config: types.Tool,
    tool_executor: Callable,
    project_dir: str = "/tmp/forgeflow_project",
    model: str | None = None,
    temperature: float = 0,
    max_tokens: int = 8000,
    on_tool_call: Callable | None = None,
) -> tuple[str, dict[str, str]]:
    """Agentic tool-calling loop — the heart of ForgeFlow's agent capability.

    Calls the LLM with tools. When the LLM returns tool_calls instead of
    text, we execute them, feed results back, and loop until the LLM
    returns its final text response.

    Args:
        prompt: The user/system prompt
        system: System instruction
        tools_config: Gemini Tool with function declarations
        tool_executor: async fn(tool_name, tool_args, project_dir) -> str
        project_dir: Working directory for file/shell tools
        model: Gemini model override
        temperature: LLM temperature
        max_tokens: Max output tokens per round
        on_tool_call: Optional callback(tool_name, tool_args, result) for UI events

    Returns:
        (final_text, extra_files) where extra_files is a dict of
        {relative_path: content} for any files written via write_file tool.
    """
    client = get_client()
    extra_files: dict[str, str] = {}

    # Build initial contents
    contents = [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]

    for round_num in range(MAX_TOOL_ROUNDS):
        logger.info(f"[Agent] Round {round_num + 1}/{MAX_TOOL_ROUNDS}")

        response = await client.aio.models.generate_content(
            model=model or settings.GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system,
                tools=[tools_config],
                temperature=temperature,
                max_output_tokens=max_tokens,
            ),
        )

        # Check if response has function calls
        candidate = response.candidates[0] if response.candidates else None
        if not candidate:
            logger.warning("[Agent] No candidate in response")
            break
        if not candidate.content:
            logger.warning("[Agent] No content in candidate (finish_reason=%s)", getattr(candidate, 'finish_reason', 'unknown'))
            break
        if not candidate.content.parts:
            logger.warning("[Agent] No parts in content")
            break

        parts = candidate.content.parts

        # Collect all function calls in this response
        function_calls = [p for p in parts if p.function_call]
        text_parts = [p for p in parts if p.text]

        if not function_calls:
            # No tool calls — LLM is done, return the text
            final_text = "\n".join(p.text for p in text_parts if p.text)
            logger.info(f"[Agent] Done after {round_num + 1} rounds, {len(extra_files)} files written")
            return final_text, extra_files

        # Add the model's response (with function calls) to contents
        contents.append(candidate.content)

        # Execute each function call and collect responses
        function_response_parts = []
        for part in function_calls:
            fc = part.function_call
            tool_name = fc.name
            tool_args = dict(fc.args) if fc.args else {}

            logger.info(f"[Agent] Tool call: {tool_name}({list(tool_args.keys())})")

            # Execute the tool
            result = await tool_executor(tool_name, tool_args, project_dir)

            # Track written files — normalize and reject path-traversal attempts
            if tool_name == "write_file" and tool_args.get("path"):
                from backend.shared.path_security import normalize_relative_path
                try:
                    safe_path = normalize_relative_path(tool_args["path"])
                    extra_files[safe_path] = tool_args.get("content", "")
                except ValueError:
                    logger.warning(f"[Agent] Rejected unsafe write_file path: {tool_args['path']!r}")

            # Notify UI
            if on_tool_call:
                try:
                    await on_tool_call(tool_name, tool_args, result)
                except Exception:
                    pass

            # Build function response part
            function_response_parts.append(
                types.Part.from_function_response(
                    name=tool_name,
                    response={"result": result[:6000]},  # Truncate for context window
                )
            )

        # Add all function responses as a single user turn
        contents.append(
            types.Content(role="user", parts=function_response_parts)
        )

    # Safety: hit max rounds
    logger.warning(f"[Agent] Hit max {MAX_TOOL_ROUNDS} tool rounds, returning last text")
    # Try to extract any text from the last response
    last_text = ""
    if response and response.candidates:
        for part in response.candidates[0].content.parts:
            if part.text:
                last_text += part.text
    return last_text, extra_files
