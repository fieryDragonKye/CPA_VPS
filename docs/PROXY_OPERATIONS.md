# VPS 节点接入与运维

本文是可复用的运维流程和配置结构说明。生产原稿、真实地址、订阅、节点标识、控制器秘密和备份位置仍保存在私有运维记录中。没有在整理文档时重新查询或修改 VPS。

故障分类、测量口径及匿名历史案例见[CPA 网络排查](NETWORK_TROUBLESHOOTING.md)。部署实例与源码仓库分开，见[部署说明](../deploy/README.md)和[发布约定](PUBLISHING.md)。

## 链路和选择策略

```text
CPA → 受鉴权保护的本机代理入口 → 主备策略
    → 前置 A／B → 同一固定出口代理 → 模型服务
```

每个固定出口包装通过 dialer-proxy 使用对应前置，见[官方链式拨号说明](https://wiki.metacubex.one/en/config/proxies/dialer-proxy/)。切换前置不必更换固定出口账户；应验证目标可见出口是否仍符合预期。

优先使用健康主节点、失败时按序选择备用，与持续竞争最低延迟属于不同选择目标。fallback 的顺序选择语义见[官方说明](https://wiki.metacubex.one/en/config/proxy-groups/fallback/)。策略是否回切、何时检查、全失败及空组行为，需在实际固定版本上验证。

固定出口是需要验收的路由约束。核对全部业务规则、嵌套组、provider 展开结果和出口保护，分别测试全部候选不可达与候选为空的情形。不要依赖组名称推定失败时一定阻断流量。

## 占位结构示例

下方仅展示包装和主备组，**不是完整可运行配置**。FRONT-A、FRONT-B 的定义未包含；请从自己获得授权的订阅中完整保留协议、Host、SNI、路径、证书和连接参数。示例域名不可用于真实探测，账户字段也是占位值。

```yaml
unified-delay: true
proxies:
  - name: EXIT-VIA-A
    type: socks5
    server: fixed-exit.example.invalid
    port: 1080
    username: "<EXIT_USERNAME>"
    password: "<EXIT_PASSWORD>"
    dialer-proxy: FRONT-A
  - name: EXIT-VIA-B
    type: socks5
    server: fixed-exit.example.invalid
    port: 1080
    username: "<EXIT_USERNAME>"
    password: "<EXIT_PASSWORD>"
    dialer-proxy: FRONT-B
proxy-groups:
  - name: MODEL-PRIMARY-BACKUP
    type: fallback
    proxies:
      - EXIT-VIA-A
      - EXIT-VIA-B
    url: https://health.example.invalid/probe
    expected-status: 200
    interval: 300
    timeout: 8000
    lazy: false
rules:
  - MATCH,MODEL-PRIMARY-BACKUP
```

选用的健康目标和状态码应对应实际服务，不能将本例的 200 或历史案例的 405 机械套用。间隔和超时是演示值，不是适用于所有链路的推荐预算，字段语义见[策略组公共配置](https://wiki.metacubex.one/en/config/proxy-groups/)。

CPA 入口协议与固定出口协议分别配置。对支持两种协议的端点做 HTTP／SOCKS5 比较时，保留端点、账户、DNS、前置和重试条件；参考[Webshare 的协议说明](https://help.webshare.io/en/articles/8375305-understanding-proxy-connection-types-direct-rotating-and-backbone)，仍须核对所用账户的具体设置。

## 变更、验证、发布

1. 记录代码仓库和实例状态，私有备份当前配置、节点映射和相关操作脚本，并确认如何恢复。完整配置和日志不进入源码仓库。
2. 使用完整连接参数匹配订阅条目；同名条目不能视为相同配置。区分新订阅与历史候选。
3. 明确只改变哪些字段。保留计划外的 DNS、前置参数、固定出口、路由规则和自动组设置。
4. 先用实例实际使用的核心版本做配置检查，再在隔离内核验证实际出口和轻量目标。
5. 验收通过后，按该版本控制 API 的鉴权要求应用变更；核对核心进程、运行时配置、候选数量和选中叶节点。
6. 在独立诊断目标下检测全部候选，再对较快候选复测。避免用不同目标的结果覆盖业务健康目标的状态。
7. 记录成功数／总数、失败阶段、完整耗时及固定出口结果。需要模型调用验收时，另外获得相应授权并限制次数。

延迟、出口查询、额度接口和真实生成各自有验收用途。低延迟或额度接口一次成功，不足以确认长请求稳定。

## 查询和维护入口

本仓库不提供实例专用的 proxy-status 脚本、SSH 别名或服务单元。使用自己的只读运维入口查询核心健康、策略组、叶节点和出口；不要假定另一台服务器有相同文件路径或命令。

网络观察器可以辅助连接关联，但不能改变或代替业务路由。更新容器网络或节点清单后，验证观察器映射和日志轮转是否仍有效。CPA 阶段日志的开关和覆盖范围见[诊断补丁说明](../patches/codex-transport-trace/README.md)。

## 备份与恢复

恢复前先确认当前配置是否已发生后续变更。优先恢复本次变更涉及的范围，保留后续统计、鉴权和页面部署，不直接覆盖整套历史实例。

节点移除也要核对包装代理、组成员、默认选择和标签引用，不能只删一个显示名称。恢复旧配置可能重新引入已经撤下的节点，需对照预期清单验证。

含凭据的备份留在受限运行目录，私有原稿记录准确位置。共享的变更摘要使用匿名候选标识，记录日期、版本、数量、协议变更范围和验收口径即可。必要的仓库内资料应随源码维护，私有原始证据不为修复链接而批量复制进来。
