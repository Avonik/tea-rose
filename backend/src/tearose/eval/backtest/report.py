"""Step 4, `report`: mapping.csv + scores.json -> results/backtest_<YYYYMMDD>[_v<N>].{md,json}.

Harness version: run 1 (v1, the pre-registered rules) wrote backtest_<date>.md/.json and is kept
as the record; harness v2 wrote backtest_<date>_v2.md/.json and added the "Deviations from
pre-registration" section; harness v3 writes backtest_<date>_v3.md/.json, adds a dated v3
paragraph (identification by the product's model-driven resolver), a "Resolver" header line and
a per-case note where the agent's pick differs from the name rule's pick. Two Qloo signals are
reported side by side for every subset: the symmetric rank percentile (censored ranks excluded)
and the symmetric affinity ratio.

Metric formulas (stats.py has the implementations):

- Label code (combined relatedness / channels-purchasers label): favors_defendant = 0,
  neutral = 1, favors_plaintiff = 2.
- (a) Spearman rho(symmetric_percentile, label code), average ranks for ties; 95% CI from a
  2000-resample percentile bootstrap over cases (seed fixed in stats.py).
- (b) AUC(symmetric_percentile; positive = favors_plaintiff, negative = the rest), Mann-Whitney
  with ties counted one half; same bootstrap for the CI.
- (c) Baselines on the SAME cases: same_category (1/0) and popularity product
  (senior_popularity x junior_popularity; cases with a missing popularity are dropped from that
  baseline only, and its n is reported).
- (d) Fame: AUC(breadth_score; positive = fame_found yes, negative = no); baseline AUC of the
  senior's popularity.
- (e) Per-case residual = label_code / 2 - symmetric_percentile (both on 0..1); sorted by
  |residual|, largest first (cases without a rank percentile use the affinity-ratio residual).
- Second Qloo signal (harness v2): symmetric_affinity_ratio, scored with the same Spearman /
  AUC formulas; each signal's n counts the cases where that signal exists.
- Primary set: include_relatedness = yes, overlap scored, no proxy on either side. Proxy cases,
  dispute-deduplicated cases (latest year per dispute) and per-factor labels are secondary.
Any metric with n < 15 is flagged as underpowered.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tearose.eval.backtest import HARNESS_VERSION, stats
from tearose.eval.backtest.common import FRONTEND_JSON, read_json, write_json
from tearose.eval.backtest.prepare import DECIDED, LABEL_CODE

MIN_N = 15

DEVIATIONS_V2 = [
    "On 2026-10-25, after run 1 (`backtest_20261025.md`, kept unchanged as the record of the "
    "pre-registered harness), three rules were changed. Each fixes a measurement error that was "
    "visible without looking at the labels:",
    "",
    "1. **Universe rule.** Pre-registered: a brand's category universe was its top-5 insights "
    "tags (`filter.tag.types=urn:tag:genre:brand`). Those tags describe what the brand's "
    '*audience* likes, not what the brand is (a sneaker brand came out as "Food & Beverage"). '
    "Now: the brand's own `urn:tag:genre:brand` tags from its /search result, most specific "
    "nodes only (ancestors dropped, depth >= 2 preferred, up to 3). The insights-tags rule "
    "remains only as the fallback for a brand without own brand-genre tags.",
    "2. **Censored ranks.** Pre-registered: a target not found among the first 150 brands "
    "counted as rank 151, i.e. percentile 0. Now such a rank is reported as censored (no rank "
    "percentile), and the target's affinity is looked up directly "
    "(`filter.results.entities=<target>`, same seeds, filter and type). This gives a second "
    "signal, the affinity ratio = target affinity / affinity of the top-ranked brand (0..1).",
    '3. **Taxonomy synonym.** "test preparation" / "educational materials" mapped to '
    "`academic` (universities); they now map to `entertainment:publisher` (partial).",
    "",
    "Labels (`cases_candidates.csv`) and `mapping.csv` are unchanged (same mapping sha256). "
    "Run 1 is kept as the record; the v2 numbers are post-hoc and should be read as such.",
]

DEVIATIONS_V3 = [
    "**Harness v3 (2026-10-25): identification by the product's resolver.** Up to v2 each "
    "brand was identified by a code-only name rule (normalised exact or strict fuzzy name "
    "match on /search, else a miss). That rule rejected matches the shipped product resolves "
    'correctly ("Hershey\'s" vs "The Hershey Company", "Chase" vs "Chase Bank", '
    '"Trek" vs "Trek Bicycle Corporation", "New York Stock Exchange" vs "NYSE"), '
    "so v2 measured a stricter pipeline than the one shipped. Now `resolve` runs the product's "
    "model-driven resolve node (`agent/nodes/resolve.py`) on the frozen mapping (queries, goods "
    "phrases, entity-type hints, case name and year; no court labels or factor columns in the "
    "input). The pick, the name-rule guardrail result, the proxy and the universe are recorded "
    "per case in `resolved.json`, together with the name rule's pick for comparison. Scoring "
    "is unchanged and stays in code. Labels (`cases_candidates.csv`) and `mapping.csv` are "
    "unchanged; the v1 and v2 reports are kept.",
]


def _fmt(x: float | None, nd: int = 2) -> str:
    return "n/a" if x is None else f"{x:.{nd}f}"


def _ci(lo: float | None, hi: float | None) -> str:
    return "n/a" if lo is None or hi is None else f"{lo:.2f} to {hi:.2f}"


def _rho_stat(pairs: list[tuple[float, float]]) -> float | None:
    return stats.spearman([p[0] for p in pairs], [p[1] for p in pairs])


def _auc_stat(pairs: list[tuple[float, float]]) -> float | None:
    return stats.auc([p[0] for p in pairs], [p[1] >= 2 for p in pairs])


def _with_ci(
    pairs: list[tuple[float, float]], fn: Callable[[list[tuple[float, float]]], float | None]
) -> dict[str, Any]:
    value = fn(pairs)
    lo, hi, valid = stats.bootstrap_ci(pairs, fn) if value is not None else (None, None, 0)
    return {"value": value, "ci": [lo, hi], "valid_resamples": valid}


def score_vs_label(
    rows: list[dict[str, Any]], score: Callable[[dict[str, Any]], float | None], label_key: str
) -> dict[str, Any]:
    """Spearman + AUC (with bootstrap CIs) of one score against one label column."""
    pairs = [
        (float(s), float(LABEL_CODE[r[label_key]]))
        for r in rows
        if (s := score(r)) is not None and r[label_key] in LABEL_CODE
    ]
    pos = sum(1 for p in pairs if p[1] >= 2)
    return {
        "n": len(pairs),
        "n_favors_plaintiff": pos,
        "n_other": len(pairs) - pos,
        "spearman": _with_ci(pairs, _rho_stat),
        "auc": _with_ci(pairs, _auc_stat),
        "underpowered": len(pairs) < MIN_N,
    }


def _sym(r: dict[str, Any]) -> float | None:
    return r["score"]["symmetric_percentile"] if r.get("score") else None


def _ratio(r: dict[str, Any]) -> float | None:
    return (r.get("score") or {}).get("symmetric_affinity_ratio")


def _has_signal(r: dict[str, Any]) -> bool:
    return _sym(r) is not None or _ratio(r) is not None


def _samecat(r: dict[str, Any]) -> float | None:
    return 1.0 if r["same_category"] == "yes" else 0.0


def _popprod(r: dict[str, Any]) -> float | None:
    s = r.get("score") or {}
    a, b = s.get("senior_popularity"), s.get("junior_popularity")
    return a * b if a is not None and b is not None else None


def relatedness_block(rows: list[dict[str, Any]], label_key: str) -> dict[str, Any]:
    return {
        "qloo": score_vs_label(rows, _sym, label_key),
        "qloo_ratio": score_vs_label(rows, _ratio, label_key),
        "same_category": score_vs_label(rows, _samecat, label_key),
        "popularity_product": score_vs_label(rows, _popprod, label_key),
    }


def fame_block(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def auc_for(key: str) -> dict[str, Any]:
        pairs = [
            (float(r["score"][key]), 2.0 if r["label_fame"] == "yes" else 0.0)
            for r in rows
            if r.get("score") and r["score"].get(key) is not None
        ]
        pos = sum(1 for p in pairs if p[1] >= 2)
        return {
            "n": len(pairs),
            "n_yes": pos,
            "n_no": len(pairs) - pos,
            "auc": _with_ci(pairs, _auc_stat),
            "underpowered": len(pairs) < MIN_N or min(pos, len(pairs) - pos) < 3,
        }

    return {"breadth": auc_for("breadth_score"), "popularity": auc_for("senior_popularity")}


def dedupe_by_dispute(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the latest-year row per dispute_id (ties: the later row in the mapping)."""
    best: dict[str, dict[str, Any]] = {}
    for r in rows:
        cur = best.get(r["dispute_id"])
        if cur is None or int(r["year"] or 0) >= int(cur["year"] or 0):
            best[r["dispute_id"]] = r
    return [r for r in rows if best[r["dispute_id"]] is r]


