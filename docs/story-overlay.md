# 剧情 overlay

剧情 overlay 是一层可以随时插话的演出层，不要求玩家先进入某个"剧情模式"。它只有三个可见部分：背景图、角色对话框、对话框旁边的立绘。

## 两种模式

剧本自己决定用哪种模式，前端不需要额外开关：

- **舞台模式**：剧本里出现了带 `asset_id` 的 `background` 步骤。overlay 全屏接管，按 16:9 居中留黑边排版，触摸设备会请求全屏并尝试 `screen.orientation.lock('landscape')`；锁不上（iOS Safari 不支持方向锁定）时显示旋转提示遮罩，玩家把手机横过来后继续，遮罩上也留了跳过入口。
- **插话模式**：剧本没有背景步骤。对话框浮在当前页面底部占满宽度，立绘不占对话框的宽度，而是站在对话框**后面**，下半截被半透明的对话框压住、透出来一点。不请求全屏、不改变屏幕方向，但整层铺满屏幕并接管点击：插话没说完之前点不到页面上的东西，点哪儿都是推进对话。移动端对话框会自动避开底部导航栏。

一句台词一次点击推进，点击整层任意位置都算推进；桌面端空格/回车推进，Esc 跳过。

## 剧本格式

剧本是手写 JSON，一个文件一个剧本（也允许一个文件放一个数组），目录是 `data/story/`。内容在加载时由 Pydantic 校验，未知触发 hook、非法参数、引用不存在的素材都会让内容加载直接失败。

```json
{
  "id": "welcome_farm",
  "title": "第一次走进农场",
  "priority": 10,
  "trigger": { "hook": "cue", "params": { "cue": "view:farm" }, "repeatable": false },
  "steps": [
    { "type": "background", "asset_id": "autumn_gate" },
    { "type": "portrait", "slot": "left", "asset_id": "maple_smile", "blend": "screen", "scale": 1.05, "offset_y": 0.04 },
    { "type": "dialogue", "speaker": "枫糖", "text": "这块地空了一整个冬天啦。", "focus": "left" },
    { "type": "portrait", "slot": "left", "visible": false }
  ]
}
```

`rewards` 是可选的，剧本第一次播完时结算一次：

```json
"rewards": { "partner_ids": ["fein"] }
```

目前只支持让伙伴加入。奖励在 `POST /api/red-leaf-town/story/<id>/seen` 里发放，同一个剧本重复上报不会再发一次，玩家已经拥有的伙伴会跳过；`repeatable: true` 的剧本不允许带奖励。发放走的是存档写入，接口会把新的存档一起返回，前端直接采用，不用等下一次轮询。奖励引用的伙伴必须存在，否则内容加载失败。

步骤只有三种：

| 类型 | 说明 |
|------|------|
| `background` | 换背景；`asset_id` 留空表示撤掉背景 |
| `portrait` | 在 `left` / `right` 显示立绘，`visible: false` 表示收起该侧。尺寸和位置跟着素材走，剧本只挑边 |
| `dialogue` | 一句台词；`speaker` 留空是旁白，`focus` 决定名牌贴在哪一侧 |

立绘一律按透明底素材处理，不提供黑底滤色选项：插话模式的 overlay 是 `position: fixed` 的独立 stacking context，`mix-blend-mode` 混不到下面的页面，滤色在那里无法按原义生效，所以统一要求上传透明底 PNG（上传转码保留透明通道）。

立绘的尺寸和位置是**素材自己的属性**，保存在 `data/story_assets.json` 里，剧本不重复写，同一张立绘在所有剧情里的站位一致。两种模式的画框比例差得远，所以各存一套：`inline_layout` 和 `stage_layout`，字段相同：

| 参数 | 范围 | 含义 |
|------|------|------|
| `scale` | 0.4–4.0 | 相对该模式默认高度的倍数。默认高度在舞台模式是舞台满高，在插话模式是 `min(40vh, 300px)`（移动端 `min(34vh, 220px)`）。缩放只改高度，脚下的基线不动，宽度朝远离贴边那侧生长 |
| `offset_x` | -0.5–0.5 | 横向平移，单位是立绘自身宽度的比例，正数往右 |
| `offset_y` | -0.5–0.5 | 纵向平移，单位是立绘自身高度的比例，正数往下 |

