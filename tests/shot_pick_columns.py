# -*- coding: utf-8 -*-
"""「열 선택」 시험 (2026-08-27).

  ① 열 선택이 뜻 없는 탭에서는 **단추가 안 보인다**(점검·수렴).
     ⚠️ 계통 데이터는 2026-09-02 부터 **보인다** — 그때 실제로 도는 열 선택이 붙었다.
  ② 「전부 켜기 · 전부 끄기 · 처음대로」가 실제로 돈다.
  ③ 전부 끄고 [적용] 하면 막고 까닭을 말해 준다.
"""
import os, sys, time
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "shots_pick"; OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(REPO / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import warnings; warnings.filterwarnings("ignore")
from PySide6.QtWidgets import (QApplication, QDialog, QPushButton, QCheckBox,
                               QMessageBox)
qapp = QApplication([])
import app as APP
_msg = []
for _n in ("information", "warning", "critical"):
    setattr(QMessageBox, _n, staticmethod(
        lambda *a, **k: _msg.append(a[2] if len(a) > 2 else "")))
win = APP.Proto(); win.resize(1600, 1000); win.show()
ok = [0]; bad = []
def chk(n, got, want):
    if got == want: ok[0] += 1; print(f"  ✅ {n}")
    else: bad.append(n); print(f"  ❌ {n}: {got!r} ≠ {want!r}")
def pump(s=0.4):
    e = time.time()+s
    while time.time() < e: qapp.processEvents(); time.sleep(0.01)

win._start_solve(str(REPO/"cases/ACDC_case24_tapctrl.xlsx"))
e = time.time()+240
while time.time() < e:
    qapp.processEvents()
    if win.thread.isFinished(): break
    time.sleep(0.02)
pump(1.0)

print("[1] 단추가 보이는 탭 · 안 보이는 탭")
# ⚠️ **계통 데이터는 2026-09-02 에 False → True 로 뒤집혔다.** 2026-08-27 에 숨긴
#    까닭은 「필요 없어서」가 아니라 거기서 **죽어 있었기 때문**이다(`TABLE_SPECS` 에
#    없어 `KeyError`). 이제 `pick_grid_columns()` 가 받으므로 보이는 것이 맞다 —
#    IC 20 열이 1512px 창에서 903px 넘치는 그 표가 여기 있다.
for tab, want in [("AC 결과", True), ("DC 결과", True), ("선로 조류", True),
                  ("점검", False), ("수렴", False), ("계통 데이터", True)]:
    win.table_tab = tab; win.rebuild(); pump(0.25)
    seen = any(b.text().startswith("열 선택") and b.isVisible()
               for b in win.findChildren(QPushButton))
    chk(f"{tab} 단추 보임={want}", seen, want)

print("[2] 묶음 단추가 실제로 도나")
win.table_tab = "AC 결과"; win.rebuild(); pump(0.4)
SPEC = APP.TABLE_SPECS["AC 결과"]
grabbed = {}
def catch(self):
    """창을 사람 대신 잡는다 — 단추를 누르고 상태를 읽는다."""
    grabbed["d"] = self
    self.show(); qapp.processEvents(); pump(0.3)
    self.grab().save(str(OUT / "01_열선택_창.png"))
    return 0                       # 취소한 셈
QDialog.exec = catch
win.pick_columns()
d = grabbed["d"]
btn = {b.text(): b for b in d.findChildren(QPushButton)}
cbs = d.findChildren(QCheckBox)
chk("체크칸 수", len(cbs), len(SPEC))
chk("묶음 단추 셋 다 있나", all(k in btn for k in ("전부 켜기", "전부 끄기", "처음대로")), True)
btn["전부 켜기"].click(); pump(0.15)
chk("전부 켜기", sum(b.isChecked() for b in cbs), len(SPEC))
btn["전부 끄기"].click(); pump(0.15)
chk("전부 끄기", sum(b.isChecked() for b in cbs), 0)
btn["처음대로"].click(); pump(0.15)
chk("처음대로", {b.text() for b in cbs if b.isChecked()},
    {c for c, always in SPEC if always})
d.close()

print("[3] 전부 끄고 적용하면 막나")
def catch_off(self):
    for b in self.findChildren(QCheckBox):
        b.setChecked(False)
    return 1                       # [적용] 을 누른 셈
QDialog.exec = catch_off
_msg.clear()
before = set(win.visible["AC 결과"])
win.pick_columns(); pump(0.3)
chk("보이는 열이 그대로인가", set(win.visible["AC 결과"]), before)
chk("까닭을 말해 주나", bool(_msg) and "하나" in _msg[-1], True)

print("[4] 고른 것이 화면 표에 실제로 먹히나")
def cols_now(tab="AC 결과"):
    # 🚨 findChildren 은 아직 안 지워진 옛 표도 준다 — 앱이 들고 있는 것을 읽는다
    got = win._res_tables.get(tab)
    if got is None:
        return []
    tb = got[0]
    return [tb.horizontalHeaderItem(i).text() if tb.horizontalHeaderItem(i) else ""
            for i in range(tb.columnCount())]

win.table_tab = "AC 결과"; win.rebuild(); pump(0.5)
base = cols_now()
chk("처음엔 켜진 열만 나오나", set(base), set(win.visible["AC 결과"]))

def uncheck(names):
    def f(self):
        for b in self.findChildren(QCheckBox):
            if b.text() in names:
                b.setChecked(False)
        return 1
    return f

QDialog.exec = uncheck({"VM[pu]"})
win.pick_columns(); pump(0.5)
chk("끈 열이 화면에서 사라지나", "VM[pu]" in cols_now(), False)
chk("나머지는 그대로인가", set(cols_now()), set(base) - {"VM[pu]"})

# 🚨 버스 번호 열을 끄면 **열 자리가 밀린다** — 정수 표기·위반 표시가 그 자리를 쓴다
QDialog.exec = uncheck({"Bus"})
win.pick_columns(); pump(0.5)
now = cols_now()
chk("버스 열도 끌 수 있나", "Bus" in now, False)
tb = win._res_tables["AC 결과"][0]
first = tb.item(0, 0).text()
chk("첫 칸이 버스 번호로 안 찍히나", "." in first or first == "", True)
print(f"       (첫 칸 = {first!r} · 열 {now})")

QDialog.exec = lambda self: [b.setChecked(True) for b in self.findChildren(QCheckBox)] and 1
win.pick_columns(); pump(0.5)
chk("전부 켜면 엔진이 준 열이 다 나오나", len(cols_now()), 13)

print("[5] 계통을 바꿔도 「보는 탭」과 「기억하는 탭」이 안 갈리나")
def open_case(f):
    win._start_solve(str(REPO/"cases"/f))
    e = time.time()+240
    while time.time() < e:
        qapp.processEvents()
        if win.thread.isFinished(): break
        time.sleep(0.02)
    pump(0.9)

def cur_tab():
    return APP._tab_base(win._tabs.tabText(win._tabs.currentIndex()))

# 🚨 AC/DC 의 `DC 결과` 는 AC 전용에서 **통째로 사라지는 탭**이다 — 그때 기록만 남았다
open_case("ACDC_case24_tapctrl.xlsx")
for i in range(win._tabs.count()):
    if APP._tab_base(win._tabs.tabText(i)) == "DC 결과":
        win._tabs.setCurrentIndex(i); break
pump(0.4)
chk("AC/DC 에서 DC 결과 를 보고 있나", (cur_tab(), win.table_tab), ("DC 결과", "DC 결과"))
open_case("AConly_case118.xlsx")
chk("AC 전용을 열면 둘이 같은가", win.table_tab, cur_tab())
chk("첫 탭으로 갔나", cur_tab(), "AC 결과")
chk("그 탭에서 단추가 보이나",
    any(b.text().startswith("열 선택") and b.isVisible()
        for b in win.findChildren(QPushButton)), True)

print("═"*56)
print(f"  통과 {ok[0]} · 실패 {len(bad)}")
for b in bad: print(f"    ❌ {b}")
sys.exit(1 if bad else 0)
