---
name: feature-research
description: "Research features and implementation options using available online tools, authoritative documentation and relevant community evidence; compare compatibility, licensing, maintenance and implementation cost."
metadata:
  version: "1.0.0"
---

# Feature Research

仅在用户显式选择本 Skill 或输入 $feature-research 时使用。独立提供研究能力，不自动加载任何 UI 或 BUG Skill。

先核对问题、现有环境、版本和决策范围，再检查本会话实际可用的网络工具。联网能力不存在时，明确只做离线分析，列出待核实项；不得编造搜索、网页内容、用户评价、Star 数或访问日期。

## 研究工作流

1. 把需求转为可验证的问题和比较标准，先读取现有资料，避免重复宽泛搜索。
2. 有网络工具时按问题选择来源：官方文档/版本记录、源码/Issue/PR，再按需查 GitHub、LINUX DO、奶昔论坛、X、Reddit、Stack Overflow、V2EX 等社区。无需每次搜索所有网站。
3. 打开支持结论的原始页面，记录版本、时间与上下文。社区经验与官方能力分开；关键结论交叉验证，无法确认的明确保留。
4. 比较可行选项的适用条件、许可证、维护状态、迁移成本、依赖、安全边界及回滚难度。Star 和讨论热度只能作辅助信号。
5. 给出适合当前环境的建议和最小验证步骤。研究不自动授权安装、上传、改配置、付费、注册或部署。

## 按需资料

- 查询与来源核验，读 [来源及事实验证](references/sources-and-verification.md)。
- 多方案决策与交付，读 [方案比较](references/option-comparison.md)。

## 证据边界

页面无法访问、登录限制或搜索无结果要如实记录，不绕过访问控制。搜索摘要只能用于发现线索，未打开的内容不得写成已核实正文。技术事实优先依靠官方文档或源码；论坛用于发现使用经验、反例和复现方法。不得把源码、凭据、私人 Trace 或完整敏感请求上传外部服务；搜索词也需脱敏。
