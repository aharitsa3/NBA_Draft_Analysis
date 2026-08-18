"""Narrative generation (design doc §7.4) — a constrained Claude prompt that
turns a team's exact computed tables into a short prose report.

Every number in the model's output is meant to be traceable back to the input
JSON package built here — the system prompt explicitly forbids inference,
estimation, or computed aggregates beyond what's provided, and requires the
model to call the projection metric "Projected Production Score" / "PPS",
never VORP (per §2's naming rule, same constraint as everywhere else in this
project). `grounding_check` is a heuristic backstop on top of the prompt
constraint, not a replacement for it — see its docstring for what it can and
can't catch.

Narratives are cached per team, keyed by a hash of that team's exact input
data (`processed_data/reports/narratives.parquet`) — a pipeline rerun that
changes the team's numbers invalidates the cache automatically; an unchanged
team is never re-sent to the API.

**No API key needed, if you'd rather not pay for usage**: `build_prompt_text`
builds the exact same system prompt + data package the live API call would
send, as one block of text you can paste into claude.ai (or any Claude chat
surface) by hand. `ingest_manual_narrative` takes Claude's reply back and
runs it through the same grounding check and cache as a live call — the
dashboard/export code can't tell the two paths apart. `python -m
reports.narrative prompt --team BOS` / `... ingest --team BOS --file
reply.txt` drives this from the CLI.
"""

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import pandas as pd

from storage.config import require_anthropic_api_key
from storage.io import exists, read_parquet, write_parquet
from storage.paths import PROCESSED_DATA_DIR

MODEL = "claude-opus-5"

SYSTEM_PROMPT = """You are writing a short draft-performance report for one NBA team, \
covering their 2019-2022 draft picks, based ONLY on the JSON data provided in the \
user message.

Hard rules:
- Every number you state (a score, a rank, a stat) must appear verbatim in the \
provided JSON. Do not calculate, estimate, extrapolate, average, or infer any \
number that is not already present in the data.
- Never invent a player fact, outcome, or comparison not present in the data.
- The projection metric must always be called "Projected Production Score" or \
"PPS" — never "VORP", even if you believe VORP is a similar or related concept.
- If the data for a pick is missing or null (e.g. a player who never made the \
NBA), say so plainly rather than guessing why or filling in a number.
- Write 3-4 short paragraphs: an overview of the team's draft-era performance \
across 2019-2022, a look at their strongest and weakest picks by value gap, and \
a one-line note on the year-over-year trend.
- Plain prose, no headers, no bullet lists, no markdown."""


