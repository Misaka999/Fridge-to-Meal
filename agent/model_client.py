"""One JSON-mode Chat Completions request; no automatic retries or hidden calls."""
import json
import os
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class ModelCallError(RuntimeError):
    def __init__(self, message, metrics=None, trace=None):
        super().__init__(message)
        self.metrics = metrics or {}
        self.trace = trace or []


def load_project_env():
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / '.env', override=False)


def complete_json(messages):
    load_project_env()
    key = os.environ.get('DEEPSEEK_API_KEY')
    model = os.environ.get('DEEPSEEK_MODEL')
    if not key or not model:
        raise ModelCallError('Set DEEPSEEK_API_KEY and DEEPSEEK_MODEL before running live evaluation.')
    base_url = os.environ.get('DEEPSEEK_BASE_URL', 'https://api.deepseek.com').rstrip('/')
    payload = {'model': model, 'messages': messages,
               'thinking': {'type': 'disabled'}, 'temperature': 0,
               'response_format': {'type': 'json_object'}, 'max_tokens': 2500}
    request = Request(base_url + '/chat/completions', data=json.dumps(payload).encode(),
                      headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
    started = time.perf_counter()
    try:
        with urlopen(request, timeout=90) as response:
            data = json.load(response)
    except HTTPError as exc:
        # Avoid putting provider bodies or credentials into saved traces.
        raise ModelCallError(f'Model API returned HTTP {exc.code}.',
                             {'model_calls': 1}, [{'kind': 'model', 'error': f'HTTP {exc.code}'}]) from exc
    except OSError as exc:
        raise ModelCallError(f'Model request failed: {type(exc).__name__}.',
                             {'model_calls': 1}) from exc
    elapsed = time.perf_counter() - started
    usage = data.get('usage', {})
    input_tokens = usage.get('prompt_tokens')
    output_tokens = usage.get('completion_tokens')
    metrics = {'model_calls': 1, 'input_tokens': input_tokens,
               'output_tokens': output_tokens,
               'total_tokens': usage.get('total_tokens'), 'model': data.get('model', model)}
    content = data['choices'][0]['message'].get('content') or ''
    trace = [{'kind': 'model', 'name': 'single_call', 'seconds': elapsed,
              'metrics': metrics, 'raw_answer': content,
              'finish_reason': data['choices'][0].get('finish_reason')}]
    if data['choices'][0].get('finish_reason') == 'length':
        raise ModelCallError('Model output reached max_tokens; response was incomplete.', metrics, trace)
    try:
        answer = json.loads(content)
        if not isinstance(answer, dict):
            raise ValueError('Expected a JSON object.')
    except (ValueError, TypeError) as exc:
        raise ModelCallError('Model did not return a valid JSON answer object.', metrics, trace) from exc
    return answer, metrics, trace
