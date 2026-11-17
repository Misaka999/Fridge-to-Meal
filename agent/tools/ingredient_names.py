"""Conservative canonical names; retrieval variants never imply interchangeability."""
import re
import unicodedata

ALIASES = {
 'eggs':'egg', 'tomatoes':'tomato', 'potatoes':'potato', 'carrots':'carrot',
 'peanuts':'peanut', 'sweet potatoes':'sweet potato', 'soybean curd':'tofu',
 'soya sauce':'soy sauce', 'scallions':'green onion', 'scallion':'green onion',
 'spring onions':'green onion', 'green onions':'green onion', 'onions':'onion',
 'olive oil':'oil', 'vegetable oil':'oil', 'cooking oil':'oil', 'wesson oil':'oil',
 'spinach leaves':'spinach', 'fresh spinach':'spinach', 'baby spinach':'spinach',
 'chicken breast':'chicken', 'cooked rice':'rice',
 'black pepper':'pepper', 'ground black pepper':'pepper',
 'unsalted butter':'butter', 'salted butter':'butter',
 'diced red apples':'diced apple', 'diced apples':'diced apple',
 'walnut pieces':'walnut', 'walnuts':'walnut',
}
RETRIEVAL_VARIANTS = {
 'firm tofu':'tofu', 'extra firm tofu':'tofu', 'soft tofu':'tofu', 'silken tofu':'tofu',
 'red onion':'onion', 'yellow onion':'onion', 'medium sweet potato':'sweet potato',
 'diced apple':'apple', 'sliced carrot':'carrot',
}


def normalize_name(name):
    name = unicodedata.normalize('NFKC', name).casefold().strip()
    name = re.sub(r'[-_]+', ' ', name)
    name = re.sub(r'\s+', ' ', name)
    return ALIASES.get(name, name)


def retrieval_name(name):
    value = normalize_name(name)
    return RETRIEVAL_VARIANTS.get(value, value)
