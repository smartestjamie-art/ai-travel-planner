# 智能旅行助手问题记录与解决方案

> 这份文档用于记录项目开发过程中实际遇到的问题、定位过程和最终修复方式，方便后续复盘、答辩展示和继续迭代。

---

## 1. 文档目的

这份文档主要解决三件事：

1. 记录开发过程中真实出现过的问题
2. 记录这些问题是如何定位和修复的
3. 为后续前后端联调、地图接入和产品化迭代提供参考

---

## 2. 后端问题记录

### 问题 1：`/trip/edit` 一直走规则回退，没有走 LLM 编辑

#### 现象

测试 `scripts/test_trip_edit_api.py` 时，第二天的行程总是变成：

- `自由活动 / 弹性安排`
- `已根据用户要求把节奏调整得更轻松。`
- `当前结果为 Day 4 规则编辑演示版本。`

这说明接口虽然能通，但实际还是走了 fallback 规则编辑。

#### 排查过程

先确认了三件事：

1. 远程代码已经同步最新版本
2. 服务已经重启
3. `trip_service.py` 中确实优先调用了 `generate_day_edit_draft(...)`

随后在 `trip_service.py` 中临时打印：

```python
print(day_edit_draft is None)
print(day_edit_draft)
```

结果发现：

```text
day_edit_draft is None
True
```

说明真正问题不在 `trip_service.py`，而在 `generate_day_edit_draft(...)`。

#### 根因

模型返回的 JSON 结构和 `DayEditDraft` 期待的结构不一致。

代码原本期待模型返回：

```json
{
  "theme": "...",
  "spot_name": "...",
  "spot_description": "...",
  "meal_name": "...",
  "meal_notes": "...",
  "daily_note": "..."
}
```

但模型实际返回的是更像 `DayPlan` 的嵌套结构：

```json
{
  "theme": "...",
  "spots": [...],
  "meals": [...],
  "notes": [...]
}
```

因此 `Pydantic` 校验报错，导致 `day_edit_draft = None`，最终走规则回退。

#### 解决方案

在 `trip_planner_agent.py` 中新增：

- `_normalize_day_edit_payload(payload)`

把模型返回的嵌套结构自动转换成 `DayEditDraft` 需要的扁平结构。

#### 结果

`/trip/edit` 终于真正走到了 LLM 编辑分支，测试结果变成更自然的智能改写，而不是规则替换。

---

### 问题 2：PDF 导出接口返回 `400 Bad Request`

#### 现象

测试：

```bash
curl -v "http://127.0.0.1:8000/export/trip_大理_2026-04-10/pdf" -o trip.pdf
```

返回：

```text
HTTP/1.1 400 Bad Request
```

#### 根因

请求路径里直接带了中文 `trip_id`，没有做 URL 编码。

浏览器或 `curl` 在这类场景下可能会把中文路径当成非法请求处理。

#### 解决方案

把中文路径编码后再访问，例如：

```bash
curl -v "http://127.0.0.1:8000/export/trip_%E5%A4%A7%E7%90%86_2026-04-10/pdf" -o trip.pdf
```

#### 结果

返回：

```text
HTTP/1.1 200 OK
content-type: application/pdf
```

说明 PDF 导出链路正常。

---

### 问题 3：PDF 下载文件名涉及中文时 header 编码异常

#### 现象

导出接口返回文件时，中文 `trip_id` 在 `Content-Disposition` 中容易触发编码问题。

#### 解决方案

导出接口改成使用 RFC 兼容写法，例如：

```text
filename*=UTF-8''trip_%E5%A4%A7%E7%90%86_2026-04-10.pdf
```

#### 结果

中文文件名可以被正常返回和下载。

---

### 问题 4：高德地图测试脚本报 `ModuleNotFoundError`

#### 现象

运行：

```bash
python scripts/test_map_service.py
```

报错：

```text
ModuleNotFoundError: No module named 'app.services.map_service'
```

#### 根因

远程环境还没有同步最新的 `map_service.py` 文件。

#### 解决方案

同步以下文件到远程：

- `backend/app/services/map_service.py`
- `backend/app/config.py`
- `backend/.env.example`
- `backend/scripts/test_map_service.py`

#### 结果

同步后脚本可以正常运行，顺利拿到：

- POI 搜索结果
- 地理编码结果
- 路线估算结果

---

### 问题 5：新增地图字段后担心破坏原有主链路

#### 现象

第三阶段给 `schemas.py` 增加：

- `address`
- `latitude`
- `longitude`
- `poi_id`
- `distance_km`
- `estimated_minutes`

