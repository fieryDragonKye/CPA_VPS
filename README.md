# CPA Personal

CPA v8.0.23 的私人管理界面（Personal.6）、统计服务、私人主题插件及手动调用 Skills。此仓库是源码与部署模板，不包含现有服务器实例或上游账号。

```text
web/       React 管理界面；默认通过同源私有网关访问统计服务
plugin/    Codex 降智测试 0.4.4-personal.1，保留上游测试逻辑
insights/  Python 标准库统计服务，SQLite 持久化
deploy/    Linux Docker Compose，回环监听、独立数据目录
skills/    四套可单独安装、仅显式调用的 Codex Skills
docs/      环境、安装、维护、许可证与发布注意事项
tools/     少量可复用的准备/构建工具
```

## 环境与最小依赖

| 部分 | 环境 | 依赖 |
| --- | --- | --- |
| 管理前端 | Windows / Linux | Node.js 24、Bun 1.3.14；使用 bun.lock |
| 统计服务 | Windows / Linux，Python 3.12+ | Python 标准库，无需 pip install |
| 插件 UI 测试 | Windows / Linux | Node.js 24 内置模块 |
| Linux 插件构建 | Linux / WSL，Go 1.24.13+、C 编译器 | go.mod / go.sum；需要 CGO |
| 正式部署模板 | Linux amd64 / arm64、Docker Engine + Compose | 首次下载对应 CPA 官方发布包及锁定基础镜像 |

Windows 可开发前端和运行 UI 测试。Linux `.so` 需要在兼容的 Linux 工具链构建；不要把 Windows DLL 放入 Linux。运行容器基于 Debian Bookworm/glibc2.36，建议用 Ubuntu22.04/glibc2.35 构建插件；不能直接假设 Ubuntu24.04 宿主生成的库可以加载。

## 本地开发

```sh
cd web
bun install --frozen-lockfile
bun run dev
# 发布前：bun run verify
```

网页的后端地址与管理密钥由用户运行时填写。不要将凭据写入源码或 Vite 环境变量，前端构建变量会进入浏览器产物。

```sh
cd plugin
node scripts/test-ui.cjs
go vet ./...
go test -race ./...
```

Linux/WSL 编译：`sh tools/build-plugin.sh`。见[环境说明](docs/ENVIRONMENTS.md)。

Linux部署见[部署说明](deploy/README.md)，Skills见[安装说明](skills/README.md)。本仓库不自动安装插件、不导入OAuth、不建立代理订阅、不创建公网入口。

## 安全与维护

- 此仓库中的 Compose 仅发布宿主127.0.0.1:18318，通过SSH转发访问。管理API继续要求密钥。
- 密钥、真实配置、OAuth、代理订阅、日志、SQLite与备份均属于私有运行数据，不进Git。
- 插件测试消耗模型额度，不在CI或部署时自动运行真实测试。
- 私人主题版本不会自行跟进上游。商店手动更新可能覆盖主题；非纯数字版本也可能产生误导的更新提示。
- 浏览器承担动画/GPU开销，VPS规格不能代替实际客户端性能验收。
- 保留有价值的单元/回归测试；已排除个人录屏、Trace、临时诊断工具和编译器缓存。

请先阅读[GitHub发布清单](docs/PUBLISHING.md)和[上游与许可证](docs/UPSTREAM.md)。不会因为源码可见就自动取得所有组件的额外许可。
