"""Canonicalize only the order of a valid model-selected recipe set.

Never insert/remove IDs, alter statuses or relax scoring. Unknown/duplicate IDs
remain invalid for the normal validation/repair path.
"""
from copy import deepcopy


def normalize_selection_order(answer,observation):
    if not isinstance(answer,dict) or answer.get('status')!='recommended' or observation.get('status')!='found':
        return answer,None
    ids=answer.get('recipe_ids')
    if not isinstance(ids,list) or not ids or any(not isinstance(x,str) for x in ids) or len(ids)!=len(set(ids)):
        return answer,None
    order=[c['recipe_id'] for c in observation['candidates']]
    if not set(ids)<=set(order):return answer,None
    ordered=sorted(ids,key=order.index)
    if ordered==ids:return answer,None
    fixed=deepcopy(answer);fixed['recipe_ids']=ordered
    return fixed,{'kind':'priority_normalization','model_selected_ids':list(ids),
                  'display_ids':ordered,'reason':'Preserved the selected set and applied the common tool priority order.'}
