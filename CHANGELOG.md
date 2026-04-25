# 更新日志

> 这里只记录项目功能、架构和工程能力相关的更新，不记录简历、面试文档等个人整理内容。

## 2026-04-15

### Redis 缓存优化

- 新增 Redis 缓存层，并支持 Redis 不可用时自动降级，不影响主流程运行。
- 接入天气查询缓存，减少同城天气的重复外部请求。
- 接入高德地图地理编码、POI 搜索和路线估算缓存，减少重复地图查询开销。
- 接入 RAG 检索结果缓存，复用高频 query 的攻略片段召回结果。
- 增加基础 `cache hit / cache miss` 日志，便于本地验证缓存命中情况。
- 通过本地 Docker Redis 容器验证缓存 key 写入成功。

### 本次验证到的缓存 key

```text
trip_planner:weather:forecast:大理
trip_planner:rag:guide:大理 自然风景 拍照 美食 轻松 不想太早起床，希望安排一个适合看日落的地点。 景点 行程 攻略 推荐:5
trip_planner:map:place:大理 舒适型住宿 2:大理:1
trip_planner:map:place:双廊古镇:大理:1
trip_planner:map:route:100.323501,25.647149:100.131582,25.852950
trip_planner:map:place:大理 舒适型住宿 1:大理:1
trip_planner:map:place:大理 舒适型住宿 3:大理:1
trip_planner:map:route:100.323501,25.647149:100.164000,25.694836
trip_planner:map:place:大理古城:大理:1
trip_planner:map:geocode:大理:大理
trip_planner:map:place:大理 出发点:大理:1
trip_planner:map:route:100.323501,25.647149:100.194322,25.908323
trip_planner:map:place:喜洲古镇:大理:1
```

## 2026-04-25

### RAG 在线阶段优化

- 接入轻量化 Query Rewrite，不再直接拼接整句备注，而是从用户偏好、节奏与备注中提炼更适合检索的关键词。
- 在 `rag_tool.py` 中补充旅行场景规则词，例如日落、傍晚、洱海、双廊、慢节奏等，提升旅行规划类 query 的检索聚焦度。
- 在 `retriever.py` 中加入第一版轻量 Rerank，对标题命中、正文命中、行程类标题和已知噪声片段做启发式打分。
- 对“文档开头”这类低信息量片段做强惩罚，并对与当前主目标弱相关的餐饮 / 预算类片段做轻量降权。
- 新增 `debug_rag_retrieval.py` 调试脚本，可直接观察检索 query、top-k 召回片段、`rerank_score` 与 `rerank_reasons`。

### 验证输入

```bash
python scripts/debug_rag_retrieval.py --destination "大理" --preferences "自然风景,拍照,美食" --pace "轻松" --special-notes "不想太早起床，希望安排一个适合看日落的地点。" --top-k 5
```

### 优化前输出

```text
=== RAG 检索调试 ===
destination: 大理
preferences: ['自然风景', '拍照', '美食']
pace: 轻松
special_notes: 不想太早起床，希望安排一个适合看日落的地点。
top_k: 5

=== 检索 Query ===
大理 自然风景 拍照 美食 轻松 日落 傍晚 洱海 双廊 慢节奏 景点 行程 攻略 推荐

=== Top-K 召回片段 ===
[Top 1]
source: dali_guide.md
title: 5. 经典三日行程参考 (Agent 提取样本)
content:
* **第一天：初识大理**
* 上午：抵达大理，入住大理古城周边客栈。
* 下午：游览【大理古城】，逛人民路，打卡五华楼。
* 晚上：品尝野生菌火锅。
* **第二天：白族文化与田园风光**
* 上午：前往【喜洲古镇】，参观白族民居，品尝喜洲粑粑。
* 下午：前往周城体验非遗【白族扎染】，随后在洱海生态廊道骑行。
* 晚上：返回古城，体验特色小酒馆。
* **第三天：山水经典**
* 上午：参观【崇圣寺三塔】，感受皇家寺院的雄伟。
* 下午：前往双廊古镇散步，享受海景下午茶，随后根据时间返程。
------------------------------------------------------------
[Top 2]
source: dali_guide.md
title: 1. 目的地简介
content:
大理白族自治州位于云南省中部偏西，以“风花雪月”（下关风、上关花、苍山雪、洱海月）闻名。这里气候温和，四季如春，非常适合慢节奏的休闲度假与深度体验。
------------------------------------------------------------
[Top 3]
source: dali_guide.md
title: 3. 特色餐饮与预算参考
content:
* **野生菌火锅**：云南必吃美食，推荐在大理古城内享用，人均预算约 **120元**。
* **喜洲粑粑**：喜洲古镇特色小吃，分为甜咸两味，人均预算 **10元**。
* **白族土八碗**：传统白族宴席，适合家庭或团队聚餐，人均预算约 **80元**。
* **凉鸡米线**：夏日解暑佳品，酸辣开胃，人均预算 **15元**。
------------------------------------------------------------
[Top 4]
source: dali_guide.md
title: 4. 住宿区域建议
content:
* **大理古城及周边**：交通便利，餐饮选择多，性价比高。酒店/客栈预算：**200-400元/晚**。
* **双廊古镇**：位于洱海东岸，以绝美海景房著称，适合情侣度假。酒店/客栈预算：**600-1500元/晚**。
* **才村/龙龛码头**：安静舒适，看日出的绝佳地点。酒店/客栈预算：**300-600元/晚**。
------------------------------------------------------------
[Top 5]
source: dali_guide.md
title: 文档开头
content:
# 2026 大理深度游玩全攻略
```

### 优化后输出

```text
=== RAG 检索调试 ===
destination: 大理
preferences: ['自然风景', '拍照', '美食']
pace: 轻松
special_notes: 不想太早起床，希望安排一个适合看日落的地点。
top_k: 5

=== 检索 Query ===
大理 自然风景 拍照 美食 轻松 日落 傍晚 洱海 双廊 慢节奏 景点 行程 攻略 推荐

=== Top-K 召回片段 ===
[Top 1]
source: dali_guide.md
title: 5. 经典三日行程参考 (Agent 提取样本)
rerank_score: 10
rerank_reasons: ['text+1:大理', 'text+1:洱海', 'text+1:双廊', 'title+3:行程', 'domain+4:行程标题']

[Top 2]
source: dali_guide.md
title: 2.1 大理古城
rerank_score: 5
rerank_reasons: ['title+3:大理', 'text+1:大理', 'text+1:傍晚']

[Top 3]
source: dali_guide.md
title: 2.4 洱海生态廊道 (骑行)
rerank_score: 5
rerank_reasons: ['title+3:洱海', 'text+1:洱海', 'text+1:推荐']

[Top 4]
source: dali_guide.md
title: 1. 目的地简介
rerank_score: 3
rerank_reasons: ['text+1:大理', 'text+1:洱海', 'text+1:慢节奏']

[Top 5]
source: dali_guide.md
title: 4. 住宿区域建议
rerank_score: 3
rerank_reasons: ['text+1:大理', 'text+1:洱海', 'text+1:双廊']
content:
* **大理古城及周边**：交通便利，餐饮选择多，性价比高。酒店/客栈预算：**200-400元/晚**。
* **双廊古镇**：位于洱海东岸，以绝美海景房著称，适合情侣度假。酒店/客栈预算：**600-1500元/晚**。
* **才村/龙龛码头**：安静舒适，看日出的绝佳地点。酒店/客栈预算：**300-600元/晚**。
```
