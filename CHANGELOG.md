# Changelog

> This log only records updates related to project features, architecture, and engineering capabilities. It does not include personal materials such as resumes or interview documents.

## 2026-06-11

### Docker Containerized Deployment

- Added `backend/Dockerfile`: based on the Python 3.11-slim image, first copies `requirements.txt` and installs dependencies (leveraging layer caching), then copies the application code and runs uvicorn.
- Added `frontend/Dockerfile`: a two-stage build — Node 20 compiles the Vue application, Nginx alpine serves the static files, and the final image contains no Node.js, shrinking the size from several hundred MB down to a few dozen MB.
- Added `frontend/nginx.conf`: Nginx configuration responsible for static file hosting plus API reverse proxying to the backend container, with `try_files` supporting Vue SPA routing.
- Added `docker-compose.yaml`: orchestrates the three services — Redis, backend, and frontend — defining their dependencies, port mappings, volume persistence, and environment variable injection.
- Added `.dockerignore`: excludes files that don't need to be packaged, such as `__pycache__`, `.env`, and `node_modules`.
- Added Docker-environment CORS allowed origins (`http://localhost`, `http://localhost:80`) to the backend `main.py`.

## 2026-04-15

### Redis Caching Optimization

- Added a Redis caching layer, with automatic degradation when Redis is unavailable so the main workflow is unaffected.
- Integrated weather query caching to reduce repeated external requests for the same city's weather.
- Integrated caching for Amap (Gaode Maps) geocoding, POI search, and route estimation to reduce redundant map query overhead.
- Integrated caching for RAG retrieval results, reusing recalled guide fragments for high-frequency queries.
- Added basic `cache hit / cache miss` logging to make it easier to verify cache hits locally.
- Verified successful cache key writes via a local Docker Redis container.

**Cache keys verified in this round**

```text
trip_planner:weather:forecast:Dali
trip_planner:rag:guide:Dali natural scenery photography food relaxed don't want to get up too early, hoping to arrange a spot suitable for watching the sunset. attractions itinerary guide recommendations:5
trip_planner:map:place:Dali comfortable accommodation 2:Dali:1
trip_planner:map:place:Shuanglang Ancient Town:Dali:1
trip_planner:map:route:100.323501,25.647149:100.131582,25.852950
trip_planner:map:place:Dali comfortable accommodation 1:Dali:1
trip_planner:map:place:Dali comfortable accommodation 3:Dali:1
trip_planner:map:route:100.323501,25.647149:100.164000,25.694836
trip_planner:map:place:Dali Ancient City:Dali:1
trip_planner:map:geocode:Dali:Dali
trip_planner:map:place:Dali departure point:Dali:1
trip_planner:map:route:100.323501,25.647149:100.194322,25.908323
trip_planner:map:place:Xizhou Ancient Town:Dali:1
```

## 2026-04-25

### RAG Online Stage Optimization

- Introduced lightweight Query Rewrite: instead of directly concatenating the entire freeform note, keywords better suited for retrieval are now extracted from the user's preferences, pace, and notes.
- Added travel-scenario rule words to `rag_tool.py` — such as sunset, evening, Erhai Lake, Shuanglang, and slow-paced — to improve retrieval focus for travel-planning queries.
- Added a first version of lightweight Rerank in `retriever.py`, applying heuristic scoring for title matches, body matches, itinerary-type titles, and known noisy fragments.
- Applied a strong penalty to low-information fragments such as "start of document," and a light downweighting to dining/budget fragments that are weakly related to the current primary goal.
- Added the `debug_rag_retrieval.py` debugging script, which lets you directly observe the retrieval query, the top-k recalled fragments, `rerank_score`, and `rerank_reasons`.

**Optimization results**

Using a Dali sunset + photography + relaxed scenario as an example:

| Top 5 before optimization | Top 5 after optimization (with rerank_score) |
|-------------|-------------------------------|
| 1. Classic three-day itinerary reference | 1. Classic three-day itinerary reference (score: 10) |
| 2. Destination overview | 2. Dali Ancient City (score: 5) |
| 3. Specialty dining & budget reference | 3. Erhai Lake Ecological Corridor (score: 5) |
| 4. Accommodation area recommendations | 4. Destination overview (score: 3) |
| 5. Start of document | 5. Accommodation area recommendations (score: 3) |

Before optimization, low-information fragments such as "Destination overview" and "Start of document" occupied top positions. After optimization, Rerank scoring pushed strongly scenario-relevant fragments like "Dali Ancient City" and "Erhai Lake Ecological Corridor" to the front, and "Start of document" was filtered out.

## 2026-04-29

### Map Route Visualization