def pick_note(score: dict[str, Any]) -> str | None:
    """'senior: Agent pick (rule: Rule pick)' for each side where the agent's pick differs."""
    cmp = score.get("pick_vs_rule") or {}
    parts = [
        f"{side}: {c.get('agent') or 'miss'} (rule: {c.get('rule') or 'miss'})"
        for side, c in cmp.items()
        if c.get("differs")
    ]
    return "; ".join(parts) or None


def resolver_line(res: dict[str, Any]) -> str:
    if res.get("resolver") == "agent":
        return (
            f"Resolver: **agent** (the product's resolve node, model `{res.get('model')}`); the "
            "name rule's pick is computed alongside, differences in the per-case table."
        )
    return "Resolver: **rule** (code-only name rule, no model)."


def _main_residual(c: dict[str, Any]) -> float:
    r = c["residual"] if c["residual"] is not None else c.get("residual_ratio")
    return float(r) if r is not None else 0.0


def build(mapping: list[dict[str, str]], scores: dict[str, Any]) -> dict[str, Any]:
    by_id = {c["case_id"]: c for c in scores.get("cases", [])}
    rows: list[dict[str, Any]] = [{**m, "score": by_id.get(m["case_id"])} for m in mapping]

    # --- exclusions for the primary relatedness metric --------------------------------
    excluded: dict[str, int] = {}

    def bump(reason: str) -> None:
        excluded[reason] = excluded.get(reason, 0) + 1

    primary: list[dict[str, Any]] = []
    with_proxy: list[dict[str, Any]] = []
    for r in rows:
        if r["include_relatedness"] != "yes":
            bump(r["relatedness_exclusion"] or "no_label")
            continue
        s = r["score"]
        if s is None:
            bump("not_resolved (not in scores.json)")
        elif s["status"] == "unresolved":
            bump("unresolved")
        elif not _has_signal(r):
            bump("no_overlap (no direction computable)")
        else:
            with_proxy.append(r)
            if s["used_proxy"]:
                bump("proxy (reported in the secondary 'with proxies' line)")
            else:
                primary.append(r)

    def factor_rows(col: str) -> list[dict[str, Any]]:
        return [
            {**r, "factor_label": r[col]}
            for r in rows
            if r[col] in DECIDED and r["score"] and _has_signal(r) and not r["score"]["used_proxy"]
        ]  # fmt: skip

    fame_rows = [r for r in rows if r["include_fame"] == "yes"]
    fame_missing = sum(1 for r in fame_rows if (r["score"] or {}).get("breadth_score") is None)

    per_case = []
    for r in with_proxy:
        pct, ratio = _sym(r), _ratio(r)
        code = LABEL_CODE[r["label_relatedness"]]
        per_case.append(
            {
                "case_id": r["case_id"],
                "case_name": r["case_name"],
                "year": r["year"],
                "senior": r["senior_query"],
                "junior": r["junior_query"],
                "label": r["label_relatedness"],
                "symmetric_percentile": pct,
                "residual": None if pct is None else code / 2 - pct,
                "symmetric_affinity_ratio": ratio,
                "residual_ratio": None if ratio is None else code / 2 - ratio,
                "same_category": r["same_category"],
                "popularity_product": _popprod(r),
                "used_proxy": r["score"]["used_proxy"],
                "pick_vs_rule": pick_note(r["score"]),
            }
        )
    per_case.sort(key=lambda c: -abs(_main_residual(c)))

    return {
        "generated": dt.date.today().isoformat(),
        "harness_version": scores.get("harness_version", 1),
        "resolver": scores.get("resolver", "rule"),
        "model": scores.get("model"),
        "qloo_mode": scores.get("qloo_mode"),
        "mapping_sha256": scores.get("mapping_sha256"),
        "comparator_rule": scores.get("comparator_rule"),
        "cases_total": len(rows),
        "relatedness": {
            "primary": relatedness_block(primary, "label_relatedness"),
            "with_proxies": relatedness_block(with_proxy, "label_relatedness"),
            "dedup_by_dispute": relatedness_block(dedupe_by_dispute(primary), "label_relatedness"),
            "relatedness_factor_only": relatedness_block(
                factor_rows("factor_relatedness"), "factor_label"
            ),
            "channels_factor_only": relatedness_block(
                factor_rows("factor_channels"), "factor_label"
            ),
            "excluded": excluded,
        },
        "fame": {**fame_block(fame_rows), "candidates": len(fame_rows), "missing": fame_missing},
        "per_case": per_case,
    }


