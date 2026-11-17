# Fridge-to-Meal ReAct

Week 6 的命令行版本使用 LangGraph 串联 DeepSeek Flash 和本地模拟食谱工具。DeepSeek 决定何时查询，LangGraph 执行工具并把结果交回模型。参见[接口约定](interface_alignment.md)。

## 运行

用 Python 3.11 或更新版本，在本目录的 PowerShell 里运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:DEEPSEEK_API_KEY = Read-Host "DeepSeek API key" -MaskInput
.\.venv\Scripts\python.exe react_agent.py example_request.json --trace
```

如使用 Windows PowerShell 5.1，可以先在已配置 `DEEPSEEK_API_KEY` 的终端运行，或在 PowerShell 7 使用上面的密钥输入命令。默认模型为 `deepseek-flash`，可通过 `DEEPSEEK_MODEL` 调整。食谱工具是本地模拟实现，模型调用使用真实 DeepSeek API，需要 API key。

命令行把包含 `status`、`recipe_ids`、`message` 的 JSON 写到标准输出。加上 `--trace` 后，会把模型调用次数、延迟、输入/输出 token 和工具调用记录写到标准错误。省略 `--trace` 时只输出结果。传入 `-` 可从标准输入读取请求 JSON。

## 四种结果

| 验证路径 | 操作 | 预期 `status` |
| --- | --- | --- |
| 推荐 | 运行 `example_request.json` | `recommended`，返回 `r_spinach_tofu_01` |
| 澄清 | 将样例的 `servings` 改为 `null` | `needs_clarification`，无食谱查询 |
| 无匹配 | 将样例的 `pantry` 改为 `[]` | `no_feasible_recipe` |
| 工具失败 | 用原始样例并加上 `--mock-error` | `tool_error` |

模拟工具只收录菠菜炒豆腐，用来联调份量、库存和状态分支。当前版本会就未知的库存数量或单位追问。模型请求失败或输出违反接口时，CLI 会打印错误并以非零状态退出。

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
