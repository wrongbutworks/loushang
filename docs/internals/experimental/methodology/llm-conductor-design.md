# LLM-Based Conductor 设计

## 核心设计原则

让大模型做调度决策，而不是硬编码规则。

## 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                    LLM Conductor                            │
├─────────────────────────────────────────────────────────────┤
│  Input: 完整上下文（状态 + 历史 + 角色输出）                  │
│       ↓                                                     │
│  LLM: "基于当前情况，哪个角色最适合接手？"                    │
│       ↓                                                     │
│  Output: 下一个角色 + 理由 + 置信度                           │
└─────────────────────────────────────────────────────────────┘
```

## Prompt 设计

```typescript
const CONDUCTOR_PROMPT = `
你是 Loushang 的指挥家（Conductor）。你的任务是根据当前任务状态，
决定下一个应该激活哪个角色。

## 可用角色及能力

${ROLES.map(r => `
- ${r.id}: ${r.name}
  能力: ${r.capabilities.join(', ')}
  适用: ${r.whenToUse}
`).join('\n')}

## 当前状态

当前角色: ${currentRole}
执行步骤: ${stepCount}
任务阶段: ${task.phase}

### 当前上下文
${formatContext(context)}

### 上一个角色的输出
${lastRoleOutput}

### 执行历史
${formatHistory(history)}

## 决策指令

基于以上信息，决定：
1. 下一个应该激活哪个角色？
2. 为什么？
3. 置信度（0-1）？

以 JSON 格式输出：
{
  "nextRole": "role_id",
  "reasoning": "详细理由...",
  "confidence": 0.85,
  "expectedOutput": "期望该角色产出什么",
  "switchType": "normal|urgent|exploratory"
}
`;
```

## 结构化输出

```typescript
interface CoordinatorDecision {
  nextRole: RoleId;
  reasoning: string;           // 可解释性
  confidence: number;          // 置信度 0-1
  expectedOutput: string;      // 期望产出
  switchType: 'normal' | 'urgent' | 'exploratory';

  // 可选：条件分支
  alternatives?: {
    role: RoleId;
    condition: string;
  }[];
}
```

## 实现代码

```typescript
class LLMCoordinator {
  private llm: LLMClient;

  async decide(context: TaskContext): Promise<CoordinatorDecision> {
    // 构建 prompt
    const prompt = this.buildPrompt(context);

    // 调用 LLM
    const response = await this.llm.complete({
      prompt,
      temperature: 0.3,  // 低温度，确定性决策
      responseFormat: 'json'
    });

    // 解析决策
    const decision = JSON.parse(response);

    // 安全校验
    if (decision.confidence < 0.6) {
      // 置信度低，询问人类
      return await this.askHuman(context, decision);
    }

    // 记录决策过程（可审计）
    this.logDecision(context, decision);

    return decision;
  }

  private buildPrompt(context: TaskContext): string {
    return `
当前任务: ${context.task.description}
当前阶段: ${context.currentPhase}
活跃角色: ${context.currentRole}

## 已完成的工作
${context.history.map(h => `
- [${h.role}] ${h.duration}: ${h.summary}
  产出: ${h.artifacts.join(', ')}
  问题: ${h.issues?.join(', ') || '无'}
`).join('\n')}

## 当前阻碍
${context.blockers.length > 0
  ? context.blockers.map(b => `- ${b}`).join('\n')
  : '无明显阻碍'}

## 决策

基于以上，应该选择哪个角色继续？
`;
  }
}
```

## 混合模式（渐进式）

```typescript
class HybridCoordinator {
  // 简单场景用规则（快）
  // 复杂场景用 LLM（准）

  decide(context: Context): Promise<Role> {
    // 1. 紧急/异常场景：规则优先（快）
    if (context.hasError) return 'debugger';
    if (context.qualityGateFailed) return 'validator';

    // 2. 常规流程：规则决定阶段
    const stage = this.rules.determineStage(context);

    // 3. 阶段内角色选择：LLM 决策（灵活）
    const candidates = this.getCandidatesForStage(stage);

    if (candidates.length === 1) {
      return candidates[0];
    }

    // 多个候选，让 LLM 选
    return this.llm.selectBestRole(candidates, context);
  }
}
```

## 动态角色发现

LLM 甚至可以**建议创建新角色**：

```typescript
interface CoordinatorOutput {
  nextRole: RoleId | 'suggest-new-role';

  // 如果建议新角色
  newRoleSuggestion?: {
    name: string;
    responsibility: string;
    reason: string;
    derivedFrom: RoleId[];  // 组合哪些现有角色
  };
}
```

**示例**：
```
当前: 任务需要既懂技术又懂业务的人...
LLM: 建议创建 "TechPM" 角色，组合 Analyst + Architect
```

## 自进化调度

```typescript
// 记录每次调度决策
interface DecisionLog {
  timestamp: number;
  context: TaskContext;
  decision: CoordinatorDecision;
  outcome: 'success' | 'failure' | 'suboptimal';
  humanFeedback?: string;
}

