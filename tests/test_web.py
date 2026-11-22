"""Exercise the browser API with a real ReAct graph and an offline model."""

import json
from threading import Thread
import unittest
from unittest.mock import patch
from urllib.request import Request, build_opener, ProxyHandler

from langchain_core.messages import AIMessage
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
                follow = api("/api/turn", {"message": "also no eggs"})
                self.assertEqual(follow["request"]["pantry"], example["pantry"])
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
