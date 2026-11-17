# Fridge-to-Meal Week 6 接口对齐

**Shuhua** 实现 ReAct 和模拟工具。**Yangyang** 实现真实食谱工具、基线和评测脚本。两人用下面同一组 JSON 样例开发。联调时，ReAct 使用真实工具替换模拟工具，调用方式和最终输出格式保持一致。

## 1. 请求样例 · 评测脚本 → Agent 或基线

```json
{
  "pantry": [
    {"name": "spinach", "quantity": 200, "unit": "g", "expires_on": "2026-11-17"},
    {"name": "tofu", "quantity": 300, "unit": "g", "expires_on": "2026-11-21"},
    {"name": "soy sauce", "quantity": 30, "unit": "ml", "expires_on": null}
  ],
  "servings": 2,
  "preferences": {
    "dietary_restrictions": ["vegetarian", "egg-free"],
    "likes": []
  },
  "as_of_date": "2026-11-16"
}
```

- `pantry` 是完整库存。`[]` 表示确实没有食材。食材名使用原始输入，由工具做名称匹配。`quantity` 用数字，`unit` 用单位字符串。未知数量或单位用 `null`。
- `servings` 是正整数。`null` 表示需要询问人数。`dietary_restrictions` 是硬限制，`likes` 是排序偏好；没有限制或偏好时对应数组为 `[]`。
- `expires_on` 和 `as_of_date` 使用 `YYYY-MM-DD`。评测固定 `as_of_date`，这样同一用例在不同日期执行时仍可比较。`expires_on: null` 表示日期未知，此食材不参与按到期日排序。样例中菠菜距离到期还有一天。

## 2. 工具返回样例 · `search_recipes` → ReAct

Week 6 的 `search_recipes` 接收第 1 节的四个字段。工具在本地食谱集合中匹配现有食材、份量和硬性饮食限制。`ingredients` 返回**已按请求人数计算的必需用量**。ReAct 从候选中选出最多三个，可以使用到期日和 `likes` 排序。

**找到候选 · `found`**

```json
{
  "status": "found",
  "candidates": [
    {
      "recipe_id": "r_spinach_tofu_01",
      "title": "菠菜炒豆腐",
      "servings": 2,
      "ingredients": [
        {"name": "spinach", "quantity": 150, "unit": "g"},
        {"name": "tofu", "quantity": 250, "unit": "g"},
        {"name": "soy sauce", "quantity": 15, "unit": "ml"}
      ],
      "steps": ["将豆腐切块，菠菜洗净。", "用不粘锅将豆腐煎至金黄，加入菠菜炒软，再拌入酱油。"]
    }
  ],
  "error_code": null
}
```

**搜索成功但无匹配 · `no_match`**

```json
{
  "status": "no_match",
  "candidates": [],
  "error_code": null
}
```

**搜索失败 · `error`**

```json
{
  "status": "error",
  "candidates": [],
  "error_code": "RECIPE_SEARCH_FAILED"
}
```

`found` 至少有一个候选，ID 采用本地食谱的固定 ID。只有查询执行成功、输入足以核对约束且确实没有符合条件的食谱时，才返回 `no_match`。如果需要人数或某项用量才能判断，ReAct 先澄清，拿到足够信息后再走完整匹配。查询异常返回 `error`，保留错误码供评测和日志使用。

## 3. 最终输出样例 · Agent 或基线 → 评测脚本

统一输出 `status`、`recipe_ids` 和 `message`。`recipe_ids` 按推荐顺序排列，评分脚本直接读取这些 ID；`message` 是展示给用户的文本。两种实现共用该格式，评测可分别保存模型调用次数、耗时、token 和工具调用记录。

**推荐 · `recommended`**

```json
{
  "status": "recommended",
  "recipe_ids": ["r_spinach_tofu_01"],
  "message": "推荐两人份菠菜炒豆腐。它用到明天到期的菠菜，且符合素食和不含鸡蛋的要求。用菠菜 150 克、豆腐 250 克、酱油 15 毫升。将豆腐切块煎至金黄，加入洗净的菠菜炒软，再拌入酱油。"
}
```

**需要澄清 · `needs_clarification`**，例如 `servings` 为 `null`。

```json
{
  "status": "needs_clarification",
  "recipe_ids": [],
  "message": "请问要做几人份？确认人数后，我可以检查现有食材的用量是否足够。"
}
```

**无可行菜谱 · `no_feasible_recipe`**，例如库存只有鸡蛋而用户要求纯素，工具返回 `no_match`。

```json
{
  "status": "no_feasible_recipe",
  "recipe_ids": [],
  "message": "你登记的库存只有鸡蛋，本地食谱中没有符合纯素要求的选项。你可以更新库存信息，或告诉我是否要调整要求。"
}
```

**工具失败 · `tool_error`**，例如工具返回 `error`。

```json
{
  "status": "tool_error",
  "recipe_ids": [],
  "message": "食谱查询失败，暂时无法判断有哪些菜可以做。你可以稍后重试。"
}
```

`recommended` 必须包含 1–3 个不同的 ID。ReAct 的 ID 来自当前查询的 `candidates`；基线从同一用例提供的食谱集合中选取 ID。其他状态的 `recipe_ids` 均为 `[]`。基线使用同一 `recommended`、`needs_clarification` 和 `no_feasible_recipe` 状态。模拟工具故障的用例用于检查 ReAct 的故障分支，基线自身的模型请求失败由评测脚本单独记录。

## 联调顺序

1. **各自先跑。** Shuhua 用三种工具返回样例写模拟工具，再用缺少人数的请求验证澄清。Yangyang 用相同请求和本地样例食谱验证真实工具及输出解析。
2. **换成真实工具。** 用第 1 节的库存和限制跑通推荐，再分别把库存改成只有鸡蛋并要求纯素、把人数设为 `null`，以及模拟一次搜索异常。核对四种 Agent 状态和对应的 `recipe_ids`。
3. **接评测脚本。** 对同一批功能题提供相同库存、偏好、参考日期和食谱集合。先用 5 条题确认可以保存结果、判分并找到失败记录，再跑全量。测试的预期状态和答案由评测脚本持有。