担心会影响：

- `/trip/generate`
- `/trip/edit`
- `/trip/save`
- `/trip/{trip_id}`
- `/export`

#### 解决方案

所有新字段全部设计成可选字段。

#### 验证

运行：

```bash
pytest test_api_trip.py -q
```

结果：

```text
13 passed
```

#### 结果

说明地图字段预留并没有破坏原主链路。

---

### 问题 6：地图 enrich 开关关闭时字段全是 `null`

#### 现象

当：

```env
ENABLE_AMAP_ENRICHMENT=false
```

生成 itinerary 后，所有地图相关字段都是：

- `address: null`
- `latitude: null`
- `longitude: null`
- `poi_id: null`
- `distance_km: null`
- `estimated_minutes: null`

#### 判断

这不是 bug，而是预期行为。

#### 原因

第三阶段地图 enrich 是用环境变量控制的：

- `false`：只预留字段，不调用高德
- `true`：生成后自动补地图信息

#### 结果

说明“开关关闭时不影响主链路”的设计是成立的。

---

### 问题 7：高德地图 enrich 是否真的生效

#### 现象

开启：

```env
ENABLE_AMAP_ENRICHMENT=true
```

再次生成 itinerary 后，返回结果中出现：

- 景点地址
- 景点经纬度
- `poi_id`
- 酒店地址和坐标
- 交通距离与预计耗时

同时 `source_notes` 中新增：

```text
已补充高德地图地址、坐标或路线估算信息。
```

#### 结果

说明高德地图 enrich 已经真正接入 itinerary 结果。

---

### 问题 8：Redis 缓存层是否真正接入成功

#### 时间

2026-04-15

#### 优化目标

为项目补充一层轻量 Redis 缓存，优先覆盖：

- 天气查询
- 地图查询
- RAG 检索结果

目标不是一次性做完整工程化，而是先验证：

1. Redis 能否顺利接入当前后端
2. 缓存逻辑是否不会破坏原有主流程
3. 天气、地图和 RAG 结果是否真的写入缓存

#### 本次具体优化

1. 在后端增加 Redis 配置项
2. 新增通用缓存服务 `cache_service.py`
3. 给天气服务增加缓存
4. 给高德地图查询增加缓存
   - 地理编码
   - POI 搜索
   - 路线估算
5. 给 RAG 检索结果增加缓存
6. 增加简单的 `cache hit / cache miss` 日志，便于后续验证

#### 验证方式

本次没有依赖本地单独安装 `redis-cli`，而是通过 Docker 启动 Redis 容器，再进入容器内部查看 key：

```bash
docker exec tripplanner-redis redis-cli KEYS "trip_planner:*"
```

#### 验证结果

Redis 中已经实际出现以下缓存 key：

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

#### 结论

说明 Redis 缓存已经不只是“代码里写了”，而是：

- 天气缓存已写入
- 地图缓存已写入
- RAG 缓存已写入

也说明当前 Redis 接入方式是成立的，缓存层已经真实接入到项目主链路中。

#### 经验总结

1. Redis 最适合先从“高频重复请求”切入
2. 先做可选缓存层，比一开始就把主流程和 Redis 强绑定更稳
3. Docker 跑 Redis 是本地验证缓存逻辑的低成本方案

---

### 问题 9：基础 RAG 能召回相关内容，但排序不够理想

#### 时间

2026-04-24

#### 现象

在新增 `debug_rag_retrieval.py` 调试脚本后，使用下面这组输入测试：

- `destination = 大理`
- `preferences = 自然风景, 拍照, 美食`
- `pace = 轻松`
- `special_notes = 不想太早起床，希望安排一个适合看日落的地点。`

构造出的检索 query 为：

```text
大理 自然风景 拍照 美食 轻松 不想太早起床，希望安排一个适合看日落的地点。 景点 行程 攻略 推荐
```

召回结果中：

- `Top 1` 是“特色餐饮与预算参考”
- `Top 2` 是“文档开头”
- `Top 3` 才是“经典三日行程参考”
- `Top 5` 才出现更接近“傍晚漫步”的大理古城片段

这说明当前基础向量检索虽然能召回相关内容，但排序还没有充分体现用户的主目标。

#### 排查过程

这次没有直接修改主业务链路，而是先增加了 RAG 在线调试脚本，用来观察：

1. 当前构造出来的检索 query
2. top-k 实际召回片段
3. 每个片段的来源文件和标题

通过调试结果发现两个明显问题：

