# ML Dashboard — Project Memory

## Project Overview
ML Dashboard for **Qamaria Coffee** franchise operations. Predicts when each franchise location will next place an order AND what products they'll order. Angular 17+ frontend, FastAPI backend, integrated with **Inflow Inventory API** (cloud ERP). Two PyTorch neural networks: one predicts days-to-next-order (regression), one predicts next-order product quantities (multi-output regression).

## Tech Stack
- **Frontend**: Angular 17+ (standalone components, `@for`/`@if` control flow, SCSS)
- **Backend**: FastAPI (Python 3.11+), Pydantic v2 schemas, async endpoints, background tasks
- **ML**: PyTorch — `OrderPredictorNet` (4-layer dense regression) + `ProductPredictorNet` (multi-output regression)
- **Data**: Inflow Inventory cloud API → cached as Parquet files via `InflowCache` singleton
- **Config**: `.env` file for API keys (`inflow_api_key`, `inflow_company_id`)

## How to Run
- Backend: `cd backend && uvicorn main:app --reload` (port 8000)
- Frontend: `cd frontend && ng serve` (port 4200)
- Backend API prefix: `/api`
- Root convenience scripts: `npm run backend`, `npm run frontend`, `npm run dev` (concurrent)

---

## Architecture

### Backend Entry Point (backend/main.py)
- Registers 3 background async tasks on startup via lifespan context:
  1. `run_polling_loop()` — startup full fetch, then incremental every 60s, full re-fetch every 60 cycles (1 hr)
  2. `run_daily_product_refresh()` — invalidates + re-fetches products every day at 4pm ET
  3. `run_daily_orders_refresh()` — rebuilds today's predicted orders at midnight ET (date rollover)
- CORS: `localhost:4200`, `localhost`
- All routers mounted at `/api` prefix

### Backend Config (backend/config.py)
- Pydantic `BaseSettings`, reads `.env`
- Key fields: `inflow_api_url`, `inflow_api_key`, `inflow_company_id`
- `model_dir = backend/saved_models/`
- `cache_dir = backend/cached_data/`
- `poll_interval = 60` seconds
- `default_epochs = 10`, `default_batch_size = 32`

### Backend Services (backend/services/)

| Service | Purpose |
|---------|---------|
| `inflow_client.py` | Async HTTP client for Inflow REST API. Rate-limiting (45 req/min), retry logic (3 max), timeout handling, auto-pagination via X-listCount header |
| `inflow_service.py` | Orchestrates data fetching from Inflow. `_fetch_all_pages()` auto-paginates with per-key locking (thundering-herd prevention). Also imports derived_frames_service and location_frames_service to auto-register their callbacks |
| `cache_service.py` | `InflowCache` singleton — DataFrame storage with Parquet + JSON metadata persistence in `cached_data/`. Features: on-update callbacks, per-key async locks, cache invalidation, merge operations, disk auto-load on startup |
| `polling_service.py` | Full startup fetch (products first → detailed sales orders → rest in parallel). Incremental merge every 60s. Full re-fetch every 60 cycles. `full_refresh()` called by `/inflow/update` endpoint |
| `order_matrix_service.py` | **Core data pipeline** — see full details below |
| `location_frames_service.py` | Builds per-location order frames. Registers callback on `sales-orders` cache updates. Deduplicates within 3-day window, filters excluded products |
| `derived_frames_service.py` | Splits sales orders into: `franchise_store_orders` (SO-*), `online_orders` (SQ-*). Registers callbacks |
| `na_orders_service.py` | Filters NA franchise orders (US + Canada). Registers callbacks |
| `training_service.py` | Multi-variant order prediction training pipeline. Also `build_combined_predictions()` merges order + product predictions |
| `product_training_service.py` | Multi-variant product quantity prediction training pipeline |
| `inference_service.py` | Loads `.pt` + `_config.json`, builds feature vector, denormalizes predictions. Caches loaded models. `clear_model()` forces reload |
| `model_registry.py` | Discovers `.pt` files in `saved_models/`, returns ModelInfo |
| `product_config.py` | **Single source of truth** for excluded categories/names/SKUs, name overrides, quantity scaling |
| `settings_service.py` | Reads/writes `settings.json` (AppSettings Pydantic model). In-memory cache, persists on save |
| `todays_orders_service.py` | Filters predictions for today's effective date (Sat/Sun → Monday rollforward). `build_all_variants()` called at startup and midnight |

