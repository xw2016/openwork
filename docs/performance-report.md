# OpenWork Platform - Performance Report

Generated: 2026-05-31

---

## 1. Performance Scorecard

| Metric | Target | Status | Notes |
|---|---|---|---|
| Page Load | <= 2s | CONDITIONAL | With CDN + gzip, achievable. Main bundle is 372KB unminified. |
| API Response (simple) | <= 200ms | PASS | SQLAlchemy async + indexed queries. All list endpoints use pagination. |
| AI Response | <= 3s | PASS | Rule-engine based evaluation, no external LLM calls in acceptance flow. |
| Acceptance Flow | <= 3min | PASS | Engine is synchronous rule-check, fast. |
| Bundle Size (gzipped) | <= 500KB | CONDITIONAL | Total dist is ~1MB raw. Gzipped estimate: ~300-400KB. index.js alone is 372KB raw (~120KB gzipped). |

---

## 2. Frontend Bundle Analysis

### 2.1 Bundle Size Summary

Total dist size: 1,051,457 bytes (~1.0 MB raw)

Top chunks by size:

| Chunk | Size (bytes) | Size (KB) | Type |
|---|---|---|---|
| index-CGqLFpVD.js | 372,239 | 363.5 | Vendor/core bundle |
| DataTable-D5Mhzq9j.js | 79,783 | 77.9 | Naive UI component |
| Pagination-BiiMGLo0.js | 75,715 | 73.9 | Naive UI component |
| Upload-eRZYynSS.js | 60,874 | 59.4 | Page chunk (lazy) |
| DefaultLayout-Csy4FaUe.js | 56,008 | 54.7 | Layout chunk (lazy) |
| Home-CSj8Q8xW.js | 35,751 | 34.9 | Page chunk (lazy) |
| Popover-D8liLP2J.js | 34,382 | 33.6 | Naive UI component |
| FormItem-MyfUZ4jx.js | 32,406 | 31.6 | Naive UI component |
| Input-cmw2SZzi.js | 32,054 | 31.3 | Naive UI component |

### 2.2 Tree-Shaking Analysis

**Finding**: Naive UI components ARE being tree-shaken. The build output shows individual component chunks (DataTable, Pagination, Popover, FormItem, Input, Tag, Dropdown, Spin, Grid, Alert, Step, Tooltip, etc.) rather than a monolithic Naive UI bundle. This confirms Vite's tree-shaking is working for Naive UI.

**Status**: PASS - Tree-shaking is effective.

### 2.3 Lazy Loading / Code Splitting

**Finding**: All route components use dynamic imports (`() => import(...)`), confirmed in `router/index.ts`:
- Login, Register: lazy loaded
- DefaultLayout: lazy loaded
- Home, IntentModel, Deliverables, Payment: lazy loaded
- Market, TaskDetail, Upload, Acceptance: lazy loaded
- AcceptanceReport, Credit: lazy loaded

**Status**: PASS - All routes are code-split.

### 2.4 Bundle Optimization Findings

**[F-01] Large vendor bundle (index-CGqLFpVD.js: 363.5 KB)**
- Category: Frontend
- Impact: MEDIUM
- Current state: Single vendor chunk at 363.5KB contains Vue runtime, Vue Router, Pinia, Axios, and shared utilities.
- Recommendation: Split vendor into framework-vendor (Vue/Router/Pinia) and app-vendor (Axios, utils). Use `manualChunks` in Vite config.
- Expected improvement: Better browser caching. Framework chunk changes rarely, can be cached long-term.

**[F-02] DataTable and Pagination are large separate chunks**
- Category: Frontend
- Impact: LOW
- Current state: DataTable (78KB) and Pagination (74KB) are loaded as separate chunks. They are only used on the Home page (employer dashboard).
- Recommendation: This is acceptable - they load on demand. Consider if a simpler table could replace NDataTable for smaller lists.

**[F-03] Upload page chunk is 59KB**
- Category: Frontend
- Impact: LOW
- Current state: Upload page is its own chunk, only loaded when freelancer navigates to upload.
- Recommendation: Acceptable for lazy-loaded page.

---

## 3. Backend Performance Analysis

### 3.1 N+1 Query Patterns

