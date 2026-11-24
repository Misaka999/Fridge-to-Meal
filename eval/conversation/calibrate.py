"""Transparent hand-authored judge conformance probes, not benchmark runs."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
from .judge import make_payload,review


def fixtures():
    recipe=next(r for r in json.loads((Path(__file__).parent/'catalogue.json').read_text()) if r['id']=='recipenlg_683038')
    state={'pantry':[{'name':'mushroom','quantity':250,'unit':'g','expires_on':None}],'servings':2,
           'preferences':{'dietary_restrictions':[],'likes':[]},'as_of_date':'2026-11-24'}
    ref={'state':state,'mode':'conditional','focus':[],'pending_foods':[],
         'acceptable_gaps':{recipe['id']:['butter']}}
    good={'request':deepcopy(state),'pending_inventory':[],'meal_ingredients':[],
          'result':{'status':'needs_clarification','recipe_ids':[],
                    'message':'Fried Mushrooms is a close original-recipe option. You have enough mushrooms, but need 59.147059125 ml butter for the original two-serving recipe. It is not ready with the current pantry. Would you like to add butter or adapt it?'},
          'adapted_recipes':[], 'conditional_options':[{'recipe_id':recipe['id'],'missing_ingredients':['butter'],'ready_to_cook':False}]}
    bad=deepcopy(good);bad.update(result={'status':'recommended','recipe_ids':[recipe['id']],
        'message':'Fried Mushrooms is ready to cook. You already have all ingredients including the butter.'},
        conditional_options=[],adapted_recipes=[{'source_recipe_id':recipe['id'],'title':'Fried Mushrooms','servings':2,
            'ingredients':[{'name':'mushroom','quantity':226.796185,'unit':'g'},{'name':'butter','quantity':59.147059125,'unit':'ml'}],
            'steps':['Fry the mushrooms in the butter.'],'changes':['Original recipe unchanged.']}])
    for name,out in [('appropriate_conditional',good),('false_ready_claim',bad)]:
        yield name,make_payload('Explain what is missing for the original Fried Mushrooms recipe; do not alter ingredients.',
            [{'role':'user','content':'Which ingredients do I need to add for the original Fried Mushrooms?'}],out,ref,[recipe])
    egg=next(r for r in json.loads((Path(__file__).parent/'catalogue.json').read_text()) if r['id']=='recipenlg_1290537')
    state={'pantry':[{'name':'egg','quantity':2,'unit':'count','expires_on':None}], 'servings':1,
           'preferences':{'dietary_restrictions':[],'likes':[]},'as_of_date':'2026-11-24'}
    response={'request':state,'meal_ingredients':[],'pending_inventory':[],
              'result':{'status':'recommended','recipe_ids':[egg['id']],'message':'Boiled eggs for one person. Use two eggs; portions are estimates and your stored pantry is unchanged.'},
              'adapted_recipes':[{'source_recipe_id':egg['id'],'title':'Boiled eggs','servings':1,
                   'ingredients':[{'name':'egg','quantity':2,'unit':'count'}],
                   'steps':['Boil the two eggs in water until cooked.'],'changes':['Proposed portion estimate; original source yield was unspecified.']}]}
    yield 'two_eggs_one_person',make_payload('Unused scenario-level future goal',
        [{'role':'user','content':'Make it for one person.'}],response,{'state':state,'mode':'recommend','focus':[],'pending_foods':[]},[egg])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=False);results=[]
    for name,payload in fixtures():
        result=review(payload);judgment=result['judgment'];scores=judgment['scores'] if judgment else {}
        meets=bool(judgment) and (scores.get('consistency')==0 if name=='false_ready_claim' else scores.get('helpfulness')==2 and scores.get('consistency')==2)
        results.append({'fixture':name,'payload':payload,**result,'meets_expected_check':meets})
    (args.out/'calibration.json').write_text(json.dumps(results,indent=2))
    print(json.dumps([{'fixture':r['fixture'],'scores':(r['judgment'] or {}).get('scores'),'meets_expected_check':r['meets_expected_check']} for r in results],indent=2))
    if not all(r['meets_expected_check'] for r in results):raise SystemExit('Judge failed a conformance probe; inspect before reporting quality scores.')

if __name__=='__main__':main()