### Backend Routers (backend/routers/)

| Router | Key Endpoints |
|--------|--------------|
| `inflow.py` | All data endpoints. Key: `/inflow/update`, `/inflow/roast-stock`, `/inflow/active-orders-today`, `/inflow/predicted-next-order-date/{variant}`, `/inflow/predicted-next-products/{variant}`, `/inflow/predicted-orderdate-with-products/{variant}`, `/inflow/todays-predicted-orders/{variant}`, franchise matrix/location endpoints |
| `training.py` | `POST /training/` (start order training), `GET /training/{job_id}` (poll status) |
| `product_training.py` | `POST /training/products/`, `GET /training/products/{job_id}` |
| `settings.py` | `GET /settings`, `PUT /settings` |
| `models.py` | `GET /models/`, `GET /models/{name}` |
| `predictions.py` | Legacy `POST /predictions/` raw inference |
| `health.py` | `GET /health` |

### Backend Schemas (backend/schemas/)
- `inflow.py` — All Inflow API response models (Product, Customer, Vendor, SalesOrder, PurchaseOrder, Location, etc. + InflowDashboardSummary)
- `training.py` — `TrainingStatus` enum, `TrainingRequest`, `TrainingResponse`, `VariantResult`, `ProductTrainingResponse`, `ProductVariantResult`
- `settings.py` — `AppSettings` with nested: `StockSettings`, `ManufacturingSettings` (timings, capacity, coverage, dailyCaps, excluded, **roastRequirements**), `TrainingSettings`, `DataPipelineSettings`, `SystemSettings`. `RoastRequirement` model: `{roast: str, lbsPerUnit: float}`
- `common.py` — `ErrorResponse`, `PaginatedResponse`

### ML Models (backend/models/)
- `OrderPredictorNet(input_dim)` — Sequential: Linear→ReLU→BatchNorm1d→Dropout(0.3)→Linear→ReLU→BatchNorm1d→Dropout(0.2)→Linear→ReLU→Linear(1). Output squeezed to scalar.
- `ProductPredictorNet(input_dim, output_dim)` — Same architecture but final layer is `Linear(output_dim)`. Multi-output, no squeeze.
- `OrderPredictor` / `ProductPredictor` — Factory wrapper classes implementing `BaseMLModel`

---

## Order Matrix Pipeline (order_matrix_service.py)

### Franchise Location Extraction
- Customer name pattern: `"Qamaria - {Location}"` or `"Qamaria Coffee - {Location}"`
- Falls back to shipping/billing city
- City normalization: e.g., `"mississagua"` → `"Mississauga"`

