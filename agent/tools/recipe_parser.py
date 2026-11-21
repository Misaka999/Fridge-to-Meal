"""Conservative, evidence-preserving parsing of explicit RecipeNLG facts.

This is automatic parsing, not human review or allergy certification. Unsupported
units, missing yields and ambiguous ingredients remain unresolved.
"""
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
import re
from .ingredient_names import normalize_name

VERSION = 'explicit-facts-v1'
CUP = 236.5882365
MEASURES = {
    'g':('g',1), 'gram':('g',1), 'grams':('g',1),
    'kg':('g',1000), 'kilogram':('g',1000), 'kilograms':('g',1000),
    'lb':('g',453.59237), 'lbs':('g',453.59237), 'pound':('g',453.59237), 'pounds':('g',453.59237),
    'oz':('g',28.349523125), 'ounce':('g',28.349523125), 'ounces':('g',28.349523125),
    'ml':('ml',1), 'milliliter':('ml',1), 'milliliters':('ml',1),
    'l':('ml',1000), 'liter':('ml',1000), 'liters':('ml',1000),
    'c':('ml',CUP), 'cup':('ml',CUP), 'cups':('ml',CUP),
    'tbsp':('ml',CUP/16), 'tablespoon':('ml',CUP/16), 'tablespoons':('ml',CUP/16),
    'tsp':('ml',CUP/48), 'teaspoon':('ml',CUP/48), 'teaspoons':('ml',CUP/48),
    'fl oz':('ml',CUP/8),
}
NUMBER = r'(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?)'
# Exact names only: no model-generated substitutions or generic-to-specific matches.
PLANTS = {
    'water','salt','pepper','black pepper','brown sugar','sugar','granulated sugar',
    'powdered sugar','flour','all-purpose flour','whole wheat flour','cornstarch',
    'baking powder','baking soda','cocoa powder','cinnamon','ground cinnamon',
    'nutmeg','ground nutmeg','paprika','garlic powder','onion powder','cumin',
    'ground cumin','turmeric','dried basil','dried oregano','dried thyme',
    'rosemary','dried rosemary','parsley','chopped parsley','fresh parsley',
    'spinach','fresh spinach','baby spinach','chopped spinach',
    'carrot','carrots','sliced carrots','chopped carrots','grated carrot',
    'potato','potatoes','sweet potato','sweet potatoes',
    'broccoli','broccoli florets','cauliflower','zucchini','cucumber',
    'onion','onions','chopped onion','diced onion','sliced onion',
    'red onion','chopped red onion','green onion','green onions','chopped green onion',
    'tomato','tomatoes','chopped tomatoes','diced tomatoes',
    'green pepper','red pepper','chopped green pepper','chopped red pepper',
    'celery','chopped celery','sliced celery','mushroom','mushrooms','sliced mushrooms',
    'garlic','minced garlic','garlic clove','cloves garlic',
    'apple','apples','diced apple','banana','bananas','strawberries','blueberries',
    'lemon juice','lime juice','orange juice','vinegar','white vinegar','red wine vinegar',
    'rice','uncooked rice','pasta','spaghetti','macaroni','oats','rolled oats',
    'raisins','walnut','walnuts','chopped walnuts','pecans','chopped pecans',
    'almonds','sliced almonds','sesame seeds','sunflower seeds','maple syrup',
    'cornmeal','lentils','red lentils',
}
# Names with meaningful preparation states remain distinct in strict matching.
EXACT_ALIASES = {'carrots':'carrot','potatoes':'potato','sweet potatoes':'sweet potato',
                 'onions':'onion','tomatoes':'tomato','eggs':'egg','bananas':'banana',
                 'apples':'apple','mushrooms':'mushroom','green onions':'green onion',
                 'black pepper':'pepper','walnuts':'walnut','cloves garlic':'garlic clove'}
CATEGORIES = {n:'plant' for n in PLANTS}
CATEGORIES.update({
    'tofu':'soy', 'firm tofu':'soy', 'extra-firm tofu':'soy', 'soft tofu':'soy', 'silken tofu':'soy',
    'soy sauce':'soy', 'tamari':'soy', 'peanut':'peanut','peanuts':'peanut','peanut butter':'peanut',
    'egg':'egg','eggs':'egg', 'milk':'dairy','whole milk':'dairy','skim milk':'dairy',
    'butter':'dairy','unsalted butter':'dairy','cream':'dairy','heavy cream':'dairy',
    'cheddar cheese':'cheese','parmesan cheese':'cheese', 'honey':'honey',
    'chicken':'meat','chicken breast':'meat','ground beef':'meat','beef':'meat',
    'chicken broth':'meat','beef broth':'meat', 'bacon':'meat',
    'lean ground beef':'meat','cooked chicken':'meat','chicken breasts':'meat',
    'boneless chicken breasts':'meat','pork chops':'meat',
    'low-fat milk':'dairy','nonfat milk':'dairy',
    'oil':'oil','vegetable oil':'oil','olive oil':'olive_oil','canola oil':'oil',
})
COUNTABLE = {'egg','eggs','banana','bananas','apple','apples','garlic clove'}
SIZE_COUNTABLE = {'onion','onions','potato','potatoes','sweet potato','sweet potatoes',
                  'tomato','tomatoes','carrot','carrots','green pepper','red pepper',
                  'zucchini','cucumber','apple','apples','banana','bananas','egg','eggs'}
