#!/usr/bin/env bash
# 회귀를 한 명령으로 (PDR §6 ①층).
#   ./tests/regress.sh            견주기
#   ./tests/regress.sh --save     지금 결과를 기준으로 삼기
#   ./tests/regress.sh --only 14  이름에 그 글자가 든 케이스만
#
# 파이썬 자리를 외우지 않아도 되게 감싼 것뿐이다.
set -e
cd "$(dirname "$0")/.."

PY="$HOME/venvs/unigrid-acdc/bin/python"
if [ ! -x "$PY" ]; then
    PY="$(command -v python3 || true)"
fi
if [ -z "$PY" ]; then
    echo "파이썬을 찾지 못했습니다. ~/venvs/unigrid-acdc 를 만들거나 python3 를 설치하세요."
    exit 2
fi

exec "$PY" tests/regress.py "$@"
