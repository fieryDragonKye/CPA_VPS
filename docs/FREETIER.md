# FreeTier 2API 私人版部署

版本：CPA v8.0.47、FreeTier `0.1.21-personal.1`。这是可选插件，不随 Compose 模板自动启用，不需要独立的 Node/Python 服务。账号需用户自行添加；安装不导入其他账号，不自动发起模型测试。

## 配置与持久化

将编译好的动态库放到已挂载插件目录的 `linux/amd64/` 子目录。使用独立文件名，不原位覆盖已加载库。先备份配置、已有插件和状态；确认没有活跃请求。保持原有其他插件与全局代理配置。

在现有 `plugins.configs` 下增加下列节点；按当前容器中的可写插件挂载路径调整 state_dir：

```yaml
freetier2api:
  enabled: true
  state_dir: /var/lib/cpa/plugins/freetier2api-data
  enabled_realms: cn,global
  auto_checkin: false
  auto_tasks: false
  log_to_file: false
  prompt_mode: passthrough
  store:
    id: freetier2api
    name: FreeTier 2API
    author: jiandanc
    version: 0.1.21-personal.1
    release-tag: v0.1.21-personal.1
    repository: https://github.com/jiandanc/CLIProxyAPI-freetier2api-plugin
    license: MIT
    install:
      type: github-release
```

**使用块式 YAML。** 此上游插件逐行解析宿主下发的配置；JSON/flow-style YAML 可能令 state_dir 等设置未生效。本仓库初始化工具生成的 JSON 兼容 YAML 在启用本插件前应先转换为块式 YAML，并核对解析后的结构完全一致；不要盲目重建已有实例配置。

目录由 CPA 的运行 UID/GID 拥有，权限0700；机器盐与状态随插件目录一起持久化备份，不复制到镜像或 Git。`log_to_file: false` 不增加插件独立文件日志。自动签到与自动任务初始关闭，添加账号后由用户决定是否开启。

## SSH 私有网关

本仓库 Caddy 模板增加以下精确路径族，仍只经回环地址和 SSH 访问；管理鉴权保持开启：

- `/v0/resource/plugins/freetier2api` 与其子路径。
- `/v0/management/plugins/freetier2api` 与其子路径。
- 宿主 OAuth 兼容端点 `/v0/management/freetier-auth-url`、`/v0/management/get-auth-status`。

控制台地址为 `http://127.0.0.1:18317/v0/resource/plugins/freetier2api/console`，或从 CPA 左侧插件入口进入。没有持久保存面板管理密钥时，控制台提供手工填写兜底；不要把密钥加入URL或源码。

安装后先验证插件 registered/effective_enabled 与版本、资源200、有效管理鉴权200、无鉴权401、可写状态持久化和原有统计/插件正常。优先让 CPA 自动发现并热加载；只有无法热加载且没有活跃任务时，才受控重启 CPA。其他容器不因安装插件而整体重建。

## 业务验证与回滚

真实供应商 OAuth、额度、签到和模型调用需添加对应合法账号后逐项验证。仅看到控制台或15个供应商不证明真实调用成功。上游控制台在认证后会读取额度、模型等，不应把正式控制台访问统称为完全无副作用。

更新前备份旧配置、库和整个 `freetier2api-data`。回滚只撤回本插件配置与库，并按差异还原网关新增路径，保留新生成的状态；不要用旧数据库/账号快照覆盖后来数据。不要解除管理鉴权或开放公网端口来解决访问问题。
