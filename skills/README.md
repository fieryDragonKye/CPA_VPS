# 四套手动调用 Skills

- personal-fluid-ui：私人蓝青流光玻璃风格。
- business-design-ui：根据品牌/业务选择风格，不默认套私人主题。
- feature-research：具备网络工具时研究，交叉核实来源。
- bug-investigation：复现、测量、隔离、最小修复与回归。

四套均包含SKILL.md、agents/openai.yaml及按需references，policy.allow_implicit_invocation=false。普通任务不自动调用；显式输入$名称或在客户端选择。两套UI不相互叠加。本仓库没有将它们放入活动.agents目录或通过AGENTS强制加载。

安装前备份同名目录，复制各独立文件夹到当前客户端实际支持的用户级Skills目录。现有Windows安装使用`%USERPROFILE%\.agents\skills`；Linux对应`~/.agents/skills`须结合所用客户端实际发现机制验证，不把文件存在当成已发现。重开会话、检查可见性并显式调用验收；本仓库不自动修改你的全局目录。

详细规则放在references，两个UI的frontend-quality.md应保持一致。更新时先改一份受控源并同步，核对SHA256；共享工程规范不代表共享视觉主题。不要将账号、客户数据或真实诊断Trace放入Skill。
