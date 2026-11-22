"""Conservative ingredient-level screening, not allergen certification."""
import re

TERMS = {
 'vegetarian': ['chicken', 'beef', 'pork', 'bacon', 'ham', 'turkey', 'fish',
                'anchovy', 'tuna', 'shrimp', 'gelatin', 'lard', 'oyster sauce'],
 'vegan': ['chicken', 'beef', 'pork', 'bacon', 'ham', 'turkey', 'fish', 'shrimp',
           'gelatin', 'lard', 'egg', 'milk', 'cream', 'cheese', 'butter', 'honey', 'yogurt'],
 'egg-free': ['egg', 'mayonnaise'],
 'peanut-free': ['peanut', 'groundnut'],
 'dairy-free': ['milk', 'cream', 'cheese', 'butter', 'yogurt', 'whey', 'casein', 'ghee'],
 'soy-free': ['soy', 'soya', 'soybean', 'tofu', 'tamari', 'miso', 'tempeh', 'edamame'],
}


def detected_conflicts(ingredients, restrictions):
    text = ' ; '.join(ingredients).lower()
    # Ambiguous compounds are excluded conservatively; absence is not clearance.
    result = []
    for restriction in restrictions:
        for term in TERMS.get(restriction, []):
            if re.search(r'\b' + re.escape(term) + r'(?:s|es)?\b', text):
                result.append({'restriction':restriction, 'ingredient_term':term})
    return result


def preparation_conflicts(steps,restrictions):
    """Flag known banned additions in preparation clauses, not arbitrary role claims.

This is a conservative second check, not a complete language or allergy parser.
"""
    findings=[]
    for step in steps:
        for match in re.finditer(r'\b(?:add|stir in|mix in|top with|garnish with|coat with|spread)\b[^.!?]{0,120}',step,re.I):
            prefix=step[max(0,match.start()-18):match.start()].lower()
            if re.search(r'(?:do not|don\x27t|never)\s*$',prefix):continue
            findings.extend(detected_conflicts([match.group(0)],restrictions))
    return findings
