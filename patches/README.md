# 夏夜潮祭活动补丁包

活动内容（路线 / 钓点 / 采集点 / 物品 / 伙伴）全部在 `data/` 里以数据配置实现；
本目录是配套的运行时补丁，**不改动 `red_leaf_town` 包内任何文件**。

| 模块 | 职责 |
|---|---|
| `local_seasons.py` | 档期窗口（`data/seasons.json`）：窗口外的活动路线/钓点从列表消失、拒绝绕接口；领队加成（顾祇SP 120%）与路线/钓点蓝字 `leader_note` / `event_note` |
| `local_gathering_season.py` | 档期外的活动采集点连同任务一并隐藏；采集加成（绯恩SP 120%）与角标 |
| `local_fishing_bonuses.py` | 陪钓加成（艾欣愉陪钓灯湾 120%） |
| `local_traits.py` | 注册活动限定伙伴特性（`stage_presence` 舞台气场 / `summer_mood` 夏日心晴），import 即注册进上游 `_TRAITS` |

## 接线（应用装配层）

在**构造 `GameService` 之前**（补丁打的是类方法，装晚了第一个请求会漏）：

```python
import patches.local_traits  # 特性注册必须在引擎消费之前

from patches import local_seasons, local_fishing_bonuses, local_gathering_season

local_seasons.install()            # 默认读 <repo>/data/seasons.json
local_fishing_bonuses.install()
local_gathering_season.install()
```

`local_seasons.install(path)` 可显式指定档期文件；三个 `install()` 均幂等。

## 档期开关

`data/seasons.json` 里每个活动条目的 `starts_at` / `ends_at` 就是开关：
窗口之外三处活动场所全部不可见、不可交互，加成与蓝字一并休眠；
已出发的探索队伍可以走完并正常结算。改文件立刻生效（每次请求现读）。

当前窗口故意设在 2099 年：活动内容已入库、剧情尚未开放。
开放活动时只需把这两个日期改成真实档期。

## 活动伙伴的获取控制

`data/partners.json` 中 `guqi_sp` / `fein_sp` 目前 `standard_recruitable: false`，
两个「全部伙伴」招募池（standard / beginner）都不会抽到它们；
其余卡池使用显式名单，本就不含。剧情开放时把这两个字段改回 `true` 即可上架。

活动新物品已全部列入 `data/game.json` 的 `commissions.excluded_item_ids`，
不会出现在日常委托里；其产出渠道仅限活动场所，档期关闭即获取链关闭。
