"""Explicit edits to a pantry snapshot, shared by meal agents."""

from copy import deepcopy

from .recipe_search import clarification, validate_pantry


def edit_pantry(pantry, edit):
    """Return (new pantry, None) on success or (original pantry, question)."""
    def ask(message):
        return pantry, clarification(message, "inventory")

    if not isinstance(edit, dict) or edit.get("op") not in ("add", "update", "delete"):
        return ask("Choose an inventory operation: add, update or delete.")
    op = edit["op"]
    name = edit.get("name")
    if not isinstance(name, str) or not name.strip():
        return ask("Which ingredient should be changed? Provide its name.")

    fields = {"quantity", "unit", "expires_on"}
    allowed = {"op", "name"}
    if op != "delete":
        allowed.update(fields)
    if op != "add":
        allowed.add("index")
    if edit.keys() - allowed:
        return ask("Unexpected field for this operation. To remove only part of a batch, update its remaining quantity.")

    if pantry is None:
        return ask("Provide your current pantry first. Use an empty list if it is empty.")
    rows = deepcopy(pantry)
    changes = {key: edit[key] for key in fields if key in edit}
    if op == "add":
        rows.append({"name": name.strip(), **changes})
    else:
        matches = [i for i, row in enumerate(rows) if row["name"].strip().casefold() == name.strip().casefold()]
        if "index" in edit:
            index = edit["index"]
            if type(index) is not int or index not in matches:
                return ask("That index does not match the ingredient. Check /state and specify the current row.")
        elif len(matches) == 1:
            index = matches[0]
        elif matches:
            return ask(f"Which batch of {name}? Resend the operation with index from {matches} (numbered from zero).")
        else:
            return ask(f"No row named {name}. Check the ingredient name in /state.")
        if op == "delete":
            rows.pop(index)
        else:
            if not changes:
                return ask(f"What quantity, unit or expiry should change for {name}?")
            if "unit" in changes and changes["unit"] != rows[index]["unit"] and "quantity" not in changes:
                return ask("What is the remaining quantity in the new unit?")
            rows[index].update(changes)
    issue = validate_pantry(rows)
    return (pantry, issue) if issue else (rows, None)
