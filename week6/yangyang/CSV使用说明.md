# 真实 RecipeNLG 工具使用说明

## 当前行为

默认检索 `data/RecipeNLG_dataset.csv` 中 source=Gathered 的记录。现有 SQLite 索引有 1,642,756 条，建立索引时跳过 342 条不完整记录。CSV 不会被修改。

同时加载 `data/recipes_recipenlg.json` 中与当前索引原始记录哈希一致的三道核对过的真实菜谱。它们不是手写示例；每条保留原始食材、步骤、链接、原文份数、来源记录哈希和用量转换依据。

三道菜是 Glazed Carrots、Peach Glazed Carrots、Whipped Sweet Potatoes，均为配菜，不代表完整餐食。它们用于数量核对及联调，不能代表整个 RecipeNLG 的覆盖率。

在本文件夹运行：

```sh
python3 tools_cli.py
python3 tools_cli.py --retrieve
python3 -m unittest discover -s tests -v
```

无完整 CSV 时先运行 `python3 tools_cli.py --recipe-file data/recipes_recipenlg.json`。第一个命令使用 `data/example_request_real.json` 检查库存、人数及限制；第二个显示检索资料。

## 保留的检查

- 数量、单位、份数都要提供；未知值需要澄清。
- g/kg/lb/oz 只在质量之间换算，ml/l/cup/tbsp/tsp 只在体积之间换算，采用 US customary measures。不猜测食材密度；糖的克数不能自动换算为汤匙。
- 过期库存不可用，未过期且名称和单位兼容的多批库存可以相加。未知日期不推断到期时间。
- 水按原接口约定可用，油、盐等不能假定有。
- 名称规范化处理大小写、空格和部分明确别名。firm tofu / silken tofu 可用于广义检索，但严格匹配不自动视为相同。
- 饮食兼容性为 true（配料层面符合）、false（已知冲突）、null（需要核对包装）。null 不能当作符合；不认证过敏安全或交叉接触风险。
- 原始 CSV 配料文本也会标记已知饮食冲突，但“没发现冲突”不等于已经核实。

## 工具输出

`found` 只包含核对过份数、全部用量及限制的候选。
`INPUT_INCOMPLETE` 表示需要确认库存、单位换算或包装标签。
`RECIPE_DETAILS_UNVERIFIED` 表示只有未核实的原始候选，详情在 retrieved_candidates；不能猜份数，也不能声称无可行菜谱。
`no_match` 只代表已提供的本地核对集合没有匹配，不代表全世界或整个 CSV 没有菜谱。
`RECIPE_SEARCH_FAILED` 才是运行故障。

这两个额外字段/错误码需要与队友对齐，原 interface_alignment.md 保持不变。

## 给 Shuhua 的接入方式

```python
from tools import load_recipes, make_tool_registry, validate_request

issue = validate_request(request)
# If issue exists, return needs_clarification before searching.
context = {"recipes": load_recipes(request)}
functions, schemas = make_tool_registry(request, context)
```

Agent 可以基于 raw_ingredients / steps 组织进一步提取和澄清；目前工具不会因为模型自行声称“已核实”就把原始候选升级为严格匹配。
如果要扩大严格可推荐集合，补充有来源依据的份数、用量及饮食标记，再通过 import_recipenlg.py / compile_recipenlg.py 整理。未写明的份数不能凭空补齐。

Agent 仍是接口占位，未实现、未替换队友代码。

## Week 6 测试

新文件 tasks_recipenlg_yangyang.jsonl 有 25 条功能题（12 条 edge，4 条 unanswerable），只针对三道核对过的真实菜谱。旧 tasks_yangyang.jsonl 保留为手写 fixture 的回归测试，不要混用。

```sh
python3 evaluate.py --tasks tasks_recipenlg_yangyang.jsonl --check-only
```

队友 Agent 接好后再运行下列收费模型评测；需自行配置 DEEPSEEK_API_KEY 和账号可用的 DEEPSEEK_MODEL：

```sh
python3 evaluate.py --tasks tasks_recipenlg_smoke.jsonl --recipe-file data/recipes_recipenlg.json --agent agent_adapter:run --agent-trials 1 --output results/real_smoke_01
python3 evaluate.py --tasks tasks_recipenlg_yangyang.jsonl --recipe-file data/recipes_recipenlg.json --agent agent_adapter:run --agent-trials 3 --output results/real_yangyang_01
```

未接入的 agent_adapter 会被评测脚本拒绝；不会伪造 Agent 结果。两人合并并核对为 50 题后才满足全组作业。25 条 safety 草稿另存，不算这 50 条功能题。

评测两个版本使用相同候选；默认 CSV 模式会为每题准备相同检索 context。检索准备时间不计入 runner 延迟，metadata.json 会注明这一点；固定集合评测使用 --recipe-file。

目前只运行了离线测试，没有调用付费 API，也没有模型准确率、token 表格或失败分析结论。自动评分检查状态、ID 和排序；数量说明、烹饪步骤及解释仍须人工核对。
