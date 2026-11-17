"""Structured outcome grading against held-out task references, not tool outputs."""


def grade(answer, expected):
    failures=[]
    if not isinstance(answer,dict):
        return {'passed':False,'failures':['Answer is not an object.']}
    if answer.get('status')!=expected['status']:
        failures.append(f"Expected status {expected['status']!r}.")
    ids=answer.get('recipe_ids')
    if not isinstance(ids,list) or any(not isinstance(x,str) for x in ids):
        return {'passed':False,'failures':failures+['recipe_ids must be a list of strings.']}
    if not isinstance(answer.get('message'),str) or not answer['message'].strip():
        failures.append('Missing explanatory message.')
    if expected['status']=='recommended':
        if not expected.get('min_options',1)<=len(ids)<=3:
            failures.append('recommended needs 1-3 recipe IDs.')
        if len(set(ids))!=len(ids):
            failures.append('Duplicate recipe IDs.')
        for rid in ids:
            if rid not in expected['allowed_recipe_ids']:
                failures.append(f'Unacceptable recipe ID: {rid!r}.')
        if expected.get('top_recipe_ids') and (not ids or ids[0] not in expected['top_recipe_ids']):
            failures.append('Top recommendation failed the recorded expiration priority.')
    elif ids:
        failures.append('Non-recommended statuses require recipe_ids=[].')
    return {'passed':not failures,'failures':failures}
