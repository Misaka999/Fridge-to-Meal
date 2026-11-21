"""Offline FoodKeeper snapshot lookup, without a model API call."""
import argparse,json
from agent.tools.foodkeeper import lookup_storage

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('food')
parser.add_argument('--product-id')
parser.add_argument('--condition',choices=['pantry','refrigerator','freezer'])
parser.add_argument('--stage',choices=['purchase','opened','thawed','as_listed'])
parser.add_argument('--reference-date')
parser.add_argument('--as-of-date')
parser.add_argument('--stored-as-directed',action='store_true')
args=parser.parse_args()
print(json.dumps(lookup_storage(**vars(args)),ensure_ascii=False,indent=2))
