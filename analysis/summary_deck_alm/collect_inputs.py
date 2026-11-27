"""Copy the result tables of the eight rebuilt analyses into inputs/.

Each analysis lives on its own branch of this repository until its pull request merges. This script
reads the named files straight from those branches (git show) so the deck can be rebuilt from a
plain checkout of this folder, and records the commit each file came from in inputs/MANIFEST.json.

    git fetch origin
    python3 analysis/summary_deck_alm/collect_inputs.py

Nothing is recomputed here: the figures are exactly the ones in each analysis' own outputs.
"""
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / "inputs"

# analysis key -> (branch, pull request, folder on that branch, files)
SOURCES = {
    "discount_curves": ("claude/project-thread-eg45ke", 8, "analysis/discount_curves/out", [
        "headline_fy2025.csv", "band.csv", "reference_curve_check.csv", "par_fy2025.csv",
        "ultimates_and_basis.csv", "trend.csv", "not_covered.csv"]),
    "portfolio_composition": ("claude/project-thread-mk8ea5", 7, "analysis/portfolio_composition_alm/out", [
        "peers.csv", "genacct_mix_l2.csv", "block_mix_l3.csv", "liabilities_by_line.csv", "basis_effect.csv"]),
    "investment_risk": ("claude/project-thread-1yngox", 6, "analysis/investment_risk_alm/dashboard", [
        "landscape.csv", "peer_stats.csv", "facts.csv", "licat_mix.csv", "licat_trend.csv", "sensitivities.csv",
        "encumbrance.csv", "rbc_capital_path.csv", "rbc_rotation.csv", "outside_study.csv", "build_info.json"]),
    "portfolio_reallocation": ("claude/project-thread-i4fgtn", 3, "analysis/portfolio_reallocation_alm", [
        "changes.csv", "context.csv", "mix_by_date.csv"]),
    "street_wallet": ("claude/project-thread-76d0od", 4, "analysis/street_wallet_alm", [
        "wallet_by_insurer.csv", "wallet_by_driver.csv"]),
    "csm_surplus_duration": ("claude/project-thread-reptne", 9, "analysis/csm_surplus_duration", [
        "results.csv", "csm_runoff_summary.csv", "fvoci.csv", "coverage.csv", "parameters.csv"]),
    "insurer_deep_dive": ("claude/project-thread-yhjyr9", 10, "analysis/insurer_deep_dive", ["alm.json"]),
    "org_charts": ("claude/project-thread-dc6j9p", 5, "analysis/org_charts/data", ["functions.json", "alm_context.json"]),
}


def git(*args):
    return subprocess.run(["git", "-C", str(ROOT), *args], check=True, capture_output=True).stdout


def main():
    manifest = {}
    for key, (branch, pr, folder, files) in SOURCES.items():
        ref = f"origin/{branch}"
        commit = git("rev-parse", ref).decode().strip()
        dest = OUT / key
        dest.mkdir(parents=True, exist_ok=True)
        for f in files:
            (dest / f).write_bytes(git("show", f"{ref}:{folder}/{f}"))
        manifest[key] = {"branch": branch, "pull_request": pr, "commit": commit, "folder": folder, "files": files}
        print(f"{key:24s} {commit[:7]}  {len(files)} files")
    (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=1) + "\n")


if __name__ == "__main__":
    main()
