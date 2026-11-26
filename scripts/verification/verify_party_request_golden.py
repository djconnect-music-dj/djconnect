"""Exercise the Apple/VibeCast Party request wire on isolated real HA and TLS.

Spotify catalogue and queue are fixtures. No installed client, live Spotify
account, physical output, or production room is used.
"""
from __future__ import annotations

import asyncio
from functools import partial
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch
from uuid import uuid4

import verify_shared_guest_actual_ha as base


def describe(status, response, language):
    from custom_components.djconnect.guest_requests import message

    if status != 200 or not response.get("success"):
        return "error"
    if response.get("guest_request"):
        return "queued" if response["guest_request"]["state"] == "queue_confirmed" else "proposal"
    if response.get("request_choices", {}).get("items"):
        return "choices"
    if response.get("text") == message("missing", language):
        return "clarification"
    return "text"


async def run_golden(hass, manager, client, post, host, origin, current_uri):
    from custom_components.djconnect import pipeline
    from custom_components.djconnect.ask_dj.dialogue import guard_effect_dispatch
    from custom_components.djconnect.guest_conversation import guard_spotify
    from custom_components.djconnect.spotify_backend import SpotifyBackend

    root = Path(os.environ["DJC_SOURCE_ROOT"])
    golden = json.loads((root / "docs/verification/fixtures/vibecast_party_request_golden_v1.json").read_text())
    catalogue = {row["id"]: row for row in golden["catalogue"]}

    def spotify_item(row):
        return {"id": row["id"] * 22, "uri": "spotify:track:" + row["id"] * 22,
                "name": row["title"], "artists": [{"name": row["artist"]}]}

    ids = {(row["title"], row["artist"]): key for key, row in catalogue.items()}
    queue, writes, searches, outcomes = [], [], [], []
    model_calls = []

    async def fixture_model(_hass, data, **kwargs):
        assert data["agent_id"] == "history-fixture-agent"
        assert kwargs.get("allow_agent_fallback") is False
        model_calls.append(True)
        return {"response": {"speech": {"plain": {
            "speech": "Dit is een synthetisch antwoord op de geselecteerde bijdrage.",
        }}}}

    async def provider(_backend, method, path, **_kwargs):
        guard_spotify(method, path)
        url = urlsplit(path)
        params = parse_qs(url.query)
        if method == "POST":
            await guard_effect_dispatch(method=method, path=path)
            assert url.path == "/me/player/queue"
            uri = params["uri"][0]
            row = catalogue[uri[-1]]
            assert uri == spotify_item(row)["uri"]
            queue.append(spotify_item(row))
            writes.append(row["id"])
            return {}
        if url.path == "/me/player":
            return {"device": {"id": "synthetic-current-output", "is_restricted": False},
                    "item": {"uri": current_uri}}
        if url.path == "/me/player/queue":
            return {"queue": list(queue)}
        if url.path == "/search":
            query = params["q"][0].casefold()
            searches.append(query)
            keys = []
            if "promise" in query:
                keys = ["J"]
            elif "beginners" in query:
                keys = ["K"]
            elif "hello" in query:
                keys = ["L"] if "adele" in query else ["L", "M"]
            elif "hallelujah" in query:
                keys = ["O"] if "live" in query else ["N", "O"]
            elif "haevn" in query:
                keys = ["J", "K"]
            return {"tracks": {"items": [spotify_item(catalogue[key]) for key in keys]}}
        raise AssertionError("Unexpected fixture provider route: " + url.path)

    async def turn(binding, token, thread, case, spec, action="ask", choice=None):
        text = spec.get("prompt", "")
        body = {**binding, "contract_version": 1, "text": text,
                "client_message_id": str(uuid4()), "thread_id": thread, "language": case["language"]}
        if choice is not None:
            body["choice_action"] = choice
        before = len(writes)
        searches_before = len(searches)
        response = await client.post("/api/djconnect/v1/participation/" + action,
                                     headers={"Authorization": "Bearer " + token, "Origin": origin}, json=body)
        value = await response.json()
        assert response.headers["Cache-Control"] == "no-store"
        if spec["expected"] == "queued":
            if request := value.get("guest_request"):
                share = manager._display_admission._shares[host["share_id"]]
                if share.request_dispatch is not None:
                    await share.request_dispatch
                status = await post("participation", "request/status",
                                    {**binding, "request_id": request["request_id"]}, token=token)
                value = {**value, "guest_request": status["request"]}
            assert writes[before:] in ([], [spec["recording"]]), "Unexpected automatic queue effect"
        else:
            assert len(writes) == before, "Review-mode guest turn wrote to the queue"
        assert not ({"profile_id", "history", "music_dna", "playback_actions"} & set(value))
        kind = describe(response.status, value, case["language"])
        request = value.get("guest_request") or {}
        choices = value.get("request_choices", {}).get("items", [])
        returned = [ids.get((row.get("title"), row.get("artist"))) for row in choices]
        recorded = ids.get((request.get("title"), request.get("artist")))
        expected = spec["expected"]
        accepted_kind = {
            "clarify_or_offer": {"clarification", "choices"},
            "proposal_or_choices": {"proposal", "choices"},
            "information": {"text"},
        }.get(expected, {expected})
        passed = kind in accepted_kind
        if kind == "proposal":
            passed &= request["state"] == "received" and recorded == spec.get("recording")
        if kind == "queued":
            passed &= recorded == spec.get("recording") and writes[before:] == [recorded]
        if kind == "choices":
            expected_choices = spec.get("choices") or ([spec["recording"]] if "recording" in spec else returned)
            passed &= sorted(returned, key=str) == sorted(expected_choices)
        if expected == "information":
            passed &= "Fixture request" in value.get("text", "")
        if spec.get("no_search"):
            passed &= len(searches) == searches_before
        return {"input": text, "route": action, "expected": expected, "actual": kind,
                "http": response.status, "text": value.get("text"), "error": value.get("error"),
                "choices": returned, "recording": recorded, "pass": bool(passed)}, value, body

    with (patch.object(SpotifyBackend, "_request", provider),
          patch.object(pipeline, "_call_conversation_process_transport", fixture_model)):
        for index, case in enumerate(golden["scenarios"]):
            # Use independent threads within the real per-guest and per-IP limits.
            policy = case.get("policy")
            if policy:
                configured = await post("participation", "owner/configure", {**host, "policy": {
                    "information": True, "requests": policy, "max_pending": 3, "screen_focus": True,
                }}, owner=True)
                assert configured["policy"]["requests"] == policy
                if policy == "auto_queue":
                    assert manager._display_admission._shares[host["share_id"]].party_requests
                    active = manager._display_admission._shares[host["share_id"]].owner
                    # The earlier confirmed review request still occupies one slot
                    # when the same display switches into Party.
                    previously_queued = queue.pop(0)
                    await manager.async_update_playback_projection(
                        owner_profile_id=active.profile_id, session_id=active.session_id,
                        state="playing", media_identity=previously_queued["uri"],
                        title=previously_queued["name"])
                    await manager.async_update_playback_projection(
                        owner_profile_id=active.profile_id, session_id=active.session_id,
                        state="playing", media_identity=current_uri, title="Fixture regular set")
            if index % 4 == 0 or policy:
                invited = await post("participation", "owner/invite", host, owner=True)
                joined = await post("participation", "redeem", {key: invited[key] for key in
                                    ("issuer_epoch", "invitation_id", "invitation_secret")})
                binding = {key: joined[key] for key in ("issuer_epoch", "guest_id")}
                token = joined["guest_token"]
            thread = str(uuid4())
            start = len(searches)
            model_start = len(model_calls)
            first, response, _ = await turn(binding, token, thread, case, case)
            result = {"id": case["id"], "turns": [first]}
            if follow := case.get("follow_up"):
                if "select" in follow and follow["select"] not in first["choices"]:
                    result["turns"].append({"expected": follow["expected"], "actual": "blocked", "pass": False})
                else:
                    if "select" in follow:
                        offers = response["request_choices"]
                        item = offers["items"][first["choices"].index(follow["select"])]
                        choice = {"result_set_id": offers["result_set_id"], "action_id": item["action_id"]}
                        spec = {**follow, "prompt": item["title"] + " — " + item["artist"]}
                        observed, selected, body = await turn(binding, token, thread, case, spec, "request", choice)
                    else:
                        observed, selected, body = await turn(binding, token, thread, case, follow)
                    result["turns"].append(observed)
                    if follow.get("approve") and observed["pass"]:
                        request = selected["guest_request"]
                        replay = await client.post("/api/djconnect/v1/participation/request", json=body,
                            headers={"Authorization": "Bearer " + token, "Origin": origin})
                        assert replay.status == 200
                        assert (await replay.json())["guest_request"]["request_id"] == request["request_id"]
                        assert not writes
                        await post("participation", "owner/decide",
                                   {**host, "request_id": request["request_id"], "decision": "accept"}, owner=True)
                        status = await post("participation", "request/status",
                                            {**binding, "request_id": request["request_id"]}, token=token)
                        assert status["request"]["state"] == "queue_confirmed" and writes == [follow["select"]]
                        result["review"] = {"replayed_same_request": True, "queue_posts": 1,
                                            "state": status["request"]["state"]}
            result["searches"] = searches[start:]
            result["fixture_model_calls"] = len(model_calls) - model_start
            result["pass"] = all(r["pass"] for r in result["turns"])
            outcomes.append(result)
    return {"host": "Mac mini isolated HA", "queue_fixture_writes": writes, "scenarios": outcomes}


async def main():
    base.harness.qualify = partial(base.qualify, party_request_golden=run_golden)
    await base.harness.run()
    lab = Path(os.environ["DJC_LAB_ROOT"])
    receipt = json.loads((lab / "http-requested-moments-receipt.json").read_text())
    result = receipt["extension"]["party_request_golden"]
    (lab / "vibecast-party-request-golden-results.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    total = len(result["scenarios"])
    passed = sum(row["pass"] for row in result["scenarios"])
    print(json.dumps({"scenarios": total, "passed": passed, "failed": total - passed}))
    if passed != total:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
