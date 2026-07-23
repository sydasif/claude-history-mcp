#!/usr/bin/env python3
"""Run Tier-1 mechanical checks and output structured JSON.

Usage:
    python scan_codebase.py <directory> [--vulture-min-confidence 80]

Outputs a JSON object with keys:
    vulture_findings:     dead code from Vulture
    ruff_unused:          unused imports/vars from Ruff (F401/F841)
    ruff_era:             commented-out code from Ruff (ERA)
    ruff_d:               docstring style issues from Ruff (D)
    ruff_fix:             TODO/FIXME/HACK markers from Ruff (FIX)
    docsig_findings:      signature-param mismatches from docsig (if installed)
    docvet_findings:      stale docstrings from docvet freshness (if installed)

If a tool is not installed, its key will be an error dict with {"error": true}.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


def _run_cmd(cmd: list[str], tool: str, timeout: int = 120) -> tuple[str, str]:
    """Run a command, return (stdout, stderr). Raises on timeout."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return "", f"{tool} timed out after {timeout}s"
    except FileNotFoundError:
        return "", f"{tool} not found"
    except OSError as e:
        return "", str(e)


def _not_installed(tool: str) -> list[dict]:
    return [{"error": True, "tool": tool, "detail": f"{tool} not installed"}]


def run_vulture(target: str, min_confidence: int = 80) -> list[dict]:
    """Run vulture and parse output into structured findings."""
    if not shutil.which("vulture"):
        return _not_installed("vulture")
    stdout, stderr = _run_cmd(["vulture", target, f"--min-confidence={min_confidence}"], "vulture")
    if stderr and not stdout:
        return _not_installed("vulture")

    findings = []
    # Vulture: file:line: confidence: message (90% confidence)
    pattern = re.compile(
        r"^(?P<file>.+?):(?P<line>\d+):\s*(?P<message>.+?)\s*\((?P<confidence>\d+)%\)$"
    )
    for line in stdout.splitlines():
        m = pattern.match(line)
        if m:
            msg = m.group("message")
            name = msg.split()[-1] if " " in msg else msg
            findings.append(
                {
                    "file": m.group("file"),
                    "line": int(m.group("line")),
                    "type": "dead_code",
                    "name": name,
                    "confidence": int(m.group("confidence")),
                    "message": msg,
                }
            )
    return findings


def run_ruff(target: str, select: str) -> list[dict]:
    """Run ruff with a --select flag and parse concise output."""
    if not shutil.which("ruff"):
        return _not_installed("ruff")
    stdout, stderr = _run_cmd(
        ["ruff", "check", f"--select={select}", "--output-format=concise", target], "ruff"
    )
    if stderr and not stdout:
        return _not_installed("ruff")

    findings = []
    # Ruff concise: file:line:col: code message
    pattern = re.compile(
        r"^(?P<file>.+?):(?P<line>\d+):(?P<col>\d+):\s*(?P<code>\S+)\s+(?P<message>.+)$"
    )
    for line in stdout.splitlines():
        m = pattern.match(line)
        if m:
            findings.append(
                {
                    "file": m.group("file"),
                    "line": int(m.group("line")),
                    "code": m.group("code"),
                    "message": m.group("message"),
                }
            )
    return findings


def run_docsig(target: str) -> list[dict]:
    """Run docsig to check signature params match docstrings."""
    if not shutil.which("docsig"):
        return _not_installed("docsig")
    stdout, stderr = _run_cmd(
        # --check-class --check-dunders --check-protected covers all scopes
        ["docsig", "--check-class", "--check-dunders", "--check-protected", target],
        "docsig",
    )
    if stderr and not stdout:
        return _not_installed("docsig")

    findings = []
    # docsig: file:line:in function message
    # e.g. src/utils.py:14:in function parse_timestamp: Extra parameter(s) in docstring: ts
    pattern = re.compile(r"^(?P<file>.+?):(?P<line>\d+):\s*(?P<message>.+)$")
    for line in stdout.splitlines():
        m = pattern.match(line)
        if m:
            findings.append(
                {
                    "file": m.group("file"),
                    "line": int(m.group("line")),
                    "type": "docstring_signature_mismatch",
                    "message": m.group("message"),
                }
            )
    return findings


def run_docvet(target: str) -> list[dict]:
    """Run docvet freshness check (diff mode by default — fast, CI-friendly)."""
    if not shutil.which("docvet"):
        return _not_installed("docvet")
    stdout, stderr = _run_cmd(["docvet", "check", "--freshness", target], "docvet")
    if stderr and not stdout:
        return _not_installed("docvet")

    findings = []
    # docvet: file:line: RULE SEVERITY message
    pattern = re.compile(
        r"^(?P<file>.+?):(?P<line>\d+):\s*(?P<rule>\S+)\s+(?P<severity>\S+)\s+(?P<message>.+)$"
    )
    for line in stdout.splitlines():
        m = pattern.match(line)
        if m:
            findings.append(
                {
                    "file": m.group("file"),
                    "line": int(m.group("line")),
                    "rule": m.group("rule"),
                    "severity": m.group("severity"),
                    "message": m.group("message"),
                }
            )
    return findings


def main():
    parser = argparse.ArgumentParser(
        description="Scan Python codebase for dead code, stale docs, zombie code."
    )
    parser.add_argument("directory", help="Target directory to scan")
    parser.add_argument(
        "--depth",
        choices=["quick", "deep"],
        default="quick",
        help="quick (default): dead code, signatures, TODOs. deep: add missing-docstring checks, docvet, coverage.",
    )
    parser.add_argument(
        "--vulture-min-confidence",
        type=int,
        default=80,
        help="Min confidence for vulture (default 80)",
    )
    parser.add_argument("--skip-vulture", action="store_true")
    parser.add_argument("--skip-ruff-f401", action="store_true")
    parser.add_argument("--skip-ruff-era", action="store_true")
    parser.add_argument("--skip-ruff-d", action="store_true")
    parser.add_argument("--skip-ruff-fix", action="store_true")
    parser.add_argument("--skip-docsig", action="store_true")
    parser.add_argument("--skip-docvet", action="store_true")
    parser.add_argument(
        "--all", action="store_true", help="Skip nothing (run every available tool)"
    )
    args = parser.parse_args()

    target = str(Path(args.directory).resolve())
    report: dict[str, list[dict]] = {}

    is_deep = args.all or args.depth == "deep"

    # Quick-depth: dead code, signatures, TODOs
    if args.all or not args.skip_vulture:
        report["vulture_findings"] = run_vulture(target, args.vulture_min_confidence)
    if args.all or not args.skip_ruff_f401:
        report["ruff_unused"] = run_ruff(target, "F401,F841")
    if args.all or not args.skip_ruff_era:
        report["ruff_era"] = run_ruff(target, "ERA")
    if args.all or not args.skip_ruff_fix:
        report["ruff_fixme"] = run_ruff(target, "FIX")
    if args.all or not args.skip_docsig:
        report["docsig_findings"] = run_docsig(target)

    # Deep-depth: docstring presence, stale docs, coverage
    if is_deep and not args.skip_ruff_d:
        report["ruff_d"] = run_ruff(target, "D")
    if is_deep and not args.skip_docvet:
        report["docvet_findings"] = run_docvet(target)

    json.dump(report, sys.stdout, indent=2)


if __name__ == "__main__":
    main()