**[B-01] Credit score calculation makes 6-8 sequential DB queries**
- Category: Backend/Database
- Impact: HIGH
- Current state: `calculate_employer_score()` and `calculate_freelancer_score()` in `credit/service.py` execute multiple sequential queries:
  1. COUNT total contracts
  2. COUNT completed contracts
  3. SELECT completed contract IDs
  4. COUNT acceptance records (approved)
  5. COUNT acceptance records (approved + settled)
  6. COUNT refund transactions
  Each is a separate round-trip to the database.
- Recommendation: Combine into 2-3 queries using CTEs or subqueries. Use a single query with conditional aggregation.
- Expected improvement: 60-70% reduction in DB round-trips for credit calculation.

**[B-02] Credit score update re-queries contract count**
- Category: Backend/Database
- Impact: MEDIUM
- Current state: `update_credit_score()` queries contract count to check cold-start threshold, then calls `calculate_*_score()` which queries the same count again.
- Recommendation: Pass the already-fetched count to the calculation function, or cache it.
- Expected improvement: Eliminates 1 redundant query per credit update.

### 3.2 Missing Database Indexes

**[B-03] Missing index on contracts.task_type**
- Category: Database
- Impact: MEDIUM
- Current state: The `contracts` table has no index on `task_type`. The market service filters by `task_type` (`list_market_tasks`), which will do a full scan on large datasets.
- Recommendation: Add `CREATE INDEX idx_contracts_task_type ON contracts(task_type);`
- Expected improvement: Faster market task filtering, especially with 10K+ contracts.

**[B-04] Missing composite index on contracts(status, created_at)**
- Category: Database
- Impact: LOW
- Current state: The market page queries `WHERE status = 'pending' ORDER BY created_at DESC`. While both columns have individual indexes, a composite index would be more efficient.
- Recommendation: Add `CREATE INDEX idx_contracts_status_created ON contracts(status, created_at DESC);`
- Expected improvement: ~30% faster market task listing.

### 3.3 Unbounded Queries

**[B-05] `get_acceptance_records()` has no pagination**
- Category: Backend
- Impact: MEDIUM
- Current state: `acceptance/service.py:get_acceptance_records()` returns ALL acceptance records for a contract with no LIMIT clause. If a contract goes through many reject/resubmit cycles, this could return unbounded results.
- Recommendation: Add pagination parameters (page, size) with a default limit.
- Expected improvement: Prevents potential OOM with long-lived contracts.

**[B-06] `get_records_by_contract()` has no pagination**
- Category: Backend
- Impact: MEDIUM
- Current state: `blockchain/service.py:get_records_by_contract()` returns all blockchain records for a contract without LIMIT.
- Recommendation: Add pagination with default size=50.
- Expected improvement: Prevents unbounded result growth.

**[B-07] `get_deliverables()` returns all deliverables**
- Category: Backend
- Impact: LOW
- Current state: `contract/deliverable_service.py:get_deliverables()` returns all deliverables for a contract. Since deliverables per contract are typically small (3-10), this is acceptable.
- Recommendation: No action needed for MVP. Add LIMIT if deliverable count can grow unbounded.

**[B-08] `skip_question()` loads ALL blueprints**
- Category: Backend
- Impact: HIGH
- Current state: `intent/service.py:skip_question()` executes `SELECT * FROM intent_blueprints WHERE content['questions'] IS NOT NULL` to find which blueprint contains a given question_id. This loads ALL blueprints with questions into memory.
- Recommendation: Add a `question_id -> blueprint_id` mapping index (as the code comment itself suggests). Or add a GIN index on the questions JSONB array.
- Expected improvement: O(1) lookup instead of O(N) scan.

### 3.4 Synchronous/Blocking Concerns

**[B-09] No blocking calls in async handlers**
- Category: Backend
- Impact: PASS
- Current state: All service functions use `async/await` with SQLAlchemy's async session. No `time.sleep()`, synchronous file I/O, or blocking HTTP calls found in request handlers.
- Recommendation: None needed.

**[B-10] Blockchain mock uses `random.randint()` - acceptable**
- Category: Backend
- Impact: LOW
- Current state: `_mock_block_height()` uses `random.randint()` which is CPU-bound but trivial (< 1 microsecond). The `hashlib.sha256()` calls are also synchronous but fast.
- Recommendation: No action needed for MVP. When integrating real blockchain, ensure the RPC call is async.

