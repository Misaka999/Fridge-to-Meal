"""Replace this body with an adapter to Shuhua's real ReAct runner."""


def run(request, context):
    # Do not replace this with the baseline and label it an agent.
    # Pass request and context['recipes'] to Shuhua's runner, and translate its
    # result to {answer: ..., metrics: ..., trace: ...}; see contracts.py.
    raise NotImplementedError('Shuhua must connect the real ReAct implementation here.')
