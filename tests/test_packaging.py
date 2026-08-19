# -*- coding: utf-8 -*-
"""설치본 만들 재료가 갖춰졌나 (2026-08-19, §7 6단계 B).

    ~/venvs/unigrid-acdc/bin/python tests/test_packaging.py

만드는 것 자체(2~5분)는 여기서 안 돌린다. **만들기 전에 조용히 어긋날 것**을 본다 —
빠진 채로 만들면 앱은 뜨는데 계산만 안 되고, 그 원인을 고객 컴퓨터에서 찾게 된다.

보는 것
    1) 포장 설정·스크립트가 다 있나
    2) 🚨 spec 이 **같이 넣는 것 셋**(app_worker.py · engine · cases)을 담나
    3) 🚨 spec 이 `matlab`·엔진 패키지를 **일부러 빼나** (얼려 넣으면 판이 어긋난다)
    4) 앱이 실제로 쓰는 Qt 모듈이 **빼는 목록에 안 들었나** (빼면 앱이 안 뜬다)
    5) 윈도우 스크립트가 보는 자리가 PyInstaller 6 배치(`_internal/`)와 맞나
    6) 윈도우로 가는 파일은 **이름이 영문**인가 (지난 인계에서 한글이 깨졌다)
    7) `.iss` 가 UTF-8 BOM 인가 (Inno Setup 6 이 한글을 읽으려면)
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PKG = REPO / "packaging"
fails = []


def check(label, got, want):
    if got == want:
        print(f"  ✅ {label:<54} {got}")
    else:
        print(f"  ❌ {label:<54} {got}  (바라던 값 {want})")
        fails.append(label)


print("[1] 포장 재료가 다 있나")
for f in ("unigrid.spec", "build_mac.sh", "make_dmg.sh",
          "build_win.bat", "unigrid.iss", "README_before_install.txt"):
    check(f, (PKG / f).is_file(), True)

spec = (PKG / "unigrid.spec").read_text(encoding="utf-8")

print("\n[2] 🚨 같이 넣는 것 셋을 담나")
for what in ("app_worker.py", '"engine" / PKG', '"cases"'):
    check(f"spec 이 {what} 를 넣나", what in spec, True)

print("\n[3] 🚨 matlab·엔진 패키지를 일부러 빼나")
# 이것들은 MATLAB Runtime 쪽에 있고 **돌 때 sys.path 로** 찾는다.
# 얼려 넣으면 고객 Runtime 과 판이 어긋나 조용히 틀린 답이 나올 수 있다.
for name in ("matlab", "unigrid_app_mac", "unigrid_app_win"):
    check(f"excludes 에 {name}", f'"{name}"' in spec, True)

print("\n[4] 실제로 쓰는 Qt 모듈을 빼지는 않나")
used = set(re.findall(r"from PySide6\.(\w+)", "\n".join(
    p.read_text(encoding="utf-8") for p in (REPO / "src").glob("*.py"))))
print(f"    앱이 쓰는 것: {sorted(used)}")
for m in sorted(used):
    check(f"{m} 를 안 뺐나", f'"PySide6.{m}"' not in spec, True)

print("\n[5] 윈도우 스크립트가 보는 자리")
bat = (PKG / "build_win.bat").read_text(encoding="utf-8")
# PyInstaller 6 의 한 폴더 배치는 `dist/<이름>/_internal/…` 이다 (맥 산출물로 확인함)
check("_internal 을 보나", "_internal" in bat, True)
check("worker 를 확인하나", "app_worker.py" in bat, True)
check("엔진 .ctf 를 확인하나", "unigrid_app_win.ctf" in bat, True)

print("\n[6] 🚨 윈도우로 가는 파일 이름이 영문인가")
for f in PKG.iterdir():
    if f.is_dir() or f.name.startswith("."):
        continue
    if f.suffix in (".bat", ".iss") or f.name.startswith("README"):
        ascii_ok = f.name.isascii()
        check(f"{f.name}", ascii_ok, True)

print("\n[7] 🚨 라이선스 의무 — 지우면 배포 조건 위반")
# MathWorks 소프트웨어 라이선스 계약이 요구하는 것
#   3.26  앱에 사용 조건(EULA)이 있어야 배포할 수 있다
#   23.3  그 조건이 MATLAB Runtime 조건(MCR_license.txt)을 포함·참조해야 한다
#   205–210행  About 상자와 함께 배포하는 문서에 저작권 고지를 넣어야 한다
eula = REPO / "EULA.txt"
check("EULA.txt 가 있나", eula.is_file(), True)
et = eula.read_text(encoding="utf-8") if eula.is_file() else ""
check("MCR_license.txt 를 참조하나", "MCR_license.txt" in et, True)
check("MathWorks 고지가 있나", "The MathWorks, Inc." in et, True)
check("보증 안 함이 있나", "보증" in et, True)

appsrc = (REPO / "src" / "app.py").read_text(encoding="utf-8")
check("앱에 정보 창이 있나", "class AboutDialog" in appsrc, True)
check("정보 창에 저작권 고지", "1984-2024 The MathWorks, Inc." in appsrc, True)
# 🚨 고지에 **닿을 수 있어야** 뜻이 있다 — 시작 화면과 위쪽 줄 둘 다에서
check("정보 단추가 두 곳에 있나", appsrc.count('AboutDialog(self, c).exec()'), 2)

check("spec 이 EULA 를 넣나", "EULA.txt" in spec, True)
for f, why in [("build_mac.sh", "맥 빌드"), ("build_win.bat", "윈도우 빌드"),
               ("make_dmg.sh", "dmg")]:
    t = (PKG / f).read_text(encoding="utf-8")
    check(f"{why} 가 EULA 를 확인하나", "EULA.txt" in t, True)
iss = (PKG / "unigrid.iss").read_bytes().decode("utf-8-sig")
check("설치 중에 사용 조건을 띄우나", "LicenseFile" in iss, True)

print("\n[8] .iss 가 UTF-8 BOM 인가")
head = (PKG / "unigrid.iss").read_bytes()[:3]
check("BOM", head == b"\xef\xbb\xbf", True)

print("\n" + ("🚨 실패 " + ", ".join(fails) if fails else "✅ 전부 통과"))
sys.exit(1 if fails else 0)