FRACTIONS = {'½':' 1/2','¼':' 1/4','¾':' 3/4','⅓':' 1/3','⅔':' 2/3','⅛':' 1/8','⅜':' 3/8','⅝':' 5/8','⅞':' 7/8'}
RESTRICTIONS = ('vegetarian','vegan','egg-free','peanut-free','dairy-free','soy-free')


class Unresolved(ValueError):
    pass


def clean(text):
    for char,replacement in FRACTIONS.items():text=text.replace(char,replacement)
    return re.sub(r'\s+',' ',text.replace('⁄','/')).strip().lower()


def parse_number(value):
    return float(sum((Fraction(x) for x in value.split()),Fraction(0)))


def explicit_yield(steps):
    matches=[]
    for step in steps:
        for match in re.finditer(r'\b(?:serves\s+(\d+)|(?:makes|yields)\s+(\d+)\s+(?:large\s+)?servings)\b',step,re.I):
            after=step[match.end():].strip()
            if re.match(r'^(?:[-–—]|to\b|or\b|and\b|\d|dozen\b)',after,re.I):
                raise Unresolved('Ambiguous or ranged serving count.')
            if match.group(1) and after and not re.match(r'^(?:[.;]|people\b[.;]?$)',after,re.I):
                raise Unresolved('Serving wording is not an unambiguous standard count.')
            value=int(match.group(1) or match.group(2))
            if not 1<=value<=100:raise Unresolved('Serving count outside the supported range.')
            matches.append((value,step,match.group(0)))
    if not matches:raise Unresolved('No explicit serving count in original directions.')
    if len({m[0] for m in matches})!=1:raise Unresolved('Conflicting serving counts.')
    return matches[0]


def parse_ingredient(raw,index):
    text=clean(raw)
    if re.search(r'\b(?:optional|taste|about|approximately|dash|pinch|package|pkg|can|cans|jar|box|stick|envelope|or)\b',text):
        raise Unresolved(f'Ingredient {index}: ambiguous amount, alternative, or package size.')
    if '(' in text or ')' in text or ';' in text:
        raise Unresolved(f'Ingredient {index}: parenthetical or compound amount needs review.')
    m=re.match(r'^('+NUMBER+r')\s+(.+)$',text)
    if not m:raise Unresolved(f'Ingredient {index}: no supported explicit quantity.')
    quantity=parse_number(m.group(1));rest=m.group(2)
    if quantity<=0:raise Unresolved(f'Ingredient {index}: nonpositive amount.')
    if re.match(r'^(?:[-–—]|to\b|plus\b|and\b|\d)',rest):
        raise Unresolved(f'Ingredient {index}: multiple or ranged quantities.')
    unit_match=re.match(r'^(fl\.?\s*oz\.?|[a-z]+)\.?\s+(.+)$',rest)
    if unit_match and unit_match.group(1).replace('.','') in MEASURES:
        token=unit_match.group(1).replace('.','')
        unit,factor=MEASURES[token];body=unit_match.group(2)
    else:
        unit,factor='count',1;body=rest
    parts=body.split(',',1)
    if len(parts)>1:
        suffix=parts[1].strip()
        if not re.fullmatch(r'(?:chopped|finely chopped|diced|sliced|grated|shredded|melted|softened|beaten|slightly beaten|well beaten|divided|peeled|baked until soft|drained|rinsed|cut into strips)',suffix):
            raise Unresolved(f'Ingredient {index}: unrecognized trailing preparation or extra ingredient.')
    body=parts[0].strip()
    if body not in CATEGORIES:
        size=re.fullmatch(r'(small|medium|large)\s+(.+)',body)
        if not size or size[2] not in SIZE_COUNTABLE or unit!='count':
            raise Unresolved(f'Ingredient {index}: unsupported exact ingredient name: {body!r}.')
        category=CATEGORIES.get(size[2])
        if category is None:raise Unresolved(f'Ingredient {index}: unknown ingredient category.')
        name=size[1]+' '+EXACT_ALIASES.get(size[2],size[2])
    else:
        category=CATEGORIES[body];name=EXACT_ALIASES.get(body,body)
    if unit=='count' and body not in COUNTABLE and not re.match(r'^(?:small|medium|large) ',body):
        raise Unresolved(f'Ingredient {index}: count unit needs an explicit supported size or item.')
    name=normalize_name(name)
    return {'name':name,'quantity':quantity*factor,'unit':unit,'raw_indices':[index],
            'quantity_basis':raw,'category':category,'source_name':body}