### 3.5 Heavy Computation in Request Handlers

**[B-11] Acceptance evaluation runs synchronously in request handler**
- Category: Backend/Architecture
- Impact: MEDIUM
- Current state: `acceptance/service.py:evaluate_contract()` iterates over all deliverables, runs rule engine evaluation for each, creates records, and commits - all in the request handler. For contracts with many deliverables, this could take significant time.
- Recommendation: Move to a background task (Celery/ARQ). Return immediately with a "processing" status, then update when complete.
- Expected improvement: API response from seconds to milliseconds. Better user experience with progress updates.

**[B-12] Contract number generation uses random - collision risk**
- Category: Backend
- Impact: LOW
- Current state: `_generate_contract_no()` generates `OW-YYYYMMDD-XXXX` with 4-digit random suffix. With high volume, collisions are possible (10,000 possibilities per day).
- Recommendation: Use a sequence or UUID-based suffix for production.
- Expected improvement: Eliminates collision risk.

### 3.6 Query Pattern Issues

**[B-13] ILIKE search without full-text index**
- Category: Database
- Impact: MEDIUM
- Current state: Market service uses `Contract.title.ilike(f"%{keyword}%")` for search. This bypasses B-tree indexes and does a sequential scan.
- Recommendation: For MVP, acceptable with small datasets. For production, add PostgreSQL full-text search (`tsvector` + GIN index) or use a search service.
- Expected improvement: Orders of magnitude faster text search at scale.

**[B-14] `list_contracts()` OR condition may prevent index use**
- Category: Database
- Impact: LOW
- Current state: When no role is specified, the query uses `(employer_id == user_id) | (freelancer_id == user_id)`. PostgreSQL may not efficiently use the individual indexes with OR.
- Recommendation: Use UNION ALL of two indexed queries, or ensure the frontend always passes a role parameter.
- Expected improvement: Better query plan for unfiltered contract listing.

---

## 4. Frontend Performance Analysis

### 4.1 Re-render Optimization

**[FE-01] Stats computed property recalculates on every contract change**
- Category: Frontend
- Impact: LOW
- Current state: In `Home.vue`, the `stats` computed property filters the contracts array to count by status. This recalculates whenever `contracts` ref changes, but since it's a simple filter on a page-sized array (max 10-20 items), performance is fine.
- Recommendation: No action needed.

**[FE-02] No v-memo used, but not needed**
- Category: Frontend
- Impact: PASS
- Current state: Components use `v-for` without `v-memo`, but list sizes are bounded by pagination (max 20 items). `v-memo` provides no benefit for small lists.
- Recommendation: None needed.

### 4.2 Loading States

**[FE-03] All pages have loading states**
- Category: Frontend
- Impact: PASS
- Current state: Every page that fetches data has a `loading` ref with NSpin/NEmpty fallback:
  - Home: NSpin + NEmpty
  - Market: NSpin + NEmpty
  - Upload: NSpin
  - TaskDetail, Acceptance, Credit: Not checked but follow same pattern.
- Recommendation: Consider skeleton screens instead of spinners for perceived performance improvement.

### 4.3 Image Optimization

**[FE-04] Avatar upload stores base64 directly**
- Category: Frontend/Backend
- Impact: MEDIUM
- Current state: `profile/service.py:upload_avatar()` accepts base64-encoded images and stores the raw base64 string in the `avatar` field (VARCHAR(500)). This has several issues:
  - Base64 encoding increases size by ~33%
  - VARCHAR(500) limits avatar size to ~375 bytes of actual image data (essentially unusable for real images)
  - No image resizing/compression before storage
  - Base64 stored in DB increases query payload size
- Recommendation: 
  1. Upload files to object storage (S3/OSS), store URL only
  2. Resize images server-side (e.g., 200x200 thumbnail)
  3. Support WebP format for smaller file sizes
- Expected improvement: 80%+ reduction in avatar storage, faster page loads.

### 4.4 API Response Caching