1. query 过长、过杂  
   目的地、偏好、节奏、完整备注和通用旅游词被直接拼在一起，导致“美食”这类词把餐饮片段推得过靠前。

2. 排序没有体现用户的主目标  
   用户更核心的诉求是“轻松、看日落、拍照、自然风景”，但当前排序没有优先突出这些信息。

#### 根因

当前在线检索阶段还处在基础版，主要问题是：

- query 构造方式比较直接
- 主要依赖基础向量相似度检索
- 没有 Query Rewrite
- 没有 Rerank
- 没有去冗和上下文压缩

因此出现了：

- 相关内容能召回
- 但排序不够精准
- 个别噪声片段仍然会进入 top-k

#### 当前判断

这不是 RAG “完全没用”，而是一个典型的基础检索阶段问题：

- 召回方向基本对
- 但排序质量还不够好

也正因为这个问题被显式观察到了，说明当前项目已经进入可以继续做 Query Rewrite、Rerank 和 Compression 的阶段。

#### 下一步优化方向

基于这次调试结果，下一步优先顺序确定为：

1. 先做 RAG 可观测
2. 再做 Query Rewrite
3. 再做轻量 Rerank
4. 再做去冗和上下文压缩
5. 最后再考虑混合检索

#### 经验总结

1. RAG 优化不能只看最终生成结果，要先能看到 top-k 召回片段
2. 基础向量检索能解决“有没有召回”，但不一定解决“排得好不好”
3. 旅行场景下，用户备注通常比较口语化，Query Rewrite 的价值很高

---

### 问题 10：第一版 Query Rewrite 是否真正改善了 RAG 检索效果

#### 时间

2026-04-24

#### 优化目标

在不引入新模型、不重构主业务流程的前提下，先通过轻量规则优化 RAG 在线检索 query，验证：

1. 是否能让召回结果更贴近用户主目标
2. 是否能减弱口语化备注带来的检索噪声
3. 是否能为下一步 Rerank 提供更稳定的输入

#### 优化前现象

原始 query 直接把用户备注整句拼进去：

```text
大理 自然风景 拍照 美食 轻松 不想太早起床，希望安排一个适合看日落的地点。 景点 行程 攻略 推荐
```

调试脚本显示：

- `Top 1` 是“特色餐饮与预算参考”
- `Top 2` 是“文档开头”
- “经典三日行程参考”只排在 `Top 3`

这说明：

- 召回方向基本对
- 但排序没有充分体现“轻松、看日落、拍照、自然风景”这些核心诉求
- `special_notes` 原样拼接导致 query 过长且语义分散

#### 本次具体优化

在 `rag_tool.py` 中对 query 构造逻辑做了第一版轻量 Query Rewrite：

1. 不再把 `special_notes` 原样拼入 query
2. 从备注中提炼更适合检索的关键词
3. 对重复词做去重
4. 对旅行领域相关词做轻量扩展

本次规则主要覆盖：

- `日落 / 傍晚`
- `日出 / 清晨`
- `拍照 / 摄影 / 出片`
- `美食 / 小吃`
- `轻松 / 慢节奏 / 休闲`
- `不想太早起床 / 睡到自然醒`
- `古镇`
- `骑行`

例如本次测试输入最终改写为：

```text
大理 自然风景 拍照 美食 轻松 日落 傍晚 洱海 双廊 慢节奏 景点 行程 攻略 推荐
```

#### 验证方式

继续使用新增的调试脚本：

```bash
python scripts/debug_rag_retrieval.py --destination "大理" --preferences "自然风景,拍照,美食" --pace "轻松" --special-notes "不想太早起床，希望安排一个适合看日落的地点。" --top-k 5
```

对比优化前后的：

- 检索 query
- top-k 召回片段
- 排序变化

#### 优化前输出

输入：

```bash
python scripts/debug_rag_retrieval.py --destination "大理" --preferences "自然风景,拍照,美食" --pace "轻松" --special-notes "不想太早起床，希望安排一个适合看日落的地点。" --top-k 5
```

输出：

```text
=== RAG 检索调试 ===
destination: 大理
preferences: ['自然风景', '拍照', '美食']
pace: 轻松
special_notes: 不想太早起床，希望安排一个适合看日落的地点。
top_k: 5

=== 检索 Query ===
大理 自然风景 拍照 美食 轻松 不想太早起床，希望安排一个适合看日落的地点。 景点 行程 攻略 推荐

=== Top-K 召回片段 ===
[Top 1]
source: dali_guide.md
title: 3. 特色餐饮与预算参考

[Top 2]
source: dali_guide.md
title: 文档开头

[Top 3]
source: dali_guide.md
title: 5. 经典三日行程参考 (Agent 提取样本)

[Top 4]
source: dali_guide.md
title: 1. 目的地简介

[Top 5]
source: dali_guide.md
title: 2.1 大理古城
```

