# -*- coding: utf-8 -*-
"""1시각 계통을 24시각으로 늘린다 — **버스마다 다른 하루 모양**으로 (2026-09-08).

  앞판(09-07)의 결함 = 모든 버스에 *같은 배율 한 줄*을 곱해서, 다이나믹 그래프에서
  버스들이 평행하게만 오르내렸다. 무엇이 어디서 걸리는지가 안 보인다.

  이번 = 버스마다 **부하 유형**을 배정하고(주거·상업·산업·야간), 유형마다 다른
  하루 모양을 쓴다. 거기에 버스별 잡음(±4%)을 얹는다. `seed` 를 박아 **다시 돌려도
  같은 값**이 나온다.
"""
import sys
import numpy as np
import pandas as pd
from pathlib import Path

# ── 하루 모양 넷 (24시각, 1.0 = 그 버스의 평균)
def shapes():
    h = np.arange(24)
    # 주거 — 아침 작은 봉우리 + 저녁 큰 봉우리
    resid = (0.62
             + 0.30 * np.exp(-((h - 8.0) ** 2) / 4.5)
             + 0.75 * np.exp(-((h - 19.5) ** 2) / 7.0))
    # 상업 — 낮 한 봉우리 (업무 시간)
    comm = 0.42 + 0.95 * np.exp(-((h - 13.5) ** 2) / 16.0)
    # 산업 — 거의 평탄, 교대 시간에만 살짝
    indus = 0.93 + 0.10 * np.sin((h - 6) * np.pi / 12.0) ** 2
    # 야간 — 새벽에 크고 낮에 낮다 (야간 조업·축열)
    night = (0.55
             + 0.80 * np.exp(-((h - 3.0) ** 2) / 9.0)
             + 0.30 * np.exp(-((h - 23.5) ** 2) / 5.0))
    out = []
    for s in (resid, comm, indus, night):
        out.append(s / s.mean())          # 평균 1.0 으로 맞춘다
    return np.array(out)                  # (4, 24)


def system_curve(depth=0.18):
    """계통 전체 수요 곡선 — 버스별 유형 위에 한 겹 더 곱한다.

    유형만 쓰면 봉우리가 서로 어긋나 **합계가 거의 평평해진다**(첫 시험 21%).
    실제 계통 총수요는 하루에 30~50% 움직이므로 공통 곡선을 얹는다.
    """
    h = np.arange(24)
    c = (1.0
         - depth * np.cos((h - 15.0) * 2 * np.pi / 24.0)     # 오후 최대·새벽 최소
         + 0.35 * depth * np.exp(-((h - 20.0) ** 2) / 6.0))  # 저녁 첨두
    return c / c.mean()


TYPES = ["주거", "상업", "산업", "야간"]


