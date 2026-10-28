---
name: bug-investigation
description: "Investigate complex bugs, performance and stability failures through reproduction, measurement, isolated hypotheses and root-cause evidence; implement the smallest authorized fix and verify regressions."
metadata:
  version: "1.0.0"
---

# Bug Investigation

仅在用户显式选择本 Skill 或输入 $bug-investigation 时使用。独立诊断，不自动加载其他 Skill，也不假定项目框架、故障根因或修复授权。

## 证据驱动流程

1. 明确预期/实际行为、触发条件、环境和操作边界。先读取现有日志、报告、源码与版本；已有可靠证据的小修复不重复开展大规模调查。
2. 复现并建立基线，区分首次/重复、真实/模拟、客户端/服务端、输入步进/掉帧等条件。记录时间和关联标识时脱敏。
3. 提出能被证伪的少数假设。每次隔离一个变量，保留原始结果、失败实验和环境差异；临时测试不得偷写正式产物。
4. 用代码路径与运行证据关联原因；错误码、标题相似、单次峰值或“看起来像”不足以定因。定位不到时明确缺失证据和下一步最小实验。
5. 只在本次授权范围内实施最小修复。只读任务到诊断和方案为止；无证据不直接改代码，不扩展到无关重构或服务操作。
6. 对照基线执行适当回归，分别报告功能、布局、性能与真实业务覆盖。若确认修复引入故障，按事先保存的基线回滚。

## 按需资料

- 设计复现和隔离实验、记录证据时，读 [证据与实验](references/evidence-and-isolation.md)。
- 浏览器帧率、布局、滚动与渲染问题，读 [前端性能诊断](references/frontend-performance.md)。
- 需要判断常见误归因时，读 [诊断案例](references/diagnostic-cases.md)；它们是反例提示，不是当前故障的既定答案。

## 必须守住的边界

不泄露凭据、完整敏感请求或用户数据。不要因诊断需求自动重启、升级、重新授权、禁用账号、修改正式配置或上传资料。读取材料及测试不扩大授权。报告分开写测量事实、合理推测和未验证项目，并给精确文件位置、最小方案及回归/回滚方法。
