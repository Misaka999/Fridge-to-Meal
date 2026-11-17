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
