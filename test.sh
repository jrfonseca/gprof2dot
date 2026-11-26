#!/bin/sh
#
# Run the regression test suite locally, the same way CI does.
#
# Usage: ./test.sh [pytest options...]
#
# The Python version can be chosen via UV_PYTHON, e.g.:
#
#   UV_PYTHON=3.10 ./test.sh -k perf
#
set -eu
cd "$(dirname "$0")"
exec uv run python -m pytest -n auto "$@"
