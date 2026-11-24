"""Bounded adaptation guards; pantry identity and quantity matching stay strict."""
import re
from urllib.parse import urlsplit, urlunsplit, unquote, parse_qsl, urlencode
from .grounded_messages import META
from .tools.ingredient_names import normalize_name
from .tools.dietary import TERMS
from .tools.recipe_parser import EXACT_ALIASES
from .tools.ingredient_names import ALIASES
from .tools.recipe_search import UNITS
from fractions import Fraction

# Exact, plain ingredient names only. Mixes, sauces and preparations are not inferred.
PLAIN_PLANTS={name:'plant' for name in (
    'lentil','lentils','red lentil','red lentils','kidney bean','kidney beans',
    'oat','oats','cabbage','bell pepper','bell peppers')}
CONTROL_PATTERNS=[
    r'\b(?:ignore|override|bypass|disregard)\b.{0,55}\b(?:instructions?|rules?|constraints?|restrictions?|system|user)\b',
    r'\b(?:system|developer|assistant)\s*:',
    r'\b(?:system|developer|admin)\s+(?:override|message|instructions?)\b',
    r'\b(?:print|reveal|expose|forward|send|show)\b.{0,65}\b(?:secrets?|passwords?|credentials?|private|api[ _-]?keys?|system prompt|hidden prompt)\b',
    r'\b(?:delete|deduct|clear|modify|overwrite|reset|consume|update|remove)\s+(?:(?:all|the|your|stored|my)\s+){0,3}(?:inventory|pantry|stock|database|user preferences)\b',
    r'\b(?:execute|run)\s+(?:this\s+)?(?:shell|python|javascript|command|code)\b',
    r'\b(?:guaranteed safe|certified allergen[ -]free|100% safe)\b',
]
CONTROL=re.compile('|'.join('(?:'+p+')' for p in CONTROL_PATTERNS),re.I)
SECRET_SHAPE=re.compile(r'\bsk-(?:proj-)?[A-Za-z0-9_-]{15,}|\b[A-Z][A-Z0-9]*_[A-Z0-9_]{20,}\b')
PREP=re.compile(r'^(?:(?:finely|roughly|freshly)\s+)?(?:(?:chopped|diced|sliced|grated|minced|shredded|beaten|peeled|crushed)\s+)+',re.I)
NEGATION=re.compile(r'\b(?:without|no|omit(?:s|ted)?|excluding|do not|don.t|not using|not adding|never)\b',re.I)
COOK=re.compile(r'\b(?:cook|cooked|boil|boiled|poach|poached|bake|baked|fry|fried|simmer|simmered|roast|roasted|saute|sear)\b',re.I)
PLURAL_REFERENCES={'lentils':'lentil','kidney beans':'kidney bean','oats':'oat','bell peppers':'bell pepper','noodles':'noodle'}


def control_directive(text):
    return bool(CONTROL.search(text) or SECRET_SHAPE.search(text))


def safe_source_title(value,recipe_id):
    """Keep attribution data from becoming unvalidated user-facing instructions."""
    if not isinstance(value,str) or not value.strip() or len(value)>160 or META.search(value) or SECRET_SHAPE.search(value) or any(c in value for c in '<>{}\r\n'):
        return 'Recipe '+recipe_id
    return value.strip()


def safe_source_url(value):
    if not isinstance(value,str) or not value or len(value)>2000 or any(c.isspace() or c in '<>{}' for c in value):return ''
    if re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:',value) and not value.startswith(('http://','https://')):return ''
    try:
        parsed=urlsplit(value if '://' in value else 'https://'+value)
        if parsed.scheme not in {'http','https'} or not parsed.hostname or parsed.username or parsed.password:return ''
        if parsed.port is not None and not 1<=parsed.port<=65535:return ''
        readable=re.sub(r'[_/\-]+',' ',unquote(parsed.path))
        if control_directive(readable) or SECRET_SHAPE.search(unquote(parsed.path)):return ''
        # Preserve ordinary numeric recipe IDs without echoing arbitrary query data.
        query=[(key,value) for key,value in parse_qsl(parsed.query)
               if key.lower() in {'id','recipe_id','recipeid'} and re.fullmatch(r'\d{1,12}',value)]
        return urlunsplit((parsed.scheme,parsed.netloc,parsed.path,urlencode(query),''))
    except ValueError:return ''


def canonical_reference(value):
    value=normalize_name(PREP.sub('',value))
    return PLURAL_REFERENCES.get(value,EXACT_ALIASES.get(value,value))


def negated(step,start):
    prefix=re.split(r'[.;!?]|\bbut\b|\bthen\b',step[max(0,start-65):start],flags=re.I)[-1]
    return bool(NEGATION.search(prefix))


