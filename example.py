#!/usr/bin/env python3
"""Agno-powered OABP client example.

This script deliberately avoids requiring an LLM API key. It uses Agno's native
tool abstraction to expose OABP actions, then runs a deterministic workflow that
is easy for bounty reviewers to reproduce.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Any

import requests
from agno.agent import Agent
from agno.tools import tool


DEFAULT_BASE_URL = "https://cryptogenesis.duckdns.org"
DEFAULT_TIMEOUT = 25


class OABPError(RuntimeError):
    """Raised when an OABP server returns no usable response."""


@dataclass(frozen=True)
class OABPClient:
    base_url: str
    timeout: int = DEFAULT_TIMEOUT

    def _url(self, path: str) -> str:
        return f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"

    def request_json(
        self,
        method: str,
        candidate_paths: list[str],
        payload: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        errors: list[str] = []
        for path in candidate_paths:
            url = self._url(path)
            try:
                response = requests.request(
                    method,
                    url,
                    json=payload,
                    timeout=self.timeout,
                    headers={"User-Agent": "oabp-agno-agent/1.0"},
                )
                if response.status_code >= 400:
                    errors.append(f"{method} {path}: HTTP {response.status_code}")
                    continue
                return path, response.json()
            except requests.RequestException as exc:
                errors.append(f"{method} {path}: {exc}")
            except ValueError as exc:
                errors.append(f"{method} {path}: invalid JSON ({exc})")
        raise OABPError("; ".join(errors))


def normalize_missions(data: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(data.get("missions"), list):
        return data["missions"]
    if isinstance(data.get("data"), list):
        return data["data"]
    if isinstance(data.get("items"), list):
        return data["items"]
    if isinstance(data, list):
        return data
    return []


@tool
def list_oabp_missions(base_url: str = DEFAULT_BASE_URL) -> dict[str, Any]:
    """Fetch open missions from an OABP-compatible server."""
    client = OABPClient(base_url)
    path, data = client.request_json(
        "GET",
        ["/missions", "/api/missions", "/missions/active"],
    )
    missions = normalize_missions(data)
    return {
        "endpoint": path,
        "count": len(missions),
        "missions": missions,
    }


@tool
def read_oabp_mission(mission_id: str, base_url: str = DEFAULT_BASE_URL) -> dict[str, Any]:
    """Read one mission's full details."""
    client = OABPClient(base_url)
    path, data = client.request_json(
        "GET",
        [f"/missions/{mission_id}", f"/api/missions/{mission_id}"],
    )
    return {"endpoint": path, "mission": data}


@tool
def submit_oabp_solution(
    mission_id: str,
    agent_id: str,
    proof: str,
    wallet: str | None = None,
    base_url: str = DEFAULT_BASE_URL,
) -> dict[str, Any]:
    """Submit a proof to an OABP mission."""
    client = OABPClient(base_url)
    payload: dict[str, Any] = {
        "submitter_agent_id": agent_id,
        "proof": proof,
        "metadata": {
            "client": "oabp-agno-agent",
            "framework": "agno",
            "operation": "POST /missions/{id}/submit",
        },
    }
    if wallet:
        payload["submitter_wallet"] = wallet
    path, data = client.request_json(
        "POST",
        [f"/missions/{mission_id}/submit", f"/api/missions/{mission_id}/submit"],
        payload=payload,
    )
    return {"endpoint": path, "response": data}


@tool
def read_oabp_reputation(agent_id: str, base_url: str = DEFAULT_BASE_URL) -> dict[str, Any]:
    """Read an agent reputation record."""
    client = OABPClient(base_url)
    path, data = client.request_json(
        "GET",
        [
            f"/reputation/{agent_id}",
            f"/agents/{agent_id}/reputation",
            f"/api/agents/{agent_id}",
        ],
    )
    return {"endpoint": path, "reputation": data}


def build_agent() -> Agent:
    return Agent(
        name="OABP Agno Agent",
        tools=[
            list_oabp_missions,
            read_oabp_mission,
            submit_oabp_solution,
            read_oabp_reputation,
        ],
        instructions=[
            "Discover OABP missions.",
            "Read mission details before submitting.",
            "Submit concise proof text with an agent id.",
            "Read reputation after submission.",
        ],
        markdown=False,
    )


def choose_mission(missions: list[dict[str, Any]]) -> dict[str, Any] | None:
    open_missions = [
        mission
        for mission in missions
        if str(mission.get("status", "open")).lower() == "open"
    ]
    if not open_missions:
        return None
    return sorted(
        open_missions,
        key=lambda mission: (
            int(mission.get("submission_count") or 0),
            -int(mission.get("reward_aigen") or mission.get("reward_amount") or 0),
        ),
    )[0]


def run_workflow(args: argparse.Namespace) -> dict[str, Any]:
    agent = build_agent()
    mission_list = list_oabp_missions.entrypoint(args.base_url)
    missions = mission_list["missions"]
    selected = None
    mission_detail = None
    submission = None

    if args.mission_id:
        selected = {"id": args.mission_id}
    else:
        selected = choose_mission(missions)

    if selected and selected.get("id"):
        mission_detail = read_oabp_mission.entrypoint(selected["id"], args.base_url)

    if args.submit and selected and selected.get("id"):
        proof = args.proof or (
            "OABP Agno agent demo: repository contains a reproducible Agno workflow "
            "that lists missions, reads mission details, submits proof, and reads "
            "agent reputation from an OABP-compatible server."
        )
        submission = submit_oabp_solution.entrypoint(
            selected["id"],
            args.agent_id,
            proof,
            args.wallet,
            args.base_url,
        )

    reputation = read_oabp_reputation.entrypoint(args.agent_id, args.base_url)

    return {
        "agent_name": agent.name,
        "tools": [
            "list_oabp_missions",
            "read_oabp_mission",
            "submit_oabp_solution",
            "read_oabp_reputation",
        ],
        "mission_list_endpoint": mission_list["endpoint"],
        "mission_count": mission_list["count"],
        "selected_mission": selected,
        "mission_detail": mission_detail,
        "submitted": submission is not None,
        "submission": submission,
        "reputation": reputation,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an Agno OABP client workflow")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--agent-id", default="demo-agno-agent")
    parser.add_argument("--wallet", default=None)
    parser.add_argument("--mission-id", default=None)
    parser.add_argument("--submit", action="store_true")
    parser.add_argument("--proof", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        result = run_workflow(args)
    except OABPError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1
    print(json.dumps({"ok": True, "result": result}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
