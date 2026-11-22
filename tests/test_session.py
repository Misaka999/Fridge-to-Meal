"""Session regressions covering preserved constraints and isolated inventory."""

from copy import deepcopy
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, ToolMessage

from agent.session import MealSessions
from agent.tools.mock_recipes import search_recipes
import react_agent


class SessionModel:
    model_name = "offline-session-test"

    def bind_tools(self, tools, tool_choice):
        return self

    def invoke(self, messages):
        if messages[0].content.startswith("Convert the user's follow-up"):
            payload = json.loads(messages[-1].content)
            if payload["follow_up"] == "Recommend dinner again.":
                return AIMessage(content="{}")
            state = payload["current_request"]
            restrictions = list(state["preferences"]["dietary_restrictions"])
            restrictions.append("egg-free")
            content = json.dumps({"preferences": {"dietary_restrictions": restrictions}})
            return AIMessage(content=content, usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15})
        if not isinstance(messages[-1], ToolMessage):
            return AIMessage(content="", tool_calls=[{"id": "search", "name": "search_recipes", "args": {}}])
        found = json.loads(messages[-1].content)
        return AIMessage(content=json.dumps({
            "status": "recommended" if found["status"] == "found" else "no_feasible_recipe",
            "recipe_ids": [recipe["recipe_id"] for recipe in found["candidates"]],
            "message": "Checked inventory.",
        }))


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.request = json.loads((Path(__file__).resolve().parents[1] / "examples/example_request_mock.json").read_text(encoding="utf-8"))
        self.request["preferences"] = {"dietary_restrictions": ["vegetarian"], "likes": ["tofu"]}
        self.sessions = MealSessions(model=SessionModel(), search=search_recipes)

    def test_follow_up_preserves_inventory_servings_preferences_and_date(self):
        initial = deepcopy(self.request)
        self.sessions.run_turn("a", self.request)
        follow_up = self.sessions.run_turn("a", message="也不要鸡蛋")
        state = follow_up["request"]
        self.assertEqual(state["pantry"], initial["pantry"])
        self.assertEqual(state["servings"], 2)
        self.assertEqual(state["as_of_date"], initial["as_of_date"])
        self.assertEqual(state["preferences"], {"dietary_restrictions": ["vegetarian", "egg-free"], "likes": ["tofu"]})
        self.assertEqual(follow_up["metrics"]["model_calls"], 3)
        self.assertEqual(follow_up["tool_trace"][0]["arguments"], state)
        self.assertEqual(self.request, initial)

    def test_sessions_and_returned_objects_are_isolated(self):
        self.sessions.run_turn("a", self.request)
        self.sessions.run_turn("b", {**self.request, "pantry": []})
        self.sessions.run_turn("a", {"servings": 1})
        state = self.sessions.get_state("a")
        state["pantry"].clear()
        self.assertEqual(self.sessions.get_state("b")["pantry"], [])
        self.assertEqual(self.sessions.get_state("b")["servings"], 2)
        self.assertEqual(len(self.sessions.get_state("a")["pantry"]), 3)

    def test_missing_information_can_be_supplied_in_next_turn(self):
        self.sessions.run_turn("a", {**self.request, "servings": None})
        run = self.sessions.run_turn("a", {"servings": 2})
        self.assertEqual(run["result"]["status"], "recommended")

    def test_explicit_inventory_replacement_clear_preferences_and_reset(self):
        self.sessions.run_turn("a", self.request)
        self.sessions.run_turn("b", self.request)
        self.sessions.run_turn("a", {"pantry": [], "preferences": {"dietary_restrictions": []}})
        self.assertEqual(self.sessions.get_state("a")["pantry"], [])
        self.assertEqual(self.sessions.get_state("a")["preferences"]["likes"], ["tofu"])
        self.sessions.reset("a")
        self.assertIsNone(self.sessions.get_state("a")["servings"])
        self.assertEqual(self.sessions.get_state("b"), self.request)

    def test_failed_model_does_not_erase_explicit_user_update(self):
        self.sessions.run_turn("a", self.request)
        with patch.object(self.sessions.model, "invoke", side_effect=RuntimeError("offline failure")):
            with self.assertRaises(RuntimeError):
                self.sessions.run_turn("a", {"servings": 1})
        self.assertEqual(self.sessions.get_state("a")["servings"], 1)
        self.assertEqual(self.sessions.run_turn("a")["result"]["status"], "recommended")

    def test_invalid_preference_patch_does_not_partially_update_state(self):
        self.sessions.run_turn("a", self.request)
        with self.assertRaises(ValueError):
            self.sessions.run_turn("a", {"servings": 1, "preferences": {"likes": None}})
        self.assertEqual(self.sessions.get_state("a"), self.request)

    def test_inventory_change_from_language_extraction_is_rejected(self):
        self.sessions.run_turn("a", self.request)
        with patch.object(self.sessions.model, "invoke", return_value=AIMessage(content='{"pantry": []}')):
            with self.assertRaises(ValueError):
                self.sessions.run_turn("a", message="推荐别的菜")
        self.assertEqual(self.sessions.get_state("a"), self.request)

    def test_inventory_edits_feed_search_and_recommendation_does_not_consume(self):
        self.sessions.run_turn("a", self.request)
        self.sessions.run_turn("b", self.request)
        initial = deepcopy(self.request["pantry"])
        added = {"name": "rice", "quantity": 100, "unit": "g", "expires_on": "2026-11-21"}
        for operation, expected in [
            ({"op": "add", **added}, initial + [added]),
            ({"op": "update", "name": "rice", "quantity": 50}, initial + [{**added, "quantity": 50}]),
            ({"op": "delete", "name": "rice"}, initial),
        ]:
            result = self.sessions.run_turn("a", {"inventory": operation})
            self.assertEqual(result["tool_trace"][0]["arguments"]["pantry"], expected)
            self.sessions.run_turn("a", message="Recommend dinner again.")
            self.assertEqual(self.sessions.get_state("a")["pantry"], expected)
            self.assertEqual(self.sessions.get_state("b"), self.request)

    def test_invalid_edits_clarify_without_writing_then_corrected_edit_succeeds(self):
        self.sessions.run_turn("a", self.request)
        for operation in [
            {"op": "add", "name": "rice", "unit": "g"},
            {"op": "update", "name": "tofu", "quantity": -1},
            {"op": "update", "name": "tofu", "unit": "kg"},
            {"op": "update", "name": "tofu", "expires_on": "tomorrow"},
            {"op": "delete", "name": "missing"},
            {"op": "add", "name": "rice", "quantity": 10, "unit": []},
        ]:
            with self.subTest(operation=operation):
                run = self.sessions.run_turn("a", {"inventory": operation})
                self.assertEqual(run["result"]["status"], "needs_clarification")
                self.assertEqual(run["metrics"]["model_calls"], 0)
                self.assertEqual(self.sessions.get_state("a"), self.request)
        run = self.sessions.run_turn("a", {"inventory": {"op": "add", "name": "rice", "unit": "g", "quantity": 10}})
        self.assertEqual(run["request"]["pantry"][-1]["quantity"], 10)

    def test_same_name_batches_require_selection_and_full_replacement_is_validated(self):
        self.sessions.run_turn("a", self.request)
        self.sessions.run_turn("a", {"inventory": {"op": "add", "name": "tofu", "quantity": 40, "unit": "g"}})
        before = self.sessions.get_state("a")
        for patch_data in [{"inventory": {"op": "delete", "name": "tofu"}}, {"pantry": [{"name": "tofu"}]}]:
            run = self.sessions.run_turn("a", patch_data)
            self.assertEqual(run["result"]["status"], "needs_clarification")
            self.assertEqual(self.sessions.get_state("a"), before)
        run = self.sessions.run_turn("a", {"inventory": {"op": "delete", "name": "tofu", "index": 3}})
        self.assertEqual(run["request"], self.request)

    def test_cli_chat_routes_json_and_language_follow_ups(self):
        with patch.object(react_agent, "deepseek_model", return_value=SessionModel()), patch(
            "builtins.input", side_effect=['{"servings": 1}', "也不要鸡蛋", "/state", "/exit"]
        ), patch("sys.stdout", new_callable=io.StringIO) as out, patch("sys.stderr", new_callable=io.StringIO):
            self.assertEqual(react_agent.chat(self.request, search=search_recipes, session_id="cli", trace=True), 0)
        state = json.loads(out.getvalue().splitlines()[-1])
        self.assertEqual(state["servings"], 1)
        self.assertEqual(state["preferences"]["dietary_restrictions"], ["vegetarian", "egg-free"])
