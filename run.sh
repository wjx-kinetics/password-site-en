#!/bin/sh
# macOS / Linux: "sh run.sh" 로 사이트를 시작합니다.
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
  echo "처음 실행: 가상환경을 만들고 패키지를 설치합니다. 1분쯤 걸립니다..."
  python3 -m venv .venv || exit 1
  .venv/bin/python -m pip install -q -r requirements.txt || exit 1
fi
exec .venv/bin/python app.py "$@"
