"""Persistent *new-tool* state; never reads NeoBot's real chat history.

Host integration (none of these methods is exposed in definitions/execute):
* Mint ToolContext from trusted credentials; consume root human intent upstream.
* Deliver ask_user_question's pending id/questions to the user, then call
  record_answer with a NEW authenticated message (answer maps question ids to
  strings/string lists). record_answer requires context.human_request and binds
  requester user_id. The host is responsible for authenticating message_id.
* Deliver exit_plan_mode's plan for approval. Inject approve(context, plan_dict)
  -> bool | None (possibly awaitable), or call record_plan_decision after
  consuming an authenticated approval. None means still pending, not approved.
* After an agent turn, reserve next_goal_round; run that round using ordinary
  non-human context; finally record_goal_round, including errors/cancellation.
  These are scheduling primitives, NOT a background agent loop. Recovery never
  schedules anything: a new root-human resume is required after restart.
* Call cancel_pending when the host cancels a session/agent. Call record_event
  after NEW tool calls/host state transitions; execute does not auto-audit.
  Audit stores structural metadata, not prompts, answers, secrets, or source.

Use one recovering instance per state directory at process startup. Additional
connections to an already-live store must use recover=False. All mutation/CAS
runs inside SQLite BEGIN IMMEDIATE; never hold a transaction across await.
State is scoped by owner/chat/agent; audit by owner/chat (all agents of that chat).
"""
from __future__ import annotations

import asyncio
import inspect
import json
import re
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

from .contracts import AgentToolError, ToolContext, tool_definition


_MAX_JSON = 65_536
_STATUSES = {"pending", "in_progress", "completed"}
_SAFE_VALUES = _STATUSES | {"active", "paused", "blocked", "complete", "armed", "disarmed",
    "approved", "rejected", "interrupted", "cancelled", "answered", "continue", "error"}
_SAFE_KEYS = {"status", "phase", "action", "activation", "revision", "max_goal_rounds",
    "rounds_started", "count", "limit", "offset", "before", "after", "goal", "todos",
    "questions", "result", "results", "events", "error", "code", "ok", "approved",
    "counts", "pending", "in_progress", "completed", "round", "outcome"}


def _fail(code: str, message: str) -> None:
    raise AgentToolError(code, message)


