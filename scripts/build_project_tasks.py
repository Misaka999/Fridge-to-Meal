"""75 authored constraint scenarios over five cited real-source recipe families.

Expected IDs/statuses are declared below, not computed by the matching tool.
These are structured request tests, not free-form conversation benchmarks.
"""
from copy import deepcopy
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
TODAY='2026-11-21'


def stock(name,quantity,unit):return {'name':name,'quantity':quantity,'unit':unit,'expires_on':None}
def req(items,servings,diet):return {'pantry':items,'servings':servings,'preferences':{'dietary_restrictions':diet,'likes':[]},'as_of_date':TODAY}

FAMILIES=[
 {'name':'pasta','id':'recipenlg_7524','base':req([stock('flour',3,'cup'),stock('eggs',4,'count')],4,['vegetarian']),
  'exact':(2.25,'cup'),'equivalent':(709.7647095,'ml'),'opposite':['egg-free'],'opposite_status':'no_feasible_recipe'},
 {'name':'lentils_rice','id':'recipenlg_309172','base':req([stock('lentils',1.2,'cup'),stock('rice',1.2,'cup'),stock('large onion',2,'count'),stock('oil',.6,'cup'),stock('salt',2,'tsp')],6,['vegan']),
  'exact':(1,'cup'),'equivalent':(283.9058838,'ml'),'opposite':['soy-free'],'opposite_status':'needs_clarification'},
 {'name':'beef_potato','id':'recipenlg_417115','base':req([stock('lean ground beef',600,'g'),stock('medium potato',4,'count'),stock('medium onion',4,'count')],4,[]),
  'exact':(453.59237,'g'),'equivalent':(.6,'kg'),'opposite':['vegetarian'],'opposite_status':'no_feasible_recipe'},
 {'name':'creamed_spinach','id':'recipenlg_61469','base':req([stock('spinach',1000,'g'),stock('butter',20,'ml'),stock('flour',20,'ml'),stock('milk',150,'ml'),stock('cream',150,'ml'),stock('salt',3,'ml'),stock('small onion',1,'count')],6,['vegetarian']),
  'exact':(907.18474,'g'),'equivalent':(1,'kg'),'opposite':['dairy-free'],'opposite_status':'no_feasible_recipe'},
 {'name':'honey_carrots','id':'recipenlg_104510','base':req([stock('carrots',250,'g'),stock('soy sauce',60,'ml'),stock('oil',40,'ml'),stock('honey',50,'ml')],4,['vegetarian']),
  'exact':(226.796185,'g'),'equivalent':(.5511556554621939,'lb'),'opposite':['vegan'],'opposite_status':'no_feasible_recipe'},
]


def build_tasks():
    result=[]
    for family in FAMILIES:
        base=deepcopy(family['base']);rid=family['id']
        base['pantry'][0]['expires_on']='2026-11-23'
        cases=[]
        def add(label,request,status='recommended',edge=False):
            cases.append({'label':label,'request':request,'status':status,'edge':edge})
        add('complete_input',deepcopy(base))
        r=deepcopy(base);r['servings']*=2
        for item in r['pantry']:item['quantity']*=2
        add('double_servings_and_stock',r)
        r=deepcopy(base);r['servings']//=2
        for item in r['pantry']:item['quantity']/=2
        add('half_servings_and_stock',r)
        r=deepcopy(base);r['pantry'][0]['quantity'],r['pantry'][0]['unit']=family['exact']
        add('exact_primary_quantity',r,edge=True)
        r=deepcopy(base);r['pantry'].pop(0);add('missing_primary_ingredient',r,'no_feasible_recipe',True)
        r=deepcopy(base);r['pantry'][0]['quantity']=0;add('zero_primary_stock',r,'no_feasible_recipe',True)
        r=deepcopy(base);q,u=family['exact'];r['pantry'][0].update(quantity=q-.001,unit=u)
        add('below_exact_quantity',r,'no_feasible_recipe',True)
        r=deepcopy(base);r['pantry'][0]['unit']='ml' if family['exact'][1]=='g' else 'g'
        add('incompatible_mass_volume',r,'needs_clarification',True)
        r=deepcopy(base);r['pantry'][0]['quantity']=None;add('unknown_quantity',r,'needs_clarification',True)
        r=deepcopy(base);r['servings']=None;add('unknown_servings',r,'needs_clarification',True)
        r=deepcopy(base);r['pantry'][0]['expires_on']='2026-11-20';add('expired_primary',r,'no_feasible_recipe',True)
        r=deepcopy(base);r['pantry'][0]['expires_on']=None;add('unknown_expiry_stays_unknown',r)
        r=deepcopy(base);r['pantry'][0]['quantity'],r['pantry'][0]['unit']=family['equivalent'];add('equivalent_units',r)
        r=deepcopy(base);r['preferences']['dietary_restrictions']=family['opposite'];add('diet_conflict_or_unverified_label',r,family['opposite_status'],True)
        r=deepcopy(base);r['pantry'][0]['expires_on']=None;r['pantry'][0]['storage']={};add('requested_storage_guidance_missing_metadata',r,'needs_clarification',True)
        assert len(cases)==15
        for case in cases:
            status=case['status']
            result.append({'id':f'YN{len(result)+1:03d}','type':'clarify' if status=='needs_clarification' else 'constraint',
                           'family':family['name'],'description':case['label'],
                           'catalogue_scope':'expanded_source_parsed_subset','request':case['request'],
                           'expected':{'status':status,'allowed_recipe_ids':[rid] if status=='recommended' else []},
                           'grader':'structured_status_and_recipe_ids; manual review of narrative amounts and steps',
                           'tags':['functional','edge'] if case['edge'] else ['functional']})
    return result


if __name__=='__main__':
    folder=ROOT/'eval/project';folder.mkdir(exist_ok=True)
    new=build_tasks()
    (folder/'tasks_yangyang_new75.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in new))
    old=[json.loads(s) for s in (ROOT/'eval/week6/tasks_recipenlg_yangyang.jsonl').read_text().splitlines() if s.strip()]
    (folder/'tasks_yangyang_100.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in old+new))
    (ROOT/'data/catalogues.json').write_text(json.dumps({'reviewed_recipenlg_subset':'recipes_recipenlg.json','expanded_source_parsed_subset':'recipes_expanded.json'},indent=2)+'\n')
    print('Prepared 75 new authored cases and the 100-case Yangyang bundle.')