# --------------------------------------------------------------------------------------
# Markdown
# --------------------------------------------------------------------------------------


def _metric_cells(b: dict[str, Any], kind: str) -> str:
    m = b[kind]
    return f"{_fmt(m['value'])} ({_ci(*m['ci'])})"


def headline(res: dict[str, Any]) -> str:
    p = res["relatedness"]["primary"]
    q, sc, qr = p["qloo"], p["same_category"], p.get("qloo_ratio")
    n = q["n"]
    if n == 0 and qr is not None and qr["n"]:
        text = (
            f"No decided case has an uncensored rank percentile; on "
            f"{qr['n']} cases Qloo's affinity ratio correlates with the courts' "
            f"relatedness/purchaser findings at rho = {_fmt(qr['spearman']['value'])} "
            f"(95% CI {_ci(*qr['spearman']['ci'])})."
        )
        if qr["underpowered"]:
            text += f" With n = {qr['n']} < {MIN_N} this metric is underpowered."
        return text
    if n == 0:
        return (
            "No decided case could be scored, so the back-test has no result yet "
            "(see exclusions below)."
        )
    rho, ci = q["spearman"]["value"], q["spearman"]["ci"]
    text = (
        f"On {n} decided cases, Qloo's symmetric overlap percentile correlates with the courts' "
        f"relatedness/purchaser findings at rho = {_fmt(rho)} (95% CI {_ci(*ci)}) versus "
        f"{_fmt(sc['spearman']['value'])} for a same-category heuristic."
    )
    if q["underpowered"]:
        text += f" With n = {n} < {MIN_N} this metric is underpowered; read it as anecdotal."
    if qr is not None and qr["n"]:
        text += (
            f" The affinity ratio (second Qloo signal, n = {qr['n']}) gives rho = "
            f"{_fmt(qr['spearman']['value'])} (95% CI {_ci(*qr['spearman']['ci'])})."
        )
    return text