def _text(value: Any, label: str, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        _fail("invalid_arguments", f"{label} must be a nonempty string of at most {maximum} characters")
    return value


def _integer(value: Any, label: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        _fail("invalid_arguments", f"{label} must be an integer between {minimum} and {maximum}")
    return value


def _json(value: Any, maximum: int = _MAX_JSON) -> str:
    try:
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError, RecursionError):
        _fail("invalid_arguments", "Expected finite JSON data")
    if len(raw.encode("utf-8")) > maximum:
        _fail("limit_exceeded", "JSON payload exceeds the size limit")
    return raw


def _root(context: ToolContext, human: bool = False) -> None:
    if context.depth != 0 or context.parent_agent_id is not None or (human and not context.human_request):
        _fail("permission_denied", "This operation requires trusted root human intent" if human
              else "This operation requires the root agent")


def _metadata(value: Any, depth: int = 0, budget: list[int] | None = None) -> Any:
    """Deliberately lossy, bounded allowlist; even dictionary keys may be secrets."""
    if budget is None:
        budget = [80]
    if budget[0] <= 0:
        return {"omitted": True}
    budget[0] -= 1
    if depth >= 4:
        return {"omitted": True}
    if value is None or type(value) is bool:
        return value
    if type(value) in (int, float):
        return {"type": "number"}
    if isinstance(value, str):
        return {"type": "string", "length": min(len(value), 1_000_000)}
    if isinstance(value, list):
        items = []
        for item in value[:8]:
            if budget[0] <= 0:
                break
            items.append(_metadata(item, depth + 1, budget))
        return {"count": len(value), "items": items}
    if isinstance(value, dict):
        result = {}
        for key in sorted(key for key in _SAFE_KEYS if key in value)[:24]:
            if budget[0] <= 0:
                break
            item = value[key]
            result[key] = item if key in {"status", "phase", "action", "activation", "outcome"} and isinstance(item, str) and item in _SAFE_VALUES else _metadata(item, depth + 1, budget)
        result["omitted_fields"] = len(value) - len(result)
        return result
    return {"type": "unsupported"}


class StateTools:
    def __init__(self, state_dir: Path, *, approve: Callable[..., Any] | None = None,
                 max_goal_rounds: int = 25, max_events_per_scope: int = 2000,
                 recover: bool = True) -> None:
        self.max_goal_rounds = _integer(max_goal_rounds, "max_goal_rounds", 1, 100)
        self.max_events = _integer(max_events_per_scope, "max_events_per_scope", 1, 100_000)
        self.approve = approve
        self._lock = threading.RLock()
        state_dir = Path(state_dir)
        state_dir.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(state_dir / "agent_state.sqlite3", timeout=10, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS state (
                owner TEXT NOT NULL, chat TEXT NOT NULL, agent TEXT NOT NULL, document TEXT NOT NULL,
                PRIMARY KEY(owner,chat,agent));
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, owner TEXT NOT NULL, chat TEXT NOT NULL,
                agent TEXT NOT NULL, name TEXT NOT NULL, created_at REAL NOT NULL, metadata TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS events_scope ON events(owner,chat,id);
            CREATE TABLE IF NOT EXISTS receipts (
                owner TEXT NOT NULL, chat TEXT NOT NULL, message_id TEXT NOT NULL,
                PRIMARY KEY(owner,chat,message_id));
        """)
        if recover:
            with self._transaction():
                for row in self._db.execute("SELECT * FROM state").fetchall():
                    doc = json.loads(row["document"])
                    self._interrupt(doc, "restart")
                    self._db.execute("UPDATE state SET document=? WHERE owner=? AND chat=? AND agent=?",
                                     (_json(doc, 1_048_576), row["owner"], row["chat"], row["agent"]))

    def close(self) -> None:
        with self._lock:
            self._db.close()

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                yield
                self._db.commit()
            except BaseException:
                self._db.rollback()
                raise

    @staticmethod
    def _scope(context: ToolContext) -> tuple[str, str, str]:
        if not isinstance(context, ToolContext):
            _fail("permission_denied", "A trusted ToolContext is required")
        return (_text(context.owner, "owner", 256), _text(context.chat_flow_id, "chat", 256),
                _text(context.agent_id, "agent", 256))

    def _load(self, context: ToolContext) -> dict:
        row = self._db.execute("SELECT document FROM state WHERE owner=? AND chat=? AND agent=?",
                               self._scope(context)).fetchone()
        return json.loads(row[0]) if row else {"todos": [], "questions": [], "plan": None, "goal": None}

    def _save(self, context: ToolContext, doc: dict) -> None:
        self._db.execute("INSERT INTO state VALUES(?,?,?,?) ON CONFLICT(owner,chat,agent) "
                         "DO UPDATE SET document=excluded.document", (*self._scope(context), _json(doc, 1_048_576)))

    @staticmethod
    def definitions() -> list[dict]:
        string = {"type": "string"}
        integer = {"type": "integer"}
        question = {"type": "object", "additionalProperties": False, "required": ["id", "question"],
                    "properties": {"id": string, "question": string, "header": string,
                                   "multi_select": {"type": "boolean"}, "options": {"type": "array", "maxItems": 12,
                                   "items": {"type": "object", "additionalProperties": False,
                                   "required": ["label"], "properties": {"label": string, "description": string}}}}}
        specs = [
            ("todo_write", "Replace the COMPLETE todo list, using pending/in_progress/completed.",
             {"todos": {"type": "array", "maxItems": 100, "items": {"type": "object", "additionalProperties": False,
              "required": ["content", "status"], "properties": {"content": string, "status": {"type": "string", "enum": sorted(_STATUSES)}}}}}, ["todos"]),
            ("ask_user_question", "Persist questions; returns pending id, NOT a user answer. Host delivers and records replies.",
             {"questions": {"type": "array", "minItems": 1, "maxItems": 8, "items": question}}, ["questions"]),
            ("question_status", "Read a pending question or a genuine host-recorded answer.", {"question_id": string}, ["question_id"]),
            ("enter_plan_mode", "Enter persistent planning mode.", {}, []),
            ("exit_plan_mode", "Submit complete plan for host approval; pending is NOT approval.", {"plan": string}, ["plan"]),
            ("create_goal", "Create one root-human goal and arm host scheduling; does not itself run an agent loop.",
             {"objective": string, "max_goal_rounds": integer}, ["objective"]),
            ("get_goal", "Read current goal revision and activation before updating.", {}, []),
            ("update_goal", "CAS update. create/edit/pause/resume require root human intent; blocked needs 3 host-recorded same blockers.",
             {"goal_id": string, "revision": integer, "action": {"type": "string", "enum": ["edit", "pause", "resume", "complete", "blocked"]},
              "objective": string, "max_goal_rounds": integer, "blocked_reason": string}, ["goal_id", "revision", "action"]),
            ("session_event_read", "Read one new-tool audit event in this owner/chat only; never real chat history.", {"event_id": integer}, ["event_id"]),
        ]
        for name in ("session_search", "session_event_search", "session_event_trace", "session_trace"):
            specs.append((name, "Query bounded new-tool audit metadata in this owner/chat only, not actual conversation history.",
                          {"query": string, "limit": integer, "before": integer}, []))
        return [tool_definition(*spec) for spec in specs]

    async def execute(self, name: str, args: dict, context: ToolContext) -> dict:
        self._scope(context)
        definitions = {d["function"]["name"]: d["function"]["parameters"] for d in self.definitions()}
        if name not in definitions:
            _fail("unknown_tool", "Unknown state tool (host APIs are not model tools)")
        schema = definitions[name]
        if not isinstance(args, dict) or set(args) - set(schema["properties"]) or set(schema["required"]) - set(args):
            _fail("invalid_arguments", "Unknown or missing arguments; authority comes only from ToolContext")
        _json(args)
        if name in {"session_search", "session_event_search", "session_event_trace", "session_trace", "session_event_read"}:
            return self._query(name, args, context)
        with self._transaction():
            doc = self._load(context)
            if name == "todo_write":
                todos = args["todos"]
                if not isinstance(todos, list) or len(todos) > 100:
                    _fail("invalid_arguments", "todos must be a list of at most 100 entries")
                for item in todos:
                    if not isinstance(item, dict) or set(item) != {"content", "status"}:
                        _fail("invalid_arguments", "Each todo needs exactly content and status")
                    _text(item["content"], "content", 1000)
                    if not isinstance(item["status"], str) or item["status"] not in _STATUSES:
                        _fail("invalid_arguments", "Invalid todo status")
                doc["todos"] = todos
                result = {"todos": todos, "counts": {s: sum(t["status"] == s for t in todos) for s in sorted(_STATUSES)}}
            elif name == "ask_user_question":
                questions = self._questions(args["questions"])
                pending = [q for q in doc["questions"] if q["status"] in {"pending", "interrupted"}]
                if len(pending) >= 20:
                    _fail("limit_exceeded", "At most 20 outstanding question requests per agent")
                item = {"question_id": uuid.uuid4().hex, "questions": questions, "status": "pending",
                        "user_id": context.user_id, "parent_agent_id": context.parent_agent_id,
                        "depth": context.depth, "created_at": time.time()}
                doc["questions"] = (pending + [q for q in doc["questions"] if q not in pending][-79:] + [item])
                result = dict(item)
            elif name == "question_status":
                result = dict(self._question(doc, args["question_id"]))
            elif name == "enter_plan_mode":
                if doc["plan"] and doc["plan"]["status"] == "pending":
                    _fail("conflict", "An approval is already pending")
                doc["plan"] = {"plan_id": uuid.uuid4().hex, "status": "planning", "user_id": context.user_id}
                result = dict(doc["plan"])
            elif name == "exit_plan_mode":
                plan = _text(args["plan"], "plan", 24_000)
                if not doc["plan"] or doc["plan"]["status"] not in {"planning", "pending"}:
                    _fail("invalid_state", "Enter plan mode before submitting a plan")
                if doc["plan"]["status"] == "pending" and doc["plan"]["plan"] != plan:
                    _fail("conflict", "Cannot replace a plan while approval is pending")
                doc["plan"].update(status="pending", plan=plan)
                result = dict(doc["plan"])
            elif name == "create_goal":
                _root(context, human=True)
                if doc["goal"] and (doc["goal"]["phase"] != "complete" or doc["goal"]["pending_round_id"]):
                    _fail("conflict", "A non-complete goal already exists")
                doc["goal"] = {"goal_id": uuid.uuid4().hex, "revision": 1,
                    "objective": _text(args["objective"], "objective", 8000), "phase": "active", "armed": True,
                    "max_goal_rounds": _integer(args.get("max_goal_rounds", self.max_goal_rounds), "max_goal_rounds", 1, self.max_goal_rounds),
                    "rounds_started": 0, "rounds": [], "pending_round_id": None, "blocker_streak": 0, "last_blocker": None}
                result = self._goal_result(doc)
            elif name == "get_goal":
                result = self._goal_result(doc)
            else:
                result = self._update_goal(doc, args, context)
            self._save(context, doc)
        if name == "exit_plan_mode" and self.approve is not None:
            try:
                decision = self.approve(context, dict(result))
                if inspect.isawaitable(decision):
                    decision = await decision
                if decision is not None and type(decision) is not bool:
                    _fail("invalid_approval", "Approval callback must return bool or None")
                if decision is not None:
                    return self._plan_decision(context, result["plan_id"], decision)
            except asyncio.CancelledError:
                # Missing credentials/errors leave pending for retry, cancellation interrupts.
                with self._transaction():
                    doc = self._load(context)
                    if doc["plan"] and doc["plan"]["plan_id"] == result["plan_id"] and doc["plan"]["status"] == "pending":
                        doc["plan"]["status"] = "interrupted"
                        self._save(context, doc)
                raise
        return result

    @staticmethod
    def _questions(questions: Any) -> list[dict]:
        if not isinstance(questions, list) or not 1 <= len(questions) <= 8:
            _fail("invalid_arguments", "Supply 1 to 8 questions")
        seen = set()
        for q in questions:
            if not isinstance(q, dict) or set(q) - {"id", "question", "header", "options", "multi_select"}:
                _fail("invalid_arguments", "Invalid question fields")
            qid = _text(q.get("id"), "question id", 64)
            if qid in seen:
                _fail("invalid_arguments", "Question ids must be unique")
            seen.add(qid)
            _text(q.get("question"), "question", 2000)
            if "header" in q:
                _text(q["header"], "header", 100)
            if "multi_select" in q and type(q["multi_select"]) is not bool:
                _fail("invalid_arguments", "multi_select must be boolean")
            options = q.get("options", [])
            if not isinstance(options, list) or len(options) > 12:
                _fail("invalid_arguments", "At most 12 options per question")
            labels = set()
            for option in options:
                if not isinstance(option, dict) or set(option) - {"label", "description"}:
                    _fail("invalid_arguments", "Invalid option fields")
                label = _text(option.get("label"), "option label", 200)
                if label in labels:
                    _fail("invalid_arguments", "Option labels must be unique")
                labels.add(label)
                if "description" in option:
                    _text(option["description"], "option description", 1000)
        return questions

    @staticmethod
    def _question(doc: dict, question_id: str) -> dict:
        _text(question_id, "question_id", 64)
        for q in doc["questions"]:
            if q["question_id"] == question_id:
                return q
        _fail("not_found", "Question not found in this scope")

    def _receipt(self, context: ToolContext, message_id: str) -> None:
        _text(message_id, "message_id", 256)
        if not context.human_request:
            _fail("permission_denied", "Host must authenticate a fresh human reply")
        try:
            self._db.execute("INSERT INTO receipts VALUES(?,?,?)", (context.owner, context.chat_flow_id, message_id))
        except sqlite3.IntegrityError:
            _fail("conflict", "This host message has already been consumed")

    def record_answer(self, context: ToolContext, question_id: str, answer: dict | str, message_id: str) -> dict:
        """Host only: answer maps ids to text/list, or one string for a single question."""
        _json(answer, 16_384)
        with self._transaction():
            doc = self._load(context)
            question = self._question(doc, question_id)
            if question["status"] not in {"pending", "interrupted"}:
                _fail("conflict", "Question is no longer awaiting an answer")
            if question["user_id"] is not None and question["user_id"] != context.user_id:
                _fail("permission_denied", "Only the original requesting user may answer")
            if isinstance(answer, str) and len(question["questions"]) == 1:
                answer = {question["questions"][0]["id"]: answer}
            if not isinstance(answer, dict) or set(answer) != {q["id"] for q in question["questions"]}:
                _fail("invalid_arguments", "Answer must map every requested question id to text or text lists")
            for q in question["questions"]:
                value = answer[q["id"]]
                if isinstance(value, list):
                    if not 1 <= len(value) <= (12 if q.get("multi_select") else 1):
                        _fail("invalid_arguments", "Invalid number of selections")
                    for item in value:
                        _text(item, "answer", 2000)
                else:
                    _text(value, "answer", 2000)
            self._receipt(context, message_id)
            question.update(status="answered", answer=answer, message_id=message_id, answered_at=time.time())
            self._save(context, doc)
            return dict(question)

    def record_plan_decision(self, context: ToolContext, plan_id: str, approved: bool, message_id: str) -> dict:
        """Host only, after consuming the parent's approval credential."""
        return self._plan_decision(context, plan_id, approved, message_id)

    def _plan_decision(self, context: ToolContext, plan_id: str, approved: bool, message_id: str | None = None) -> dict:
        _text(plan_id, "plan_id", 64)
        if type(approved) is not bool:
            _fail("invalid_arguments", "approved must be boolean")
        with self._transaction():
            doc = self._load(context)
            plan = doc["plan"]
            if not plan or plan["plan_id"] != plan_id:
                _fail("not_found", "Plan not found in this scope")
            if plan["status"] != "pending":
                _fail("conflict", "Plan is not awaiting approval; resubmit after interruption")
            if message_id is not None:
                if plan.get("user_id") is not None and plan["user_id"] != context.user_id:
                    _fail("permission_denied", "Only the original requesting user may approve")
                self._receipt(context, message_id)
            plan.update(status="approved" if approved else "rejected", approved=approved)
            self._save(context, doc)
            return dict(plan)

    @staticmethod
    def _goal_result(doc: dict) -> dict:
        goal = doc["goal"]
        return {"goal": json.loads(_json(goal)), "activation": "armed" if goal and goal["armed"] else "disarmed"}

    def _update_goal(self, doc: dict, args: dict, context: ToolContext) -> dict:
        _root(context)
        action = args["action"]
        if not isinstance(action, str) or action not in {"edit", "pause", "resume", "complete", "blocked"}:
            _fail("invalid_arguments", "Unknown goal action")
        if action in {"edit", "pause", "resume"}:
            _root(context, human=True)
        if (set(args) & {"objective", "max_goal_rounds"}) and action != "edit":
            _fail("invalid_arguments", "objective/max_goal_rounds are only valid for edit")
        if "blocked_reason" in args and action != "blocked":
            _fail("invalid_arguments", "blocked_reason is only valid for blocked")
        goal = doc["goal"]
        _text(args["goal_id"], "goal_id", 64)
        _integer(args["revision"], "revision", 1, 2**53 - 1)
        if not goal or goal["goal_id"] != args["goal_id"]:
            _fail("not_found", "Goal not found in this scope")
        if goal["revision"] != args["revision"]:
            _fail("version_conflict", "Goal revision changed; get_goal and retry with the current revision")
        if goal["phase"] == "complete":
            _fail("invalid_state", "Completed goals cannot be resumed or edited; create a new goal")
        if action == "edit":
            if goal["pending_round_id"]:
                _fail("conflict", "Finish or cancel the pending round before editing its objective/budget")
            if "objective" in args:
                goal["objective"] = _text(args["objective"], "objective", 8000)
                goal.update(blocker_streak=0, last_blocker=None)
            if "max_goal_rounds" in args:
                goal["max_goal_rounds"] = _integer(args["max_goal_rounds"], "max_goal_rounds", max(1, goal["rounds_started"]), self.max_goal_rounds)
            if goal["rounds_started"] >= goal["max_goal_rounds"]:
                goal["armed"] = False
        elif action == "resume":
            if goal["pending_round_id"]:
                _fail("conflict", "A goal round is already running")
            if goal["rounds_started"] >= goal["max_goal_rounds"]:
                _fail("budget_exhausted", "Goal round budget exhausted; a human may edit the budget")
            goal.update(phase="active", armed=True, blocker_streak=0, last_blocker=None)
            goal.pop("blocked_reason", None)
        else:
            if action == "blocked":
                reason = _text(args.get("blocked_reason"), "blocked_reason", 2000)
                if goal["blocker_streak"] < 3 or goal["last_blocker"] != reason:
                    _fail("insufficient_rounds", "Same blocker must be recorded by the host in 3 consecutive rounds")
                goal["blocked_reason"] = reason
            goal.update(phase={"pause": "paused", "complete": "complete", "blocked": "blocked"}[action], armed=False)
        goal["revision"] += 1
        return self._goal_result(doc)

    def next_goal_round(self, context: ToolContext) -> dict:
        """Host only: atomically reserve one continuation; call record_goal_round finally.

        Returns round=None when disarmed/busy/exhausted. Reservation consumes one
        budget unit even if execution is later interrupted. Never pass human_request
        from the initiating message to the autonomous agent round.
        """
        _root(context)
        with self._transaction():
            doc = self._load(context)
            goal = doc["goal"]
            if not goal or goal["phase"] != "active" or not goal["armed"] or goal["pending_round_id"] or goal["rounds_started"] >= goal["max_goal_rounds"]:
                return {"round": None, **self._goal_result(doc)}
            goal["rounds_started"] += 1
            item = {"round_id": uuid.uuid4().hex, "number": goal["rounds_started"], "status": "pending", "started_at": time.time()}
            goal["rounds"].append(item)
            goal.update(pending_round_id=item["round_id"], armed=False, revision=goal["revision"] + 1)
            self._save(context, doc)
            return {"round": dict(item), **self._goal_result(doc)}

    def record_goal_round(self, context: ToolContext, round_id: str, outcome: str,
                          blocker_reason: str | None = None) -> dict:
        """Host only: outcome continue/complete/blocked/error/cancelled.

        'blocked' records evidence, continues below 3 identical consecutive reports,
        then marks blocked. Host, not worker/model, owns the truth of outcomes.
        Errors/cancellation disarm; a fresh root-human resume is required.
        """
        _root(context)
        _text(round_id, "round_id", 64)
        if not isinstance(outcome, str) or outcome not in {"continue", "complete", "blocked", "error", "cancelled"}:
            _fail("invalid_arguments", "Invalid round outcome")
        if outcome == "blocked":
            _text(blocker_reason, "blocker_reason", 2000)
        elif blocker_reason is not None:
            _fail("invalid_arguments", "blocker_reason is only valid for blocked")
        with self._transaction():
            doc = self._load(context)
            goal = doc["goal"]
            if not goal or goal["pending_round_id"] != round_id:
                _fail("conflict", "No matching pending round in this scope")
            item = goal["rounds"][-1]
            item.update(status=outcome, finished_at=time.time())
            goal["pending_round_id"] = None
            if outcome == "blocked":
                goal["blocker_streak"] = goal["blocker_streak"] + 1 if goal["last_blocker"] == blocker_reason else 1
                goal["last_blocker"] = blocker_reason
            else:
                goal.update(blocker_streak=0, last_blocker=None)
            # A late worker result must not undo a human pause/complete/block.
            if goal["phase"] == "active":
                if outcome == "complete":
                    goal["phase"] = "complete"
                elif outcome == "blocked" and goal["blocker_streak"] >= 3:
                    goal.update(phase="blocked", blocked_reason=blocker_reason)
            goal["armed"] = goal["phase"] == "active" and outcome in {"continue", "blocked"} and goal["rounds_started"] < goal["max_goal_rounds"]
            goal["revision"] += 1
            self._save(context, doc)
            return self._goal_result(doc)

    @staticmethod
    def _interrupt(doc: dict, reason: str) -> None:
        status = "interrupted" if reason == "restart" else "cancelled"
        for question in doc["questions"]:
            if question["status"] in {"pending", "interrupted"}:
                question.update(status=status, interruption_reason=reason)
        if doc["plan"] and doc["plan"]["status"] in {"planning", "pending"}:
            doc["plan"].update(status=status)
        goal = doc["goal"]
        if goal and (goal["armed"] or goal["pending_round_id"]):
            if goal["pending_round_id"]:
                goal["rounds"][-1].update(status=status, finished_at=time.time())
            goal.update(armed=False, pending_round_id=None, revision=goal["revision"] + 1,
                        blocker_streak=0, last_blocker=None)

    def is_planning(self, context: ToolContext) -> bool:
        """Synchronous host execution gate: only approved (or absent) plans permit work."""
        with self._lock:
            plan = self._load(context)["plan"]
        return bool(plan and plan["status"] != "approved")

    def resolve_pending_question(self, chat_flow_id: str, user_id: int, question_id: str) -> ToolContext:
        """HOST ONLY cross-owner routing for an authenticated real user message.

        No model tool exposes this lookup. Parent must authenticate chat/user first;
        it returns authority ONLY for the matching question origin, not arbitrary
        state access. Unknown/mismatched user and chat return the same not_found.
        """
        _text(chat_flow_id, "chat_flow_id", 256)
        _text(question_id, "question_id", 64)
        if type(user_id) is not int:
            _fail("not_found", "No pending question for this chat/user")
        matches = []
        with self._lock:
            for row in self._db.execute("SELECT * FROM state WHERE chat=?", (chat_flow_id,)):
                for q in json.loads(row["document"])["questions"]:
                    if q["question_id"] == question_id and q["user_id"] == user_id and q["status"] in {"pending", "interrupted"}:
                        matches.append(ToolContext(owner=row["owner"], chat_flow_id=chat_flow_id,
                            user_id=user_id, agent_id=row["agent"], parent_agent_id=q.get("parent_agent_id"),
                            depth=q.get("depth", 0), human_request=True))
        if len(matches) != 1:
            _fail("not_found", "No pending question for this chat/user")
        return matches[0]

    def pending_requests(self, context: ToolContext) -> dict:
        """Host only: recover deliverable questions/plan for one trusted agent scope."""
        with self._lock:
            doc = self._load(context)
        return {"questions": [q for q in doc["questions"] if q["status"] in {"pending", "interrupted"}],
                "plan": doc["plan"] if doc["plan"] and doc["plan"]["status"] in {"pending", "interrupted"} else None}

    def cancel_pending(self, context: ToolContext, reason: str = "cancelled") -> dict:
        """Host only: disarm this agent's goal and cancel pending questions/plans."""
        _text(reason, "reason", 200)
        with self._transaction():
            doc = self._load(context)
            self._interrupt(doc, reason)
            self._save(context, doc)
            return {"status": "cancelled", **self._goal_result(doc)}

    def record_event(self, context: ToolContext, name: str, args: Any, result: Any) -> dict:
        """Host only audit ingress, only for this new tool subsystem, not chat history.

        Never supply arbitrary message text as 'name'. Args/results are reduced to
        allowlisted structural metadata; raw bodies, secrets and code are not stored.
        """
        owner, chat, agent = self._scope(context)
        if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", name):
            _fail("invalid_arguments", "Audit name must be a tool/host-event identifier")
        metadata = {"args": _metadata(args), "result": _metadata(result)}
        raw = _json(metadata, 16_384)
        with self._transaction():
            cursor = self._db.execute("INSERT INTO events(owner,chat,agent,name,created_at,metadata) VALUES(?,?,?,?,?,?)",
                                      (owner, chat, agent, name, time.time(), raw))
            self._db.execute("DELETE FROM events WHERE owner=? AND chat=? AND id NOT IN "
                "(SELECT id FROM events WHERE owner=? AND chat=? ORDER BY id DESC LIMIT ?)",
                (owner, chat, owner, chat, self.max_events))
            return {"event_id": cursor.lastrowid, "source": "new_tool_audit"}

    def _query(self, name: str, args: dict, context: ToolContext) -> dict:
        owner, chat, _ = self._scope(context)
        with self._lock:
            if name == "session_event_read":
                event_id = _integer(args["event_id"], "event_id", 1, 2**63 - 1)
                rows = self._db.execute("SELECT * FROM events WHERE owner=? AND chat=? AND id=?", (owner, chat, event_id)).fetchall()
                if not rows:
                    _fail("not_found", "Audit event not found in this owner/chat")
            else:
                limit = _integer(args.get("limit", 20), "limit", 1, 100)
                before = _integer(args.get("before", 2**63 - 1), "before", 1, 2**63 - 1)
                query = args.get("query", "")
                if not isinstance(query, str) or len(query) > 200:
                    _fail("invalid_arguments", "query must be a string of at most 200 characters")
                # instr is literal substring, not wildcard/regex or user SQL.
                rows = self._db.execute("SELECT * FROM events WHERE owner=? AND chat=? AND id<? "
                    "AND (instr(name,?)>0 OR instr(metadata,?)>0) ORDER BY id DESC LIMIT ?",
                    (owner, chat, before, query, query, limit)).fetchall()
        events = [{"event_id": row["id"], "agent_id": row["agent"], "name": row["name"],
                   "created_at": row["created_at"], "metadata": json.loads(row["metadata"])} for row in rows]
        if name == "session_event_read":
            return {"source": "new_tool_audit", "event": events[0]}
        return {"source": "new_tool_audit", "events": events, "next_before": events[-1]["event_id"] if events else None}
