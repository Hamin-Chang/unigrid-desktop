#!/usr/bin/env bash
# UNIGRID 맥 설치본 만들기 (§7 6단계 B, 2026-08-19)
#
#   ./packaging/build_mac.sh
#
# 만드는 것: packaging/dist/UNIGRID.app  (한 폴더 방식)
# ⚠️ 서명·공증은 **안 한다.** 고객에게 줄 때 붙인다(그때 앱을 다시 만들 필요는 없다).
set -e
cd "$(dirname "$0")/.."

PY="$HOME/venvs/unigrid-acdc/bin/python"
[ -x "$PY" ] || { echo "[UNIGRID] 파이썬을 못 찾음: $PY"; exit 1; }
"$PY" -c "import PyInstaller" 2>/dev/null || { echo "[UNIGRID] PyInstaller 가 없다 — $PY -m pip install pyinstaller"; exit 1; }

# 🚨 **넣을 것이 다 있는지 먼저 본다.** 없는 채로 만들면 앱은 뜨는데 계산이 안 되고,
#    그 원인을 고객 컴퓨터에서 찾게 된다.
for f in src/app.py src/app_worker.py engine/unigrid_app_mac/unigrid_app_mac.ctf; do
    [ -e "$f" ] || { echo "[UNIGRID] 없다: $f"; exit 1; }
done

echo "[UNIGRID] 얼리는 중… (2~5분)"
"$HOME/venvs/unigrid-acdc/bin/pyinstaller" packaging/unigrid.spec \
    --noconfirm --distpath packaging/dist --workpath packaging/build

APP="packaging/dist/UNIGRID.app"
RES="$APP/Contents/Resources"
echo ""
echo "[UNIGRID] 들어갔는지 확인"
ok=1
for f in "src/app_worker.py" "engine/unigrid_app_mac/unigrid_app_mac.ctf" "EULA.txt"; do
    if [ -e "$RES/$f" ]; then echo "   ✅ $f"; else echo "   ❌ $f 없음"; ok=0; fi
done
n=$(ls "$RES/cases" 2>/dev/null | wc -l | tr -d ' ')
echo "   예제 계통 $n 개"
[ "$ok" = 1 ] || { echo "[UNIGRID] 빠진 것이 있다 — 설치본으로 쓰면 안 된다"; exit 1; }

echo ""
echo "[UNIGRID] 다 됐다: $APP  ($(du -sh "$APP" | cut -f1))"
echo "   켜 보기:  open $APP"
echo "   ⚠️ 서명을 안 했으므로 남의 맥에서는 시스템 설정 → 개인정보 보호 및 보안 →"
echo "      맨 아래 「그래도 열기」 를 거쳐야 한다."