#### 验证结果

优化后结果变成：

- `Top 1`：经典三日行程参考
- `Top 2`：目的地简介
- `Top 3`：特色餐饮与预算参考
- `Top 4`：住宿区域建议
- `Top 5`：文档开头

相比优化前：

- “餐饮预算”不再占据 `Top 1`
- “经典三日行程”明显前移
- `洱海 / 双廊 / 慢节奏 / 日落` 相关语义开始进入排序影响

对应输出如下：

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

[Top 2]
source: dali_guide.md
title: 1. 目的地简介

[Top 3]
source: dali_guide.md
title: 3. 特色餐饮与预算参考

[Top 4]
source: dali_guide.md
title: 4. 住宿区域建议

[Top 5]
source: dali_guide.md
title: 文档开头
```

#### 结论

说明第一版 Query Rewrite 是有效的：

- query 更短、更聚焦
- 用户主目标开始更明显地影响召回排序
- 当前在线阶段优化方向正确

但同时也暴露出新的问题：

- 仍然存在噪声片段，例如“文档开头”
- top-k 内部排序还不够理想
- 还缺少更细的相关性排序机制

#### 下一步优化方向

基于这次结果，下一步优先做：

1. 轻量 Rerank
2. 去冗和噪声过滤
3. 再考虑混合检索

而不是立刻跳到更重的 GraphRAG 或复杂多路召回。

#### 经验总结

1. Query Rewrite 能直接改善在线检索阶段效果
2. RAG 优化最好先做最小闭环，而不是一开始引入复杂新框架
3. 基础向量检索 + Query Rewrite 可以先解决一部分排序问题，后续再用 Rerank 补足

---

### 问题 11：第一版轻量 Rerank 是否进一步改善了排序质量

#### 时间

2026-04-25

#### 优化目标

在 Query Rewrite 已经生效的基础上，继续解决两个问题：

1. `文档开头` 这类低信息量噪声片段仍会进入 top-k
2. 更贴近“轻松 / 日落 / 拍照 / 自然风景”的片段还没有稳定排到更靠前的位置

#### 本次具体优化

在 `retriever.py` 中加入第一版轻量 Rerank：

1. 标题命中 query 关键词：加分
2. 正文命中 query 关键词：加分
3. 标题为 `文档开头`：强惩罚
4. 标题包含 `行程`：额外加权
5. 与当前主目标弱相关的餐饮 / 预算片段：轻量降权

同时在调试脚本中输出：

- `rerank_score`
- `rerank_reasons`

#### 验证方式

继续使用同一组大理样例输入测试：

```bash
python scripts/debug_rag_retrieval.py --destination "大理" --preferences "自然风景,拍照,美食" --pace "轻松" --special-notes "不想太早起床，希望安排一个适合看日落的地点。" --top-k 5
```

#### 验证结果

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

[Top 2]
source: dali_guide.md
title: 2.1 大理古城
rerank_score: 5

[Top 3]
source: dali_guide.md
title: 2.4 洱海生态廊道 (骑行)
rerank_score: 5

[Top 4]
source: dali_guide.md
title: 1. 目的地简介
rerank_score: 3

[Top 5]
source: dali_guide.md
title: 3. 特色餐饮与预算参考
rerank_score: 3
```

这次结果说明：

- `文档开头` 已经被成功挤出 top 5
- “大理古城”“洱海生态廊道”这类更贴近傍晚散步、拍照、自然风景的片段明显前移
- 纯餐饮片段被进一步压后

#### 结论

说明第一版轻量 Rerank 是有效的：

1. Query Rewrite 负责把 query 改得更适合检索
2. Rerank 负责在候选片段内部进一步优化排序
3. 两者组合后，在线阶段已经形成了一个可观测、可验证、可继续迭代的小闭环

#### 下一步优化方向

基于当前效果，下一步优先考虑：

1. 轻量去冗 / 噪声过滤
2. 检索结果压缩
3. 再考虑混合检索或更复杂的 rerank 模型

#### 经验总结

1. Query Rewrite 和 Rerank 解决的不是同一个问题
2. Query Rewrite 负责“找得更准”，Rerank 负责“排得更好”
3. 先做轻量、可解释的规则版 Rerank，有利于快速建立对排序机制的理解

