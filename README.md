# Fridge-to-Meal ReAct

Week 6 的命令行版本使用 LangGraph 串联 DeepSeek Flash 和 Yangyang 的食谱搜索与库存匹配工具。默认使用经过核对的 RecipeNLG 子集。参见[接口约定](docs/interface_alignment.md)和[数据及评测说明](docs/README.md)。

## 运行

用 Python 3.11 或更新版本，在本目录的 PowerShell 里运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe react_agent.py examples/example_request_real.json --trace
```

运行前，在项目根目录的 `.env` 中填写 `DEEPSEEK_API_KEY`。默认模型为 `deepseek-flash`，可通过 `DEEPSEEK_MODEL` 调整。终端已设置的环境变量优先。要跑原来的菠菜豆腐样例，用 `react_agent.py examples/example_request_mock.json --mock`。

命令行把包含 `status`、`recipe_ids`、`message` 的 JSON 写到标准输出。加上 `--trace` 后，会把模型调用次数、延迟、输入/输出 token 和工具调用记录写到标准错误。省略 `--trace` 时只输出结果。传入 `-` 可从标准输入读取请求 JSON。

## 四种结果

| 验证路径 | 操作 | 预期 `status` |
| --- | --- | --- |
| 推荐 | 运行 `examples/example_request_real.json` | `recommended`，返回 `recipenlg_68810` |
| 澄清 | 将样例的 `servings` 改为 `null` | `needs_clarification`，无食谱查询 |
| 无匹配 | 将样例的 `pantry` 改为 `[]` | `no_feasible_recipe` |
| 工具失败 | 用原始样例并加上 `--mock-error` | `tool_error` |

ReAct 会复用工具的请求校验。未知数量、单位等可在搜索前直接追问。查询后如需核实包装标签、单位换算或原始食谱细节，输出 `needs_clarification`。检索无记录时也会说明范围并请求补充信息。真实查询失败输出 `tool_error`。模型请求失败或输出违反接口时，CLI 会打印错误并以非零状态退出。

## 跑 Week 6 小规模联调

从项目根目录运行。评测脚本将同一份食谱集合提供给 ReAct 和单次 LLM 基线。

```powershell
$env:DEEPSEEK_MODEL = "deepseek-flash"
.\.venv\Scripts\python.exe -m eval.evaluate --agent eval.agent_adapter:run --tasks eval/week6/tasks_recipenlg_smoke.jsonl --recipe-file data/recipes_recipenlg.json --agent-trials 1 --output results/smoke_01
```

正式评测用两人合并并审核过的 50 条题，使用 `--agent-trials 3`，并给 `--output` 一个尚未创建的目录。

## 给评测脚本调用

```python
from react_agent import deepseek_model, run_agent

model = deepseek_model()  # Reuse for every case in a batch.
run = run_agent(request, model=model)
result = run["result"]
metrics = run["metrics"]
tool_trace = run["tool_trace"]
```

接真实工具时，改为 `run_agent(request, model=model, search=real_search_recipes)`。真实工具用关键字参数接收 `pantry`、`servings`、`preferences`、`as_of_date`，按接口约定返回查询状态和候选列表。模型只选择调用哪个工具，ReAct 从已校验的请求传入这些参数。


## Yangyang: tools and Plan-and-Replan

The additional Plan-and-Replan implementation, conservative RecipeNLG parsing, FoodKeeper archive lookup, and member test partitions are documented in [the integration handoff](docs/YANGYANG_HANDOFF.md). See [architecture](docs/ARCHITECTURE.md) and [interfaces](docs/INTEGRATION.md).

```sh
python plan_replan_agent.py examples/example_request_expanded_pasta.json --trace
python -m unittest discover -s tests -q
python -m eval.evaluate_project --check-only
python -m eval.evaluate_safety --check-only
```

The included expanded catalogue has 20 source-linked records; it does not provide complete RecipeNLG coverage. Automatically parsed records are not human-reviewed. FoodKeeper is a pinned third-party archive with explicit provenance, not a safety guarantee. Large CSV/index files, credentials and evaluation results are not included. The existing ReAct entry point and its default historical catalogue are preserved.
