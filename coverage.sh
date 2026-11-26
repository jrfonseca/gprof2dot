#!/bin/sh
#
# Run the test suite with coverage, opening an HTML report when interactive.
#
# Usage: ./coverage.sh [pytest options...]
#
set -eu
cd "$(dirname "$0")"
if [ -t 0 ] && [ -t 1 ] && [ -t 2 ]
then
    report=html
else
    report=term
fi
./test.sh --cov --cov-report=$report "$@"
if [ $report = html ]
then
    xdg-open htmlcov/index.html
fi