def _block_table(title: str, b: dict[str, Any]) -> list[str]:
    lines = [
        f"#### {title}",
        "",
        "| signal | n | Spearman rho (95% CI) | AUC favors_plaintiff (95% CI) | note |",
        "|---|---:|---|---|---|",
    ]
    for key, label in (
        ("qloo", "Qloo symmetric rank percentile (censored ranks excluded)"),
        ("qloo_ratio", "Qloo symmetric affinity ratio"),
        ("same_category", "Baseline: same-category heuristic"),
        ("popularity_product", "Baseline: popularity product"),
    ):
        if key not in b:  # reports built before harness v2
            continue
        m = b[key]
        note = "underpowered (n < 15)" if m["underpowered"] else ""
        if m["n"] and (m["n_favors_plaintiff"] == 0 or m["n_other"] == 0):
            note = (note + "; " if note else "") + "one label class only: AUC undefined"
        lines.append(
            f"| {label} | {m['n']} | {_metric_cells(m, 'spearman')} | "
            f"{_metric_cells(m, 'auc')} | {note} |"
        )
    return [*lines, ""]


def render_markdown(res: dict[str, Any]) -> str:
    rel = res["relatedness"]
    version = res.get("harness_version", 1)
    out = [
        f"# Tea Rose back-test, {res['generated']} (harness v{version})",
        "",
        f"Qloo mode: **{res['qloo_mode']}**. Harness version: **{version}**. Mapping sha256: "
        f"`{res['mapping_sha256']}`. Cases in mapping: {res['cases_total']}.",
        "",
        resolver_line(res),
        "",
    ]
    if version >= 2:
        out += ["## Deviations from pre-registration", "", *DEVIATIONS_V2, ""]
    if version >= 3:
        out += [*DEVIATIONS_V3, ""]
    if res["qloo_mode"] != "live":
        out += [
            "> **Fixture run.** These numbers come from synthetic fixtures and say nothing about "
            "Qloo. They only show that the harness runs end to end.",
            "",
        ]
    out += [
        "## Headline",
        "",
        headline(res),
        "",
        "## Relatedness / channels-purchasers",
        "",
        "Label code: favors_defendant = 0, neutral = 1, favors_plaintiff = 2 (combined label; "
        "disagreeing factors are 'mixed' and excluded).",
        "",
    ]
    out += _block_table("Primary (no proxy)", rel["primary"])
    out += _block_table("Secondary: including proxy cases", rel["with_proxies"])
    out += _block_table("Secondary: deduplicated by dispute (latest year)", rel["dedup_by_dispute"])
    out += _block_table(
        "Secondary: relatedness-of-goods label only", rel["relatedness_factor_only"]
    )
    out += _block_table("Secondary: channels/purchasers label only", rel["channels_factor_only"])

    fame = res["fame"]
    out += ["## Fame", "", "| signal | n (yes/no) | AUC fame_found yes (95% CI) | note |",
            "|---|---|---|---|"]  # fmt: skip
    for key, label in (("breadth", "Qloo breadth score"), ("popularity", "Baseline: popularity")):
        m = fame[key]
        note = "underpowered" if m["underpowered"] else ""
        out.append(
            f"| {label} | {m['n']} ({m['n_yes']}/{m['n_no']}) | "
            f"{_fmt(m['auc']['value'])} ({_ci(*m['auc']['ci'])}) | {note} |"
        )
    out += [
        "",
        f"{fame['candidates']} cases have a dilution fame finding; {fame['missing']} of them "
        "have no breadth score (senior not resolved or no demographics).",
        "",
        "## Per-case table (largest disagreements first)",
        "",
        "residual = label_code / 2 - signal (rank percentile; affinity ratio in the second "
        "residual column). Positive: the court found the goods "
        "more related than Qloo's overlap suggests; negative: Qloo overlap is higher than the "
        "finding.",
        "",
        "| case | year | senior / junior | label | rank pct | residual | affinity ratio | "
        "residual (ratio) | same cat | proxy | pick vs rule |",
        "|---|---|---|---|---:|---:|---:|---:|---|---|---|",
    ]
    for i, c in enumerate(res["per_case"]):
        flag = " **(failure)**" if i < 5 and abs(_main_residual(c)) >= 0.5 else ""
        out.append(
            f"| {c['case_name']}{flag} | {c['year']} | {c['senior']} / {c['junior']} | "
            f"{c['label']} | {_fmt(c['symmetric_percentile'])} | {_fmt(c['residual'])} | "
            f"{_fmt(c.get('symmetric_affinity_ratio'))} | {_fmt(c.get('residual_ratio'))} | "
            f"{c['same_category']} | {'yes' if c['used_proxy'] else 'no'} | "
            f"{c.get('pick_vs_rule') or ''} |"
        )
    if not res["per_case"]:
        out.append("| (no scored cases) | | | | | | | | | | |")
    out += ["", "## Exclusions (primary relatedness metric)", ""]
    for reason, n in sorted(rel["excluded"].items(), key=lambda kv: -kv[1]):
        out.append(f"- {reason}: {n}")
    out += [
        "",
        "## Method notes",
        "",
        "- Spearman uses average ranks for ties; with only two label levels present it is a "
        "rank-biserial-type correlation.",
        "- 95% CIs: percentile bootstrap, 2000 resamples of cases, fixed seed; resamples where "
        "the statistic is undefined are skipped.",
        f"- Proxy comparators: {res.get('comparator_rule') or 'n/a'}.",
        "- Scoring and statistics use no language model. "
        + (
            "Identification used the product's model-driven resolve node (harness v3)."
            if res.get("resolver") == "agent"
            else "Identification used the code-only name rule."
        ),
        "",
    ]
    return "\n".join(out)


