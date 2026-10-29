# FreeTier 2API — CPA Personal

基于 [jiandanc/CLIProxyAPI-freetier2api-plugin v0.1.21](https://github.com/jiandanc/CLIProxyAPI-freetier2api-plugin/tree/v0.1.21)，提交 `9283810ec62f5b893824b2a6f991b7f5d9435550`。私人构建版本 **0.1.21-personal.1**，保留 MIT LICENSE 和原作者声明。

## 定制范围

`internal/admin/console.html` 增加深蓝/青蓝私人主题、分级玻璃材质、按钮局部高光和原生深色 Select。只保留一个 transform/opacity 渐变光场动画，提供减少动态、减少透明与不支持背景模糊时的降级。主题只读跟随 CPA 的保存偏好；窄屏宽表内部滚动。账号、供应商协议、任务、配额、模型与认证实现保持上游逻辑。

此源码目录保留上游有价值的单元/集成/架构测试；不包含个人预览服务器、临时浏览器脚本、模拟演示数据、截图或部署操作脚本。原版 Docker 编译包装和一次性 Auth 迁移脚本未纳入；统一使用仓库根目录的构建工具。

## 构建

```sh
# 仓库根，Linux/WSL，Go 1.24.13 与 gcc；运行时不需要 Go。
sh tools/build-freetier-plugin.sh
```

产物在 `plugin-freetier/dist/`，不提交到 Git。默认执行 vet、离线测试和 race 检查，不执行 `live` 标签实况测试。Linux amd64/glibc 库不可用于 Windows 或 arm64；其他平台需独立编译和兼容验证。

## 安装与更新

见 [FreeTier 部署说明](../docs/FREETIER.md)。状态必须持久化在可写目录，不能依赖只读容器内的默认 HOME。每个配置键使用独立的块式 YAML；不要使用单行 JSON/flow style 作为插件配置。

手动从官方商店更新/重装可能覆盖私人主题；没有额外添加自动升级任务。合并上游后重新验收，使用新版本/新库文件并保留回滚资料。商店旧 GPL-3.0 元数据与本固定源码的 MIT 文件不一致，以本目录所保留的固定版本许可为核对依据。
