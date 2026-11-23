"""Validate explicit user-language edit proposals; never invent stock amounts."""
from copy import deepcopy
from .ingredient_names import normalize_name
from .inventory import edit_pantry


def apply_language_edits(pantry, proposals):
    """Return (pantry, pending edits, question). Batch edits are atomic."""
    if not isinstance(proposals,list) or not 1<=len(proposals)<=12:
        raise ValueError('Use 1-12 explicit ingredient edits.')
    edits=deepcopy(proposals);rows=deepcopy(pantry)
    questions=[]
    for edit in edits:
        if not isinstance(edit,dict) or edit.get('op') not in {'add','update','delete'}:
            raise ValueError('Invalid inventory edit action.')
        if set(edit)-{'op','name','quantity','unit','expires_on','index'}:
            raise ValueError('Unexpected inventory edit field.')
        if not isinstance(edit.get('name'),str) or not edit['name'].strip():
            raise ValueError('An ingredient name is required.')
        edit['name']=normalize_name(edit['name'])
        # Resolve aliases to existing labels for update/delete, without merging batches.
        if edit['op']!='add':
            matches=[x['name'] for x in (pantry or []) if normalize_name(x['name'])==edit['name']]
            if matches:edit['name']=matches[0]
        if edit['op']=='add':
            name=edit['name']
            if edit.get('quantity') is None:
                questions.append('How many tomatoes do you have (or what weight)?' if name=='tomato'
                                 else f'How much {name} do you have'+(' (for example, in ml or tbsp)?' if name=='oil' else ', and in what unit?'))
                continue
            if edit.get('unit') is None:
                questions.append(f'What unit is the amount of {name} in?')
                continue
        clean={k:v for k,v in edit.items() if v is not None or k=='expires_on'}
        rows,issue=edit_pantry(rows,clean)
        if issue:
            return pantry,edits,issue['message']+' You can reply in normal language.'
    if questions:
        return pantry,edits,' '.join(questions)+' You can reply in normal language.'
    return rows,[],None
