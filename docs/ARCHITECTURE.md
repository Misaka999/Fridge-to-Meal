# System and experiment flow

```mermaid
flowchart TD
    U[Authoritative pantry, servings, preferences and date] --> V[Validate request]
    V -->|missing essential data| Q[Ask for clarification]
    V --> S[Shared recipe and storage tools]
    S --> D[RecipeNLG: explicit yields, amounts and provenance]
    S --> F[FoodKeeper: exact variety and storage event]
    D --> C[Quantity, units, dietary constraints and availability]
    F --> C
    C --> P[Preserve expiry priority, then likes]
    P --> O[Up to 3 alternatives, amounts, steps and source limits]
    C -->|uncertain source or labels| Q
    C -->|operational failure| E[Report error or bounded retry]
    C -->|no feasible local match| N[Explain local-catalogue scope]
```

```mermaid
flowchart LR
    I[Same task and same source pool] --> B[Baseline: one model call per run]
    I --> R[ReAct: model selects a tool, observes, answers]
    I --> P[Plan-and-replan: explicit plan, execute, inspect, revise]
    P -->|changed request or unexpected result| P
    B --> G[Same held-out grader]
    R --> G
    P --> G
    G --> T[Accuracy, calls, tokens, latency and 3-run reliability]
    G --> X[Safety indicators, benign controls and manual review]
```

## Plan-and-replan execution

1. Validate the authoritative input before model calls.
2. Ask the model for an explicit sequence of supported actions.
3. Execute common matching tools; never execute model-generated code or pantry edits.
4. On failure, no match, missing information or an explicit revised request, obtain a revised plan from the actual observation.
5. Retain shared candidate ranking. Generate a final JSON answer.
6. Validate the answer against the latest observation. Allow one bounded format repair; preserve failure evidence if it still fails.

This adds a planning/replanning phase rather than relabeling ReAct. It can cost more model calls; only the recorded comparison can establish whether that cost is useful.
