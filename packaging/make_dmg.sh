#!/usr/bin/env bash
# UNIGRID 맥 배포 파일(.dmg) 만들기 (§7 6단계 B, 2026-08-19)
#
#   ./packaging/make_dmg.sh          # packaging/build_mac.sh 를 먼저 돌려 둘 것
#
# 만드는 것: packaging/dist/UNIGRID-<판>-mac.dmg
# 고객은 이 파일을 열어 **UNIGRID 를 Applications 로 끌어다 놓는다.**
#
# 맥 기본 도구(hdiutil)만 쓴다 — 별도 도구를 깔게 하지 않는다.
set -e
cd "$(dirname "$0")/.."

APP="packaging/dist/UNIGRID.app"
VER="${1:-$(date +%Y%m%d)}"
DMG="packaging/dist/UNIGRID-${VER}-mac.dmg"
STAGE="packaging/build/dmg_stage"

[ -d "$APP" ] || { echo "[UNIGRID] $APP 이 없다 — 먼저 ./packaging/build_mac.sh"; exit 1; }

# 🚨 **넣기 전에 속을 다시 본다.** .app 이 있다고 다 든 것이 아니다 —
#    worker·engine 이 빠진 앱도 겉보기엔 멀쩡히 뜬다(계산만 안 된다).
RES="$APP/Contents/Resources"
for f in "src/app_worker.py" "engine/unigrid_app_mac/unigrid_app_mac.ctf"; do
    [ -e "$RES/$f" ] || { echo "[UNIGRID] 앱 속에 없다: $f"; exit 1; }
done

rm -rf "$STAGE" "$DMG"
mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"       # 끌어다 놓을 자리

# 처음 켤 때 막히는 것을 안내한다 — 서명을 안 했으므로 반드시 필요하다
cat > "$STAGE/처음 켤 때 읽어 주세요.txt" <<'TXT'
UNIGRID — 맥에 설치하기

1) 왼쪽의 UNIGRID 를 오른쪽 Applications 로 끌어다 놓습니다.

2) 처음 한 번은 이렇게 엽니다.
   - 응용 프로그램에서 UNIGRID 를 엽니다. "확인되지 않은 개발자" 라며 막힙니다.
   - 시스템 설정 → 개인정보 보호 및 보안 을 엽니다.
   - 맨 아래까지 내려가 [그래도 열기] 를 누르고 암호를 넣습니다.
   두 번째부터는 그냥 열립니다.

3) 계산을 하려면 MATLAB Runtime R2024b 가 있어야 합니다.
   없으면 앱이 어디서 받아 어디에 까는지 알려 줍니다.
   ※ 판이 정확히 R2024b 여야 합니다. 다른 판은 안 됩니다.

만든 곳: 중앙대학교 GML
TXT

echo "[UNIGRID] .dmg 만드는 중…"
hdiutil create -volname "UNIGRID" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null
rm -rf "$STAGE"

echo "[UNIGRID] 다 됐다: $DMG  ($(du -sh "$DMG" | cut -f1))"
