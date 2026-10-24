# Qloo API notes (pre-key, documentation-only)

Status: compiled 2026-10-24 from official sources only, **before** we had an API key. Every item marked **UNVERIFIED** is a gap or contradiction in the docs and must be checked in Monday's live test (see the last section).

Sources read:

- `github.com/qloo/docs-public`: `reference/*.md`, `docs/*.md`, `recipes/recipes.md`. Note: its `openapi-schema.json` is only the generic OpenAPI 3.1 *meta-schema*, not Qloo's spec.
- `docs.qloo.com/reference/<page>.md` (embedded OpenAPI per endpoint, updated 2026-07): insights-api-deep-dive, analysis-compare, get-search, get-entities, get-tag-types, get-audiences, api-information, the use-case pages, and `qloo-llm-hackathon-developer-guide` (updated 2026-10-07).
- Docs MCP `https://docs.qloo.com/mcp` (reference only): `list-endpoints`, `get-endpoint` for `/v2/tags`, `/v2/insights`, `/v2/analysis/compare`, `/search`, recipes (`compare-two-brands-audiences`, `search-for-an-entity-by-name`, `find-a-tag-id-by-keyword`, `get-the-taste-tags-that-describe-an-entitys-audience`, heatmap recipes, demographics/personalization recipe), and `reference/schema-taxonomy`. I never called `execute-request`.
- `github.com/qloo/qloo-hackathon-kit`: README, docs/*, starters. The kit wraps the API in the `@qloo/qloo-harness` CLI/MCP, which returns its **own** envelope (`status`, `summary`, `results`, `result_count`, `error{code,retryable,recovery}`). That envelope is **not** the raw REST shape, so don't confuse the two.

---

## 0. Global facts

| Item | Value | Source |
|---|---|---|
| Base URL (hackathon) | `https://hackathon.api.qloo.com` | hackathon guide |
| Wrong base URL | `api.qloo.com` and `staging.api.qloo.com` reject hackathon keys with **401** | hackathon guide |
| Auth | header `X-Api-Key: <key>`. Not a query param, not Bearer. A missing header gives 401 `"No API key found in request"` | hackathon guide, OpenAPI `securitySchemes.ApiKey` |
| Method | **GET only**, with parameters in the query string. POST with a JSON body to `/v2/insights` fails (`"No path matching request parameters"` / 404) | hackathon guide |
| Array params | comma-separated in GET (`style: form, explode: false`) | OpenAPI |
| Base URL alone | 404 or no response. Always append a path | hackathon guide |
| Legacy endpoints | `/recommendations`, `/recs` are **not supported** | hackathon guide |
| Invalid params | **silently ignored, not rejected**. The usual symptom is 200 with empty `results.entities` | hackathon guide |
| Unsupported `filter.type` | 403 `"You do not have permission to access urn:entity:..."` | hackathon guide |
| Invalid tags/audiences | error text `"at least one valid signal or filter is required"`. HTTP status not stated: **UNVERIFIED** (probably 400) | hackathon guide |
| Rate limits | "rate and monthly quota limits set high enough for typical projects", raised on request via Discord #api-help. **No rate-limit headers are documented anywhere** (UNVERIFIED). OpenAPI lists `429 Rate limit exceeded` with an empty `headers: {}` | hackathon guide, OpenAPI |
| Field selection | not possible. Responses are full (including verbose `akas`) | hackathon guide FAQ |
| Caching | private server-side caching allowed with no time limit. **Never store responses in a public repo** | hackathon guide FAQ |
| Error body | documented schema `{ "code": number, "reason": string, "message": string }` (for 404/429 on `/search`, `/entities`, `/`, compare). Example: `{"code":400,"reason":"Bad Request","message":"entity_ids must be specified."}` | OpenAPI |
| `duration` | present on most responses. Docs examples show ms-looking ints (`34`, `77`) while the OpenAPI text says "seconds" (`0.1`) and the compare recipe shows `0.42`. Unit is **UNVERIFIED**, so don't rely on it | use cases, OpenAPI |

### Entity type spelling (contradiction)

- OpenAPI enum for `/v2/insights filter.type` and `/search types`: `urn:entity:artist, book, brand, locality (partial), movie, person, place, podcast, tv_show, videogame, urn:heatmap, urn:entity:audience (deprecated)`. Spelled **`videogame`**.
- Hackathon guide's supported list: `... urn:entity:tv_show, urn:entity:video_game`. Spelled **`video_game`**, and it adds `urn:entity:destination`.
- `urn:demographics` and `urn:tag` are **not** in the OpenAPI enum but are documented use cases (demographics-use-case, taste-analysis).
- Heatmap: `urn:heatmap` everywhere, except that the `heatmap.dimensions` description says `filter.type=urn:entity:heatmap`.
- `/search` also accepts legacy search-only types `urn:entity:actor|album|author|director|locality`, which are not valid in `/v2/insights`.
- Tea Rose only needs `urn:entity:brand`, `urn:heatmap`, `urn:demographics` and `urn:tag`, so the videogame ambiguity doesn't block us.

### Score semantics

- `query.affinity` on entities is a float **0..1** (recipes: `0.97`). The docs prose talks about "0 to 100" (UI percentages). Insights API docs: "Affinity Scores: ranging from 0 to +1".
- Affinity is **normalized per query**: "compare brands based on their relative position in the results, not just the raw score" (interpreting-affinity-scores). Scores also "may decrease as more inputs or filters are applied". Consequence for Tea Rose: **never compare raw affinities across two different requests**, for example the filtered pet query against the unfiltered query. Use rank or within-query percentiles.
- Ranges (UI scale): >80 very high, 60–80 high, =50 medium, <50 low. Differences of about 1 point are not meaningful.
- `popularity` is a percentile 0..1 within the category (e.g. `0.9984`).
- Without any signal, `query.affinity` (and `distance`) come back **`null`** and results are ranked by popularity (WKT-polygon recipe).
- Demographics values are **signed relative affinities** (e.g. `-0.28 … 0.70`), not shares. In every documented example `male == -female`.

### Pagination

- `/v2/insights`, `/v2/tags`, `/v2/tags/types`, `/v2/audiences`, `/v2/audiences/types`, `/v2/analysis/compare`: `take` 1..**50** (default 20), `page` ≥1 (OpenAPI max 100, default 1), and `offset` (int, skip N). `page` is recommended ("equivalent to take + offset").
- `/search`: `take` is an integer with `exclusiveMaximum: 200` in the live OpenAPI. The older GitHub page says 1..100, default 20. `page` is 1..100.
- **No total count or next-page token is documented** in any response (UNVERIFIED). Assume you page until a short or empty page.

---

## 1. `GET /search`: entity lookup by name

Parameters (live OpenAPI, 2026-07):

| Param | Type / constraints | Notes |
|---|---|---|
| `query` | string | text to search |
| `types` | array of string (comma-sep), enum above | e.g. `urn:entity:brand` |
| `filter.location` | string | `"lat,lon"`, WKT, or Qloo locality UUID |
| `filter.radius` | number 0..100, default 10 | **miles** (unlike insights, which uses meters) |
| `filter.exists` | array, pattern `^external\.\w+$` | e.g. `external.resy` |
| `filter.tags` | array of string | |
| `filter.rating` | number 0..5 | |
| `filter.popularity` | number 0..1 | minimum popularity |
| `filter.address` | string | partial match |
| `operator.filter.tags` | `union` (default) / `intersection` | |
| `filter.exclude.tags`, `operator.filter.exclude.tags` | array / enum | GitHub page only |
| `page` | int 1..100, default 1 | |
| `take` | int, < 200 | |
| `sort_by` | `match` (default) / `distance` / `popularity` | |

Responses: 200, **404 "No results"**, 429. Shape (recipe `search-for-an-entity-by-name`; "results come back as a **flat array** under `results`, not nested under `results.entities`"):

```json
{
  "results": [
    {
      "name": "Balthazar",
      "entity_id": "FCE8B172-4795-43E4-B222-3B550DC05FD9",
      "types": ["urn:entity:place"],
      "popularity": 0.998,
      "properties": {}
    }
  ]
}
```

- The search result uses **`types` (array)**. Insights entities use `type: "urn:entity"` plus `subtype`. The OpenAPI wraps the result with `success` and `duration` (allOf), but the recipe example omits them. Treat both as optional.
- Zero hits: either `200 {"results": []}` or `404 {"code":404,...}`. **UNVERIFIED** which one. The client must handle both.
- Fixtures: `search_brand_*.json`.

## 2. `GET /entities`: lookup by ID

Params: `entity_ids` (array of UUID, comma-sep), or any of `external.{facebook,goodreads,goodreads_author,igdb,imdb,instagram,isbn10,isbn13,itunes,lastfm,library_of_congress,metacritic,michelin,musicbrainz,rottentomatoes,soundcloud,spotify,tablet,twitch,twitter,wikidata,resy}.ids`. Response: same `results: [entity]` wrapper as `/search` (OpenAPI uses the same unresolved `$include` schema). The entity fields are **UNVERIFIED** and presumably match the insights entity object. We don't need this endpoint (search returns everything we need).

## 3. `GET /v2/insights`: the core endpoint

### 3.1 Parameters relevant to Tea Rose

`filter.type` is **required**, plus at least one valid filter or signal.

| Param | Type / constraints | Notes |
|---|---|---|
| `filter.type` | enum (see §0) | `urn:entity:brand`, `urn:heatmap`, `urn:demographics`, `urn:tag` |
| `signal.interests.entities` | array of UUID (comma-sep) | seed brand(s) |
| `signal.interests.entities.weight` | number ≥0 or `very_low/low/mid/medium/high/very_high` | |
| `signal.interests.tags` | array of tag IDs (GET: comma-sep). Weighted objects only via POST, which isn't available to us | |
| `operator.signal.interests.tags` | `union`/`intersection` | |
| `signal.interests.tags.weight` | number or weight string | |
| `signal.demographics.age` | enum: `24_and_younger, 25_to_29, 30_to_34, 35_to_44, 45_to_54, 55_and_older`. The live OpenAPI **also** lists `35_and_younger, 36_to_55` | comma-sep list |
| `signal.demographics.gender` | `male` / `female` | |
| `signal.demographics.audiences` | array of audience IDs (from `/v2/audiences`) | |
| `signal.demographics.{age,gender,audiences}.weight` | number or weight string | |
| `signal.location` | WKT POINT/POLYGON or locality UUID (lon first) | |
| `signal.location.query` | string, fuzzy locality name. **400** if nothing matches | |
| `signal.location.radius` | int meters ≤ 800000 (not recommended) | |
| `signal.location.weight` | number or weight string | |
| `filter.tags` | comma-sep tag IDs | |
| `operator.filter.tags` | `union` (default) / `intersection` | |
| `filter.exclude.tags` + `operator.exclude.tags` (also spelled `operator.filter.exclude.tags`) | | spelling differs between pages (**UNVERIFIED**) |
| `filter.results.entities` | comma-sep entity IDs | restricts results to these IDs, which is how you get "affinity of B given seed A" |
| `filter.results.entities.query` | string (GET: one name) | |
| `filter.results.tags` | array of tag IDs | |
| `filter.exclude.entities` | comma-sep IDs | |
| `filter.popularity.min` / `.max` | number 0..1 | |
| `filter.parents.types` | documented enum is audience types (`urn:audience:*`). The taste-analysis example passes `urn:entity:movie, urn:entity:tv_show` | inconsistent, **UNVERIFIED** |
| `filter.tag.types` | comma-sep tag types (for `urn:tag`) | listed in the GitHub reference, **missing** from the live insights OpenAPI |
| `filter.location`, `filter.location.query`, `filter.location.radius` (int **meters**; default pads the locality by min(10% diameter, 2414 m); `0` = strict; max 800000) | | entity-type guide: **Destination and Place only** (plus heatmap) |
| `filter.geocode.*`, `filter.location.geohash` | | Destination/Place only |
| `bias.trends` | `off, very_low, low, mid, medium (default), high, very_high` | |
| `bias.content_based` | 0..1, default 0.5 | |
| `diversify.by` / `diversify.take` | `properties.geocode.city / metro`, or `subtype` (urn:tag only) | |
| `backfill.cross_domain.take` (1..20, default 20), `backfill.content_based.take` (1..10, default 10) | | **backfill**: results can be padded with cross-domain or content-based items when signal is thin, so don't treat every result as a "real" co-purchase signal |
| `feature.explainability` | boolean, default false | see §3.3 |
| `output.heatmap.boundary` | string: default geohashes; also city/neighborhood (example value `urn:entity:locality`; description of `heatmap.dimensions` mentions `urn:geohash`) | |
| `heatmap.dimensions` | `quality, popularity, hotel_class, price_level` → adds `<dim>_affinity_rank` / `<dim>_affinity` | place-oriented, not needed |
| `sort_by` | `affinity` (default) / `distance` / `rating` / `quality` | |
| `take` 1..50 (default 20), `page`, `offset` | | |

Parameters valid for **`urn:entity:brand`** (Entity Type Parameter Guide): `bias.trends, filter.exclude.entities, filter.exclude.tags, operator.exclude.tags, filter.external.exists, operator.filter.external.exists, filter.parents.types, filter.popularity.min/max, filter.results.entities(.query), filter.tags, operator.filter.tags, signal.demographics.age/gender/audiences(.weight), signal.interests.entities, signal.interests.tags, offset, take`.

**Location filters do NOT apply to brands.** `filter.location*`, `filter.geocode.*` and `signal.location*` are not in the brand list. Because invalid parameters are ignored silently, a "brands popular in Nashville" query either ignores the location or returns empty. Contradiction: the location-use-case page lists `urn:entity:brand` as an example with `signal.location.query`, and an older recipe was "popular brands inside Paris" (since rewritten to *places*). **UNVERIFIED**, test live. For geography use **`urn:heatmap` with a brand as signal** (documented: MUJI and Jacquemus recipes).

### 3.2 Entity results (`filter.type=urn:entity:*`)

Documented shape (basic-insights-use-case, truncated, plus recipes for `query.affinity`):

```json
{
  "success": true,
  "results": {
    "entities": [
      {
        "name": "Everything Everywhere All at Once",
        "entity_id": "F0D354AA-BA7E-49D2-8ABA-9A8250F5C852",
        "type": "urn:entity",
        "subtype": "urn:entity:movie",
        "properties": {
          "release_year": 2022,
          "description": "…",
          "image": { "url": "https://staging.images.qloo.com/i/F0D354AA-…-420x-outside.jpg" },
          "akas": [{ "value": "…", "languages": ["hu"] }],
          "short_descriptions": [{ "value": "…", "languages": ["cs"] }],
          "websites": ["https://…"]
        },
        "popularity": 0.9984116946335868,
        "tags": [
          { "id": "urn:tag:keyword:media:multiverse", "name": "Multiverse", "type": "urn:tag:keyword:media" }
        ],
        "query": {
          "affinity": 0.97,
          "measurements": { "audience_growth": -0.04072975141723856 }
        },
        "disambiguation": "2022, Daniel Scheinert, Daniel Kwan",
        "external": { "wikidata": [{ "id": "q83808444" }], "instagram": [{ "id": "…" }] }
      }
    ]
  },
  "duration": 34
}
```

- `query.affinity` comes from the recipes (Balthazar, il Buco). With a location filter there is also `query.distance` (meters). Without a signal both are `null`.
- Brand-specific `properties` (Schema & Taxonomy page) can include `description, official_site, founded_year, inception, headquartered, headquarters_address, direct_owner, parent_company, owned_by, industries[], products[], subsidiaries[], brand_type[], industry_categories[], core_values[], brand_personality[], brand_adjectives[], lifestyles[], use_occasions[], target_audience[], psychographic_segments[], customer_personas[], key_influencer_types[], aspirational_outcomes[], celebrity_spokesperson[], price_tier[], business_model[], target_markets[], fashion_style[], competitive_set[], complementary_brands[], sustainability_initiatives[], audience_growth`. Caveat: that page shows these fields **flattened at the top level**, with `affinity` and `url` top-level too. That contradicts the raw API nesting (`properties.*`, `query.affinity`, `properties.image.url`). Treat the taxonomy page as a field catalogue, not a wire format. **UNVERIFIED** where `competitive_set` etc. live on the wire. `competitive_set` and `complementary_brands` would be very useful for Tea Rose ("relatedness of goods").
- One recipe (personalize-by-age-gender…) shows `"type": "urn:entity:artist"` and `properties.affinity`. That conflicts with every other example and looks like a docs error. Parse defensively: prefer `query.affinity`, fall back to `properties.affinity`.
- Root-level `query` object (sibling of `results`): echoes resolved inputs, e.g. `query.localities.filter{entity_id,name,subtype,location{lat,lng},popularity,disambiguation}`, `query.locality.signal`, `query.entities.exclude`, `query.explainability`. The heatmap example has `location.lat = -73.94`, `lng = 40.66`, which is **swapped** (a docs bug, or the wire really is swapped: UNVERIFIED).
- Brand tags: `urn:tag:genre:brand:<category>[:<sub>…]` (documented top-level: automotive, electronics, entertainment, fashion, **food_and_beverage**, games, health_and_beauty, mobile_app, retail, software, sports_organization, website, **wine_and_spirits**). Plus `urn:tag:adjective:qloo:*` and `urn:tag:wikipedia_category:wikidata:*`. The basic-insights page uses `urn:tag:genre:brand:food_beverage` instead of `food_and_beverage` (**UNVERIFIED**, resolve via `/v2/tags`). **No pet-supply brand tag appears in the docs**. Fixtures use synthetic `urn:tag:genre:brand:pet_supplies[:dog_toys|:pet_food]`.

Fixtures: `insights_brand_seed_jack_daniels.json`, `insights_brand_seed_jack_daniels_filter_pet_tags.json`, `empty_results.json`.

### 3.3 `feature.explainability=true`

Documented **only in prose** (deep dive / parameter reference):

- Per result: `query.explainability` shows which input entities (from `signal.interests.entities`) contributed, with normalized scores 0..1. Entities scoring ≥ 0.1 are always included, and lower ones may be omitted.
- Aggregate: the top-level `query.explainability` gives the average influence of each input entity across top-N subsets (top 3, 5, 10, all).
- If it cannot be computed, `query.explainability.warning` is set and results are returned normally.

Fixture shape (inner keys are **UNVERIFIED** guesses):

```json
"query": { "affinity": 0.971,
  "explainability": { "signal.interests.entities": [ { "entity_id": "<seed>", "score": 1.0 } ] } }
...
"query": { "explainability": { "signal.interests.entities": [
  { "entity_id": "<seed>", "average_score": { "top_3": 1.0, "top_5": 1.0, "top_10": 1.0, "all": 1.0 } } ] } }
```

With a single seed entity, explainability carries no information. It only matters with 2+ seeds (e.g. senior mark plus a category tag).

### 3.4 Heatmap (`filter.type=urn:heatmap`)

Required: a location (`filter.location` WKT/locality UUID **or** `filter.location.query`) **and** a signal (`signal.interests.entities` or `signal.interests.tags`). Optional: `bias.trends`, `output.heatmap.boundary`, `signal.demographics.*`.

```json
{
  "success": true,
  "results": {
    "heatmap": [
      {
        "location": { "latitude": 40.591736, "longitude": -73.756714, "geohash": "dr5wct" },
        "query": { "affinity": 1, "affinity_rank": 0.9976498237367802, "popularity": 0.9717472118959107 }
      }
    ]
  },
  "query": { "localities": { "filter": { "entity_id": "81E61924-…", "name": "New York", "subtype": "urn:entity:locality",
    "location": { "lat": -73.938, "lng": 40.663 }, "popularity": 1, "disambiguation": "New York, New York, United States of America" } } },
  "duration": 75
}
```

- Meaning (docs/heatmaps): `affinity_rank` measures how the entity performs **vs. itself** across the area. `popularity` is the percentile of signal density within the geohash vs. other entities there. `affinity` compares the entity to other entities in that location, locally and globally. Results are sorted by `affinity` descending, which looks like a percent rank.
- The MUJI recipe example has `query` with only `affinity` and `popularity` (no `affinity_rank`), so treat `affinity_rank` as optional.
- Geohash length 6–7 in examples. The grid resolution for a **country-sized** area, and whether a country polygon or `filter.location.query=United States` is accepted at all, is **UNVERIFIED**. A cell count cap is undocumented.
- Fixtures: `insights_heatmap_{in_n_out,smashburger,jack_daniels}.json` (40 points each, one per US metro, precision-5 geohashes, US bounding-box polygon as `filter.location`).

### 3.5 Demographics (`filter.type=urn:demographics`)

Required: `signal.interests.entities` and/or `signal.interests.tags`. Both together give one block per input.

```json
{
  "success": true,
  "results": {
    "demographics": [
      { "entity_id": "urn:tag:genre:media:action",
        "query": { "age": { "24_and_younger": 0, "25_to_29": 0.43, "30_to_34": 0.23, "35_to_44": -0.02, "45_to_54": -0.28, "55_and_older": -0.17 },
                   "gender": { "male": 0.08, "female": -0.08 } } },
      { "entity_id": "B8BEE72B-B321-481F-B81A-A44881D094D6", "query": { "age": { "…": 0 }, "gender": { "male": 0.16, "female": -0.16 } } }
    ]
  },
  "duration": 77
}
```

- `entity_id` holds the tag URN when the input was a tag. No `name` field, so map IDs back yourself.
- Age keys are exactly `24_and_younger, 25_to_29, 30_to_34, 35_to_44, 45_to_54, 55_and_older`. Gender keys are only `male`, `female`. No geographic or income breakdown.
- Fixtures: `insights_demographics_{jack_daniels,coach,nike}.json`.

### 3.6 Taste analysis (`filter.type=urn:tag`)

Signal: `signal.interests.entities` / `signal.interests.tags` / `signal.demographics.audiences` / `signal.location(.query)`. Optional `filter.tag.types`, `filter.parents.types`, `diversify.by=subtype`.

Two documented shapes, which **contradict** each other:

```json
// reference/taste-analysis (no signal, so empty query)
{ "tag_id": "urn:tag:keyword:media:brady_bunch", "name": "Brady Bunch",
  "types": ["urn:entity:tv_show", "urn:entity:movie", "…"], "subtype": "urn:tag:keyword:media",
  "tag_value": "urn:tag:keyword:media:brady_bunch", "query": {} }
// recipe get-the-taste-tags-that-describe-an-entitys-audience
{ "tag_id": "urn:tag:ambience:qloo:intimate", "name": "Intimate", "types": ["urn:tag"],
  "subtype": "urn:tag:ambience:qloo", "query": { "affinity": 0.992 } }
```

Wrapper: `{"success": true, "results": {"tags": [...]}, "duration": 25}`. The fixture (`insights_tag_seed_jack_daniels.json`) uses the union of both. Whether `types` lists entity types or `["urn:tag"]` is **UNVERIFIED**.

## 4. `GET /v2/tags`: tag search

| Param | Type / constraints |
|---|---|
| `filter.query` | string, partial match on tag name |
| `feature.typo_tolerance` | bool, default false |
| `feature.semantic_search` | bool, default false (beta, use with `filter.query`) |
| `filter.tag.types` | array of tag types (exact match, see `/v2/tags/types`) |
| `filter.parents.types` | documented enum = `urn:audience:*` (likely a copy-paste error; probably entity types) **UNVERIFIED** |
| `filter.results.tags` | array of tag IDs |
| `filter.popularity.min` / `.max` | 0..1 |
| `page` ≥1 (≤100), `take` 1..50 (default 20) |

Response (recipe `find-a-tag-id-by-keyword`, OpenAPI: `{duration, success, results{tags[]}}`):

```json
{ "success": true,
  "results": { "tags": [
    { "id": "urn:tag:amenity:place:rooftop_bar", "name": "Rooftop Bar", "type": "urn:tag:amenity:place",
      "parents": [ { "type": "urn:entity:place" } ], "popularity": 0.95 } ] } }
```

**Naming trap:** tag search returns **`id`** + `type`, while insights `urn:tag` and compare return **`tag_id`** + `subtype`, and tags embedded in entities use `id`/`name`/`type`. The guide says there is no static tag list, so always search.
Fixtures: `tags_search_{dog_toys,pet_supplies,whiskey}.json`.

## 5. `GET /v2/tags/types`

Params: `filter.parents.types` (same audience enum as above), `page`, `take` 1..50. **No response schema or example documented** (UNVERIFIED). Expect `results` with a list of tag-type URNs per entity type. No fixture yet.

## 6. `GET /v2/audiences`, `/v2/audiences/types`

`/v2/audiences`: `filter.parents.types` (enum `urn:audience:communities, global_issues, hobbies_and_interests, investing_interests, leisure, life_stage, lifestyle_preferences_beliefs, political_preferences, professional_area, spending_habits`), `filter.results.audiences`, `filter.audience.types`, `filter.query`, `filter.popularity.min/max`, `page`, `take` 1..50. Response schema: `{success, results{entities[], duration}}`, with item fields **UNVERIFIED**. Note `/v2/audiences` is not in the docs MCP `list-endpoints` output. Tea Rose doesn't need audiences for v1.

## 7. `GET /v2/analysis/compare`

| Param | Type | Notes |
|---|---|---|
| `a.signal.interests.entities` | array, **required** | group A |
| `b.signal.interests.entities` | array, **required** | group B |
| (any insights param with `a.` / `b.` prefix) | | per recipe: "each side accepts the full insights parameter set" (**UNVERIFIED** which ones) |
| `filter.type` | array, enum as insights | |
| `filter.subtype` | `urn:tag:occupation` / `urn:tag:genre` | |
| `model` | `descriptive` / `predictive` | semantics undocumented |
| `filter.entities.query`, `filter.location.query`, `filter.location.radius` (default 15000, max 800000), `filter.exclude.location.query/radius` | | |
| `page` 1..100, `take` 1..50 (default 20), `offset` | | |

Response (recipe `compare-two-brands-audiences`): "always returns **tags, never entities**". "Top-level keys are `duration` and `results` only, with **no `success` field**."

```json
{ "duration": 0.42,
  "results": { "tags": [
    { "tag_id": "urn:tag:style:qloo:athletic", "name": "Athletic", "type": "urn:tag",
      "subtype": "urn:tag:style:qloo", "popularity": 0.91, "query": { "score": 0.729 } } ] } }
```

`query.score` means "how strongly both audiences index for it". Its range and whether it is symmetric (A,B vs B,A) are **UNVERIFIED**. The OpenAPI 200 schema says `results` is an *array of entities*, which is a generic copy-paste and contradicts the recipe; trust the recipe.
Fixtures: `compare_jack_daniels_vs_barkbox.json`, `compare_adidas_vs_thom_browne.json`.

## 8. Other endpoints (not used)

`GET /` (API info: `version, title, description, contact`), `GET /v2/trending` (Get Trending Data), `get-trends-category`, `get-trends-entity`. The harness exposes `qloo_trends` for 1–5 entities plus a date range.

## 9. Error and empty behaviour (for the client)

| Situation | Expected | Source / status |
|---|---|---|
| wrong base URL with hackathon key | 401 | documented. Body fields **UNVERIFIED** (`error_401_wrong_base_url.json` uses `{code, reason, message}`) |
| missing `X-Api-Key` | 401 `"No API key found in request"` | documented |
| unsupported `filter.type` | 403 `"You do not have permission to access urn:entity:..."` | documented |
| POST to `/v2/insights` | `"No path matching request parameters"` / 404 | documented |
| bad tag or audience IDs | `"at least one valid signal or filter is required"` | status **UNVERIFIED** |
| `*.location.query` or `filter.exclude.entities.query` resolves nothing | **400** | documented |
| parameter not valid for type / no data | **200 with `results.entities: []`** | documented (`empty_results.json`) |
| `/search` with no hits | 200 `[]` or 404 "No results" | **UNVERIFIED** |
| rate limit | 429, no headers documented | **UNVERIFIED** |

---

## UNVERIFIED items (summary)

1. Inner layout of `query.explainability` (per-result and aggregate). Only prose is documented.
2. `/search` zero hits: 200 with an empty array or 404. Also whether `success`/`duration` appear on `/search`.
3. 401/403/429 response bodies. Only `{code, reason, message}` is documented, for other codes.
4. HTTP status for "at least one valid signal or filter is required".
5. Rate-limit headers (none documented) and the actual hackathon quota numbers.
6. `duration` unit (ms vs s).
7. `urn:entity:videogame` vs `urn:entity:video_game`, and whether `urn:entity:destination` is valid.
8. Whether `signal.location*` / `filter.location*` have any effect for `filter.type=urn:entity:brand`.
9. Heatmap at national scale: accepted location forms (country polygon, `filter.location.query=United States`), geohash precision, number of cells, whether `affinity_rank` is always present.
10. Heatmap `query.localities.filter.location` lat/lng swap.
11. `urn:tag` result `types` content (entity types vs `["urn:tag"]`) and presence of `tag_value`.
12. Compare: `query.score` range and symmetry, meaning of `model`, and which `a.`/`b.` params are accepted.
13. Where brand fields (`competitive_set`, `complementary_brands`, `industries`, `price_tier` …) live on the wire (under `properties`?) and how often they are populated.
14. Whether `properties.affinity` (one recipe) ever appears instead of `query.affinity`.
15. Brand tag IDs: pet-supply / dog-toy / whiskey sub-tags (all synthetic in the fixtures), and `food_beverage` vs `food_and_beverage`.
16. `filter.parents.types` accepted values (audience enum vs entity types) on `/v2/tags` and `urn:tag`.
17. `operator.exclude.tags` vs `operator.filter.exclude.tags` spelling.
18. `/v2/tags/types` and `/v2/audiences` response shapes.
19. Paging metadata (total count / has-more). None documented.
20. `/search` `take` maximum (<200 per the live spec vs ≤100 on the GitHub page).

## Open questions for Monday's live test

Run each once and record **shapes only** (no values) into the fixtures. Keep raw responses out of git.

1. `GET /search?query=Jack Daniel's&types=urn:entity:brand&take=5`: wrapper keys, `types` vs `type`, which `properties` brand fields exist, and whether `tags` are included.
2. `GET /search?query=Bad Spaniels&types=urn:entity:brand`: 200 `[]` or 404? Also try `VIP Products`.
3. `GET /v2/insights?filter.type=urn:entity:brand&signal.interests.entities=<JD>&take=50&feature.explainability=true`: exact `query.explainability` layout, both per result and at the root. Repeat with **two** seeds to see non-trivial scores.
4. The same with `filter.results.entities=<BarkBox>`: does it return BarkBox with an affinity even when it's far down the list? (This is the cleanest "do they share purchasers" number.)
5. `GET /v2/tags?filter.query=dog toys` and `pet supplies` / `whiskey`: real tag IDs, and whether brand-genre pet tags exist. Try `feature.semantic_search=true`.
6. `filter.type=urn:entity:brand&filter.tags=<pet tag>&signal.interests.entities=<JD>`: does `filter.tags` constrain brands as expected? Is `operator.filter.tags` needed?
7. Brand plus `signal.location.query=Nashville` vs no location: do results change? (Settles "location filters don't apply to brands".)
8. `filter.type=urn:heatmap&signal.interests.entities=<In-N-Out>` with (a) `filter.location.query=United States`, (b) a US WKT polygon, (c) `filter.location.query=California`: which work, how many cells, geohash precision, `affinity_rank` presence, and root `query.localities` lat/lng order.
9. `filter.type=urn:demographics&signal.interests.entities=<JD>,<Coach>`: one block per entity? Any `name` field?
10. `filter.type=urn:tag&signal.interests.entities=<JD>&take=20`: `types` content, `tag_value`, and `query.affinity` presence. Try `filter.tag.types=urn:tag:adjective:qloo` and `diversify.by=subtype`.
11. `/v2/analysis/compare?a.signal.interests.entities=<JD>&b.signal.interests.entities=<BarkBox>`: confirm no `success`, the `query.score` range, and A/B symmetry (swap them). Also try `model=predictive`.
12. Wrong base URL (`api.qloo.com`), missing header, `filter.type=urn:entity:music`, and a garbage tag: record status codes and body keys, and check every response for `X-RateLimit-*` / `Retry-After` headers.
13. `duration` unit: compare it with measured latency.
14. `filter.type=urn:entity:videogame` vs `urn:entity:video_game`: which returns 403 (low priority).
15. `take=50&page=2`: any paging metadata? Is `take=51` clamped or rejected?