def build(src: Path, dst: Path, *, seed=20260908, level=1.0, noise=0.04,
          dc_share=0.0, depth=0.18, verbose=True):
    """src(1시각) → dst(24시각).

    level    : 전체 부하 크기 (1.0 = 원본의 하루 평균이 원본 값)
    dc_share : DC 버스에 넣을 부하 [MW]. 0 이면 원본대로 0 을 둔다.
    """
    rng = np.random.default_rng(seed)
    SH = shapes()
    SYS = system_curve(depth)
    xl = pd.ExcelFile(src)
    sheets = {sh: pd.read_excel(src, sheet_name=sh, header=None)
              for sh in xl.sheet_names}

    # AC 버스마다 유형을 배정한다 — 버스 번호로 seed 해서 P·Q 가 같은 유형을 받게
    acp = sheets["AC P Consume Data"]
    bus_ids = acp.iloc[1:, 0].to_numpy()
    n_bus = len(bus_ids)
    kind = rng.integers(0, 4, size=n_bus)
    # 잡음도 버스마다 미리 뽑는다 (P·Q 가 같이 움직이게)
    jitter = rng.normal(0.0, noise, size=(n_bus, 24))

    info = []
    for name, unit in [("AC P Consume Data", "MW"), ("AC Q Consume Data", "Mvar")]:
        d = sheets[name]
        base = d.iloc[1:, 1].to_numpy(dtype=float)
        prof = SH[kind] * SYS[None, :] * (1.0 + jitter)   # (n_bus, 24)
        prof = np.clip(prof, 0.25, 2.2)
        arr = base[:, None] * prof * level
        out = pd.DataFrame(index=range(n_bus + 1), columns=range(25), dtype=object)
        out.iloc[0, 0] = f"Bus / 시각 [{unit}]"
        out.iloc[0, 1:] = list(range(1, 25))
        out.iloc[1:, 0] = bus_ids
        out.iloc[1:, 1:] = np.round(arr, 3)
        sheets[name] = out
        tot = arr.sum(axis=0)
        info.append((name, tot.min(), tot.max(), base.sum()))

    # DC 부하
    dcp = sheets["DC P Consume Data"]
    dc_ids = dcp.iloc[1:, 0].to_numpy()
    n_dc = len(dc_ids)
    dbase = pd.to_numeric(dcp.iloc[1:, 1], errors="coerce").fillna(0.0).to_numpy(float)
    have_dc = float(np.abs(dbase).sum()) > 0
    if have_dc or dc_share > 0:
        dkind = rng.integers(0, 4, size=n_dc)
        djit = rng.normal(0.0, noise, size=(n_dc, 24))
        dprof = np.clip(SH[dkind] * SYS[None, :] * (1.0 + djit), 0.25, 2.2)
        if have_dc:
            # 🚨 원본에 DC 부하가 **이미 있으면 그것을 늘린다** — 새 값으로 덮으면
            #    그 계통이 원래 지고 있던 몫이 사라져 IC 균형이 뒤집힌다.
            darr = dbase[:, None] * dprof * level
        else:
            scale = rng.uniform(0.6, 1.4, size=n_dc)   # 버스마다 크기를 조금씩 다르게
            darr = dc_share * scale[:, None] * dprof
    else:
        darr = np.zeros((n_dc, 24))
    out = pd.DataFrame(index=range(n_dc + 1), columns=range(25), dtype=object)
    out.iloc[0, 0] = "Bus / 시각 [MW]"
    out.iloc[0, 1:] = list(range(1, 25))
    out.iloc[1:, 0] = dc_ids
    out.iloc[1:, 1:] = np.round(darr, 3)
    sheets["DC P Consume Data"] = out

    with pd.ExcelWriter(dst, engine="openpyxl") as w:
        for sh in xl.sheet_names:
            sheets[sh].to_excel(w, sheet_name=sh, header=False, index=False)

    if verbose:
        print(f"  → {dst.name}")
        for nm, lo, hi, b in info:
            print(f"     {nm}: 시각 합계 {lo:.0f} ~ {hi:.0f}  "
                  f"(원본 1시각 {b:.0f} · 변동 {(hi/lo-1)*100:.0f}%)")
        cnt = {TYPES[k]: int((kind == k).sum()) for k in range(4)}
        print(f"     AC 버스 유형: {cnt}")
        if dc_share > 0:
            print(f"     DC 부하 시각 합계 {darr.sum(axis=0).min():.1f} ~ "
                  f"{darr.sum(axis=0).max():.1f} MW")
    return dst


# ── 지금 `cases/` 에 든 24시각 계통을 만든 값 (2026-09-08)
#    다시 만들려면:  ~/venvs/unigrid-acdc/bin/python tools/make_24h_case.py
MADE = [
    # (원본, 만들 것, level, dc_share, depth)
    ("ACDC_case24_MatACDC.xlsx", "ACDC_case24_MatACDC_24h.xlsx", 1.0, 40, 0.18),
    ("ACDC_71bus_3IC_parallel.xlsx", "ACDC_71bus_3IC_parallel_24h.xlsx", 1.0, 0, 0.35),
]
# 🚨 값을 함부로 올리지 말 것 — case24 는 `depth` 0.25 부터, DC 부하는 60 MW 부터
#    발산한다(2026-09-08 실측). 71bus 는 0.35 에서 주파수가 48.73~50.57 Hz 로 움직인다.

if __name__ == "__main__":
    C = Path(__file__).resolve().parent.parent / "cases"
    args = dict(a.split("=") for a in sys.argv[1:] if "=" in a)
    if args:
        build(C / args.get("src", "ACDC_case24_MatACDC.xlsx"),
              Path(args.get("out", "/tmp/case24_24h_시험.xlsx")),
              level=float(args.get("level", 1.0)),
              dc_share=float(args.get("dc", 0.0)),
              depth=float(args.get("depth", 0.18)))
    else:
        for src, dst, lv, dc, dp in MADE:
            build(C / src, C / dst, level=lv, dc_share=dc, depth=dp)