- Connected each day's itinerary points on Amap with dashed arrows to display the complete route.
- Marked each destination with a 🚩 flag icon for an intuitive check-in style.
- Displayed a popup bubble with attraction photos (including scenic images and place names) on hover, with a placeholder shown when no image is available.
- Adopted a lightweight card design for the popup bubble, compact in size so it doesn't obscure the main map content.

### RAG Knowledge Base Expansion

- Added 4 new destination guide documents: `chengdu_guide.md`, `xian_guide.md`, `xiamen_guide.md`, and `sanya_guide.md`.
- Together with the existing `dali_guide.md`, these now cover 5 destinations, bringing the total to 49 retrieval fragments in ChromaDB after ingestion.
- Each guide follows a consistent structure: destination overview → core attractions (with admission/location/duration) → specialty dining (with per-person budget) → accommodation areas (with price ranges) → classic itinerary reference.

### RAG Evaluation Sample Set Expansion

- Expanded `rag_eval_cases.json` from 3 cases to 15, with 3 cases per destination.
- Covers different traveler groups (couples, families with children, traveling with parents), different paces (relaxed, moderate), and different preferences (food, culture, nature, resort/leisure).

### RAG Online Stage Rule-Level Optimization

This round improved the ranking quality of the RAG online retrieval stage through rule-based optimization, without introducing a model.

**Query Rewrite Destination Filtering**