def _round(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return round(float(value), 2)


def build_team_data_package(team: str) -> dict:
    """The exact, complete set of numbers the narrative is allowed to reference."""
    report = read_parquet("pipeline/final_report.parquet")
    team_rows = report[report["team_abbreviation_espn"] == team].sort_values(["draft_year", "pick"])

    picks = [
        {
            "draft_year": int(row["draft_year"]),
            "pick": int(row["pick"]),
            "player_selected": row["player_name"],
            "predicted_pps": _round(row["predicted_pps_selected"]),
            "actual_pps": _round(row["actual_pps"]),
            "bpa_top_available_player": row["bpa_top_player"],
            "bpa_top_available_predicted_pps": _round(row["bpa_top_predicted_pps"]),
            "rank_differential": _round(row["rank_differential"]),
            "value_gap_pps_points": _round(row["value_gap"]),
        }
        for _, row in team_rows.iterrows()
    ]

    yearly = (
        team_rows[["draft_year", "team_draft_year_n_picks", "headline_score", "grade_letter"]]
        .drop_duplicates()
        .sort_values("draft_year")
    )
    yearly_grades = [
        {
            "draft_year": int(r["draft_year"]),
            "n_picks": int(r["team_draft_year_n_picks"]),
            "headline_score": _round(r["headline_score"]),
            "grade_letter": r["grade_letter"],
        }
        for _, r in yearly.iterrows()
    ]

    return {"team": team, "picks": picks, "yearly_grades": yearly_grades}


def _data_hash(team_data: dict) -> str:
    return hashlib.sha256(json.dumps(team_data, sort_keys=True).encode()).hexdigest()


# (?<!\d) keeps a year range like "2019-2022" from being misread as "2019" and
# "-2022" — the hyphen is only treated as a minus sign when NOT immediately
# preceded by another digit (a genuine negative number is preceded by
# whitespace, a paren, start-of-string, etc., never by a digit).
_NUMBER_RE = re.compile(r"(?<!\d)-?\d+\.?\d*")


def grounding_check(narrative_text: str, team_data: dict) -> list[str]:
    """Heuristic check: every number mentioned in the narrative should trace
    back to a number present in team_data.

    This is NOT a semantic check — it can't verify a true number was attached
    to the right claim, and small integers (a draft year, a pick number) will
    often coincidentally "match" even when unrelated. It only catches numbers
    that don't appear anywhere in the input data at all, i.e. values the model
    likely fabricated or computed on its own. Returns the list of narrative
    number-strings that don't match anything (empty list = clean).
    """
    allowed = set()

    def collect(value):
        if isinstance(value, dict):
            for v in value.values():
                collect(v)
        elif isinstance(value, list):
            for v in value:
                collect(v)
        elif isinstance(value, (int, float)):
            allowed.add(round(float(value), 1))
            allowed.add(round(float(value)))  # prose often rounds to a whole number

    collect(team_data)

    unverified = []
    for match in _NUMBER_RE.findall(narrative_text):
        num = float(match)
        if round(num, 1) not in allowed and round(num) not in allowed:
            unverified.append(match)
    return unverified


def build_prompt_text(team: str) -> str:
    """System prompt + this team's data package as one pasteable block, for
    the zero-API-key manual workflow. Uses the exact same team_data as
    generate_narrative, so a narrative pasted back via ingest_manual_narrative
    caches under the same data hash a live call would have used.
    """
    team_data = build_team_data_package(team)
    return (
        SYSTEM_PROMPT
        + "\n\n---\n\nHere is the JSON data for this team. Follow the rules above exactly.\n\n"
        + json.dumps(team_data, indent=2)
    )


def save_prompt_for_manual_use(team: str, output_path: str | Path | None = None) -> Path:
    output_path = Path(output_path) if output_path else PROCESSED_DATA_DIR / "reports" / "prompts" / f"{team}_prompt.txt"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(build_prompt_text(team))
    return output_path


def ingest_manual_narrative(team: str, narrative_text: str) -> dict:
    """Cache a narrative pasted back from claude.ai (using the prompt from
    build_prompt_text / save_prompt_for_manual_use) — same grounding check,
    same cache table, same data-hash keying as a live API call.
    """
    team_data = build_team_data_package(team)
    if not team_data["picks"]:
        raise ValueError(f"{team} has no picks in the pipeline output — nothing to narrate")

    narrative_text = narrative_text.strip()
    if not narrative_text:
        raise ValueError("Pasted narrative text is empty")

    warnings = grounding_check(narrative_text, team_data)
    result = {
        "team": team,
        "narrative": narrative_text,
        "grounding_warnings": warnings,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cached": False,
        "source": "manual",
    }
    _upsert_cache(team, _data_hash(team_data), result)
    return result


def load_cached_narrative(team: str) -> dict | None:
    """Read-only cache lookup — never calls the API. Returns None if this
    team has no cached narrative for its CURRENT data (a stale entry from
    before a pipeline rerun does not count as a hit).
    """
    if not exists("reports/narratives.parquet"):
        return None

    data_hash = _data_hash(build_team_data_package(team))
    cache = read_parquet("reports/narratives.parquet")
    hit = cache[(cache["team"] == team) & (cache["data_hash"] == data_hash)]
    if hit.empty:
        return None

    row = hit.iloc[0].to_dict()
    return {
        "team": team,
        "narrative": row["narrative"],
        "grounding_warnings": json.loads(row["grounding_warnings"]),
        "generated_at": row["generated_at"],
        "source": row.get("source", "api"),  # cache rows written before this field existed default to "api"
        "cached": True,
    }


def generate_narrative(team: str, force: bool = False) -> dict:
    """Cache-first: returns the cached narrative if this team's current data
    already has one; only calls the Anthropic API on a genuine cache miss.
    Pass force=True to bypass the cache and always call the API (e.g. a
    dashboard "regenerate" action) — the fresh result still overwrites the
    cache entry for this team's current data hash.
    """
    if not force:
        cached = load_cached_narrative(team)
        if cached is not None:
            return cached

    team_data = build_team_data_package(team)
    if not team_data["picks"]:
        raise ValueError(f"{team} has no picks in the pipeline output — nothing to narrate")

    require_anthropic_api_key()
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,  # headroom for adaptive thinking + a few paragraphs of prose
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": json.dumps(team_data, indent=2)}],
    )

    if response.stop_reason == "refusal":
        raise RuntimeError(f"Anthropic API declined to generate a narrative for {team} "
                            f"(stop_details={response.stop_details})")

    narrative_text = next(b.text for b in response.content if b.type == "text")
    warnings = grounding_check(narrative_text, team_data)

    result = {
        "team": team,
        "narrative": narrative_text,
        "grounding_warnings": warnings,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cached": False,
        "source": "api",
    }
    _upsert_cache(team, _data_hash(team_data), result)
    return result


