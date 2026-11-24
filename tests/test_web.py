"""Exercise the browser API with a real ReAct graph and an offline model."""

import json
from threading import Event, Thread
import unittest
from unittest.mock import patch
from urllib.request import Request, build_opener, ProxyHandler

from langchain_core.messages import AIMessage, AIMessageChunk
from pydantic import ValidationError

from react_agent import SearchResult, parse_response
from agent.session import MealSessions
from test_session import SessionModel
from web_app import make_server


class WebTests(unittest.TestCase):
    def test_web_meal_then_follow_up_and_separate_kitchen(self):
        with make_server(0, MealSessions(model=SessionModel())) as server:
            worker = Thread(target=server.serve_forever, daemon=True)
            worker.start()
            base = f"http://127.0.0.1:{server.server_port}"
            client = build_opener(ProxyHandler({}))

            def api(path, data=None, key="a"*32):
                request = Request(base + path, data=None if data is None else json.dumps(data).encode(),
                                  headers={"X-Meal-Session": key, "Content-Type": "application/json"})
                with client.open(request, timeout=5) as response:
                    return json.load(response)

            try:
                with client.open(base, timeout=5) as response:
                    self.assertIn(b"Find recipes", response.read())
                example = api("/api/kitchen")["example"]
                first = api("/api/turn", {"update": example})
                self.assertEqual(first["result"]["recipe_ids"], ["recipenlg_68810"])
                call = first["tool_trace"][0]
                self.assertEqual(call["tool"], "search_recipes")
                self.assertEqual(call["result"]["candidates"][0]["source_url"],
                                 "www.cookbooks.com/Recipe-Details.aspx?id=260993")
                self.assertFalse(first["follow_up_processed"])
                follow = api("/api/turn", {"message": "also no eggs"})
                self.assertEqual(follow["request"]["pantry"], example["pantry"])
                self.assertTrue(follow["follow_up_processed"])
                self.assertIn("egg-free", follow["request"]["preferences"]["dietary_restrictions"])
                self.assertIsNone(api("/api/kitchen", key="b"*32)["state"]["pantry"])
                with patch.object(SessionModel, "invoke", side_effect=[
                    AIMessage(content="", tool_calls=[{"id": "search", "name": "search_recipes", "args": {}}]),
                    AIMessage(content='{"status":"no_feasible_recipe","recipe_ids":[]}'),
                ]):
                    empty = api("/api/turn", {"update": {"pantry": []}})
                self.assertEqual(empty["metrics"]["model_calls"], 2)
                self.assertEqual(empty["result"]["recipe_ids"], [])
                self.assertIn("searched catalogue", empty["result"]["message"])
                self.assertEqual(empty["result"]["status"], "no_feasible_recipe")
            finally:
                server.shutdown()
                worker.join()

    def test_stream_sends_recipe_text_before_model_finishes(self):
        finish = Event()

        class StreamingModel(SessionModel):
            def stream(self, messages):
                yield AIMessageChunk(content='{"status":"recommended","recipe_ids":["recipenlg_68810"],'
                                             '"message":"Try Glazed Carrots')
                if not finish.wait(5):
                    raise TimeoutError("Client did not receive the first chunk.")
                yield AIMessageChunk(content=' for four."}')

        with make_server(0, MealSessions(model=StreamingModel())) as server:
            worker = Thread(target=server.serve_forever, daemon=True)
            worker.start()
            client = build_opener(ProxyHandler({}))
            url = f"http://127.0.0.1:{server.server_port}"
            headers = {"X-Meal-Session": "c" * 32, "Content-Type": "application/json"}
            try:
                with client.open(Request(url + "/api/kitchen", headers=headers), timeout=5) as response:
                    example = json.load(response)["example"]
                headers["Accept"] = "application/x-ndjson"
                request = Request(url + "/api/turn", json.dumps({"update": example}).encode(), headers)
                with client.open(request, timeout=5) as response:
                    self.assertEqual(response.headers.get_content_type(), "application/x-ndjson")
                    while True:
                        event = json.loads(response.readline())
                        if event["type"] != "progress":
                            break
                    self.assertEqual(event, {"type": "text", "data": "Try Glazed Carrots"})
                    finish.set()
                    remaining = [json.loads(line) for line in response]
                self.assertEqual(remaining[0], {"type": "text", "data": " for four."})
                self.assertEqual(remaining[1]["type"], "done")
                run = remaining[1]["data"]
                self.assertEqual(run["result"]["message"], "Try Glazed Carrots for four.")
                self.assertEqual(run["metrics"]["model_calls"], 2)
                self.assertEqual(run["tool_trace"][0]["tool"], "search_recipes")
            finally:
                finish.set()
                server.shutdown()
                worker.join()

    def test_no_match_fallback_is_limited_to_missing_message(self):
        answer = {"status": "no_feasible_recipe", "recipe_ids": []}
        for status, fields in [
            ("error", {}), ("no_match", {"status": "recommended"}),
            ("no_match", {"recipe_ids": ["unknown"]}), ("no_match", {"message": ""}),
        ]:
            with self.subTest(status=status, fields=fields), self.assertRaises(ValidationError):
                parse_response({
                    "messages": [AIMessage(content=json.dumps({**answer, **fields}))],
                    "search_result": SearchResult(status=status, candidates=[], error_code=None),
                })
