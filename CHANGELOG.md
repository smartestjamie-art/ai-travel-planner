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