这些值在后台可视化调：`/red-leaf-town/admin/story` 的立绘卡片上点「位置」，会用真正的 overlay 起一个锁定的预览（点击不会翻页），拖滑块实时看效果，可以切左右站位、切插话/舞台模式（两种模式各自一套参数，分别调）、换预览背景，满意再保存。保存走 `PATCH /api/red-leaf-town/admin/story/assets/<id>`，一次写入两套 layout，后端复核范围。背景素材不允许带 layout 参数。读取旧结构时，直接挂在素材上的一套 `scale`/`offset_x`/`offset_y` 会迁移成两种模式共用同样的值。

复用伙伴插画的立绘（`partner_id`）没有素材记录，按默认值 1 / 0 / 0 显示。

立绘来源二选一：素材库的 `asset_id`，或者 `partner_id` + `breakthrough` 直接复用伙伴卡片已有的 9:16 插画。伙伴插画还没上传时该步骤退化为不显示立绘，不会让剧情播不下去。

## 触发

服务端负责判断，前端只负责发信号。玩家进入某个页面或完成某个操作时，前端 `POST /api/red-leaf-town/story/cue` 带上信号代号，服务端评估所有还没看过的剧本并返回该播的那些；播完前端 `POST /api/red-leaf-town/story/<id>/seen`，剧本 ID 记进存档的 `seen_story_ids`（schema v9）。`repeatable: true` 的剧本不受已看过约束。

信号代号形如 `view:farm`、`action:harvest`、`action:collect_mining`，由前端路由和 `stores/game.ts` 里的动作发出。

触发条件由 `src/red_leaf_town/story_triggers.py` 的 Python 注册表解释，剧本里只写 hook 代号和结构化参数，不写可执行表达式：

| hook | 参数 | 含义 |
|------|------|------|
| `cue` | `cue` | 收到指定信号 |
| `player_level` | `level` | 居民等级达到 |
| `has_item` | `item_id`, `quantity` | 仓库里有指定数量的物品（不分品质） |
| `owns_partner` | `partner_id` | 已经拥有某个伙伴 |
| `talent_unlocked` | `node_id` | 已经点亮某个天赋节点 |
| `all_of` / `any_of` / `none_of` | `conditions` | 组合上面的条件，最多嵌套 4 层 |

不带 `cue` 条件的剧本在任何信号下都会被评估，所以"升到 5 级就演一段"不需要专门的信号。新增触发方式的正确做法是注册一个新 hook，而不是在页面里写特判。

## 素材

图还没画好的时候，可以先在 `data/story_assets.json` 里手写一条 `asset_key` 为空的占位素材，剧本照常引用它：占位素材没有 URL，演出时这一步静默降级（背景不画、立绘不显示），舞台模式仍然按背景步骤判定。后台的素材卡会标出"占位"，之后用**同一个素材 ID** 上传真图就会原地替换，剧本不用改。

背景和立绘在 `/red-leaf-town/admin/story` 上传，沿用宿主统一的 CDN provider：服务端校验格式、按类型限制长边（背景 2560、立绘 1920）、统一转码 WebP（保留 PNG 透明通道），只把 object key 存进 `data/story_assets.json`。剧本引用素材 ID，不引用 URL。仍被剧本引用的素材不允许删除。

换图要显式覆盖：上传时 ID 已存在会直接报 `asset_exists`，带上 `overwrite` 才会替换，素材卡上的「替换」/「补图」按钮就是把表单填好并勾上这个选项。覆盖只换图——名称留空时沿用原名，立绘调好的 `inline_layout` / `stage_layout` 也会保留，所以补完图不用重新调站位。素材类型不能被覆盖改掉（剧本会因此失效），要改类型只能换 ID 或先删掉原素材。旧的 CDN object 不会被删除：object key 带内容摘要，覆盖后是一个新对象，旧文件留在 CDN 上。

剧本 JSON 和素材目录都有进程内缓存，改完文件后在后台点"重新读取剧本"（`POST /api/red-leaf-town/admin/story/reload`）即可生效，不需要重启服务。
