#!/bin/sh
# macOS / Linux: start the site with "sh run.sh".
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
  echo "First run: creating a virtual environment and installing packages. This takes about a minute..."
  python3 -m venv .venv || exit 1
  .venv/bin/python -m pip install -q -r requirements.txt || exit 1
fi
exec .venv/bin/python app.py "$@"