- Introduced a destination filtering mechanism into `_extract_note_keywords` in `rag_tool.py`.
- Destination-specific keywords (e.g., "Erhai Lake, Shuanglang" are only injected for Dali, "Muslim Quarter" only for Xi'an) no longer leak across destinations.
- Added destination rules for Chengdu (giant pandas), Xi'an (ancient towns → Muslim Quarter), Xiamen (ancient towns → Gulangyu/Zengcuoan, cycling → Ring Island Road), and Sanya (diving → Wuzhizhou Island, seafood → First Market).

**Rerank Multi-Layer Downweighting**

- Added a three-layer downweighting mechanism to `_score_chunk_for_rerank` in `retriever.py`:
  - Itinerary reference fragment downweighting (-4): prevents "classic itinerary reference" from dominating Top1 due to its overly comprehensive content.
  - Destination overview downweighting (-2): prevents overly generic overview fragments from ranking Top1.
  - Destination mismatch downweighting (-5): heavily downweights fragments whose source destination doesn't match the query destination, resolving cross-destination contamination.
- The `destination` parameter is now passed through the entire chain in `rerank_guide_chunks` and `retrieve_travel_guide_chunks`.

**Optimization results**

| Metric | Baseline | After optimization |
|------|------|--------|
| Top1 Hit Rate | 13/15 (87%) | 12/15 (80%) |
| TopK Hit Rate | 15/15 (100%) | 15/15 (100%) |
| Cross-destination pollution | Present | Eliminated |
| Noisy fragments | 0 | 0 |

The apparent drop in Top1 hit rate is actually because the baseline's "itinerary fragment" was artificially dominating results. After optimization, topical fragments (dining, attractions, accommodation) correctly rank Top1, representing a real improvement in ranking quality. The remaining 3 Top1 misses are all ranking competitions within the same destination, requiring semantic-level rerank for further optimization.

**Optimization roadmap overview**

```text
Completed (rule-level)                Next (model-level)
┌─────────────────────┐      ┌──────────────────────┐
│ Query Rewrite       │      │ LLM-based Rewrite    │
│  └ Destination filter│ ──→  │  └ qwen-max query rewrite│
├─────────────────────┤      ├──────────────────────┤
│ Rerank              │      │ Cross-encoder Rerank │
│  └ Keyword scoring  │ ──→  │  └ bge-reranker-base │
│  └ Itinerary/overview downweighting│      │  └ Semantic relevance scoring│
│  └ Destination mismatch downweighting│      │                      │
└─────────────────────┘      └──────────────────────┘
```

## 2026-05-06

### RAG Evaluation Metrics System Completed

- Added 4 quantitative metrics to `evaluate_rag_retrieval.py`, establishing a complete RAG retrieval quality evaluation system.
- **MRR (Mean Reciprocal Rank)**: measures the ranking quality of hit results, a standard IR metric.
- **Noise Rate**: the percentage of noisy fragments within the Top-K, more intuitive than an absolute count.
- **Latency (retrieval time)**: time taken per retrieval (ms), reflecting engineering optimization value.
- **Cross-destination Pollution**: the count of cross-destination-polluted fragments, quantifying prior optimization gains.

**Baseline data (rule-level RAG)**

| Metric | Value |
|------|------|
| Top1 Hit Rate | 12/15 (80.0%) |
| TopK Hit Rate | 15/15 (100.0%) |
| MRR | 0.889 |
| Keyword Coverage | 59/63 |
| Noise Rate | 0.0% |
| Cross-destination Pollution | 0 |
| Avg Latency | 461.8ms |

All 3 Top1 misses are ranking competitions within the same destination (Xi'an food → expected Muslim Quarter, Xi'an family trip → expected attractions, Xiamen cycling → expected Ring Island Road), requiring semantic-level optimization for further improvement.

### LLM-based Query Rewrite

- Replaced hand-written rules with qwen-max to automatically rewrite the user's travel requirements into a vector-retrieval query.
- Added `llm_rewrite_query()` to `rag_tool.py`, following the project's existing LangChain + ChatOpenAI calling pattern.
- Retained the rule-based `_rule_based_query()` as a fallback, automatically degrading when the LLM is unavailable.
- Prompt design: the System message specifies the output format (plain keywords, space-separated, no explanation); the Human message includes destination/preferences/pace/notes.

**Optimization comparison**

| Metric | Baseline (rule-level) | LLM-based | Change |
|------|-------------------|-----------|------|
| Top1 Hit Rate | 12/15 (80.0%) | 13/15 (86.7%) | +6.7% |
| TopK Hit Rate | 15/15 (100.0%) | 15/15 (100.0%) | - |
| MRR | 0.889 | 0.922 | +3.7% |
| Keyword Coverage | 59/63 | 60/63 | +1 |
| Noise Rate | 0.0% | 0.0% | - |
| Cross-destination Pollution | 0 | 0 | - |
| Avg Latency | 461.8ms | 347.7ms | -24.7% |

LLM Rewrite improved Top1 hits from 12 to 13, and MRR from 0.889 to 0.922. The Xi'an food scenario improved from RR=0.5 to RR=1.0 (the LLM directly generated the "Muslim Quarter" keyword). The remaining 2 Top1 misses are ranking competitions within the same destination, requiring Cross-encoder Rerank for further optimization.

## 2026-05-07

### Cross-encoder Rerank

- Integrated the DashScope qwen3-rerank model to replace rule-based Rerank with semantic-level re-ranking.
- Added `_rerank_with_dashscope()` to `retriever.py`, calling the DashScope Reranker API via httpx.
- Retained the rule-based `_score_chunk_for_rerank()` as a fallback, automatically degrading when the API is unavailable.
- Added an `instruct` parameter to guide the model toward preferring concrete, detailed travel guide fragments over generic introductions.
- Filtered known noisy fragments ("start of document") before rerank to avoid wasting rerank slots.

**Optimization comparison**

| Metric | Baseline (rule-level) | LLM Rewrite | + Cross-encoder | Change (vs Baseline) |
|------|-------------------|-------------|-----------------|-------------------|
| Top1 Hit Rate | 12/15 (80.0%) | 13/15 (86.7%) | 14/15 (93.3%) | +13.3% |
| TopK Hit Rate | 15/15 (100.0%) | 15/15 (100.0%) | 15/15 (100.0%) | - |
| MRR | 0.889 | 0.922 | 0.967 | +8.8% |
| Keyword Coverage | 59/63 | 60/63 | 61/63 | +2 |
| Noise Rate | 0.0% | 0.0% | 0.0% | - |
| Cross-destination Pollution | 0 | 0 | 0 | - |
| Avg Latency | 461.8ms | 347.7ms | 728.4ms | +57.7% |

After the three-stage optimization of LLM Query Rewrite + Cross-encoder Rerank + noise pre-filtering, the Top1 hit rate rose from 80% to 93.3%, MRR rose from 0.889 to 0.967, and the noise rate remained 0. The increased latency mainly comes from the rerank API call, which can be optimized further via caching.

### Rerank Caching Optimization

- Added Rerank result caching to `rerank_guide_chunks` in `retriever.py`, skipping the DashScope API call on a cache hit.
- The cache key is composed of the normalized query plus a content hash of the chunks, ensuring the cache is reused when the same query is paired with the same candidate set.
- The cached value stores only indices and scores (`[{"i", "s"}]`), without duplicating the chunk text, saving storage.
- Added the `REDIS_RERANK_TTL_SECONDS` configuration item to `config.py`, sharing its on/off switch with the existing Redis cache.
- Added `REDIS_RERANK_TTL_SECONDS=21600` to both `.env` and `.env.example`.

**Rerank cache keys verified in this round**

```text
trip_planner:rerank:Chengdu Panda Base food leisure relaxed family-friendly:86281a27592a
trip_planner:rerank:Dali natural scenery photography food relaxed sunset spot:feaeff944221
trip_planner:rerank:Xi'an Muslim Quarter food snacks night market specialty snacks:6aca260efd77
trip_planner:rerank:Sanya beach resort relaxation luxury hotel beach leisure:aa3ac37f0667
trip_planner:rerank:Xiamen Xiamen University Nanputuo Temple photography culture architecture:6e5f7b5d1ae0
trip_planner:rerank:Sanya food seafood Nanshan Temple culture moderate pace fresh seafood:610d238b719e
trip_planner:rerank:Dali ancient town cultural experience slow pace Bai culture relaxed travel:25c88c579b45
trip_planner:rerank:Chengdu natural scenery hiking culture Dujiangyan Qingcheng Mountain outdoors:e651b63c9ec0
trip_planner:rerank:Dali food snacks budget specialty dining spending:edd9f0093e5f
trip_planner:rerank:Xiamen Gulangyu island artsy food ambiance relaxed travel:229afa03f280
trip_planner:rerank:Xi'an family study tour culture relaxed educational unhurried:7184d33a1e75
trip_planner:rerank:Chengdu food snacks hotpot specialty food foodie exploring:584c7e41a41b
trip_planner:rerank:Sanya family water park marine animals relaxed:ca99c53ae7e7
trip_planner:rerank:Xi'an history culture historical sites in-depth tour:480addc7dfe9
trip_planner:rerank:Xiamen cycling sea view leisure sunset relaxation:14207650ed1a
```

**Optimization results**

| Metric | No Rerank | + Cross-encoder | + Rerank cache |
|------|-----------|-----------------|---------------|
| Top1 Hit Rate | 12/15 (80.0%) | 14/15 (93.3%) | 14/15 (93.3%) |
| MRR | 0.889 | 0.967 | 0.967 |
| Noise Rate | 0.0% | 0.0% | 0.0% |
| Avg Latency (first run) | 461.8ms | 728.4ms | 654.6ms |
| Avg Latency (cache hit) | - | - | **424.8ms** |

After a cache hit, latency drops by 41.6%, returning to roughly the level of the LLM Rewrite stage, while retaining the quality improvement from Cross-encoder Rerank.

## 2026-05-19

### Token Consumption Tracking

- Added a `token_usage` field to `Itinerary` in `schemas.py` to record token consumption during a single itinerary generation run.
- Extracted input/output tokens for LLM-based Query Rewrite in `rag_tool.py`.
- Extracted the official `usage` for online Query Embedding in `vector_db.py`, counting only the online retrieval query embedding — not the offline knowledge-base ingestion embedding.
- Extracted the official DashScope qwen3-rerank `usage` in `retriever.py`, recording Rerank input/output tokens.
- Extracted input/output tokens for Planner itinerary generation in `trip_planner_agent.py`.
- Aggregated the four stages — Query Rewrite, Query Embedding, Rerank, and Planner — in `trip_service.py`, printing the breakdown and total in the backend terminal.
- Added a `/trip/stats` endpoint to aggregate token consumption across saved itineraries.

**Frontend input used in this test**

```text
Destination city: Dali
Start date: 2026-05-19
End date: 2026-05-21
Number of travelers: 2
Trip duration: 3 days
Pace preference: relaxed
Accommodation preference: comfortable
Budget: 3200
Travel preferences: natural scenery, photography, food
Dietary preference: mild spice
Additional requirements: don't want to get up too early, hoping to arrange a spot suitable for watching the sunset.
```

**Verification log from this run**

```text
[embedding] query embedding token: prompt=20, completion=0, source=api
[rerank] qwen3-rerank token: prompt=1703, completion=0, source=api
[trip_planner_agent] LLM call completed. token: prompt=1159, completion=437
[token_usage] Query Rewrite: prompt=134, completion=19
[token_usage] Rerank: prompt=1703, completion=0
[token_usage] Query Embedding: prompt=20, completion=0
[token_usage] Planner: prompt=1159, completion=437
[token_usage] Total: prompt=3016, completion=456, all=3472
```

**Token consumption across the four model calls**

| Call | Model | Input tokens | Output tokens | Reason |
|------|------|-----------|-----------|------|
| Query Rewrite | qwen-max | ✅ Yes | ✅ Yes | Generative LLM: takes a prompt as input, outputs keyword text |
| Query Embedding | text-embedding-v4 | ✅ Yes | ❌ 0 | Only converts text to a vector, generates no text |
| Rerank | qwen3-rerank | ✅ Yes | ❌ 0 | Only computes relevance scores, generates no text |
| Itinerary generation | qwen-max | ✅ Yes | ✅ Yes | Generative LLM: takes a prompt as input, outputs a JSON itinerary |

**Notes**

- `source=api` indicates that the Query Embedding and Rerank tokens both come from DashScope's official response fields, not local estimation.
- This round of statistics covers only online request costs: Query Rewrite, Query Embedding, Rerank, and Planner; document embedding performed when offline knowledge-base chunks are ingested is not counted toward a single `/trip/generate` call.
- A `completion=0` for Rerank and Embedding is expected, since Embedding outputs a vector and Rerank outputs a score — neither generates natural-language text.
- The `/trip/generate` response also includes `token_usage`, making it easy for the frontend or debugging tools to see the cost of that generation run.
</content>
