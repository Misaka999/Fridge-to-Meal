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

## 连续对话与会话状态

在已激活的 Python 环境中，从项目根目录启动：

```powershell
python react_agent.py examples/example_request_real.json --chat --trace
```

程序先处理初始请求，然后接受自然语言追问或 JSON 更新。例如依次输入：

```text
改成两人份
也不要鸡蛋
/state
/exit
```

人数和饮食偏好的自然语言更新会额外调用一次 DeepSeek 提取变化，再把完整的会话库存、人数和偏好交给 ReAct。新的硬限制会加入现有要求。可以用 `/state` 查看当前状态，用 `/reset` 清空当前会话。初始样例的参考日期会继续保留。

JSON 更新按提供的字段覆盖，省略的字段继续沿用。偏好只覆盖提供的子字段，空数组可以清除对应偏好：

```json
{"servings": 2}
{"preferences": {"dietary_restrictions": ["vegetarian", "egg-free"]}}
{"preferences": {"likes": []}}
```

在聊天模式下，每行输入一条明确的库存操作。下面三行依次新增一批大米、把这批大米的剩余量设为 50 g、删除整批。网页或另一个 Agent 可以把同样的对象传给同一实例的 `sessions.run_turn(session_id, update)`。

```jsonl
{"inventory":{"op":"add","name":"rice","quantity":100,"unit":"g"}}
{"inventory":{"op":"update","name":"rice","quantity":50}}
{"inventory":{"op":"delete","name":"rice"}}
```

每次成功写入后，ReAct 会使用新库存重新推荐。普通推荐只读取库存。输入 `/state` 可以检查剩余量。新增操作可带 `expires_on`，更新操作会保留省略的字段。如果同名食材有多批，系统会询问要编辑哪一批，并列出从 0 开始的行号；在操作中补入 `"index": 行号` 即可指定。编辑时请使用库存中登记的名称。

缺少数量、单位或目标不明确时，系统会返回 `needs_clarification` 并保留原库存。补齐信息后重新发送完整操作。自然语言要求修改库存时，系统会引导用户提交显式 JSON。仍可用 `{"pantry": []}` 清空库存，或提交完整的新库存数组整体替换。参考日期可用 `as_of_date` 单独更新。

网页可创建一个 `MealSessions` 实例，用独立的会话 ID 调用：

```python
from agent.session import MealSessions
from react_agent import deepseek_model

sessions = MealSessions(model=deepseek_model())
first = sessions.run_turn("user-a", request)
second = sessions.run_turn("user-a", message="也不要鸡蛋")
other = sessions.run_turn("user-b", another_request)
state = sessions.get_state("user-a")
```

会话状态存在该实例的内存里，重启后需重新初始化。返回值在原有 `result`、`metrics` 和 `tool_trace` 之外附带本轮完整 `request`。模型调用和 token 指标包含自然语言更新提取步骤，未知 token 用量保留为 `null`。显式用户更新在推荐运行前保存，因此模型调用失败后可以沿用已更新的状态重试。

## 本地网页

在项目根目录激活 LLM 环境，运行 `python web_app.py`，打开 http://127.0.0.1:8765 。网页沿用项目根目录的 DeepSeek 环境配置。端口被占用时可以运行 `python web_app.py --port 8766`。

选择 **Load example** 会填入 Glazed Carrots 样例的库存和参考日期。点击 **Find recipes** 才会提交给 ReAct。可直接在表格中增加、修改或删除食材，再次提交即更新本轮库存。推荐完成后，在 **Ask a follow-up** 输入“改成两人份”，可观察人数和结果变化。点击 **Run details** 可查看菜谱 ID、模型调用次数和耗时。

同一标签页刷新后会恢复已提交的库存和偏好，聊天记录只在当前页面展示。服务重启后需要重新提交库存。

## Yangyang: tools and Plan-and-Replan

The additional Plan-and-Replan implementation, conservative RecipeNLG parsing, FoodKeeper archive lookup, and member test partitions are documented in [the integration handoff](docs/YANGYANG_HANDOFF.md). See [architecture](docs/ARCHITECTURE.md) and [interfaces](docs/INTEGRATION.md).

```sh
python plan_replan_agent.py examples/example_request_expanded_pasta.json --trace
python -m unittest discover -s tests -q
python -m eval.evaluate_project --check-only
python -m eval.evaluate_safety --check-only
```

The included expanded catalogue has 20 source-linked records; it does not provide complete RecipeNLG coverage. Automatically parsed records are not human-reviewed. FoodKeeper is a pinned third-party archive with explicit provenance, not a safety guarantee. Large CSV/index files, credentials and evaluation results are not included. The existing ReAct entry point and its default historical catalogue are preserved.
