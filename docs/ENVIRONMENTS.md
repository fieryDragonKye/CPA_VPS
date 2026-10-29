# Windows / Linux 的区别

## Windows

用于前端开发、Node插件UI检查与Skills安装。Bun使用package.json声明的1.3.14，Node使用24。不要复制他人的node_modules；使用冻结锁文件安装。

统一前端的统计请求使用同源路径，避免硬编码浏览器本机8320。通过SSH访问VPS时，API地址是本地隧道地址，例如http://127.0.0.1:18317；这不是CPA容器内部端口。

旧版Windows双端口运行目录不在此仓库自动迁移。若完全本机运行，需要同源网关，或让统计服务提供管理页和管理API代理；不要把Linux配置中的容器路径直接填到Windows。

## Linux / WSL

插件通过CGO构建c-shared动态库；Go只负责构建，最终CPA运行无需Go。arm64库与amd64库不可互换。

Ubuntu22.04/glibc2.35已用于当前amd64私人插件构建；Debian Bookworm运行容器glibc2.36兼容该产物。其他发行版、编译器或架构需重新验证。CI测试不等于生产.so兼容验收。

```sh
# 仓库根，已安装Go与gcc
sh tools/build-plugin.sh
# 可选的 FreeTier 私人插件
sh tools/build-freetier-plugin.sh
```

正式替换.so之前：备份原库、插件历史JSON、配置；核对store.version/release-tag与文件内版本一致；确认无活跃请求；按平台能力热更新或只重启CPA。不要原位覆盖正被加载的库。

## Python

Python3.12+，无需requirements.txt。统计服务入口为insights/run.py，通过环境变量提供管理密钥文件、CPA_URL、SQLite路径和管理页路径，不硬编码个人目录。

```sh
cd insights
python -m unittest test_server
```

MANAGEMENT_KEY_FILE必须是仅含管理密钥的受保护文件。部署使用新的密钥与空数据库，不复制用户现有账号或数据库。
