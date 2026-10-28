# Linux 私有部署模板

这是供新实例使用的源码模板，不是原VPS文件镜像。不要在现有生产目录直接执行初始化。

1. 用Node24/Bun1.3.14构建web，设置VERSION=v8.0.23-personal.6。
2. 仓库根运行 `python tools/prepare-assets.py --arch amd64`（arm64主机选arm64）。工具下载CPA v8.0.23，验证官方checksums，仅提取程序；生成的vendor、assets均被Git忽略。
3. Docker基础镜像来源固定在lock.json，不使用latest；先拉取两个对应reference。没有网络时可在可信环境核对digest后离线docker load，不修改全局网络规则绕过问题。
4. 在Linux空目录初始化：

```sh
sudo mkdir -p /opt/cpa-personal
sudo python3 deploy/scripts/prepare-instance.py --instance /srv/cpa-personal --env-file /opt/cpa-personal/instance.env
sudo docker compose -f deploy/docker-compose.yml --env-file /opt/cpa-personal/instance.env build --pull=false
sudo docker compose -f deploy/docker-compose.yml --env-file /opt/cpa-personal/instance.env up -d --wait
```

程序生成新管理密钥、客户端Key、空Auth目录与空统计目录，不打印密钥。非root初始化需要按提示设置UID/GID10001权限。脚本拒绝覆盖非空实例；检查UID冲突。

容器通过network-owner共享网络命名空间，CPA127.0.0.1:8317、统计127.0.0.1:8320、网关8080；宿主仅发布127.0.0.1:18318。allow-remote=false与管理鉴权保持。不要把它改为0.0.0.0端口映射。

SSH配置使用自己的服务器别名，例如`cpa-vps`：

```sh
ssh -N -T -o ExitOnForwardFailure=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -L 127.0.0.1:18317:127.0.0.1:18318 cpa-vps
```

打开http://127.0.0.1:18317/management.html。前台隧道窗口关闭会断开本机访问；不会停止VPS服务。SSH认证与管理密钥是两套凭据。

首次启动不预装任何第三方插件、不导入OAuth或代理。需要私人插件时，先在兼容环境构建plugin，备份后放入实例plugins/linux/对应架构，设置全局插件开关与对应store.version/release-tag。不要混用同ID的多个库。官方商店更新可能覆盖私人主题。

network-owner更换后所有共享者需要一并重建；不要只替换网络锚点。CPA单容器在锚点保持时可以受控重启，但必须确认没有活跃请求。Compose的unless-stopped支持Docker启动后恢复；宿主Docker自启由服务器管理员配置。

## 备份恢复

停止CPA和统计写入并确认无任务后：

```sh
sudo python3 deploy/scripts/snapshot.py backup --source /srv/cpa-personal --to /srv/private-backups/cpa-YYYYMMDD --offline-confirmed
sudo python3 deploy/scripts/snapshot.py restore --source /srv/private-backups/cpa-YYYYMMDD --to /srv/cpa-restored --offline-confirmed
```

备份包含秘密，必须私有保存，绝不能提交Git。恢复只能到新目录。模板日志仍为文件日志开启、详细请求日志关闭、20MiB/3错误文件；统计90天/25万条由服务维护。Docker stdout/stderr使用独立轮转。

这些模板从已验证部署提取，但仓库重排后的完整Compose尚需新环境启动验收；不要把语法检查或单元测试当成已部署成功。