// 定期用历史数据微调 LLM
async function evolveCoordinator(logs: DecisionLog[]) {
  // 找出成功和失败的决策模式
  const trainingData = logs.map(log => ({
    prompt: log.context,
    completion: log.outcome === 'success'
      ? log.decision
      : { correction: log.humanFeedback }
  }));

  // 微调或更新 prompt
  await fineTuneOrUpdatePrompt(trainingData);
}
```

## 人类在环（Human-in-the-loop）

```typescript
interface CoordinatorWithHuman {
  // LLM 提议
  const proposal = await llmCoordinator.propose(context);

  // 人类确认/修改
  const humanDecision = await ui.showProposal({
    current: context.currentRole,
    proposed: proposal.nextRole,
    reasoning: proposal.reasoning,
    confidence: proposal.confidence,

    options: [
      { label: '确认', action: 'accept' },
      { label: '换一个', action: 'select-alternative' },
      { label: '指定角色', action: 'manual-select' },
      { label: '为什么？', action: 'explain-more' }
    ]
  });

  return humanDecision.role;
}
```

## 三层调度策略（推荐）

```typescript
class AdaptiveCoordinator {
  async decide(context: Context): Promise<Role> {
    // Layer 1: 硬规则（紧急、异常，0延迟）
    if (context.criticalError) return 'debugger';

    // Layer 2: 轻量 LLM（缓存、简单决策，快）
    const cacheKey = this.hash(context);
    if (this.cache.has(cacheKey)) {
      return this.cache.get(cacheKey);
    }

    // Layer 3: 完整 LLM（复杂场景，准）
    const decision = await this.llm.decide(context);

    // 缓存简单决策
    if (decision.confidence > 0.9) {
      this.cache.set(cacheKey, decision.nextRole);
    }

    return decision.nextRole;
  }
}
```

## 实际示例

```typescript
// 场景：软件开发
async function executeTask(task: Task) {
  const coordinator = new Coordinator();
  let currentRole = 'explorer';

  while (!task.completed) {
    const role = createRole(currentRole);

    // 执行当前角色
    const result = await role.execute(task.context);

    // 更新上下文
    task.context.update(result);

    // 协调器决定下一个角色
    currentRole = coordinator.decideNextRole(task.context);

    // 记录切换
    task.history.log({
      from: role.id,
      to: currentRole,
      reason: coordinator.lastDecisionReason
    });
  }
}
```

## 执行流程

```
任务: 设计一个新的用户认证系统

[Step 1]
Context: 刚启动，需求模糊
LLM: "需要探索可能方案 → Explorer"
Role: Explorer
Output: 3种方案：JWT/Session/OAuth

[Step 2]
Context: 有方案，需评估
LLM: "需要分析可行性 → Analyst"
Role: Analyst
Output: JWT适合，Session太重，OAuth过度

[Step 3]
Context: 方案确定，需设计
LLM: "需要架构设计 → Architect"
Role: Architect
Output: 系统架构图

[Step 4]
Context: 架构完成，准备实现
LLM: "需要详细设计 → Designer"
Role: Designer
Output: API设计、数据库schema

[Step 5]
Context: 设计完成
LLM: "需要实现 → Implementor"
Role: Implementor
...
```

## 优势对比

| 维度 | 规则调度 | LLM 调度 |
|------|---------|---------|
| **灵活性** | 低，硬编码 | 高，动态判断 |
| **解释性** | 明确 | 可生成理由 |
| **适应性** | 需改代码 | 调 prompt 即可 |
| **异常处理** | 难覆盖所有情况 | 可泛化处理 |
| **速度** | 快 | 需一次 LLM 调用 |
| **成本** | 无 | 有 API 成本 |

## 规则兜底（紧急情况）

```yaml
# coordinator-rules.yml
rules:
  - if: "has_error"
    then: "debugger"
    priority: 100

  - if: "uncertainty > 0.7"
    then: "explorer"
    priority: 90

  - if: "stage == 'discovery' && !problem_defined"
    then: "explorer"
    priority: 80

  - if: "stage == 'analysis' && !requirements_clear"
    then: "analyst"
    priority: 80

  - if: "stage == 'design' && !architecture_done"
    then: "architect"
    priority: 70

  - if: "stage == 'implement' && !code_complete"
    then: "implementor"
    priority: 60

  - if: "stage == 'verify' && !tests_pass"
    then: "validator"
    priority: 60

  - if: "technical_debt > threshold"
    then: "governor"
    priority: 50
```

---
