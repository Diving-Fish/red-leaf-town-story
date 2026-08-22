# 红叶镇物语

一个以种植、生产和长期成长为核心的轻量放置游戏。仓库包含游戏数据、领域逻辑、Web 前端、QQ 插件和测试。

## 目录

- `data/`：版本化的游戏数值与内容配置
- `src/red_leaf_town/domain/`：不依赖 Web、QQ 或 Redis 的游戏规则
- `src/red_leaf_town/application/`：用例与结算服务
- `src/red_leaf_town/infrastructure/`：Redis 等外部适配器
- `src/red_leaf_town/web/`：Quart Web/API 适配器
- `src/red_leaf_town/qq/`：NoneBot QQ 插件
- `frontend/`：Vue 3 前端
- `tests/`：单元和接口测试

设计约束和后续系统扩展方式见 [`docs/architecture.md`](docs/architecture.md)，伙伴、主角天赋、逐格生产和品质公式见 [`docs/game-design-foundations.md`](docs/game-design-foundations.md)。

## 本地测试

```bash
../../venv/bin/python -m pytest tests
```

## 前端开发

```bash
cd frontend
npm install
npm run dev
```

生产构建与静态资源部署：

```bash
./build-front.sh
```

伙伴卡片后台位于 `/red-leaf-town/admin/partners`。它使用管理员 Token 鉴权，包含卡片配置和玩家发放两个面板；插画上传沿用宿主的统一 CDN provider，伙伴数值和图片 object key 保存在 `data/partners.json`。玩家登录后可以从 `/red-leaf-town/partners` 管理自己的伙伴仓库。

农田支持安排一名具有农作倾向的伙伴驻场。开工时服务端根据伙伴有效能力生成不可变任务快照并缩短种植时间；任务进行中伙伴被锁定，作物成熟后自动恢复移动资格。

## OAuth 配置

授权中心需要登记独立应用 `red_leaf_town`，回调地址必须是：

```text
https://chiyuki.diving-fish.com/api/oauth/red-leaf-town/callback
```

随后在主服务的 `DF_OAUTH_CONFIG` 中加入同名配置项。作用域只需要
`openid profile`，不申请邮箱或 QQ 号。