---

## 3. 前端问题记录

### 问题 1：前端可以打开页面，但点击“开始规划”后提示生成失败

#### 现象

页面能正常打开，样式也正常，但点击“开始规划”后总提示：

```text
行程生成失败，请检查后端地址或服务状态。
```

而后端日志中一开始只有：

```text
GET /
```

没有：

```text
POST /trip/generate
```

#### 根因

前端请求没有正确打到后端，可能原因包括：

- `baseURL` 没配好
- 请求默认打到了前端自己的 `5173`
- 后端没有配置 CORS

#### 解决方案

1. 给前端 `api.ts` 设置兜底地址：

```ts
baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:8000"
```

2. 后端增加 `CORSMiddleware`，允许：

- `http://localhost:5173`
- `http://127.0.0.1:5173`

#### 结果

后端开始能收到：

```text
POST /trip/generate
```

说明请求链路已经通了。

---

### 问题 2：后端已经返回 `200 OK`，但前端仍然提示失败

#### 现象

后端日志里已经出现：

```text
POST /trip/generate HTTP/1.1 200 OK
```

并且大模型也调用成功。

但前端仍然提示生成失败。

#### 根因

前端 `axios` 超时时间太短，原来配置为：

```ts
timeout: 30000
```

而 `/trip/generate` 这条链路包含：

- RAG 检索
- LLM 调用
- itinerary 生成
- 高德地图 enrich

因此 30 秒在远程环境里不一定够。

于是发生了这种情况：

1. 前端发起请求
2. 后端开始生成
3. 前端等满 30 秒后先超时
4. 后端随后真正返回 `200`

所以会出现：

- 后端看起来成功
- 前端却先报失败

#### 解决方案

把超时调大到：

```ts
timeout: 120000
```

同时在 `Home.vue` 中增加更细的错误提示，区分：

- 超时
- 后端状态码错误
- 连接失败

#### 结果

再次测试后，前端终于可以正常切到结果页。

---

### 问题 3：前端开发环境到底该写什么 `VITE_API_BASE_URL`

#### 现象

前端和后端都跑在远程服务器上，但浏览器是本地打开页面，容易混淆：

- `127.0.0.1`
- `localhost`
- 服务器 IP
- 端口映射地址

#### 实际情况

如果本地浏览器里访问后端的地址是：

```text
http://localhost:8000
```

那说明当前环境已经做了端口映射，这时前端也可以直接写：

```env
VITE_API_BASE_URL=http://localhost:8000
```

#### 结果

最终前端用 `localhost:8000` 作为默认后端地址，可以顺利完成联调。

---

### 问题 4：前端文件中出现乱码显示

#### 现象

在 PowerShell 终端里读取 `.vue` 文件时，有时中文会显示成乱码。

#### 判断

这通常不是文件真的坏了，而是：

- 终端编码
- PowerShell 输出编码

导致的显示异常。

#### 解决方案

- 以 IDE 中实际显示内容为准
- 关键中文文案如果确实异常，再重写文件确认

#### 结果

文件在 IDE 中正常即可，终端乱码不等于源码损坏。

---

## 4. 当前阶段总结

到目前为止，项目已经解决并跑通了以下关键链路：

### 后端

- 行程生成
- 行程编辑
- 行程保存
- 单条查询
- 历史列表
- Markdown 导出
- PDF 导出
- 高德地图 enrich

### 前端

- 前端骨架搭建完成
- 规划页可打开
- 结果页可打开
- `/trip/generate` 前后端联调成功
- 真实 itinerary 已经可以显示在结果页

---

## 5. 后续建议继续记录的问题类型

后面建议继续把这些问题也记录进来：

1. 地图前端展示问题
2. 前端历史列表页联调问题
3. 编辑页联调问题
4. 导出按钮联调问题
5. 前端部署与端口映射问题
6. 高德 JavaScript API 接入问题

---

## 6. 当前最有价值的经验

这次开发过程中最典型的经验有三条：

1. **“后端成功”不等于“前端成功”**
   前端可能因为超时、跨域、地址配置而先失败。

2. **先确认请求有没有真正打到后端**
   看日志里有没有 `POST /trip/generate`，比盲猜快得多。

3. **复杂接口不要设置过短超时**
   只要涉及 LLM、RAG、地图 enrich，就要给前端足够等待时间。

---

## 7. 文档用途建议

这份文档后续可以用于：

- 项目复盘
- 阶段总结
- 答辩汇报
- README 或课程文档补充材料
- 后续新同学接手项目时的排坑说明
