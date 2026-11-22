"""Map the real plan-and-replan runner to the common evaluation interface."""
from agent.plan_replan import run_agent


def run(request,context):
    result=run_agent(request,context=context)
    return {'answer':result['result'],'metrics':result['metrics'],'trace':result['tool_trace']}