def _upsert_cache(team: str, data_hash: str, result: dict) -> None:
    new_row = pd.DataFrame([{
        "team": team,
        "data_hash": data_hash,
        "narrative": result["narrative"],
        "grounding_warnings": json.dumps(result["grounding_warnings"]),
        "generated_at": result["generated_at"],
        "source": result.get("source", "api"),
    }])

    if exists("reports/narratives.parquet"):
        cache = read_parquet("reports/narratives.parquet")
        cache = cache[cache["team"] != team]  # drop this team's stale entry, if any
        cache = pd.concat([cache, new_row], ignore_index=True)
    else:
        cache = new_row

    write_parquet(cache, "reports/narratives.parquet")


def main() -> None:
    parser = argparse.ArgumentParser(description="Narrative generation (Phase 9) — live API or manual-paste workflow.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_prompt = sub.add_parser("prompt", help="Build/save the prompt for a team, to paste into claude.ai by hand")
    p_prompt.add_argument("--team", required=True)
    p_prompt.add_argument("--output", default=None)

    p_ingest = sub.add_parser("ingest", help="Cache a narrative pasted back from claude.ai")
    p_ingest.add_argument("--team", required=True)
    p_ingest.add_argument("--file", default=None, help="Read the narrative from this file (default: stdin)")

    p_gen = sub.add_parser("generate", help="Generate via the live Anthropic API (requires ANTHROPIC_API_KEY)")
    p_gen.add_argument("--team", required=True)
    p_gen.add_argument("--force", action="store_true")

    args = parser.parse_args()

    if args.command == "prompt":
        path = save_prompt_for_manual_use(args.team, args.output)
        print(f"Wrote prompt -> {path}")
        print()
        print("Paste that file's contents into claude.ai, copy Claude's reply to a text file, then run:")
        print(f"  python -m reports.narrative ingest --team {args.team} --file <path-to-reply.txt>")
    elif args.command == "ingest":
        text = Path(args.file).read_text() if args.file else sys.stdin.read()
        result = ingest_manual_narrative(args.team, text)
        print(f"Cached narrative for {args.team} (source=manual)")
        if result["grounding_warnings"]:
            print(f"  grounding check flagged: {result['grounding_warnings']}")
    elif args.command == "generate":
        result = generate_narrative(args.team, force=args.force)
        print(result["narrative"])
        if result["grounding_warnings"]:
            print(f"\ngrounding check flagged: {result['grounding_warnings']}")


if __name__ == "__main__":
    main()
