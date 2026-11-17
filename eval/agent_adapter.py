"""Expose Shuhua's ReAct runner to the shared evaluation harness."""

from functools import partial

from react_agent import run_agent
from agent.tools.recipe_search import search_recipes


def run(request, context):
    search = partial(search_recipes, recipes=context["recipes"])
    result = run_agent(request, search=search)
    return {"answer": result["result"], "metrics": result["metrics"], "trace": result["tool_trace"]}
