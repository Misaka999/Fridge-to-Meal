"""One local recipe for testing the search tool interface."""

from datetime import date


RECIPE = {
    "recipe_id": "r_spinach_tofu_01",
    "title": "菠菜炒豆腐",
    "ingredients": [
        {"name": "spinach", "quantity": 150, "unit": "g"},
        {"name": "tofu", "quantity": 250, "unit": "g"},
        {"name": "soy sauce", "quantity": 15, "unit": "ml"},
    ],
    "steps": ["将豆腐切块，菠菜洗净。", "用不粘锅将豆腐煎至金黄，加入菠菜炒软，再拌入酱油。"],
}
RESTRICTIONS_MET = {"vegetarian", "vegan", "egg-free", "dairy-free"}


def search_recipes(*, pantry, servings, preferences, as_of_date):
    """Match the fixture against the inventory, portions and known diet tags."""
    ingredients = [
        {**ingredient, "quantity": ingredient["quantity"] * servings / 2}
        for ingredient in RECIPE["ingredients"]
    ]
    available = {}
    for item in pantry:
        if item.get("expires_on") and date.fromisoformat(item["expires_on"]) < date.fromisoformat(as_of_date):
            continue
        key = (item["name"].strip().casefold(), item["unit"].strip().casefold())
        available[key] = available.get(key, 0) + item["quantity"]

    restrictions = {value.strip().casefold() for value in preferences["dietary_restrictions"]}
    enough = all(
        available.get((item["name"], item["unit"]), 0) >= item["quantity"]
        for item in ingredients
    )
    if not enough or not restrictions <= RESTRICTIONS_MET:
        return {"status": "no_match", "candidates": [], "error_code": None}

    candidate = {**RECIPE, "servings": servings, "ingredients": ingredients}
    return {"status": "found", "candidates": [candidate], "error_code": None}


def failing_search(**request):
    """Exercise the same error handling used for a real tool exception."""
    raise OSError("Simulated recipe search failure")
