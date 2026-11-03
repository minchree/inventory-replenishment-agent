"""python -m replenish generate | run | evaluate | readme"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m replenish", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="write data/sales.csv, inventory.csv, params.csv from the seeded generator")
    g.add_argument("--data-dir", default="data")
    g.add_argument("--seed", type=int, default=None)

    r = sub.add_parser("run", help="run the full agent on the CSVs: daily log, decisions, ledger, charts")
    r.add_argument("--data-dir", default="data")
    r.add_argument("--out", default="outputs")
    r.add_argument("--policy", default="P3 full agent")
    r.add_argument("--alpha", type=float, default=None, help="fix the EWMA smoothing constant (default: chosen on warm-up)")
    r.add_argument("--order-cost", type=float, default=0.0)
    r.add_argument("--shortage", choices=("backorder", "lost_sales"), default="backorder")
    r.add_argument("--quiet", action="store_true", help="write files without printing the log")

    e = sub.add_parser("evaluate", help="baselines, ablations, Monte Carlo, service-level sweep, figures")
    e.add_argument("--data-dir", default="data")
    e.add_argument("--out", default="outputs")
    e.add_argument("--seeds", type=int, default=200)
    e.add_argument("--sweep-seeds", type=int, default=100)
    e.add_argument("--dev", action="store_true",
                   help="use the design-time seeds (1000+) instead of the held-out test seeds (5000+)")

    m = sub.add_parser("readme", help="copy outputs/results.md into README.md between the results markers")
    m.add_argument("--readme", default="README.md")
    m.add_argument("--results", default="outputs/results.md")

    args = parser.parse_args(argv)
    import matplotlib
    matplotlib.use("Agg")

    from . import report
    from .data import load_dataset
    from .datagen import DATA_SEED, write_dataset
    from .evaluate import POLICIES, ABLATIONS, evaluate_all, metrics_table, run_dataset
    from .sim import SimConfig

    if args.cmd == "generate":
        paths = write_dataset(args.data_dir, DATA_SEED if args.seed is None else args.seed)
        for p in paths.values():
            print(f"wrote {p}")
    elif args.cmd == "run":
        lineup = {**POLICIES, **ABLATIONS}
        if args.policy not in lineup:
            parser.error(f"--policy must be one of {list(lineup)}")
        ds = load_dataset(args.data_dir)
        spec = {**lineup[args.policy], "alpha": args.alpha}
        runs = run_dataset(ds, spec,
                           config=SimConfig(order_cost=args.order_cost, shortage=args.shortage))
        table = metrics_table(runs)
        log = report.write_run_outputs(runs, table, args.out)
        fig_dir = Path(args.out) / "figures"
        fig_dir.mkdir(parents=True, exist_ok=True)
        for sku, run in runs.items():
            report.plot_inventory_story(run, fig_dir / f"inventory_{sku}.png")
        (Path(args.out) / "run_metrics.json").write_text(
            json.dumps({sku: {k: (None if v != v else v) for k, v in mt.items()} for sku, mt in table.items()},
                       indent=2), encoding="utf-8")
        if not args.quiet:
            print("\n".join(log))
        print("\n".join(["", *report.scorecard(table)]))
    elif args.cmd == "evaluate":
        from .config import DEV_SEED0, TEST_SEED0
        evaluate_all(load_dataset(args.data_dir), args.out, mc_seeds=args.seeds, sweep_seeds=args.sweep_seeds,
                     seed0=DEV_SEED0 if args.dev else TEST_SEED0)
    elif args.cmd == "readme":
        report.update_readme(args.readme, args.results)
        print(f"updated {args.readme}")
    return 0
