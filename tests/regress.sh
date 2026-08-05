#!/usr/bin/env bash
# 회귀를 한 명령으로 (PDR §6 ①층).
#   ./tests/regress.sh            견주기
#   ./tests/regress.sh --save     지금 결과를 기준으로 삼기
#   ./tests/regress.sh --only 14  이름에 그 글자가 든 케이스만
#
# 파이썬 자리를 외우지 않아도 되게 감싼 것뿐이다.
set -e
cd "$(dirname "$0")/.."

VENV="$HOME/venvs/unigrid-acdc/bin/python"
PY="$VENV"
WHERE="정해둔 환경"
if [ ! -x "$PY" ]; then
    PY="$(command -v python3 || true)"
    WHERE="⚠️ 대체 — $VENV 가 없어 시스템 파이썬으로 돌립니다"
fi
if [ -z "$PY" ]; then
    echo "파이썬을 찾지 못했습니다. ~/venvs/unigrid-acdc 를 만들거나 python3 를 설치하세요."
    exit 2
fi

# 어느 환경에서 돌았는지 한 줄로 찍는다.
# 2026-08-06: 맥을 옮겼더니 ~/venvs 가 없어 **조용히** 시스템 파이썬으로 갈아탔다.
# 통과는 했지만 "무엇으로 돌아서 통과했는지"를 알 수 없었다 — 통과의 뜻이 흐려진다.
"$PY" - <<'PYEOF'
import sys
try:
    import numpy, pandas
    extra = f" · numpy {numpy.__version__} · pandas {pandas.__version__}"
except Exception as exc:
    extra = f"  ⚠️ {type(exc).__name__}: {exc}"
print(f"파이썬 {sys.version.split()[0]}{extra}")
print(f"  {sys.executable}")
PYEOF
echo "  $WHERE"
echo

exec "$PY" tests/regress.py "$@"