### Excluded Franchise Locations (prefix match, case-insensitive)
- windermere, canton, phoenix, dmv catering, dearborn (hashem

### Product Column Sourcing
Product columns in the matrix are **sourced from the Inflow products cache** (same filtering as `/products` page) via `_get_products_page_names()`, not dynamically discovered from order history. This means:
- Columns are stable and consistent with what's visible in the product inventory page
- New products added to Inflow automatically gain matrix columns on next full rebuild
- Products not on the products page are excluded from the matrix
- Falls back to order-discovered products only if products cache is empty at rebuild time

### Processing Steps (Full Rebuild)
1. Filter to `SO-*` order numbers only, North America only (US/Canada by country, state, or ZIP)
2. Parse each order: extract location, products (with exclusions + scaling), order date
3. **Same-day merge**: per location, merge orders within `mergeWindowDays` (default 3) days → combine order numbers, earliest date, sum product quantities
4. **Small order absorption**: if location has <20% small orders (qty ≤ 5), absorb small orders into previous order. Then cascade: absorb orders below 25% of location average until stable
5. **Dormancy filter**: iteratively remove orders where gap to next > `dormantThresholdDays` (default 180) until stable
6. **Closed shop removal**: if a location's most recent raw order is >180 days behind dataset max, remove all their orders from latest
7. Compute temporal features per order (see feature engineering)
8. Compute `order_size` (piecewise linear: min→0.0, mean→0.5, max→1.0 per location)
9. Build flat rows with all features + next-order product targets (`next_prod_*`)
10. Split and save 4 variants

### Incremental Update Path
When `_state_ready = True` and only new order IDs detected (none removed), uses fast incremental path:
- Detects new orders vs. known set
- Same-day merge → dormancy → update `_latest_per_location`
- Appends new training rows to existing variant Parquet files
- Triggers `_trigger_incremental_training()` → fine-tunes existing models

### Module-level State (for incremental updates)
```python
_order_data, _latest_per_location, _known_order_ids
_all_cities, _all_products, _city_groups_idx
_temporal_features, _next_order_ts, _next_order_num
_flat_rows, _state_ready
```

---

## Product Configuration (backend/services/product_config.py)
**Single source of truth for ALL product filtering/naming. Frontend mirrors in `inflow.model.ts` and `products.ts`.**

### Excluded Categories
inactive, bags, storage bins, tools, merchandise, raw material, packaging, equipment, roasts, services, preblends, pastries, supplies, warehouse supplies

### Key Excluded Product Names (lowercase, partial list)
monin pumpkin spice syrup (bottle), pumpkin powder (ground), shipping discount, tea, qamaria mix, and many more — see `product_config.py` for full list

### Excluded SKUs
IF5127635, IF5127634, IF5127554, IF5127797, IF5127553, IF5127552

### Name Overrides (key examples)
- ghirardelli caramel sauce / caramel sauce → "Caramel Sauce"
- ghirardelli chocolate sauce / chocolate sauce → "Chocolate Sauce"
- monin mango smoothie / mango smoothie → "Mango Smoothie"
- monin strawberry smoothie / strawberry smoothie → "Strawberry Smoothie"
- ceremonial matcha tin → "Ceremonial Matcha"
- all lid variants → "Hot Lids" or "Cold Lids"
- all 16oz cup variants → "16oz Cold Cups"

### Quantity Scaling (key examples)
- ceremonial matcha tin: ×2.64555 vs regular
- marib/sanaa/radaa/juban mix 5 lbs bag: ×(5/3) vs 3 lbs bag
- al-kbous black tea variants: 0.5/1.0/1.5/2.0 based on bag count
- 6oz white sipper lids (non-2000 variants): ×2.5

---

## Multi-Variant Training System

### 4 Data Variants
| Variant | Min Orders (3+) | Year Feature |
|---------|----------------|-------------|
| `base` | No | No |
| `min_orders` | Yes | No |
| `year` | No | Yes |
| `min_orders_year` | Yes | Yes |

### File Layout per Variant
```
cached_data/
  franchise_order_matrix_{variant}/matrix.parquet + matrix.meta.json
  latest_franchise_orders_{variant}/latest.parquet + latest.meta.json
  franchise_product_matrix_{variant}/matrix.parquet
  latest_franchise_product_orders_{variant}/latest.parquet
  predictions/predicted_next_order_date_{variant}_{timestamp}.json
  predictions/predicted_next_products_{variant}_{timestamp}.json
  predictions/predicted_orderdate_with_products_{variant}_{timestamp}.json

saved_models/
  order_predictor_{variant}.pt
  order_predictor_{variant}_config.json
  order_predictor_{variant}_{timestamp}.pt   (versioned)
  product_predictor_{variant}.pt
  product_predictor_{variant}_config.json
```

### Feature Engineering (order prediction)
Build order (7 groups):
1. `day_sin`, `day_cos` — cyclical day of month (period 31)
2. `month_sin`, `month_cos` — cyclical month (period 12)
3. `order_size` — piecewise linear 0.0–1.0 (kept as-is)
4. `days_since_last`, `avg_gap`, `order_count`, `prev_gap`, `gap_trend` — StandardScaled (params saved)
5. `year_norm` — only in `year`/`min_orders_year` variants
6. `loc_{city_slug}` — one-hot location columns
7. `loc_{city_slug}_month_sin`, `loc_{city_slug}_month_cos` — season×location interactions
8. `prod_{slug}` — product quantities, StandardScaled (params saved)

### Training Hyperparameters (from AppSettings.training)
- `learningRate`: 0.001
- `weightDecay`: 1e-4
- `lrSchedulerPatience`: 5, `lrSchedulerFactor`: 0.5
- `earlyStoppingPatience`: 10
- `trainValSplit`: 0.8 (random shuffle, seed=42)
- `predictionTolerance`: 7.0 days (for accuracy % metric)
- `recencyWeightMin`: 0.5, `recencyWeightMax`: 1.0
- `finalLearningRate`: 0.0001 (post-validation retraining)
- Post-validation retraining: if `val_r2 > minR2ForRetraining` (0.0) AND accuracy > 50% AND val/train MAE ratio < 2.0

### Incremental Fine-tuning
- lr=5e-5, 3 epochs, weight_decay=1e-4
- Uses **stored** scaler params (no re-fitting)
- Triggers automatically when new completed orders detected in order matrix

### Training Flow
1. `POST /training/` → starts background job, returns `job_id`
2. Trains all 4 variants sequentially
3. Frontend polls `GET /training/{job_id}` every 2 seconds
4. On completion: `variant_results` dict with per-variant metrics
5. `_run_predictions()` generates predictions from `latest_franchise_orders_{variant}`
6. `build_combined_predictions()` merges order + product predictions into `predicted_orderdate_with_products_{variant}`
7. `build_todays_predicted_orders()` filters for today

### Model Config JSON (saved alongside .pt)
```json
{
  "feature_names": [...],
  "loc_cols": [...],
  "prod_cols": [...],
  "interaction_cols": [...],
  "temporal_cols": [...],
  "temporal_scaler_mean": [...],
  "temporal_scaler_scale": [...],
  "prod_scaler_mean": [...],
  "prod_scaler_scale": [...],
  "target_mean": float,
  "target_std": float,
  "input_dim": int
}
```
Product model also has: `model_type: "product_predictor"`, `target_names`, `target_means`, `target_stds`, `output_dim`

---

## Key Data Interfaces

### TrainingResponse (backend schema + frontend model)
```
job_id, status, epoch, loss, accuracy, train_mae, val_mae, val_rmse, val_r2,
samples_total, samples_train, samples_val, num_features, num_locations, num_products,
predictions_count, predictions_file, variant_results: dict[str, VariantResult], error
```

### VariantResult
```
variant, train_mae, val_mae, val_rmse, val_r2, accuracy (within 7 days),
epoch, samples_total, samples_train, samples_val, num_features,
num_locations, num_products, predictions_count, predictions_file, error
```

### CombinedPredictionRow (frontend — primary prediction shape)
```
orderNumber, contactName, customerName, city, orderDate,
predictedDaysToNext, predictedNextOrderDate,
predictedEarliestDate, predictedLatestDate,
predictedProducts: Record<string, number>  // keyed by next_prod_{slug}
```

### PredictionRow (order-only)
```
orderNumber, contactName, city, orderDate,
predictedDaysToNext, predictedNextOrderDate,
predictedEarliestDate, predictedLatestDate
```

---

## Frontend Structure

### Pages (frontend/src/app/dashboard/pages/)
| Page | Route | Key Features |
|------|-------|-------------|
| `dashboard-home` | `/dashboard` | Active orders today, combined predictions table, stock tracking, manufacturing recommendations. Day/Week/Month view modes. Weekend roll-forward logic |
| `training-predictions` | `/training-predictions` | Model training UI, 4 variant tabs, metrics, product training section |
| `product-inventory` | `/products` | Product listing with stock levels |
| `order-information` | `/orders` | Order details |
| `franchise-store-orders` | `/franchise-store-orders` | SO-* franchise orders |
| `franchise-location-orders` | `/franchise-location-orders` | Per-city order history with Next Order Date |
| `franchise-order-matrix` | `/franchise-order-matrix` | Raw matrix view |
| `franchise-product-matrix` | `/franchise-product-matrix` | Product matrix view |
| `na-franchise-orders` | `/na-franchise-orders` | North America only |
| `online-orders` | `/online-orders` | SQ-* online orders |
| `latest-franchise-orders` | `/latest-franchise-orders` | Most recent per location |
| `latest-franchise-product-orders` | `/latest-franchise-product-orders` | Most recent product orders |
| `demand-forecast` | `/demand-forecast` | Demand forecasting |
| `roast-inventory` | `/roast-inventory` | Roast stock (Light/Medium/Dark) |
| `settings` | `/settings` | App configuration UI |

### Frontend Services (frontend/src/app/shared/services/)
- `api.service.ts` — Base HTTP wrapper, adds `/api` prefix, `get/post/put/delete` methods
- `inflow.service.ts` — All Inflow API calls with 5-min TTL frontend cache. Has `roastRows$` BehaviorSubject populated by product fetch. `updateData()` calls `/inflow/update`
- `training.service.ts` — `startTraining()`, `getStatus()`, `getCombinedPredictions(variant)`, `startProductTraining()`, `getProductStatus()`
- `settings.service.ts` — `load()`, `save()`, `current` getter. Exposes `AppSettings` to all components

### Frontend Models (frontend/src/app/shared/models/)
- `inflow.model.ts` — All Inflow data types + `FranchiseLocationCity`, `FranchiseLocationOrderRow`, `FranchiseOrderMatrixRow`
- `training.model.ts` — All training/prediction interfaces
- `settings.model.ts` — `AppSettings` interface with `DEFAULT_SETTINGS`

### Frontend Constants (frontend/src/app/shared/constants/)
- `products.ts` — `MATRIX_PRODUCTS: MatrixProduct[]` — 18 products with `displayName` and `slug`
  - `prodCol(p)` → `prod_{slug}`
  - `nextProdCol(p)` → `next_prod_{slug}`

### 18 Tracked Matrix Products
Medium Roast Coffee (Whole), Dark Roast Coffee (Whole), Qishr, Sunrise Socotra, Mount Haraz, Gate of Yemen, Queen Sheeba, Cinnamon (Ground), Cloves (Whole), Cardamom (Ground), Ginger (Ground), Juban Mix, Radaa Mix, Marib Mix, Sanaa Mix, Ancient Marib, Old City Sana'a, Valley Juban

### Dashboard Manufacturing Logic
- **View modes**: Day (7h=420min), Week (35h=2100min), Month (140h=8400min)
- **Product rounding rules**: ×16 min 32 (Whole coffees, specialty blends), ×10 (Dark Roast Whole, Qishr, Mixes, Cardamom), ×5 (Cinnamon, Cloves, Ginger)
- **2-phase coverage sort**: Phase 1 (coverage <150%) — below-threshold items first, then by demand. Phase 2 (150–200%) — by demand. ≥200% excluded
- **Time budget**: fills capacity from most-urgent item, trims last item to valid partial batch
- **Stock source**: `inflow.service.listProducts()` with `inventoryLines` for most; roast SKUs: IF5127699/IF5127705/IF5127683
- **Roast budget constraint**: `roastBudget` initialized from `stockMap` at start of loop. Each item with a `roastRequirement` is capped by `floor(roastBudget[roast] / lbsPerUnit)`, rounded down to valid batch. Consumed roast deducted after item added. `roastRequirements` read live from `settingsService.current.manufacturing.roastRequirements`.
- **Weekend roll-forward**: Sat (+2 days) / Sun (+1 day) predictions count as Monday
- **Dashboard section order**: metrics → product stock → manufacturing recommendations → predicted orders (+ overdue) → active orders today

---

## Data Flow Diagram
```
Inflow API
  ↓ (polling_service — startup full fetch, then incremental every 60s)
InflowCache (Parquet on disk)
  ↓ (on-update callback registered by order_matrix_service)
order_matrix_service._rebuild_order_matrix()
  ↓
4 Variant Parquet files (franchise_order_matrix_{variant}/matrix.parquet)
4 Variant Latest files (latest_franchise_orders_{variant}/latest.parquet)
4 Variant Product Matrix files
  ↓ (triggered by training.py endpoint or incremental fine-tune)
training_service._train_variant() × 4
  ↓
saved_models/order_predictor_{variant}.pt + _config.json
  ↓
training_service._run_predictions()
  ↓
inflow_cache["predicted_next_order_date_{variant}"]
  ↓ (after product training)
build_combined_predictions(variant)
  ↓
inflow_cache["predicted_orderdate_with_products_{variant}"]
  ↓
todays_orders_service.build_todays_predicted_orders(variant)
  ↓
inflow_cache["todays_predicted_orders_{variant}"]
  ↓
Frontend: GET /inflow/predicted-orderdate-with-products/base
  ↓
DashboardHomeComponent.allPredictions[]
  → filteredPredictions (view period)
  → productTotals (demand aggregation)
  → manufacturingRecommendations (stock vs demand vs capacity)
```

---

## AppSettings Defaults (settings.json / backend/schemas/settings.py)

### DataPipelineSettings
- `minOrdersThreshold`: 3 (min_orders variants)
- `mergeWindowDays`: 3
- `dormantThresholdDays`: 180
- `smallOrderQtyThreshold`: 5
- `smallOrderCascadeThreshold`: 0.25

### TrainingSettings
- `learningRate`: 0.001, `weightDecay`: 1e-4
- `lrSchedulerPatience`: 5, `lrSchedulerFactor`: 0.5
- `earlyStoppingPatience`: 10, `trainValSplit`: 0.8
- `predictionTolerance`: 7.0 (days for accuracy%)
- `recencyWeightMin`: 0.5, `recencyWeightMax`: 1.0
- `minR2ForRetraining`: 0.0, `minAccuracyForRetraining`: 50.0
- `maxValTrainMaeRatio`: 2.0, `finalLearningRate`: 0.0001

### SystemSettings
- `backendPollInterval`: 60s
- `fullRefreshEveryCycles`: 60 (= 1 hr)
- `apiPageSize`: 100
- `productRefreshHour`: 16 (4pm ET)
- `frontendPollIntervalMs`: 60000 (1 min)

### ManufacturingSettings (key defaults)
- `dailyHours`: 7.0, `weeklyHours`: 35.0, `monthlyHours`: 140.0
- `bufferMinutes`: 10 (between items)
- `phase1Threshold`: 1.5 (150% coverage), `exclusionThreshold`: 2.0 (200%)
- `dailyCaps`: {"Cardamom (Ground)": 30}
- `excluded`: ["Medium Roast Coffee (Whole)"]
- `roastRequirements`: {"Gate of Yemen": {roast: "Dark Roast", lbsPerUnit: 0.75}, "Sunrise Socotra": {roast: "Light Roast", lbsPerUnit: 0.75}, "Mount Haraz": {roast: "Medium Roast", lbsPerUnit: 0.75}, "Dark Roast Coffee (Whole)": {roast: "Dark Roast", lbsPerUnit: 2.5}}

### StockSettings (key thresholds)
Sunrise Socotra: 64, Old City Sana'a: 64, Queen Sheeba: 32, Ancient Marib: 80, Gate of Yemen: 80, Mount Haraz: 128, Valley Juban: 64, Dark Roast Coffee Whole: 10, Qishr: 10, all Mixes: 10, Cardamom: 10, Cinnamon/Cloves/Ginger: 5

---

## Current State (as of Feb 28, 2026)
- All multi-variant training + product training code is implemented and working
- Dashboard uses `getCombinedPredictions('base')` — combines order date + product quantity predictions
- Incremental fine-tuning triggers automatically on new orders detected via polling
- All Improve-1.1 through 1.13 implemented (see Improvements section)
- Changes uncommitted — see `git status` for full list
- `CLAUDE.md` — this file (not committed)

---

## Improvements
Identified 2026-02-27. All completed 2026-02-28.

### Biggest Wins (small effort, high impact)
- **Improve-1.1** ✅ (done 2026-02-27) — **Memoize heavy dashboard getters** — Convert `manufacturingRecommendations`, `productTotals`, `weekPredictions`, `allPredictionTotals`, `weekPredictionTotals`, `filteredPredictions`, `overduePredictions` from getters to plain component properties in `dashboard-home.component.ts`. Recalculate only inside `loadPredictions()` / `ngOnInit()`. Also cache `getProductEntries(row)` result to avoid calling it twice per row in the template (`dashboard-home.component.html`). Expected: eliminates 50–200ms UI lag per change detection cycle.
- **Improve-1.2** ✅ (done 2026-02-28) — **Track all subscriptions with `takeUntilDestroyed`** — Added `DestroyRef` + `inject` + `takeUntilDestroyed` to `dashboard-home.component.ts` (all 6 subscriptions: `settingsService.load()`, `triggerUpdate()`, `startPolling()`, `loadPredictions()`, `loadStock()`, `loadActiveOrdersWeek()`). Removed manual `ngOnDestroy`/`pollSub` in favour of `takeUntilDestroyed`. Also fixed `training-predictions.component.ts`: added `takeUntilDestroyed` to `startTraining()`, poll inner subscription, `startProductTraining()`, product poll inner subscription, and all `loadAllCombinedPredictions()` inner subscriptions.
- **Improve-1.3** ✅ (done 2026-02-28) — **Prune `_jobs` dict in training service** — Added `_MAX_JOBS = 20` constant to `backend/services/training_service.py`. In `start()`, after appending a new job, evicts the oldest entries when `len(_jobs) > _MAX_JOBS`. Prevents unbounded memory growth across long-running backend sessions.
- **Improve-1.4** ✅ (done 2026-02-28) — **Delete stale frontend cache entries** — In `frontend/src/app/shared/services/inflow.service.ts` `cached()` method: added explicit `this.cache.delete(key)` when an expired entry is found before creating the new one. Prevents the Map from growing indefinitely with unreachable stale observables.
- **Improve-1.5** ✅ (done 2026-02-28) — **Add `threading.Lock` around order matrix module globals** — Added `import threading` and `_rebuild_lock = threading.Lock()` to `backend/services/order_matrix_service.py`. Split both core functions into outer (lock-guarded) + inner: `_rebuild_order_matrix` acquires with `with _rebuild_lock`, `_incremental_update` uses non-blocking `acquire(blocking=False)` and skips with a warning if a rebuild is already running. Prevents state corruption from concurrent full rebuild + incremental update callbacks.

### Medium Effort, High Stability
- **Improve-1.6** ✅ (done 2026-02-28) — **Validate feature dimensions before incremental fine-tuning** — In `backend/services/training_service.py` incremental_train path: changed the dimension mismatch log from `logger.info` to `logger.warning` and enriched the message to include `X.shape[1]` (new), saved `input_dim`, and `len(saved_names)`. Gives a clear signal in logs that a full retrain is required when new products expand the feature set.
- **Improve-1.7** ✅ (done 2026-02-28) — **Offload Parquet I/O to thread pool executor** — Added `import concurrent.futures`, a module-level `_parquet_pool = ThreadPoolExecutor(max_workers=2)`, and helper functions `_pq_read(path)` / `_pq_write(df, path)` to `backend/services/order_matrix_service.py`. Replaced all `pd.read_parquet` and `df.to_parquet` calls inside `_rebuild_variant_files_incremental` with these helpers. Releases the GIL during file I/O and structures code for future async migration.
- **Improve-1.8** ✅ (done 2026-02-28) — **Add `ChangeDetectionStrategy.OnPush`** — Applied to all three heavy components: `dashboard-home.component.ts`, `training-predictions.component.ts`, `product-inventory.component.ts`. Each has `ChangeDetectorRef` injected and `cdr.markForCheck()` called at the end of every async subscription callback (next + error) that mutates component state. Eliminates unnecessary change detection runs on every Angular tick for these components.
- **Improve-1.9** ✅ (done 2026-02-28) — **Circuit breaker / exponential backoff for polling service** — Added `_CB_FAILURE_THRESHOLD = 5` and `_CB_BACKOFF_CAP = 600` constants to `backend/services/polling_service.py`. `run_polling_loop()` now tracks `consecutive_failures` and `current_interval`; on success both reset to defaults; after 5+ consecutive failures the interval doubles each cycle (capped at 600s). Prevents log flooding and excessive API hammering when Inflow is unreachable.

### Lower Priority
- **Improve-1.10** ✅ (done 2026-02-28) — **Surface partial training failures in job status** — In `backend/services/training_service.py`, after all variants train, detects any with `.error` set, assigns `job.error = f"Partial failure: variant(s) {', '.join(failed)} failed"`, and logs a warning. `job.status = COMPLETED` is set after the check so the error field is preserved. Frontend can now display partial failure warnings from `trainingResult.error`.
- **Improve-1.11** ✅ (done 2026-02-28) — **Add size validation to `torch.load()`** — Added `_MAX_MODEL_BYTES = 500 MB` guard in `backend/services/inference_service.py` `_get_model()`. Checks `model_path.stat().st_size` before `torch.load()` and raises `ValueError` if exceeded. Prevents loading corrupted or unexpectedly large model files.
- **Improve-1.12** ✅ (done 2026-02-28) — **Log task cancellations in `main.py`** — Added `import logging` + `logger` to `backend/main.py`. Replaced the anonymous task list + silent `except asyncio.CancelledError: pass` with a named `[(task, name), ...]` list; each cancellation is logged with `logger.info("Background task '%s' cancelled on shutdown", name)`. Shutdown diagnostics now show which tasks were cancelled.
- **Improve-1.13** ✅ (done 2026-02-28) — **Delete `backend/nul`** — Stray Windows NUL device redirect artifact deleted from the repository.

---

## Improvements Round 2
Identified and implemented 2026-02-28.

### Deduplication / Consolidation
- **Improve-2.1** ✅ (done 2026-02-28) — **Centralize `VARIANT_NAMES` in `config.py`** — Added `VARIANT_NAMES = ["base", "min_orders", "year", "min_orders_year"]` as a module-level constant in `backend/config.py`. Updated imports in `training_service.py`, `product_training_service.py`, `todays_orders_service.py`, and `order_matrix_service.py`. Removes 4 duplicated list literals.
- **Improve-2.2** ✅ (done 2026-02-28) — **Extract `_safe_value` + `_NA_COUNTRIES` to `backend/utils.py`** — Created `backend/utils.py` with `safe_value(v)` and `NA_COUNTRIES` (frozenset). Updated imports in `order_matrix_service.py`, `location_frames_service.py`, `na_orders_service.py`. Removed 3 duplicate `_safe_value` function definitions and 2 duplicate `_NA_COUNTRIES` sets.
- **Improve-2.3** ✅ (done 2026-02-28) — **Deduplicate `_DETAILED_SO_PARAMS`** — `inflow.py` router now imports `_DETAILED_SO_PARAMS` from `polling_service.py`. Also reuses it inside `get_franchise_location_orders` instead of a redundant inline dict.
- **Improve-2.4** ✅ (done 2026-02-28) — **Variant validation helper in `inflow.py`** — Added `_VALID_VARIANTS: frozenset[str]` and `_validate_variant(variant)` raising `HTTPException(400)`. Replaced 4 duplicated validation blocks with single `_validate_variant(variant)` calls.
- **Improve-2.5** ✅ (done 2026-02-28) — **Active orders row builder in `inflow.py`** — Extracted `_build_active_row(row)` helper. Both `get_active_orders_week` and `get_active_orders` now call it, eliminating a duplicated ~15-line flatten+filter body.
- **Improve-2.6** ✅ (done 2026-02-28) — **`InflowCache.get_entry()` public method** — Added `get_entry(key: str) -> _CacheEntry | None` to `cache_service.py`. Replaced all `inflow_cache._store.get(...)` calls in 5 files (7 call sites): `inflow.py`, `na_orders_service.py`, `derived_frames_service.py`, `location_frames_service.py`, `order_matrix_service.py`.

### Functional Parity / Correctness
- **Improve-2.7** ✅ (done 2026-02-28) — **Product training reads hyperparams from settings** — In `product_training_service.py` `_train_product_variant`: replaced all hardcoded hyperparams (`lr`, `patience`, `factor`, `finalLR`, `maxRatio`, `minR2`, `trainValSplit`, recency weights) with values from `settings_service.get().training`. Matches `training_service.py`.
- **Improve-2.8** ✅ (done 2026-02-28) — **`ProductTrainingService` feature parity** — Added `_MAX_JOBS = 20` eviction cap in `start()`. After all variants train, detects any with `.error`, sets `job.error = "Partial failure: ..."` before marking `COMPLETED`. Mirrors Improve-1.3 and Improve-1.10 applied to `TrainingService`.
- **Improve-2.9** ✅ (done 2026-02-28) — **`refresh_all_predictions` uses singleton** — Replaced `svc = TrainingService()` with `svc = training_service` (module-level singleton). Avoids creating a throwaway instance with an orphaned `_jobs` dict.

### Cleanup
- **Improve-2.10** ✅ (done 2026-02-28) — **Remove unused imports from `inflow.py`** — Removed `get_cities, get_city_orders` from the `location_frames_service` import; these were never called (the router reimplements their logic inline).
- **Improve-2.11** ✅ (done 2026-02-28) — **Frontend shared prediction utilities** — Created `frontend/src/app/shared/utils/prediction.utils.ts` with `formatCity(slug)`, `formatDate(date?)`, and `buildProductEntries(row)`. Updated `dashboard-home.component.ts` and `training-predictions.component.ts` to delegate to the shared functions.

---

### Changes made Feb 25, 2026
1. **Roast inventory constraints in manufacturing** — `manufacturingRecommendations` getter in `dashboard-home.component.ts` now initializes a `roastBudget` from `stockMap` and caps each item's `toManufacture` by available roast stock based on `lbsPerUnit`. Deducts consumed roast as items are added.
2. **Roast requirements configurable via Settings** — `RoastRequirement` added to `backend/schemas/settings.py` and `ManufacturingSettings.roastRequirements`. Mirrored in `frontend/src/app/shared/models/settings.model.ts`. Settings UI (Manufacturing tab) has a new "Roast Requirements" table with roast type dropdown + lbs/unit input per product. Dashboard reads requirements live from `settingsService.current` instead of a hardcoded map.
3. **Product matrix columns from /products page** — `_get_products_page_names()` added to `order_matrix_service.py`. Matrix columns now sourced from the products cache (same filtering as frontend /products page) rather than dynamically discovered from order history. `_all_products` state stores the products-page set.
4. **Dashboard section reorder** — Active orders section moved below predicted orders. New order: metrics → stock → manufacturing → predicted orders → active orders.
