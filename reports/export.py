"""Standalone report export (design doc §8.3) — a team's full report as
static HTML or PDF.

Reuses the dashboard's own data layer (`dashboard/data.py`) and grading
logic (`grading/grade.py`'s `letter_grade_from_score`, via
`compute_multiyear_grades`) rather than re-reading parquet files or
re-deriving the weighted-grade formula here — the export shows exactly the
same numbers the dashboard does, computed by exactly the same code.

PDF export converts the same HTML this module renders (via xhtml2pdf) rather
than building a separate PDF layout — one template, two output formats.

Run standalone: python -m reports.export --team BOS --format both
"""

import argparse
import html
import io
from datetime import datetime, timezone
from pathlib import Path

from dashboard.data import compute_multiyear_grades, load_final_report, load_team_rollup
from dashboard.palette import GRADE_STATUS_COLOR, MUTED_INK, PRIMARY_INK, SECONDARY_INK, SURFACE
from reports.narrative import load_cached_narrative
from storage.paths import PROCESSED_DATA_DIR

DEFAULT_EXPORT_DIR = PROCESSED_DATA_DIR / "reports" / "exports"


def build_team_report_data(team: str, years: list[int] | None = None) -> dict:
    """Everything a team's report needs, scoped to `years` (all years if None)."""
    report = load_final_report()
    team_rollup = load_team_rollup()

    if years is not None:
        report = report[report["draft_year"].isin(years)]
        team_rollup = team_rollup[team_rollup["draft_year"].isin(years)]

    team_picks = report[report["team_abbreviation_espn"] == team].sort_values(["draft_year", "pick"])
    team_yearly = team_rollup[team_rollup["team_abbreviation_espn"] == team].sort_values("draft_year")

    agg = compute_multiyear_grades(team_rollup[team_rollup["team_abbreviation_espn"] == team])
    aggregate = None if agg.empty else agg.iloc[0].to_dict()

    picks = [
        {
            "draft_year": int(row["draft_year"]),
            "pick": int(row["pick"]),
            "player_name": row["player_name"],
            "predicted_pps": row["predicted_pps_selected"],
            "actual_pps": row["actual_pps"],
            "bpa_top_player": row["bpa_top_player"],
            "bpa_top_predicted_pps": row["bpa_top_predicted_pps"],
            "rank_differential": row["rank_differential"],
            "value_gap": row["value_gap"],
        }
        for _, row in team_picks.iterrows()
    ]

    yearly_grades = [
        {
            "draft_year": int(r["draft_year"]),
            "n_picks": int(r["n_picks"]),
            "headline_score": r["headline_score"],
            "grade_letter": r["grade_letter"],
        }
        for _, r in team_yearly.iterrows()
    ]

    narrative = load_cached_narrative(team)

    return {
        "team": team,
        "years": years,
        "aggregate": aggregate,
        "yearly_grades": yearly_grades,
        "picks": picks,
        "narrative": narrative,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _fmt(value, decimals=2):
    if value is None:
        return "N/A"
    try:
        if value != value:  # NaN
            return "N/A"
    except TypeError:
        pass
    return f"{value:.{decimals}f}"


def render_html(data: dict) -> str:
    team = html.escape(data["team"])
    scope = ", ".join(str(y) for y in data["years"]) if data["years"] else "2019-2022 (all years)"

    agg = data["aggregate"]
    if agg:
        grade_color = GRADE_STATUS_COLOR.get(agg["grade_letter"], MUTED_INK)
        agg_html = f"""
        <div class="badge" style="border-color:{grade_color}">
          <div class="badge-grade" style="color:{grade_color}">{html.escape(agg["grade_letter"])}</div>
          <div class="badge-sub">headline score {_fmt(agg["headline_score"])} · {int(agg["n_picks"])} pick(s)</div>
        </div>"""
    else:
        agg_html = '<p class="muted">No picks in this scope.</p>'

    yearly_rows = "".join(
        f"<tr><td>{y['draft_year']}</td><td>{y['n_picks']}</td>"
        f"<td>{_fmt(y['headline_score'])}</td><td>{html.escape(y['grade_letter'])}</td></tr>"
        for y in data["yearly_grades"]
    )

    narrative_html = ""
    if data["narrative"]:
        narrative_html = f"""
        <h2>Team Report</h2>
        <p class="narrative">{html.escape(data["narrative"]["narrative"])}</p>
        <p class="muted small">Generated {html.escape(str(data["narrative"]["generated_at"]))}</p>"""
        if data["narrative"]["grounding_warnings"]:
            warnings = ", ".join(html.escape(w) for w in data["narrative"]["grounding_warnings"])
            narrative_html += f'<p class="warning">Grounding check flagged: {warnings}</p>'
    else:
        narrative_html = '<h2>Team Report</h2><p class="muted">No narrative generated yet for this team.</p>'

    pick_rows = "".join(
        f"<tr><td>{p['draft_year']}</td><td>{p['pick']}</td>"
        f"<td>{html.escape(str(p['player_name']))}</td>"
        f"<td>{_fmt(p['predicted_pps'])}</td><td>{_fmt(p['actual_pps'])}</td>"
        f"<td>{html.escape(str(p['bpa_top_player']))}</td><td>{_fmt(p['bpa_top_predicted_pps'])}</td>"
        f"<td>{_fmt(p['rank_differential'], 0)}</td><td>{_fmt(p['value_gap'])}</td></tr>"
        for p in data["picks"]
    )

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{team} Draft Report</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", sans-serif; background: {SURFACE}; color: {PRIMARY_INK}; margin: 2rem; }}
  h1 {{ margin-bottom: 0.2rem; }}
  h2 {{ margin-top: 2rem; border-bottom: 1px solid #e1e0d9; padding-bottom: 0.3rem; }}
  .muted {{ color: {MUTED_INK}; }}
  .small {{ font-size: 0.85rem; }}
  .subtitle {{ color: {SECONDARY_INK}; margin-top: 0; }}
  .badge {{ display: inline-block; border: 2px solid; border-radius: 8px; padding: 0.6rem 1.2rem; margin: 0.5rem 0 1rem 0; }}
  .badge-grade {{ font-size: 2.4rem; font-weight: 700; line-height: 1; }}
  .badge-sub {{ color: {SECONDARY_INK}; font-size: 0.85rem; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 0.5rem; }}
  th, td {{ text-align: left; padding: 0.4rem 0.6rem; border-bottom: 1px solid #e1e0d9; font-size: 0.9rem; }}
  th {{ color: {MUTED_INK}; font-weight: 600; }}
  .narrative {{ line-height: 1.5; max-width: 60em; }}
  .warning {{ color: #d03b3b; font-size: 0.85rem; }}
  footer {{ margin-top: 2rem; color: {MUTED_INK}; font-size: 0.8rem; }}
</style>
</head>
<body>
  <h1>{team} — Draft Analysis Report</h1>
  <p class="subtitle">Draft year(s): {html.escape(scope)}</p>
  {agg_html}

  <h2>Grade by Draft Year</h2>
  <table>
    <tr><th>Year</th><th>Picks</th><th>Headline Score</th><th>Grade</th></tr>
    {yearly_rows or '<tr><td colspan="4" class="muted">No data</td></tr>'}
  </table>

  {narrative_html}

  <h2>Pick-by-Pick Detail</h2>
  <table>
    <tr>
      <th>Year</th><th>Pick</th><th>Player Selected</th><th>Predicted PPS</th>
      <th>Actual PPS</th><th>#1 BPA Alternative</th><th>Alt. Predicted PPS</th>
      <th>Rank Diff.</th><th>Value Gap</th>
    </tr>
    {pick_rows or '<tr><td colspan="9" class="muted">No picks</td></tr>'}
  </table>

  <footer>
    Generated {html.escape(data["generated_at"])} · PPS = Projected Production Score, not VORP ·
    Pure BPA rankings only (no positional-fit adjustment)
  </footer>
</body>
</html>"""


def render_pdf_bytes(html_str: str) -> bytes:
    from xhtml2pdf import pisa  # imported lazily — only needed for PDF export

    buffer = io.BytesIO()
    result = pisa.CreatePDF(html_str, dest=buffer)
    if result.err:
        raise RuntimeError(f"PDF generation failed ({result.err} error(s))")
    return buffer.getvalue()


def generate_report_html(team: str, years: list[int] | None = None) -> str:
    """In-memory HTML generation — used by both the file-writing export below
    and the dashboard's download button (no disk round-trip needed there)."""
    return render_html(build_team_report_data(team, years))


def generate_report_pdf(team: str, years: list[int] | None = None) -> bytes:
    return render_pdf_bytes(generate_report_html(team, years))


def export_html(team: str, years: list[int] | None = None, output_path: str | Path | None = None) -> Path:
    html_str = generate_report_html(team, years)

    output_path = Path(output_path) if output_path else DEFAULT_EXPORT_DIR / f"{team}_report.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_str)
    return output_path


def export_pdf(team: str, years: list[int] | None = None, output_path: str | Path | None = None) -> Path:
    pdf_bytes = generate_report_pdf(team, years)

    output_path = Path(output_path) if output_path else DEFAULT_EXPORT_DIR / f"{team}_report.pdf"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(pdf_bytes)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a team's draft report (design doc §8.3).")
    parser.add_argument("--team", required=True, help="ESPN team abbreviation, e.g. BOS")
    parser.add_argument("--format", choices=["html", "pdf", "both"], default="both")
    parser.add_argument("--years", nargs="+", type=int, default=None, help="Draft years to include (default: all)")
    parser.add_argument("--output", default=None, help="Output file path (single-format only)")
    args = parser.parse_args()

    if args.output and args.format == "both":
        parser.error("--output requires a single --format (html or pdf), not both")

    if args.format in ("html", "both"):
        path = export_html(args.team, args.years, args.output if args.format == "html" else None)
        print(f"Wrote {path}")
    if args.format in ("pdf", "both"):
        path = export_pdf(args.team, args.years, args.output if args.format == "pdf" else None)
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