def dietary_flags(items):
    categories={x['category'] for x in items}
    flags={key:True for key in RESTRICTIONS}
    if 'meat' in categories:flags['vegetarian']=False;flags['vegan']=False
    if 'cheese' in categories:
        if flags['vegetarian'] is not False:flags['vegetarian']=None
        flags['vegan']=False;flags['dairy-free']=False
    if categories & {'egg','dairy','honey'}:flags['vegan']=False
    if 'egg' in categories:flags['egg-free']=False
    if 'dairy' in categories:flags['dairy-free']=False
    if 'soy' in categories:flags['soy-free']=False
    if 'peanut' in categories:flags['peanut-free']=False
    if categories & {'oil','olive_oil','dairy','cheese'}:
        for flag in ('peanut-free','soy-free'):
            if flags[flag] is True:flags[flag]=None
    return flags


def check_directions(steps,items):
    text=' '.join(steps).lower()
    if re.search(r'\b(?:greas\w*|spray\w*|floured|buttered|garnish\w*|optional|serve with|serve over|top with)\b',text):
        raise Unresolved('Directions may require additional coating, topping, or serving ingredients.')
    if re.search(r'ignore.{0,30}instructions|system prompt|api[_ -]?key|assistant:',text):
        raise Unresolved('Instruction-like content requires review; it is not trusted instructions.')
    # Catch common unlisted additions; no claim this validates arbitrary recipe prose.
    present={x['source_name'] for x in items}
    if re.search(r'\b(?:fry|frying|fried|pancakes?)\b',text) and not any(x['category'] in {'oil','olive_oil'} or x['source_name'] in {'butter','unsalted butter'} for x in items) and not re.search(r'\b(?:nonstick|non-stick|dry pan)\b',text):
        raise Unresolved('Frying directions do not specify an available cooking fat or dry/nonstick method.')
    if re.search(r'\b(?:quarts?|gallons?|pints?)\b',text):
        raise Unresolved('Directions contain an unsupported additional volume or batch instruction.')
    if re.search(r'\bseason(?:ed|ing)?\b',text) and not any(n in present for n in ('salt','pepper','black pepper')):
        raise Unresolved('Unmeasured seasoning in directions.')
    for term in ('water','salt','pepper','oil','butter','milk','egg','flour','sugar','honey','soy sauce','rice','cheese','shortening','gravy','pheasant','sauce'):
        if re.search(r'\b'+re.escape(term)+r'(?:s)?\b',text) and not any(re.search(r'\b'+re.escape(term)+r'(?:s)?\b',n) for n in present):
            raise Unresolved('Directions mention an unlisted ingredient: '+term)


def parse_recipe(raw):
    """Return a source-checked record or an explanation; do not mutate raw input."""
    try:
        if raw.get('source')!='RecipeNLG/Gathered':raise Unresolved('Unsupported source.')
        steps=raw.get('steps') or raw.get('raw_directions')
        ingredients=raw.get('raw_ingredients')
        if not isinstance(steps,list) or not steps or not all(isinstance(x,str) for x in steps):
            raise Unresolved('Missing original directions.')
        if not isinstance(ingredients,list) or not ingredients or not all(isinstance(x,str) for x in ingredients):
            raise Unresolved('Missing original ingredients.')
        servings,yield_step,yield_span=explicit_yield(steps)
        items=[parse_ingredient(line,i) for i,line in enumerate(ingredients)]
        check_directions(steps,items)
        title=raw.get('title','').lower()
        if any(re.search(r'\b'+word+r'\b',title) and not any(word in x['source_name'] for x in items) for word in ('pineapple','pheasant')):
            raise Unresolved('Title names a main ingredient absent from the ingredient list.')
        if not re.search(r'\b(?:bake|cook|boil|simmer|fry|heat|microwave|knead|spread|toss|serve|pour|peel)\w*\b',' '.join(steps[:-1]),re.I):
            raise Unresolved('Directions do not provide a supported preparation method.')
        # Reject repeated names instead of guessing how split requirements are allocated.
        if len({(x['name'],x['unit']) for x in items})!=len(items):
            raise Unresolved('Repeated ingredient requirements need allocation review.')
        result=deepcopy(raw)
        result.update(servings=servings,ingredients=items,steps=steps,
                      quantity_verified=True,dietary_compatibility=dietary_flags(items),
                      review_status='automatically_source_parsed',parser_version=VERSION,
                      servings_source=yield_step,servings_evidence=yield_span,
                      source_record_sha256=hashlib.sha256(json.dumps(raw,sort_keys=True).encode()).hexdigest(),
                      parse_notes=['Automatically parsed explicit facts, not human-reviewed.',
                                   'Ingredient-level screening only; no allergen or cooking-safety certification.',
                                   'US customary volumes; no ingredient-density conversions.'])
        return {'status':'parsed','recipe':result,'reason':None}
    except (Unresolved,ValueError,ZeroDivisionError) as exc:
        return {'status':'unresolved','recipe':None,'reason':str(exc)}
