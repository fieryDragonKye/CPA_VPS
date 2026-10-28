# 上传 GitHub 前

这份目录从运行工作区按允许清单导出，没有继承工作区Git历史，防止历史中夹带私有内容。原始代码和数据没有被删除。

1. 决定仓库公开/私有。两种都不要提交密钥；曾提交过的密钥需要轮换，删文件或加.gitignore不能清除历史。
2. 审查docs/UPSTREAM.md中的许可范围；个人新增部分尚未自动统一授权，确认许可证后再公开分发。
3. 运行tools/review-public.py，检查报告；扫描只是辅助，不保证检出所有秘密。人工检查git diff和待提交文件。
4. 保留web/bun.lock与plugin/go.sum，排除node_modules、dist、编译器、缓存、截图、历史数据库和备份。
5. README示例仅使用回环地址与占位服务器名；不要提交自己的SSH配置、私钥、VPS地址、Webshare账号或机场订阅。
6. 首次仓库先作一个经过人工审查的基线提交；后续用feature/fix分支，经检查后合并main。当前准备分支为codex/prepare-github，不要直接把运行目录的全部历史推上去。
7. GitHub Actions只跑离线/模拟检查，不给CI放生产管理密钥，不自动部署、OAuth登录或消耗模型额度。

本次整理不执行git push、不创建远端仓库、不配置GitHub Secrets。依赖数量精简不意味着删除实际使用的库；更换编辑器/路由/动画库属于另一个重构任务。