def validate_step_amounts(steps, ingredients):
    """Check explicit English amounts against the proposed ingredient list.

    This is a bounded consistency check, not a complete natural-language parser.
    Repeated references to the same portion are not summed across instructions.
    Mass/volume/count conversions require an explicitly compatible unit.
    """
    words = dict(zip(('zero one two three four five six seven eight nine ten eleven twelve').split(), range(13)))
    number = r'(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?|' + '|'.join(words) + r'|half)'
    unit_aliases = {u:u for u in UNITS}
    unit_aliases.update({'gram':'g', 'grams':'g', 'kilogram':'kg', 'kilograms':'kg',
                         'milliliter':'ml', 'milliliters':'ml', 'liter':'l', 'liters':'l',
                         'cups':'cup', 'tablespoon':'tbsp', 'tablespoons':'tbsp',
                         'teaspoon':'tsp', 'teaspoons':'tsp', 'pieces':'count', 'piece':'count'})
    unit_pattern = '|'.join(sorted(unit_aliases, key=len, reverse=True))
    for item in ingredients:
        name = item['name']
        references = {name} | {alias for alias in set(ALIASES) | set(EXACT_ALIASES) | set(PLURAL_REFERENCES)
                               if canonical_reference(alias) == canonical_reference(name)}
        food = '|'.join(re.escape(n).replace(r'\ ', r'[\s-]+') + r'(?:s|es)?' for n in sorted(references, key=len, reverse=True))
        pattern = re.compile(r'\b(?P<amount>'+number+r')\s*(?:[-–]\s*(?P<upper>'+number+r')\s*)?'
                             r'(?:(?P<unit>'+unit_pattern+r')\b\s*(?:of\s+)?)?'
                             r'(?:(?:large|medium|small|beaten|chopped|diced|sliced|cooked|raw)\s+)*'
                             r'(?P<food>'+food+r')\b', re.I)
        for step in steps:
            for match in pattern.finditer(step):
                if re.search(r'\b(?:without|omit|do not add|don.t add)\s*$', step[:match.start()], re.I):
                    continue
                raw = (match['upper'] or match['amount']).lower()
                amount = words[raw] if raw in words else 0.5 if raw == 'half' else float(sum((Fraction(v) for v in raw.split()), Fraction(0)))
                stated_unit = unit_aliases[match['unit'].lower()] if match['unit'] else 'count'
                dimension, factor = UNITS[stated_unit]
                expected_dimension, expected_factor = UNITS[item['unit']]
                if dimension != expected_dimension:
                    raise ValueError('Cooking step uses an unverified unit conversion for '+name+'. Use the listed ingredient unit.')
                if amount * factor > item['quantity'] * expected_factor + 1e-8:
                    raise ValueError('Cooking step amount exceeds the listed amount for '+name+'. Use the adapted quantities consistently.')


def validate_steps(steps,ingredients,category_names):
    names={x['name'] for x in ingredients};units={x['name']:x['unit'] for x in ingredients}
    text=' '.join(steps)
    # A liquid egg/oil mixture cannot be kneaded into a rollable dough.
    if names and names<={'egg','oil','water','salt'} and re.search(r'\bknead\b',text,re.I) and re.search(r'\bdough\b',text,re.I):
        raise ValueError('A liquid egg mixture cannot be kneaded into dough without a suitable binding ingredient.')
    terms=set(category_names)|{term for values in TERMS.values() for term in values}|{'bread','toast','avocado','ketchup','lettuce','noodle','noodles','fish sauce','salmon','bell pepper'}
    patterns=[(term,re.compile(r'\b'+re.escape(term).replace(r'\ ',r'[\s-]+')+r'(?:s|es)?\b',re.I)) for term in sorted(terms,key=len,reverse=True)]
    made=set();heated=set()
    for step in steps:
        # Derived products are allowed only when this recipe actually forms them.
        if 'flour' in names and names&{'egg','water'} and re.search(r'\b(?:dough|knead|roll|cut|shape)\b',step,re.I):
            if re.search(r'\b(?:pasta|noodles?)\b',text,re.I):made.update({'pasta','noodle','noodles'})
        if 'bread' in names and re.search(r'\btoast(?:ing|ed)?\b',step,re.I):made.add('toast')
        occupied=[]
        for term,pattern in patterns:
            for match in pattern.finditer(step):
                if any(a<match.end() and match.start()<b for a,b in occupied):continue
                occupied.append((match.start(),match.end()))
                if negated(step,match.start()):continue
                ref=canonical_reference(term)
                if ref=='water' or ref in names or ref in made:continue
                if ref=='soy' and 'soy-sugar mixture' in made and re.search(r'\bsoy[ -]sugar mixture\b',step,re.I):continue
                # A later reference to the same salmon or bell pepper is not new stock.
                if ref=='fish' and 'salmon' in names:continue
                if ref=='pepper' and 'bell pepper' in names and not re.search(r'\b(?:black|white|ground) pepper|salt and pepper',step,re.I):continue
                if ref.startswith('cooked '):
                    base=ref[len('cooked '):]
                    if base in names and base in heated:continue
                    if base in names:raise ValueError('Cook '+base+' before referring to it as cooked; raw and cooked stock are not interchangeable.')
                if ref=='garlic clove' and 'garlic' in names:
                    if units['garlic'] in {'g','kg','gram','grams','lb','oz'}:
                        # A weighed garlic portion may be chopped; never invent a clove-to-mass conversion.
                        if re.search(r'\b\d+(?:\.\d+)?\s+(?:garlic\s+)?cloves?\b',step,re.I):
                            raise ValueError('Confirm the garlic clove amount; no clove-to-mass conversion is recorded.')
                        continue
                    raise ValueError('Specify whether garlic count means cloves or whole bulbs; they cannot be assumed equal.')
                raise ValueError('Cooking step mentions an unlisted ingredient: '+ref)
        if {'soy sauce','sugar'}<=names and re.search(r'\b(?:whisk|mix|stir)\b',step,re.I) and re.search(r'\bsoy[ -]sauce\b',step,re.I) and re.search(r'\bsugar\b',step,re.I):
            made.add('soy-sugar mixture')
        if COOK.search(step) and not re.search(r'\b(?:do not|don.t|never)\s+(?:cook|boil|poach|bake|fry|simmer|roast)\b',step,re.I):
            for name in names:
                if re.search(r'\b'+re.escape(name)+r'(?:s|es)?\b',step,re.I):heated.add(name)
    validate_step_amounts(steps, ingredients)
