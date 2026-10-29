# 上游、来源与许可边界

本项目是多组件源码整理，不是CPA后端重新开发。请保留上游版权、许可证与来源链接。

| 组件 | 来源 | 本目录许可 |
| --- | --- | --- |
| CPA后端8.0.47 | https://github.com/router-for-me/CLIProxyAPI/tree/v8.0.47 | licenses/CPA-LICENSE；程序不随Git提交，按校验和下载 |
| Web UI | https://github.com/router-for-me/Cli-Proxy-API-Management-Center | web/LICENSE、licenses/Frontend-LICENSE，保留MIT通知 |
| Codex插件原版0.4.4 | https://github.com/haowang02/cpa-plugin-codex-candy-eval/tree/v0.4.4 | plugin/LICENSE，MIT |
| FreeTier 2API原版0.1.21 | https://github.com/jiandanc/CLIProxyAPI-freetier2api-plugin/tree/v0.1.21 | plugin-freetier/LICENSE，MIT |
| 插件指纹检测数据 | plugin/internal/plugin/data/lm-detector | 保留其LICENSE、README及归因 |
| 私人UI、统计与部署维护、Skills | 本仓库个人定制部分 | 尚未额外统一授予根级开源许可证；发布者需确认授权意图 |

插件基线提交179d6dae48a0f0a735637ea2f373345b91caaca8，私人版0.4.4-personal.1仅改版本与三个UI文件。私有工作区历史、原VPS信息、测试账号和运行数据不在此整理版中。

FreeTier基线提交9283810ec62f5b893824b2a6f991b7f5d9435550，私人版0.1.21-personal.1的可执行源码仅修改控制台HTML；版本在构建时注入。整理版以根目录构建工具替代原Docker包装及Auth迁移脚本，并调整中英文README构建指令；保留上游回归测试。商店GPL-3.0标注与此固定源码的MIT LICENSE/registry.json不一致，没有据商店旧标签重写许可证。

Web来自Personal.6的Linux部署副本。该副本在工作区内不是独立受跟踪的上游Git检出，因此不伪造其上游精确commit；保留组件源码及本次导出清单，进一步发布标签前应补齐可核实的上游基线。Linux/Windows原副本差异集中于统计请求同源适配及其测试。

第三方npm/Go依赖受其各自许可证约束；bun.lock、go.sum用于复现，不替代许可证。字体、品牌图标及第三方模型测试数据也需遵守各自条款。不要删除许可证文件来精简体积。

是否给个人新增部分采用MIT或其他许可证，由仓库所有者决定；此准备过程没有替你追溯改变原作品授权。公开GitHub和授予开源许可证不是同一件事。
