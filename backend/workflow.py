"""Durable, bounded LangGraph investigation over the read-only tool catalog."""

from __future__ import annotations

import json
import operator
import os
import threading
from pathlib import Path
from typing import Annotated, Any

from typing_extensions import TypedDict

import app as core
from backend import investigation_tools as tools
from backend.llm import rank_hypotheses
from langgraph.graph import END, START, StateGraph

os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")

_CHECKPOINT_SETUP_LOCK = threading.Lock()
_CHECKPOINT_SETUP_PATH: str | None = None


class InvestigationState(TypedDict, total=False):
    incident_id: str
    service_id: str
    service_scope: list[str]
    evidence: Annotated[list[dict[str, Any]], operator.add]
    tool_errors: Annotated[list[dict[str, Any]], operator.add]
    tool_history: Annotated[list[dict[str, Any]], operator.add]
    hypotheses: list[dict[str, Any]]
    normalized_evidence: list[dict[str, Any]]
    diagnosis: dict[str, Any]
    model_review: dict[str, Any]
    missing_evidence: list[str]


def _invoke_tool(state: InvestigationState, name: str, function, *args, kind: str | None = None):
    try:
        result = function(*args)
        records = result.get("items", []) if isinstance(result, dict) else []
        failures = []
        status = "completed"
        count = len(records)
    except core.ApiError as error:
        records = []
        failures = [{"kind": kind or name, "code": error.code, "message": error.message}]
        status, count = "unavailable", 0
    return {"evidence": records, "tool_errors": failures,
        "tool_history": [{"name": name, "status": status, "result_count": count,
            "service_scope": state.get("service_scope", []), "incident_id": state["incident_id"]}]}


def intake(state: InvestigationState):
    incident, _scenario, _services, scope, _lab = tools._context(state["incident_id"])
    return {"service_id": incident["service_id"], "service_scope": sorted(scope),
        "tool_history": [{"name": "incident_intake", "status": "completed", "result_count": 1,
            "service_scope": sorted(scope), "incident_id": incident["id"]}]}


def read_logs(state: InvestigationState):
    return _invoke_tool(state, "get_recent_logs", tools.get_recent_logs, state["incident_id"], None, 50, kind="logs")


def read_metrics(state: InvestigationState):
    return _invoke_tool(state, "query_error_metrics", tools.query_error_metrics, state["incident_id"], None, 50, kind="metrics")


def read_traces(state: InvestigationState):
    return _invoke_tool(state, "get_request_traces", tools.get_request_traces, state["incident_id"], None, 50, kind="traces")


def read_change_events(state: InvestigationState):
    return _invoke_tool(state, "get_deployment_history", tools.get_deployment_history, state["incident_id"], None, 50, kind="changes")


def evaluate_hypotheses(state: InvestigationState):
    seen, evidence, errors = set(), [], []
    for item in state.get("evidence", []):
        key = (item.get("kind"), item.get("source"), item.get("observation"), item.get("signal_id"))
        if key in seen:
            continue
        seen.add(key)
        item = dict(item)
        item.setdefault("id", core.ident("ev"))
        evidence.append(item)
    for error in state.get("tool_errors", []):
        key = (error.get("kind"), error.get("code"), error.get("message"))
        if key not in {(item.get("kind"), item.get("code"), item.get("message")) for item in errors}:
            errors.append(error)
    result = core.diagnose(evidence, errors)
    return {"normalized_evidence": evidence, "hypotheses": result.get("hypotheses", []), "diagnosis": result,
        "missing_evidence": result.get("missing_evidence", [])}


def review_hypotheses(state: InvestigationState):
    result = dict(state["diagnosis"])
    review = rank_hypotheses(state.get("hypotheses", []), state.get("normalized_evidence", []))
    if review.get("status") == "used":
        by_id = {item["cause_id"]: item for item in state.get("hypotheses", [])}
        order = review["order"]
        if result.get("status") == "supported" and result.get("cause_id") in by_id:
            order = [result["cause_id"]] + [item for item in order if item != result["cause_id"]]
        result["hypotheses"] = [by_id[item] for item in order if item in by_id]
        observed = {item.get("kind") for item in state.get("normalized_evidence", [])}
        review["missing_evidence"] = [kind for kind in review.get("missing_evidence", []) if kind not in observed]
        result["model_review"] = {"status": "used", "rationale": review["rationale"], "missing_evidence": review["missing_evidence"],
            "evidence_ids": [item.get("id") for item in state.get("normalized_evidence", [])]}
    history = {"name": "llm_hypothesis_review", "status": review["status"], "result_count": 1 if review["status"] == "used" else 0,
        "service_scope": state.get("service_scope", []), "incident_id": state["incident_id"]}
    return {"diagnosis": result, "model_review": review, "tool_history": [history]}


def _build(checkpointer):
    graph = StateGraph(InvestigationState)
    for name, function in (("intake", intake), ("logs", read_logs),
        ("metrics", read_metrics), ("traces", read_traces), ("change_events", read_change_events),
        ("hypothesis_evaluation", evaluate_hypotheses), ("llm_hypothesis_review", review_hypotheses)):
        graph.add_node(name, function)
    graph.add_edge(START, "intake")
    graph.add_edge("intake", "logs")
    graph.add_edge("logs", "metrics")
    graph.add_edge("metrics", "traces")
    graph.add_edge("traces", "change_events")
    graph.add_edge("change_events", "hypothesis_evaluation")
    graph.add_edge("hypothesis_evaluation", "llm_hypothesis_review")
    graph.add_edge("llm_hypothesis_review", END)
    return graph.compile(checkpointer=checkpointer)


def run_investigation(incident_id: str, run_id: str):
    global _CHECKPOINT_SETUP_PATH
    initial: InvestigationState = {"incident_id": incident_id, "service_scope": [], "evidence": [], "tool_errors": [], "tool_history": []}
    config = {"configurable": {"thread_id": run_id}, "recursion_limit": 16}
    postgres_url = os.environ.get("OPSPILOT_CHECKPOINT_DATABASE_URL") or os.environ.get("OPSPILOT_DATABASE_URL")
    if postgres_url:
        from langgraph.checkpoint.postgres import PostgresSaver
        with PostgresSaver.from_conn_string(postgres_url) as checkpointer:
            checkpointer.setup()
            return _build(checkpointer).invoke(initial, config)
    from langgraph.checkpoint.sqlite import SqliteSaver
    checkpoint_path = (core.DATA / "workflow-checkpoints.sqlite").resolve()
    core.DATA.mkdir(parents=True, exist_ok=True)
    with SqliteSaver.from_conn_string(str(Path(checkpoint_path))) as checkpointer:
        checkpointer.conn.execute("PRAGMA busy_timeout=15000")
        with _CHECKPOINT_SETUP_LOCK:
            if _CHECKPOINT_SETUP_PATH != str(checkpoint_path):
                checkpointer.setup()
                # shortcut: setup is cached per path; restart after replacing the checkpoint file.
                _CHECKPOINT_SETUP_PATH = str(checkpoint_path)
            else:
                checkpointer.is_setup = True
        graph = _build(checkpointer)
        snapshot = graph.get_state(config)
        return graph.invoke(None if snapshot and snapshot.next else initial, config)
