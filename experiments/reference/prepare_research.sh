#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/../.."
source "$HOME/matsim-work/java-maven-env.sh"
mvn -o -Dmatsim.build.directory=target-research -DskipTests package
.venv/bin/python scripts/verify.py --jar target-research/matsim-nyc-modernized-1.0.0.jar
.venv/bin/python -m unittest discover -s experiments/reference -p 'test_*.py'
.venv/bin/python experiments/reference/run_reference.py inputs
snapshot=$(.venv/bin/python experiments/reference/snapshot.py)
printf '%s\n' "$snapshot" > "$HOME/matsim-work/latest-research-snapshot.txt"
printf 'Prepared snapshot: %s\n' "$snapshot"
if [[ "${1:-}" != --prepare-only ]]; then bash "$snapshot/experiments/reference/submit_research.sh" "${1:-validation}"; fi
