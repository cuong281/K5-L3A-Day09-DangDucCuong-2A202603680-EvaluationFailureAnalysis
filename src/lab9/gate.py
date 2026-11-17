"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, aggregate, load_spec, per_item
from lab9.graders import GRADERS


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)
    Also caught: duplicated (item_id, seed) rows, an item tagged inconsistently across seeds,
    and headline metrics that do not match what the rows actually say (edited aggregates)."""
    problems: list[str] = []
    metrics = pr.get("metrics") or {}
    rows = pr.get("rows") or []
    base_rows = base.get("rows") or []
    graded = [m["id"] for m in spec.get("metrics", []) if m["id"] in GRADERS]

    # 1. NaN / inf headline metrics (they compare False against every threshold and slip through).
    for k, v in metrics.items():
        if isinstance(v, float) and not math.isfinite(v):
            problems.append(f"metric {k} is {v} (NaN/inf)")

    # 2. Row count and uniqueness against the manifest.
    man = pr.get("manifest") or {}
    try:
        want_rows = int(man["items"]) * len(man["seeds"])
    except (KeyError, TypeError, ValueError):
        want_rows = None
        problems.append("manifest lacks items/seeds: cannot check coverage")
    if want_rows is not None and len(rows) != want_rows:
        problems.append(f"{len(rows)} rows != {man['items']} items x {len(man['seeds'])} seeds = {want_rows}")
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    dups = sorted({k for k in keys if keys.count(k) > 1}, key=str)
    if dups:
        problems.append(f"duplicated (item_id, seed) rows: {dups[:5]}")

    # 3. Same (item_id, seed) set as the baseline: no cherry-picked items or seeds.
    base_keys = {(r.get("item_id"), r.get("seed")) for r in base_rows}
    if set(keys) != base_keys:
        missing, extra = base_keys - set(keys), set(keys) - base_keys
        problems.append(f"(item_id, seed) set differs from baseline: {len(missing)} missing, {len(extra)} extra")
    if sorted(man.get("seeds") or []) != sorted((base.get("manifest") or {}).get("seeds") or []):
        problems.append(f"seeds {man.get('seeds')} differ from baseline {(base.get('manifest') or {}).get('seeds')}")

    # 4. Crashed graders: recorded failures, or a graded value that silently became None.
    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s), e.g. {pr['evaluator_failures'][0]}")
    none_rows = [f"{r.get('item_id')}@{r.get('seed')}:{m}" for r in rows for m in graded
                 if m not in r or r[m] is None]
    if none_rows:
        problems.append(f"{len(none_rows)} graded value(s) missing/None, e.g. {none_rows[:3]}")

    # 4b. Headline metrics must be what the rows say (an edited aggregate hides failing rows).
    if rows and not none_rows:
        recomputed = aggregate([{"cost": 0.0, **r} for r in rows], graded, spec.get("pass_k") or [])
        for k, v in recomputed.items():
            if k == "cost_per_success" or k not in metrics or v is None:
                continue
            got = metrics[k]
            if not isinstance(got, (int, float)) or isinstance(got, bool) or abs(float(got) - float(v)) > 1e-3:
                problems.append(f"metric {k}={got} but the rows give {v}")

    # 5. Ratchet: on the same eval set a spec may only get stricter.
    if base_spec is not None:
        problems += _ratchet(spec, base_spec)

    # 6. Slice tags per item must match the baseline (and be consistent across seeds).
    pr_tags, base_tags = _slice_tags(rows), _slice_tags(base_rows)
    for item, tags in sorted(pr_tags.items()):
        if len(tags) > 1:
            problems.append(f"{item}: slice tags differ between seeds {sorted(tags)}")
        elif item in base_tags and tags != base_tags[item]:
            problems.append(f"{item}: slice tags {sorted(tags)[0]} != baseline {sorted(base_tags[item])[0]}")
    return problems


def _slice_tags(rows: list[dict]) -> dict[str, set[tuple[str, ...]]]:
    out: dict[str, set[tuple[str, ...]]] = {}
    for r in rows:
        out.setdefault(r.get("item_id"), set()).add(tuple(sorted(r.get("slices") or [])))
    return out


def _looser(where: str, old: dict, new: dict | None) -> list[str]:
    """Problems if `new` (same metric or slice in the PR spec) is looser than `old` (base spec)."""
    if new is None:
        return [f"{where} removed"]
    out = []
    if old.get("blocking") and not new.get("blocking"):
        out.append(f"{where} no longer blocking")
    o_th = old.get("threshold", old)        # metrics nest thresholds; slices keep them at top level
    n_th = new.get("threshold", new)
    if "min" in o_th and ("min" not in n_th or n_th["min"] < o_th["min"]):
        out.append(f"{where} min {o_th['min']} -> {n_th.get('min')}")
    if "max" in o_th and ("max" not in n_th or n_th["max"] > o_th["max"]):
        out.append(f"{where} max {o_th['max']} -> {n_th.get('max')}")
    if "max_increase" in o_th and ("max_increase" not in n_th or n_th["max_increase"] > o_th["max_increase"]):
        out.append(f"{where} max_increase {o_th['max_increase']} -> {n_th.get('max_increase')}")
    if o_th.get("no_significant_drop") and not n_th.get("no_significant_drop"):
        out.append(f"{where} dropped no_significant_drop")
    return out


def _ratchet(spec: dict, base_spec: dict) -> list[str]:
    # The gate only compares reports on the same eval_set_sha, so the same eval set is in play
    # whatever eval_set_version the PR spec claims: the ratchet always applies.
    out = []
    new_m = {m["id"]: m for m in spec.get("metrics", [])}
    for m in base_spec.get("metrics", []):
        out += [f"ratchet: {p}" for p in _looser(f"metric {m['id']}", m, new_m.get(m["id"]))]
    new_s = {(s.get("name"), s.get("metric")): s for s in spec.get("slices") or []}
    for s in base_spec.get("slices") or []:
        key = (s.get("name"), s.get("metric"))
        out += [f"ratchet: {p}" for p in _looser(f"slice {key[0]}/{key[1]}", s, new_s.get(key))]
    if sorted(spec.get("seeds") or []) != sorted(base_spec.get("seeds") or []):
        out.append(f"ratchet: seeds {spec.get('seeds')} != {base_spec.get('seeds')}")
    old_conf = (base_spec.get("bootstrap") or {}).get("confidence", 0.95)
    if (spec.get("bootstrap") or {}).get("confidence", 0.95) > old_conf:
        out.append("ratchet: bootstrap confidence raised (wider CI hides drops)")
    return out


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for s in spec.get("slices") or []:
        name, metric = s["name"], s["metric"]
        sid = f"slice:{name}/{metric}"
        a, b = per_item(pr, metric, slice_name=name), per_item(base, metric, slice_name=name)
        note = ""
        if not a:
            val, verdict = None, "fail"            # an empty slice cannot vouch for anything
            note = "no items in slice"
        else:
            val = sum(a.values()) / len(a)
            verdict = "ok"
            if "min" in s and val < s["min"]:
                verdict = "fail"
            if "max" in s and val > s["max"]:
                verdict = "fail"
            if s.get("no_significant_drop"):
                keys = sorted(set(a) & set(b))
                d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                   n_resamples=bs.get("n_resamples", 1000),
                                                   rng=bs.get("rng", 2027),
                                                   confidence=bs.get("confidence", 0.95))
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}] n={len(keys)}"
                if hi < 0:
                    verdict = "fail"
        if verdict != "ok" and s.get("blocking"):
            blocked.append(sid)
        label = "ok" if verdict == "ok" else ("BLOCK" if s.get("blocking") else "warn")
        shown = "None" if val is None else f"{val:.4f}"
        th = {k: s[k] for k in ("min", "max", "no_significant_drop") if k in s}
        lines.append(f"  {sid:<34} {shown:<8} {json.dumps(th):<40} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
