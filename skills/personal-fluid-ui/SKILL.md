---
name: personal-fluid-ui
description: "Design, implement, or review personal web UI explicitly requesting the owner's Premium Fluid Glass aesthetic: blue-cyan light fields, layered glass, refined reflections and motion."
metadata:
  version: "1.0.0"
---

# Personal Fluid UI

仅在用户显式选择本 Skill 或输入 $personal-fluid-ui 时使用。不要因普通任务描述相似而主动启用，也不自动加载另一套 UI Skill。

以 CPA Personal 的私人审美为方向：深蓝空间、青蓝柔光、多层玻璃、方向性反射、精致 Hover 和自然动画。业务可用性与真实流畅性优先于装饰数量；用户本次要求、品牌和已有产品约束始终优先。

## 实施方式

1. 读取实际页面、技术栈、设计系统与任务边界。维护既有项目时保留真实数据、导航、接口和交互语义，不把概念参考图中的虚构功能带入产品。
2. 明确背景光场、重点面板、普通卡片、密集数据区的层次。只改任务所需区域，不把每个信息块都做成发光可点击卡片。
3. 沿用项目组件和 CSS，先建立文件基线，再最小实施。小修复直接复用已有诊断证据，不重新设计全站。
4. 用实际渲染检查视觉，用适当测量判断性能。构建与测试通过不代表材质、动态或帧率已达标；报告实际验证和剩余问题。

## 按需资料

- 决定颜色、玻璃层次与空间关系时，读 [视觉系统](references/visual-system.md)。
- 实现流光、Hover 或低性能设备降级时，读 [材质与动画](references/motion-and-materials.md)。
- 完整页面、响应式与交付检查，读 [前端工程质量规范](references/frontend-quality.md)。窄范围修改只读取相关条目。
- 遇到滤镜卡顿、导航重影、布局跳动或控件裁切，读 [CPA 已验证经验](references/cpa-lessons.md)，将旧测量当作案例而非当前项目的证明。

## 交付约束

不因私人风格增加 WebGL、持续鼠标追踪或大型动画依赖。需要新依赖或超出当前授权的服务操作时，先说明必要性并遵守用户边界。保持减少动态、减少透明和无背景模糊时的可读替代。没有浏览器或性能工具时明确写未验证，不声称所有设备 60fps。