# --------------------------------------------------------------------------------------
# Frontend rows
# --------------------------------------------------------------------------------------


def _value(m: dict[str, Any], kind: str) -> str:
    v = m[kind]
    s = f"{_fmt(v['value'])} (95% CI {_ci(*v['ci'])})"
    return s + (" · underpowered" if m["underpowered"] else "")


def frontend_doc(res: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    rel = res["relatedness"]
    p, ch, rf = rel["primary"], rel["channels_factor_only"], rel["relatedness_factor_only"]
    fame = res["fame"]
    ch_base = ch["same_category"]["spearman"]["value"]

    def row(
        metric: str, m: dict[str, Any], kind: str, baseline: str, base: dict[str, Any] | None
    ) -> dict[str, Any]:
        return {
            "n": m["n"],
            "metric": metric,
            "value": _value(m, kind),
            "ci": [None if x is None else round(x, 3) for x in m[kind]["ci"]],
            "baseline": baseline,
            "baseline_value": None if base is None else base[kind]["value"],
        }

    rows = [
        row("Spearman ρ: rank percentile vs court's channels/purchasers finding", ch["qloo"],
            "spearman", f"Same-category heuristic: {_fmt(ch_base)}",
            ch["same_category"]),
        row("AUC: rank percentile predicts \"favors plaintiff\"", p["qloo"], "auc",
            f"Popularity-only: {_fmt(p['popularity_product']['auc']['value'])}; same-category: "
            f"{_fmt(p['same_category']['auc']['value'])}", p["popularity_product"]),
        row("Spearman ρ: rank percentile vs court's relatedness finding", rf["qloo"], "spearman",
            f"Same-category heuristic: {_fmt(rf['same_category']['spearman']['value'])}",
            rf["same_category"]),
        row("Spearman ρ: rank percentile vs combined relatedness/purchaser finding (primary)",
            p["qloo"], "spearman",
            f"Same-category heuristic: {_fmt(p['same_category']['spearman']['value'])}; "
            f"popularity-only: {_fmt(p['popularity_product']['spearman']['value'])}",
            p["same_category"]),
        row("Spearman ρ: affinity ratio vs combined relatedness/purchaser finding (primary)",
            p["qloo_ratio"], "spearman",
            f"Rank percentile: {_fmt(p['qloo']['spearman']['value'])}; same-category: "
            f"{_fmt(p['same_category']['spearman']['value'])}", p["same_category"]),
        row("AUC: affinity ratio predicts \"favors plaintiff\"", p["qloo_ratio"], "auc",
            f"Rank percentile: {_fmt(p['qloo']['auc']['value'])}; popularity-only: "
            f"{_fmt(p['popularity_product']['auc']['value'])}", p["popularity_product"]),
        {
            "n": fame["breadth"]["n"],
            "metric": "AUC: fame breadth predicts court's fame finding",
            "value": _value(fame["breadth"], "auc"),
            "ci": [None if x is None else round(x, 3) for x in fame["breadth"]["auc"]["ci"]],
            "baseline": f"Popularity-only: {_fmt(fame['popularity']['auc']['value'])}",
            "baseline_value": fame["popularity"]["auc"]["value"],
        },
    ]  # fmt: skip
    llm = next((r for r in current.get("rows", []) if "LLM" in str(r.get("metric"))), None)
    if llm is not None:
        rows.append({**llm, "value": "not run (outside this Qloo-only harness)"}
                    if llm.get("value") == "pending" else llm)  # fmt: skip
    version = res.get("harness_version", 1)
    deviation = (
        " Harness v2: universe = the brand's own category tags, censored ranks "
        "reported as censored with a direct affinity lookup, one taxonomy synonym corrected "
        "(post-hoc deviations from pre-registration, documented; run 1 kept as the record)."
        if version >= 2
        else ""
    )
    if version >= 3:
        deviation += (
            f" Harness v3: brands identified by the product's resolver "
            f"({res.get('resolver', 'rule')}"
            + (f", model {res.get('model')}" if res.get("resolver") == "agent" else "")
            + "); scoring unchanged."
        )
    return {
        "status": "complete",
        "harness_version": version,
        "note": f"{headline(res)} Run {res['generated']}; labels and mapping pre-registered "
        f"(mapping sha256 {str(res['mapping_sha256'])[:12]}).{deviation}",
        "rows": rows,
    }


def run(
    mapping: list[dict[str, str]],
    scores: dict[str, Any],
    results_dir: Path,
    update_frontend: bool,
    frontend_json: Path = FRONTEND_JSON,
) -> dict[str, Any]:
    version = scores.get("harness_version", 1)
    if version != HARNESS_VERSION:
        raise SystemExit(
            f"scores.json was produced by harness v{version}; re-run resolve and score with "
            f"harness v{HARNESS_VERSION} (run 1 results stay untouched)"
        )
    res = build(mapping, scores)
    stamp = dt.date.today().strftime("%Y%m%d")
    suffix = f"_v{HARNESS_VERSION}" if HARNESS_VERSION >= 2 else ""
    md_path = results_dir / f"backtest_{stamp}{suffix}.md"
    json_path = results_dir / f"backtest_{stamp}{suffix}.json"
    results_dir.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(res), encoding="utf-8", newline="\n")
    write_json(json_path, res)
    frontend = "skipped (not a live run; pass --frontend to force)"
    if update_frontend:
        current = read_json(frontend_json) if frontend_json.exists() else {}
        write_json(frontend_json, frontend_doc(res, current))
        frontend = f"updated {frontend_json}"
    return {
        "markdown": str(md_path),
        "json": str(json_path),
        "frontend": frontend,
        "headline": headline(res),
        "harness_version": res["harness_version"],
        "primary_n": res["relatedness"]["primary"]["qloo"]["n"],
        "primary_n_affinity_ratio": res["relatedness"]["primary"]["qloo_ratio"]["n"],
        "excluded": res["relatedness"]["excluded"],
    }