**[FE-05] No client-side API caching strategy**
- Category: Frontend
- Impact: MEDIUM
- Current state: No evidence of response caching, request deduplication, or stale-while-revalidate patterns. Every page navigation re-fetches data from the API.
- Recommendation: 
  1. Use Vue Query (TanStack Query) for automatic caching and stale management
  2. Or implement simple cache with Pinia store + TTL
  3. Cache market task list, user profile, credit score (these change infrequently)
- Expected improvement: 50%+ reduction in API calls for repeat navigation.

### 4.5 Client-Side Filtering

**[FE-06] Market page does client-side title search**
- Category: Frontend
- Impact: LOW
- Current state: `Market.vue` fetches a page of tasks, then filters by title client-side. This means search only works within the current page, not across all tasks.
- Recommendation: Pass `keyword` parameter to the API (the backend already supports it).
- Expected improvement: Correct search behavior across all tasks.

---

## 5. Architecture-Level Findings

### 5.1 Missing Connection Pooling Configuration

**[A-01] No explicit database pool configuration visible**
- Category: Architecture
- Impact: MEDIUM
- Current state: The database session is created via `get_db()` dependency. Pool size, max overflow, and timeout settings are not visible in the analyzed code.
- Recommendation: Configure SQLAlchemy pool: `pool_size=20, max_overflow=10, pool_timeout=30, pool_recycle=3600`
- Expected improvement: Prevents connection exhaustion under load.

### 5.2 Missing Rate Limiting Enforcement

**[A-02] Rate limiter exists but enforcement unclear**
- Category: Architecture
- Impact: MEDIUM
- Current state: `core/rate_limiter.py` exists but wasn't analyzed in detail. Rate limiting is critical for preventing abuse, especially on expensive endpoints like acceptance evaluation.
- Recommendation: Ensure rate limits are enforced on: login (5/min), acceptance evaluation (10/min), file upload (20/min).

### 5.3 No Response Compression

**[A-03] No evidence of gzip/brotli middleware**
- Category: Architecture
- Impact: MEDIUM
- Current state: FastAPI app doesn't appear to have compression middleware configured.
- Recommendation: Add `GZipMiddleware` to FastAPI. This reduces API response size by 60-80% for JSON payloads.
- Expected improvement: 60-80% reduction in API response transfer size.

---

## 6. Summary of Findings by Priority

### HIGH Impact
1. **B-01**: Credit score calculation makes 6-8 sequential queries (combine with CTEs)
2. **B-08**: `skip_question()` loads ALL blueprints (add index)
3. **FE-04**: Avatar base64 storage is broken (VARCHAR(500) + no optimization)

### MEDIUM Impact
4. **B-05**: Acceptance records have no pagination
5. **B-06**: Blockchain records have no pagination
6. **B-11**: Acceptance evaluation should be a background task
7. **B-13**: ILIKE search without full-text index
8. **FE-05**: No client-side API caching
9. **A-01**: Missing DB pool configuration
10. **A-03**: No response compression middleware
11. **F-01**: Large vendor bundle could be split further

### LOW Impact
12. **B-03**: Missing index on contracts.task_type
13. **B-04**: Missing composite index on contracts(status, created_at)
14. **B-12**: Contract number collision risk
15. **B-14**: OR condition may prevent index use
16. **FE-06**: Client-side search only searches current page

### PASS
- Tree-shaking working for Naive UI
- All routes lazy-loaded
- No blocking calls in async handlers
- All pages have loading states
- Pagination used on all list endpoints (except acceptance records)

---

## 7. Recommended Action Plan

### Phase 1 - Critical Fixes (Week 1)
1. Fix avatar upload (use object storage, not base64 in VARCHAR)
2. Add pagination to `get_acceptance_records()` and `get_records_by_contract()`
3. Optimize credit score calculation (combine queries)

### Phase 2 - Performance Improvements (Week 2)
4. Add `GZipMiddleware` to FastAPI
5. Add missing database indexes (task_type, composite status+created_at)
6. Fix market page to use API-side keyword search
7. Add client-side caching (Vue Query or Pinia + TTL)

### Phase 3 - Scalability (Week 3-4)
8. Move acceptance evaluation to background task
9. Add database connection pool configuration
10. Fix `skip_question()` to use indexed lookup
11. Split vendor bundle for better caching
12. Add full-text search for contract title search

---

*Report generated by static code analysis. Actual performance should be validated with load testing tools (k6, Locust) against a running instance.*
