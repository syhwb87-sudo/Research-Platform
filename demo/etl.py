# -*- coding: utf-8 -*-
"""PRIDE Demo Dashboard ETL
CSV 6종(a1~a6)을 읽어 대시보드용 집계 데이터(demo_data.js)를 생성한다.
설계서 8장 Star Schema의 집계 결과물에 해당하며, 활용평가(fact_utilization)는
CSV에 실적값이 없으므로 시드 고정 난수로 시뮬레이션한다(화면에 DEMO 표기).

실행:  python3 demo/etl.py
출력:  demo/demo_data.js  (window.DEMO_DATA = {...})
"""
import csv
import json
import random
import re
from collections import Counter, defaultdict
from datetime import timedelta, date
from pathlib import Path

BASE = Path(__file__).parent
DATA = BASE / "data"
TODAY = date(2026, 8, 31)  # 데모 기준일 (데이터 최신일)
CUR_YEAR = TODAY.year

ACT = {1: "전략 프로젝트", 2: "장기 성과관리·확산", 3: "현업·고객 문제해결",
       4: "탐색·혁신", 5: "지식자산·전문활동", 6: "조직 성과·역량 강화"}

rng = random.Random(20260831)  # 재현 가능한 시뮬레이션


def read_csv(name):
    with open(DATA / name, encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    hdr = [h.strip() for h in rows[0]]
    out = []
    for r in rows[1:]:
        if not any(c.strip() for c in r):
            continue
        out.append({hdr[i]: (r[i].strip() if i < len(r) else "") for i in range(len(hdr))})
    return out


def money(s):
    s = re.sub(r"[^0-9.-]", "", s or "")
    try:
        return float(s) if s else 0.0
    except ValueError:
        return 0.0


def d(s):
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", (s or "").strip())
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def code_letter(code):
    m = re.match(r"^\s*\d{4}([A-Z])", code or "")
    return m.group(1) if m else ""


def classify(code):
    # 설계 규칙: W→현업, N→탐색, 그 외→전략.
    # Demo 확장: a2(ManWeek)에는 N코드 과제가 없어 L코드(신사업 시험과제)를
    # 탐색·혁신으로 간주한다. 실운영 시 PRIDE 과제유형 코드로 대체.
    letter = code_letter(code)
    if letter == "W":
        return 3
    if letter in ("N", "L"):
        return 4
    return 1


def eok(v):  # 원 → 억원
    return round(v / 1e8, 1)


# ──────────────────────────────── 로드 ────────────────────────────────
a1 = read_csv("a1_completion.csv")
a2 = read_csv("a2_manweek.csv")
a3 = read_csv("a3_projects.csv")
a4 = read_csv("a4_support.csv")
a5 = read_csv("a5_knowledge.csv")
a6 = read_csv("a6_promotion.csv")

# ─────────────────────────── a2: Man Week ───────────────────────────
MONTH_COLS = [f"{m}월" for m in range(1, 13)]
mw_monthly_act = defaultdict(lambda: defaultdict(float))   # ym -> act -> mw
mw_org_act = defaultdict(lambda: defaultdict(float))       # org -> act -> mw
mw_org_ym = defaultdict(lambda: defaultdict(float))        # org -> ym -> mw
person = {}                                                # name -> dict
person_projects = defaultdict(set)

def top_org(dept):
    dept = (dept or "").strip()
    if not dept:
        return "기타"
    first = dept.split()[0]
    if "연구소" in first or "연구원" in first:
        return first
    return "기타(파견/TF 등)"

person_ym = defaultdict(lambda: defaultdict(float))            # name -> ym -> mw
person_proj_mw = defaultdict(lambda: defaultdict(float))       # name -> 과제코드 -> mw
proj_name_map = {}                                             # 과제코드 -> 과제명

for r in a2:
    act = classify(r["과제코드"])
    year = r.get("연도구분", "").strip()
    if not year.isdigit():
        continue
    org = top_org(r["부서명"])
    name = r["연구원성명"]
    total = 0.0
    for i, col in enumerate(MONTH_COLS, start=1):
        v = money(r.get(col, ""))
        if v <= 0:
            continue
        ym = f"{year}-{i:02d}"
        mw_monthly_act[ym][act] += v
        mw_org_ym[org][ym] += v
        person_ym[name][ym] += v
        total += v
    if total <= 0:
        continue
    mw_org_act[org][act] += total
    p = person.setdefault(name, {"name": name, "org": org, "acts": defaultdict(float), "total": 0.0})
    p["acts"][act] += total
    p["total"] += total
    person_projects[name].add(r["과제코드"])
    person_proj_mw[name][r["과제코드"]] += total
    proj_name_map.setdefault(r["과제코드"], r["과제명"])

# 기준일 이후(계획) 데이터는 차트 축에서 제외
yms = [ym for ym in sorted(mw_monthly_act.keys())
       if ym <= f"{CUR_YEAR}-{TODAY.month:02d}" and sum(mw_monthly_act[ym].values()) > 0]
act_mw_total = defaultdict(float)
for ym in yms:
    for act, v in mw_monthly_act[ym].items():
        act_mw_total[act] += v

# 인당 부하 기준연도: 기준일 이전 연도 중 투입 MW가 가장 큰 해(= 최근 완전한 연도)
year_totals = defaultdict(float)
for ym in yms:
    year_totals[ym[:4]] += sum(mw_monthly_act[ym].values())
latest_year = max((y for y in year_totals if int(y) < CUR_YEAR), key=lambda y: year_totals[y])
latest_year_mw = year_totals[latest_year]
latest_year_people = {r["연구원성명"] for r in a2 if r.get("연도구분", "").strip() == latest_year
                      and any(money(r.get(c, "")) > 0 for c in MONTH_COLS)}

people_rows = sorted(person.values(), key=lambda p: -p["total"])[:80]
people_table = [{
    "name": p["name"], "org": p["org"],
    "a1": round(p["acts"].get(1, 0), 1), "a3": round(p["acts"].get(3, 0), 1),
    "a4": round(p["acts"].get(4, 0), 1), "total": round(p["total"], 1),
    "projects": len(person_projects[p["name"]]),
} for p in people_rows]

orgs_sorted = sorted(mw_org_act.keys(), key=lambda o: -sum(mw_org_act[o].values()))
org_stack = [{"org": o,
              "a1": round(mw_org_act[o].get(1, 0), 1),
              "a3": round(mw_org_act[o].get(3, 0), 1),
              "a4": round(mw_org_act[o].get(4, 0), 1)} for o in orgs_sorted]

heat_orgs = orgs_sorted[:10]
heat_yms = yms[-24:]
heatmap = [[oi, yi, round(mw_org_ym[o].get(ym, 0), 1)]
           for oi, o in enumerate(heat_orgs) for yi, ym in enumerate(heat_yms)]

# ─────────────────────────── a3: 연구과제 ───────────────────────────
proj_count_act = Counter()
proj_budget_act = defaultdict(float)
running_act = Counter()
upcoming = []
for r in a3:
    act = classify(r["과제코드"])
    proj_count_act[act] += 1
    proj_budget_act[act] += money(r["연구비"])
    if "진행중" in r.get("진행상태", ""):
        running_act[act] += 1
        end = d(r.get("완료일"))
        if end and 0 <= (end - TODAY).days <= 90:
            upcoming.append({"code": r["과제코드"], "name": r["과제명"][:34], "end": str(end)})
upcoming.sort(key=lambda x: x["end"])

# ─────────────────────────── a4: 현업지원 ───────────────────────────
sup_month_recv = Counter()
sup_month_done = Counter()
lead_times = []
req_dept = Counter()
sup_done = sup_open = sup_delayed_open = 0
effect_types = Counter()
for r in a4:
    rq, dn = d(r["요청일자"]), d(r["완료일"])
    if rq:
        sup_month_recv[f"{rq.year}-{rq.month:02d}"] += 1
    dept = r["요청부서"].split()[0] if r["요청부서"] else "기타"
    req_dept[dept] += 1
    st = r.get("진행상태", "")
    if dn or "완료" in st:
        sup_done += 1
        if dn:
            sup_month_done[f"{dn.year}-{dn.month:02d}"] += 1
            if rq:
                lead_times.append((dn - rq).days)
    elif "취소" in st:
        pass
    else:
        sup_open += 1
        if r.get("지연여부") == "지연":
            sup_delayed_open += 1
    if r.get("성과유형"):
        effect_types[r["성과유형"]] += 1

sup_total = len(a4)
sup_yms = sorted(set(sup_month_recv) | set(sup_month_done))[-12:]
support = {
    "total": sup_total, "done": sup_done, "open": sup_open,
    "doneRate": round(100 * sup_done / max(1, sup_total)),
    "avgLead": round(sum(lead_times) / max(1, len(lead_times))),
    "delayedOpen": sup_delayed_open,
    "months": sup_yms,
    "recv": [sup_month_recv.get(m, 0) for m in sup_yms],
    "doneM": [sup_month_done.get(m, 0) for m in sup_yms],
    "topDepts": req_dept.most_common(10),
    "effectTypes": effect_types.most_common(8),
}

# ─────────────────────────── a5: 지식자산 ───────────────────────────
know_year_type = defaultdict(Counter)
know_people = set()
for r in a5:
    dt = d(r["기안일자"])
    if not dt:
        continue
    know_year_type[dt.year][r["활동구분"]] += 1
    know_people.add(r["성명"])
know_years = sorted(know_year_type)
know_types = ["논문발표", "논문투고", "학회참가"]
know_cur = sum(know_year_type.get(CUR_YEAR, Counter()).values())
know_prev = sum(know_year_type.get(CUR_YEAR - 1, Counter()).values())
knowledge = {
    "years": know_years,
    "series": {t: [know_year_type[y].get(t, 0) for y in know_years] for t in know_types},
    "cur": know_cur, "prev": know_prev, "people": len(know_people),
    "papersCur": know_year_type.get(CUR_YEAR, Counter()).get("논문발표", 0)
    + know_year_type.get(CUR_YEAR, Counter()).get("논문투고", 0),
}

# ─────────────────────────── a6: 기술홍보 ───────────────────────────
promo_status = Counter(r["진행상태"] for r in a6)
promo_media = Counter()
for r in a6:
    m = r["홍보매체"].split(",")[0].strip() or "기타"
    promo_media[m] += 1
promotion = {
    "total": len(a6),
    "done": promo_status.get("완료", 0),
    "doneRate": round(100 * promo_status.get("완료", 0) / max(1, len(a6))),
    "media": promo_media.most_common(8),
    "groups": Counter(r["연구그룹"].split()[0] for r in a6 if r["연구그룹"]).most_common(8),
}

# ──────────────────── a1 + 활용평가 시뮬레이션 (DEMO) ────────────────────
EFFECT_COLS = ["생산성향상", "원단위절감", "제품개발/수입대체", "자재수명향상", "분석기술개발",
               "부산물/폐기물재활용", "신수요창출", "실수율/품질향상", "공정개선", "에너지절감",
               "장치제작개발", "자동화에의한인력합리", "환경비용절감", "기타"]
AXIS_MAP = {"신수요창출": "매출", "제품개발/수입대체": "매출", "원단위절감": "원가절감",
            "부산물/폐기물재활용": "원가절감", "생산성향상": "생산성", "공정개선": "생산성",
            "자동화에의한인력합리": "생산성", "장치제작개발": "생산성", "실수율/품질향상": "품질",
            "자재수명향상": "품질", "분석기술개발": "품질", "에너지절감": "환경",
            "환경비용절감": "환경", "기타": "원가절감"}
AXES = ["매출", "원가절감", "생산성", "품질", "안전", "환경"]
UNUSED_REASONS = ["조업조건 변경", "설비투자 보류", "활용부서 담당자 이동", "기술 완성도 부족",
                  "제품 수요 변화", "후속과제로 통합"]

effect_sum = Counter()
completed = []
for r in a1:
    cy_date = d(r["완료평가결재일"]) or d(r["완료일"])
    if not cy_date:
        continue
    annual = money(r["년간기대이익"])
    persist = money(r["기술지속년수"]) or 4
    for c in EFFECT_COLS:
        effect_sum[c] += money(r.get(c, ""))
    axis = AXIS_MAP.get(re.split(r"[,\s]", r.get("정량효과유형", "").strip() or "기타")[0], "원가절감")
    completed.append({
        "code": r["과제코드"], "name": r["과제명"], "type": r["과제유형"],
        "cy": cy_date.year, "cost": money(r["집행실적"]) or money(r["총연구비"]),
        "annual": annual, "persist": persist, "roi": money(r["투자효율"]),
        "useDept": r["활용부서"].split()[0] if r["활용부서"] else "미지정", "axis": axis,
        "qual": annual <= 0,
        "effect": re.split(r"[,\s]", r.get("정량효과유형", "").strip() or "기타")[0] or "기타",
        "start": r.get("착수일", ""), "rdept": r.get("연구부서", ""),
    })

util_year_status = defaultdict(Counter)          # 차수 -> 상태 -> n
realized_by_caly = defaultdict(float)            # 평가연도 -> 실현액
cost_by_caly = defaultdict(float)
dept_realized = Counter()
axis_realized = Counter()
unused_reasons = Counter()
cohort = defaultdict(lambda: {"exp": 0.0, "real": 0.0, "n": 0})
proj_results = []
evals_due = evals_done_n = 0
STATUS_P = {1: (.60, .22), 2: (.55, .24), 3: (.50, .25), 4: (.45, .25), 5: (.42, .24)}

for p in completed:
    cost_by_caly[p["cy"]] += p["cost"]
    n_years = max(0, min(5, CUR_YEAR - p["cy"]))
    if n_years == 0:
        continue
    exp_total = p["annual"] * min(n_years, p["persist"])
    real_total = 0.0
    last_status = None
    traj = []
    for yr in range(1, n_years + 1):
        evals_due += 1
        if rng.random() < 0.12:            # 평가 미실시 시뮬레이션
            continue
        evals_done_n += 1
        pu, pp = STATUS_P[yr]
        x = rng.random()
        status = "활용중" if x < pu else ("부분활용" if x < pu + pp else "미활용")
        if last_status == "미활용" and rng.random() < 0.7:
            status = "미활용"               # 미활용은 관성이 강함
        last_status = status
        traj.append(status)
        util_year_status[yr][status] += 1
        if p["qual"]:
            continue
        if yr > p["persist"]:
            continue
        factor = {"활용중": rng.uniform(.65, 1.1), "부분활용": rng.uniform(.2, .55), "미활용": 0.0}[status]
        amt = p["annual"] * factor
        real_total += amt
        realized_by_caly[p["cy"] + yr] += amt
        dept_realized[p["useDept"]] += amt
        axis_realized[p["axis"]] += amt
        if status == "미활용":
            unused_reasons[rng.choice(UNUSED_REASONS)] += 1
    if last_status == "미활용":
        unused_reasons[rng.choice(UNUSED_REASONS)] += 1
    c = cohort[p["cy"]]
    c["exp"] += exp_total
    c["real"] += real_total
    c["n"] += 1
    if not p["qual"] and exp_total > 0:
        proj_results.append({
            "code": p["code"], "name": p["name"][:30], "cy": p["cy"], "dept": p["useDept"],
            "exp": eok(exp_total), "real": eok(real_total),
            "achv": round(100 * real_total / exp_total),
            "cost": eok(p["cost"]), "status": last_status or "미평가", "traj": traj, "act": classify(p["code"]),
            "effect": p.get("effect", "기타"),
        })

tracked = [p for p in completed if CUR_YEAR - p["cy"] >= 1]
latest_status = Counter()
for p in tracked:
    yr = min(5, CUR_YEAR - p["cy"])
    # 최신 차수 상태를 근사: 차수별 상태 분포에서 가장 마지막 기록 이용
for yr, cnt in util_year_status.items():
    pass
# 최신 상태 분포: 각 과제의 마지막 평가 상태를 다시 시뮬레이션하지 않고
# proj_results status + 정성과제 비율로 집계
for pr in proj_results:
    latest_status[pr["status"]] += 1
qual_n = sum(1 for p in tracked if p["qual"])
util_rate = round(100 * (latest_status.get("활용중", 0) + 0.5 * latest_status.get("부분활용", 0))
                  / max(1, sum(latest_status.values())))
total_exp = sum(c["exp"] for c in cohort.values())
total_real = sum(c["real"] for c in cohort.values())
achievement = round(100 * total_real / max(1, total_exp))

cum_years = sorted(set(list(realized_by_caly) + list(cost_by_caly)))
cum_real = []
cum_cost = []
acc_r = acc_c = 0.0
for y in cum_years:
    acc_r += realized_by_caly.get(y, 0)
    acc_c += cost_by_caly.get(y, 0)
    cum_real.append(eok(acc_r))
    cum_cost.append(eok(acc_c))

unused_projects = [pr for pr in proj_results if pr["status"] == "미활용"]
sunk = sum(pr["cost"] for pr in unused_projects)
proj_sorted = sorted(proj_results, key=lambda x: -x["achv"])
top10 = proj_sorted[:10]
bottom10 = sorted([p for p in proj_sorted if p["exp"] >= 1], key=lambda x: x["achv"])[:10]

cohort_years = sorted(cohort)
longterm = {
    "tracked": len(tracked), "qualN": qual_n,
    "utilRate": util_rate, "achievement": achievement,
    "cumRealized": eok(total_real),
    "evalRate": round(100 * evals_done_n / max(1, evals_due)),
    "statusShare": {k: latest_status.get(k, 0) for k in ["활용중", "부분활용", "미활용"]},
    "yearly": {str(yr): {k: util_year_status[yr].get(k, 0) for k in ["활용중", "부분활용", "미활용"]}
               for yr in sorted(util_year_status)},
    "cohortYears": cohort_years,
    "cohortExp": [eok(cohort[y]["exp"]) for y in cohort_years],
    "cohortReal": [eok(cohort[y]["real"]) for y in cohort_years],
    "cumYears": cum_years, "cumReal": cum_real, "cumCost": cum_cost,
    "effectTreemap": [{"name": k, "value": eok(v)} for k, v in effect_sum.items() if v > 0],
    "deptLeaderboard": [[k, eok(v)] for k, v in dept_realized.most_common(10)],
    "axisRadar": [{"name": a, "value": eok(axis_realized.get(a, 0))} for a in AXES],
    "unusedPareto": unused_reasons.most_common(),
    "unusedSunk": round(sunk), "unusedN": len(unused_projects),
    "top10": top10, "bottom10": bottom10,
    "scatter": [[pr["cost"], pr["real"], pr["name"]] for pr in proj_results if pr["cost"] > 0][:250],
}

# ──────────────────────────── 종합/Executive ────────────────────────────
mw_a1 = act_mw_total.get(1, 0)
mw_a3 = act_mw_total.get(3, 0)
mw_a4 = act_mw_total.get(4, 0)
mw_all = mw_a1 + mw_a3 + mw_a4
explore_share = round(100 * mw_a4 / max(1, mw_all), 1)
bal_a = round(100 * mw_a1 / max(1, mw_a1 + mw_a3))

total_invest = sum(p["cost"] for p in completed) + sum(proj_budget_act.values())
top5 = sorted([p for p in completed if p["roi"] > 0 and p["annual"] > 0],
              key=lambda p: -p["roi"])[:5]

home = {
    "cards": [
        {"act": 1, "l1": f"진행 {running_act[1]}건", "l2": f"{round(mw_a1):,} MW"},
        {"act": 2, "l1": f"추적 {len(tracked)}건", "l2": f"활용률 {util_rate}%"},
        {"act": 3, "l1": f"금년 {sum(1 for r in a4 if (d(r['요청일자']) or TODAY).year == CUR_YEAR)}건",
         "l2": f"완료율 {support['doneRate']}%", "warn": f"지연 {support['delayedOpen']}건" if support['delayedOpen'] else ""},
        {"act": 4, "l1": f"진행 {running_act[4]}건", "l2": f"{round(mw_a4):,} MW"},
        {"act": 5, "l1": f"금년 {know_cur}건", "l2": f"활동인원 {knowledge['people']}명"},
        {"act": 6, "l1": f"금년 {promotion['total']}건", "l2": f"실행률 {promotion['doneRate']}%"},
    ],
    "portfolio": {
        "MW": [{"act": a, "value": round(act_mw_total.get(a, 0))} for a in (1, 3, 4)],
        "예산": [{"act": a, "value": eok(proj_budget_act.get(a, 0))} for a in (1, 3, 4)],
        "건수": [{"act": 1, "value": proj_count_act[1]}, {"act": 2, "value": len(completed)},
                 {"act": 3, "value": proj_count_act[3] + sup_total}, {"act": 4, "value": proj_count_act[4]},
                 {"act": 5, "value": len(a5)}, {"act": 6, "value": len(a6)}],
    },
    "balance": {"strategy": bal_a, "support": 100 - bal_a, "explore": explore_share,
                "exploreTarget": 15, "knowYoY": know_cur - know_prev,
                "mwPerPerson": round(latest_year_mw / max(1, len(latest_year_people)), 1)},
    "mwYms": yms, "mwMonthly": {str(a): [round(mw_monthly_act[ym].get(a, 0), 1) for ym in yms]
                                for a in (1, 3, 4)},
    "attention": {
        "delayedSupport": support["delayedOpen"],
        "evalMissed": evals_due - evals_done_n,
        "unusedOld": len(unused_projects),
        "upcoming": upcoming[:6],
        "feed": ([{"t": "논문발표", "s": f"{r['성명']} · {r['학회명'][:18]}", "d": r["기안일자"]}
                  for r in a5[:3]] +
                 [{"t": "기술홍보", "s": r["홍보제목"][:24], "d": r["홍보일"] or r["홍보예정일"]}
                  for r in a6[:3]]),
    },
}

executive = {
    "cards": {"invest": eok(total_invest), "investMW": round(mw_all),
              "realized": eok(total_real), "achv": achievement,
              "utilRate": util_rate, "balA": bal_a, "explore": explore_share},
    "top5": [{"name": p["name"][:26], "roi": p["roi"], "dept": p["useDept"],
              "annual": eok(p["annual"])} for p in top5],
    "alerts": [
        {"lv": "warn", "t": f"미활용 매몰 {round(sunk)}억원 ({len(unused_projects)}과제)"},
        {"lv": "warn", "t": f"탐색·혁신 비중 {explore_share}% — 목표 15% 대비 {15 - explore_share}%p 미달"}
        if explore_share < 15 else {"lv": "good", "t": f"탐색·혁신 비중 {explore_share}% 목표 달성"},
        {"lv": "warn", "t": f"활용평가 미실시 {evals_due - evals_done_n}건"},
        {"lv": "good", "t": f"현업지원 완료율 {support['doneRate']}% 양호"},
    ],
    "sankey": {
        "nodes": ["연구비", "전략 프로젝트", "현업·고객 문제해결", "탐색·혁신",
                  "완료·추적", "활용중", "부분활용", "미활용", "실현이익"],
        "links": [
            ["연구비", "전략 프로젝트", eok(proj_budget_act.get(1, 0))],
            ["연구비", "현업·고객 문제해결", eok(proj_budget_act.get(3, 0))],
            ["연구비", "탐색·혁신", max(1, eok(proj_budget_act.get(4, 0)))],
            ["전략 프로젝트", "완료·추적", eok(sum(p["cost"] for p in completed) * .7)],
            ["현업·고객 문제해결", "완료·추적", eok(sum(p["cost"] for p in completed) * .3)],
            ["완료·추적", "활용중", max(1, round(total_real / 1e8 * .68))],
            ["완료·추적", "부분활용", max(1, round(total_real / 1e8 * .22))],
            ["완료·추적", "미활용", max(1, round(sunk * .4))],
            ["활용중", "실현이익", max(1, round(total_real / 1e8 * .68))],
            ["부분활용", "실현이익", max(1, round(total_real / 1e8 * .22))],
        ],
    },
    "brief": (f"누적 실현이익은 {eok(total_real):,}억원으로 기대 대비 Achievement {achievement}%입니다. "
              f"장기 활용률은 {util_rate}%이며, 탐색·혁신 MW 비중({explore_share}%)이 목표(15%)"
              f"{'를 달성했습니다' if explore_share >= 15 else '에 미달해 포트폴리오 재배분 검토가 필요합니다'}. "
              f"미활용 과제 {len(unused_projects)}건의 매몰비용 {round(sunk)}억원에 대한 Revival 심의를 권고합니다."),
}

# ──────────────────── Phase 2: 활동군 상세 + 시뮬레이터 ────────────────────
def short(s, n):
    s = (s or "").strip()
    return s if len(s) <= n else s[:n - 1] + "…"

def dept_short(s):
    parts = (s or "").split()
    return parts[0] if parts else "기타"

# 4.1 전략 프로젝트 상세 (a3, W/N/L 제외)
strat_run = [r for r in a3 if classify(r["과제코드"]) == 1 and "진행중" in r.get("진행상태", "")]
tech_budget = defaultdict(float)
type_dist = Counter()
dept_cnt = Counter()
for r in strat_run:
    t = r.get("기술분류", "").strip()
    if t and t != "-":
        tech_budget[t] += money(r["연구비"])
    type_dist[r.get("과제유형", "기타")] += 1
    dept_cnt[dept_short(r.get("연구부서"))] += 1
strat_budget = sum(money(r["연구비"]) for r in strat_run)
strat_exec = sum(money(r["집행예산"]) for r in strat_run)
strategy_detail = {
    "kpi": {"running": len(strat_run), "budget": eok(strat_budget),
            "execRate": round(100 * strat_exec / max(1, strat_budget)),
            "mw": round(act_mw_total.get(1, 0))},
    "techTreemap": sorted([{"name": short(k, 22), "value": eok(v)}
                           for k, v in tech_budget.items() if v > 0],
                          key=lambda x: -x["value"])[:14],
    "typeDist": type_dist.most_common(7),
    "deptBar": dept_cnt.most_common(10),
    "projects": [{"code": r["과제코드"], "name": short(r["과제명"], 38),
                  "dept": dept_short(r.get("연구부서")), "leader": r.get("연구책임자", ""),
                  "budget": eok(money(r["연구비"])), "end": r.get("완료일", "")}
                 for r in sorted(strat_run, key=lambda x: -money(x["연구비"]))[:60]],
}

# 4.4 탐색·혁신 상세 (a3, N·L 코드)
expl = [r for r in a3 if classify(r["과제코드"]) == 4]
explore_detail = {
    "kpi": {"total": len(expl),
            "running": sum(1 for r in expl if "진행중" in r.get("진행상태", "")),
            "mw": round(act_mw_total.get(4, 0)),
            "share": round(100 * act_mw_total.get(4, 0)
                           / max(1, sum(act_mw_total.values())), 1)},
    "projects": [{"code": r["과제코드"], "name": short(r["과제명"], 38),
                  "dept": dept_short(r.get("연구부서")), "leader": r.get("연구책임자", ""),
                  "start": r.get("착수일", ""), "end": r.get("완료일", ""),
                  "status": short(r.get("진행상태", ""), 10)}
                 for r in sorted(expl, key=lambda x: x.get("착수일", ""), reverse=True)],
}

# 4.3 현업지원 상세
resp_stat = defaultdict(lambda: {"n": 0, "lead": [], "delay": 0})
for r in a4:
    resp = short(r.get("대응부서", "기타"), 20)
    s = resp_stat[resp]
    s["n"] += 1
    rq, dn = d(r["요청일자"]), d(r["완료일"])
    if rq and dn:
        s["lead"].append((dn - rq).days)
    if r.get("지연여부") == "지연":
        s["delay"] += 1
support_detail = {
    "byResp": sorted([[k, v["n"], round(sum(v["lead"]) / len(v["lead"])) if v["lead"] else 0]
                      for k, v in resp_stat.items()], key=lambda x: -x[1])[:8],
    "recent": [{"name": short(r["요청명"], 34), "resp": short(r.get("대응부서", ""), 18),
                "owner": r.get("대응담당자", ""), "status": short(r.get("진행상태", ""), 14),
                "delayed": r.get("지연여부") == "지연", "date": r.get("요청일자", "")}
               for r in a4[:40]],
}

# 4.5 지식자산 상세
know_tech = Counter()
know_dept = Counter()
for r in a5:
    t = r.get("기술분류", "").strip()
    if t:
        know_tech[short(t, 20)] += 1
    know_dept[dept_short(r.get("부서명"))] += 1
knowledge_detail = {
    "byTech": know_tech.most_common(10),
    "byDept": know_dept.most_common(8),
    "recent": [{"type": r["활동구분"], "person": r["성명"],
                "society": short(r.get("학회명", ""), 24), "date": r.get("기안일자", ""),
                "field": r.get("학회구분", "")} for r in a5[:25]],
}

# 4.6 조직역량 상세
promo_detail = {
    "list": [{"title": short(r["홍보제목"], 32), "media": short(r.get("홍보매체", ""), 14),
              "group": dept_short(r.get("연구그룹")), "owner": r.get("담당자", ""),
              "date": r.get("홍보일") or r.get("홍보예정일", ""),
              "status": r.get("진행상태", "")} for r in a6],
}

# 투입 시뮬레이터: 최근 6개월(기준일 이전) 월평균 부하
SIM_WINDOW = yms[-6:]
sim_orgs = []
for o in orgs_sorted:
    avg_m = sum(mw_org_ym[o].get(ym, 0) for ym in SIM_WINDOW) / len(SIM_WINDOW)
    ppl = {p["name"] for p in person.values() if p["org"] == o}
    if not ppl:
        continue
    sim_orgs.append({"org": o, "people": len(ppl), "avgMonthly": round(avg_m, 1),
                     "cap": round(len(ppl) * 4.3, 1)})
sim_people = []
for name, p in person.items():
    avg6 = sum(person_ym[name].get(ym, 0) for ym in SIM_WINDOW) / len(SIM_WINDOW)
    sim_people.append({"n": name, "o": p["org"], "a": round(avg6, 2)})
sim = {"window": [SIM_WINDOW[0], SIM_WINDOW[-1]], "capPerPerson": 4.3,
       "orgs": sim_orgs, "people": sim_people}

detail = {"strategy": strategy_detail, "explore": explore_detail,
          "support": support_detail, "knowledge": knowledge_detail, "promo": promo_detail}

# ──────────────────── My Dashboard (아이디어 27~34) ────────────────────
a3_status = {r["과제코드"]: short(r.get("진행상태", ""), 10) for r in a3}
util_by_code = {}
for pr_ in proj_results:
    util_by_code[pr_["code"]] = pr_
know_by_person = defaultdict(list)
for r in a5:
    know_by_person[r["성명"]].append(
        [r["활동구분"], short(r.get("학회명", ""), 22), r.get("기안일자", "")])
totals_sorted = sorted(p["total"] for p in person.values())
def percentile(total):
    import bisect
    return round(100 * bisect.bisect_left(totals_sorted, total) / max(1, len(totals_sorted)))
LATEST_YM = yms[-1]
me_people = {}
for name, p in person.items():
    projs = sorted(person_proj_mw[name].items(), key=lambda x: -x[1])
    impact = []
    for code, _mw in projs:
        u = util_by_code.get(code)
        if u:
            impact.append([short(u["name"], 26), u["cy"], u["status"], u["real"]])
        if len(impact) >= 6:
            break
    me_people[name] = {
        "o": p["org"],
        # 실제 참여 과제 총건수 (projects는 표시용 상위 8건이라 집계에 쓸 수 없음)
        "projN": len(person_projects[name]),
        "acts": [round(p["acts"].get(1, 0), 1), round(p["acts"].get(3, 0), 1),
                 round(p["acts"].get(4, 0), 1)],
        "ym": {ym: round(v, 1) for ym, v in person_ym[name].items() if v > 0 and ym <= LATEST_YM},
        "projects": [[c, short(proj_name_map.get(c, c), 30), round(m, 1),
                      a3_status.get(c, "-")] for c, m in projs[:8]],
        "impact": impact,
        "knowledge": know_by_person.get(name, [])[:6],
        "pct": percentile(p["total"]),
        "curYm": round(person_ym[name].get(LATEST_YM, 0), 1),
    }
org_avg_year = {o["org"]: round(o["avgMonthly"] / max(1, o["people"]) * 12, 1) for o in sim_orgs}
me = {"latestYm": LATEST_YM, "years": sorted({ym[:4] for ym in yms}),
      "orgAvgYear": org_avg_year,
      "allAvgYear": round(latest_year_mw / max(1, len(latest_year_people)), 1),
      "people": me_people}

# ──────────── P-1: 연구성과 자동산출 플랫폼 (목업, PRIDE_Performance_Platform_Design.md) ────────────
PERF_TYPES = [
    ["A-1", "A", "판매량증대"], ["A-2", "A", "판매가격인상"], ["A-3", "A", "고마진 Mix 확대"],
    ["A-4", "A", "주문외 판매감소"],
    ["B-1", "B", "구매단가 절감"], ["B-2", "B", "동일품목 원단위 절감"], ["B-3", "B", "저가원료 대체"],
    ["B-3(2)", "B", "부산물/배합비 변경"], ["B-4", "B", "변동가공비 절감"], ["B-5", "B", "변동가공비 단가절감"],
    ["B-6", "B", "수율 개선"], ["B-6(2)", "B", "수율 개선(매출이익형)"], ["B-7", "B", "공정생략"], ["B-8", "B", "고정가공비 절감"], ["B-9", "B", "생산량 증가"],
    ["C-1", "C", "판관비 절감"], ["C-1(2)", "C", "판관비 절감(총액형)"], ["C-2", "C", "클레임 비용 절감"],
]
# 연구효과 14종 → 재무성과 후보 매핑 (설계서 3.1)
EFFECT_MAP = {
    "신수요창출": ["A-1", "A-2", "A-3"],
    "제품개발/수입대체": ["A-1", "B-1", "B-3", "C-1"],
    "실수율/품질향상": ["A-4", "B-6", "B-6(2)", "C-2"],
    "원단위절감": ["B-2", "B-4", "B-5", "B-9"],
    "생산성향상": ["B-9", "B-8"],
    "공정개선": ["B-7", "B-4"],
    "에너지절감": ["B-2", "B-4"],
    "자재수명향상": ["B-8", "B-1"],
    "자동화에의한인력합리": ["B-8", "C-1"],
    "부산물/폐기물재활용": ["B-3(2)", "B-3"],
    "환경비용절감": ["B-4", "C-1"],
    "장치제작개발": ["B-8", "C-1(2)"],
    "분석기술개발": ["C-1", "C-1(2)"],
    "기타": [],
}
EROSION_CATALOG = {
    "A-1": ["기존제품 잠식", "잠식 품목 판매 감소량 × 해당 한계이익"],
    "A-2": ["판매량 감소(가격탄력)", "수량 감소분 × 한계이익"],
    "A-3": ["일반재 판매 감소", "일반재 감소량 × 일반재 마진"],
    "A-4": ["초기 품질비용 증가", "전환 초기 검사·클레임 비용 증가분"],
    "B-3": ["품질 저하 보정 비용", "후공정 처리비 증가분"],
    "B-7": ["품질 리스크 비용", "불량률 변동 × 처리비"],
}
# ── 성과 총액 산식 18종 (재무실 세부 산식 v1). 화면 명칭 "성과 총액", 식별자는 Rule Bank(RB-*) 유지.
#    expr: 곱셈항 리스트의 합 (Σ Π term). term = {"d":[후, 전]} 차이 | {"v":변수} 값.
#    varsDef: n 변수명 · u 단위 · s 원천 · lock 재무실 잠금 · r 목업 표본 범위 · dec 소수 · pct 백분율(계산 시 /100)
#    solve: 목업에서 성과총액에 맞춰 역산하는 변수(곱셈항별 1개). keys: 대상 식별 Key(KEY_DICT 참조).
KEY_DICT = {
    "강종": ["MM 자재마스터 · 강종코드", "제품 강종"], "품명": ["SD 품목마스터 · 품명코드", "제품 품명"],
    "규격약호": ["SD 품목마스터 · 규격약호", "치수·규격"], "고객사코드": ["SD 거래처마스터", "판매 고객"],
    "용도코드": ["SD 수주 · 용도코드", "최종 용도"], "내수/수출구분": ["SD 수주 · 판매구분", "내수·수출"],
    "신규고객여부": ["SD 거래처마스터 · 최초거래일", "신규 고객 판정"], "판매인식기간": ["등록 시 지정", "기준/검증 판매 인식기간"],
    "Extra코드": ["SD 가격조건 · Extra 코드(사이즈/품질/성분/표면)", "Extra 가격 항목"], "FOB가격적용기간": ["SD 가격조건 · 적용기간", "FOB 적용기간"],
    "고마진 제품군 코드": ["SD 품목마스터 · WIP 제품군", "고마진(WIP) 분류"], "일반재 대비 분류 기준": ["재무실 고시", "고마진/일반재 구분 기준"],
    "강종군": ["MM 자재마스터 · 강종군", "강종 그룹"], "고객용도 코드": ["SD 수주 · 용도코드", "고객 용도"], "Mix측정기간": ["등록 시 지정", "구성비 측정기간"],
    "주문외/등급하향 코드": ["품질 DW · 등급판정", "주문외·등급하향 사유"], "결함코드": ["품질 DW · 결함코드", "결함 유형"], "품질등급": ["품질 DW · 품질등급", "판정 등급"],
    "측정기간": ["등록 시 지정", "기준/검증 측정기간"], "원료/재료 코드": ["MM 자재마스터", "원료·재료"], "공급사코드": ["MM 공급사마스터", "공급사"],
    "구매계약기간": ["MM 구매계약", "계약 적용기간"], "대상 공장/공정": ["PP 작업장 · 공정코드", "적용 공장·공정"],
    "대상 품목 코드": ["MM 자재마스터 (결함재/연료/용수/Roll/약품)", "원단위 관리 품목"], "공장/공정/설비": ["PP 설비마스터", "적용 설비"],
    "고가/저가 원료코드": ["MM 자재마스터", "대체 전후 원료"], "대상 공정": ["PP 공정코드 (고로·소결 등)", "적용 공정"],
    "배합 원료코드": ["MM 자재마스터 (분탄·무연탄·가공부산물)", "배합 원료"], "배합 공정": ["PP 공정코드", "배합 공정"],
    "변동가공비 항목": ["CO 원가요소 (LNG/COG/용수/산세액/산소/약품)", "변동가공비 항목"], "공장/공정": ["PP 작업장", "적용 공장·공정"],
    "공급 계약/요금제": ["MM 구매계약 · 요금제", "단가 계약"], "외주 항목": ["MM 외주계약", "외주 항목"],
    "공정코드": ["PP 공정코드", "적용 공정"], "설비번호": ["PM 설비마스터", "적용 설비"], "수율/실수율 코드": ["생산 DW · 수율 지표코드", "수율 지표"],
    "강종제품 코드": ["MM 자재마스터", "제품 코드"], "판매연계 인증 데이터": ["SD 판매실적 · 품질 DW 연계", "증량분 판매 인증"],
    "생략 공정 코드": ["PP 공정코드 (소둔/산세/정정 등)", "생략 공정"], "대체 공정 코드": ["PP 공정코드", "대체 공정"], "강종제품": ["MM 자재마스터", "제품"],
    "비용항목코드": ["CO 원가요소", "비용 항목"], "비용센터": ["CO 코스트센터", "비용 귀속 조직"], "원가계정": ["FI 계정과목", "회계 계정"], "대상 조직/설비": ["CO 코스트센터 · PM 설비", "적용 조직·설비"],
    "공장/라인/설비번호": ["PP 작업장 · PM 설비", "적용 라인"], "생산성 코드": ["생산 DW (T/H, Ch/D)", "생산성 지표"], "가동률": ["생산 DW", "설비 가동률"], "작업률": ["생산 DW", "작업률"],
    "판관비 항목": ["FI 판관비 계정 (물류/포장/검사/보관/수수료)", "판관비 항목"], "대상 제품/고객/물류 경로": ["SD 수주 · 물류 DW", "적용 대상"],
    "Work Order/설비": ["PM 작업오더", "정비 대상"], "외주 계약 항목": ["MM 외주계약", "외주 항목"],
    "클레임 코드": ["품질 DW · 클레임코드", "클레임 유형"], "결함 코드": ["품질 DW · 결함코드", "결함 유형"], "대상 제품/고객": ["SD 수주", "적용 제품·고객"],
}
def _v(n, u, s, r, dec=0, lock=False, pct=False):
    return {"n": n, "u": u, "s": s, "r": r, "dec": dec, "lock": lock, "pct": pct}
RULES = [
    {"id": "RB-A1-003", "type": "A-1", "ver": "v2", "status": "승인", "period": "2026-01-01 ~", "source": "ERP SD · CO",
     "subtitle": "판매량 증대", "pattern": "DIFF",
     "formula": "(개선 후 판매량 − 개선 전 판매량) × 톤당 한계이익",
     "expr": [[{"d": ["개선 후 판매량", "개선 전 판매량"]}, {"v": "톤당 한계이익"}]],
     "varsDef": [_v("개선 후 판매량", "톤", "ERP SD 판매실적 (검증기간·지정 Key)", [8000, 60000]), _v("개선 전 판매량", "톤", "ERP SD 판매실적 (착수 직전 12개월)", [8000, 60000]),
                 _v("톤당 한계이익", "원/톤", "CO 관리회계 공식값", [120000, 300000], lock=True)],
     "solve": ["개선 후 판매량"],
     "keys": ["강종", "품명", "규격약호", "고객사코드", "용도코드", "내수/수출구분", "신규고객여부"], "periodKey": "판매인식기간",
     "notes": ["기존 제품 잠식분은 역효과(④)에서 차감 — 총액 산식에는 반영하지 않는다", "신규고객여부 Key로 신수요 창출과 기존 고객 증량을 구분"],
     "history": ["v1 2025-01 최초 제정", "v2 2026-03 기준기간 정의 변경(재무실)"]},
    {"id": "RB-A2-001", "type": "A-2", "ver": "v1", "status": "승인", "period": "2025-01-01 ~", "source": "ERP SD",
     "subtitle": "판매가격 인상", "pattern": "ADD",
     "formula": "(개선 후 FOB − 개선 전 FOB) × 판매량 + Extra 인상액 × Extra 대상 판매량",
     "expr": [[{"d": ["개선 후 FOB", "개선 전 FOB"]}, {"v": "판매량"}], [{"v": "Extra 인상액"}, {"v": "Extra 대상 판매량"}]],
     "varsDef": [_v("개선 후 FOB", "원/톤", "ERP SD 수출단가 (검증기간)", [900000, 1500000]), _v("개선 전 FOB", "원/톤", "ERP SD 수출단가 (기준기간)", [900000, 1500000]),
                 _v("판매량", "톤", "ERP SD 판매실적", [5000, 40000]), _v("Extra 인상액", "원/톤", "SD 가격조건 · Extra 코드", [3000, 20000]), _v("Extra 대상 판매량", "톤", "ERP SD 판매실적 (Extra 적용분)", [1000, 10000])],
     "solve": ["개선 후 FOB", "Extra 대상 판매량"],
     "keys": ["강종", "품명", "고객사코드", "Extra코드", "용도코드"], "periodKey": "FOB가격적용기간",
     "notes": ["기본항(FOB 인상)과 가산항(Extra)을 분리 산출 — Extra 코드가 개발 기술과 직접 연동되면 기여율 상향 조건(⑤)", "시황에 의한 전반적 단가 상승은 공통-8 외부요인으로 점검"],
     "history": ["v1 2025-01 최초 제정"]},
    {"id": "RB-A3-001", "type": "A-3", "ver": "v1", "status": "승인", "period": "2026-01-01 ~", "source": "ERP SD · CO",
     "subtitle": "고마진 Mix 확대", "pattern": "RATIO",
     "formula": "(개선 후 고마진 구성비 − 개선 전 고마진 구성비) × 판매량 × (고마진 한계이익 − 일반 한계이익)",
     "expr": [[{"d": ["개선 후 고마진 구성비", "개선 전 고마진 구성비"]}, {"v": "판매량"}, {"v": "한계이익 차이(고마진−일반)"}]],
     "varsDef": [_v("개선 후 고마진 구성비", "%", "ERP SD 판매실적 · WIP 제품군 (검증기간)", [20, 60], dec=1, pct=True), _v("개선 전 고마진 구성비", "%", "ERP SD 판매실적 (기준기간)", [20, 60], dec=1, pct=True),
                 _v("판매량", "톤", "ERP SD 판매실적 (강종군 전체)", [50000, 300000]), _v("한계이익 차이(고마진−일반)", "원/톤", "CO 관리회계 공식값", [40000, 150000], lock=True)],
     "solve": ["개선 후 고마진 구성비"],
     "keys": ["고마진 제품군 코드", "일반재 대비 분류 기준", "강종군", "고객용도 코드"], "periodKey": "Mix측정기간",
     "notes": ["일반재 판매 축소·고정비 회수 저하는 역효과(④)에서 점검", "A-1 판매량 증대와 동일 물량 중복 계상 금지"],
     "history": ["v1 2026-01 최초 제정"]},
    {"id": "RB-A4-001", "type": "A-4", "ver": "v1", "status": "승인", "period": "2025-07-01 ~", "source": "품질 DW · ERP SD",
     "subtitle": "주문외 판매 감소", "pattern": "RATIO",
     "formula": "(개선 전 주문외율 − 개선 후 주문외율) × 판매량 × (정상가 − 주문외가)",
     "expr": [[{"d": ["개선 전 주문외율", "개선 후 주문외율"]}, {"v": "판매량"}, {"v": "가격차(정상가−주문외가)"}]],
     "varsDef": [_v("개선 전 주문외율", "%", "품질 DW 주문외 실적 (기준기간)", [2, 8], dec=2, pct=True), _v("개선 후 주문외율", "%", "품질 DW 주문외 실적 (검증기간)", [1, 6], dec=2, pct=True),
                 _v("판매량", "톤", "ERP SD 판매실적", [50000, 300000]), _v("가격차(정상가−주문외가)", "원/톤", "ERP SD 단가", [30000, 90000])],
     "solve": ["개선 전 주문외율"],
     "keys": ["강종", "품명", "주문외/등급하향 코드", "결함코드", "용도코드", "품질등급"], "periodKey": "측정기간",
     "notes": ["B-6 수율 개선과 동일한 불량 감소량을 이중 계상하지 않도록 결함코드 Key 일치 확인"],
     "history": ["v1 2025-07 최초 제정"]},
    {"id": "RB-B1-001", "type": "B-1", "ver": "v1", "status": "승인", "period": "2026-01-01 ~", "source": "ERP MM",
     "subtitle": "구매단가 절감", "pattern": "DIFF",
     "formula": "(개선 전 단가 − 개선 후 단가) × 구매량",
     "expr": [[{"d": ["개선 전 단가", "개선 후 단가"]}, {"v": "구매량"}]],
     "varsDef": [_v("개선 전 단가", "원/톤", "ERP MM 구매단가 (기준기간)", [200000, 800000]), _v("개선 후 단가", "원/톤", "ERP MM 구매단가 (검증기간)", [200000, 800000]),
                 _v("구매량", "톤", "ERP MM 입고실적", [10000, 200000])],
     "solve": ["개선 전 단가"],
     "keys": ["원료/재료 코드", "공급사코드", "대상 공장/공정"], "periodKey": "구매계약기간",
     "notes": ["시황에 따른 원료가 하락(공통-8)과 협상·대체 검증에 의한 절감을 분리", "B-3 저가원료 대체와 동일 품목 중복 금지"],
     "history": ["v1 2026-01 최초 제정"]},
    {"id": "RB-B2-002", "type": "B-2", "ver": "v3", "status": "승인", "period": "2026-04-01 ~", "source": "생산 DW · ERP MM",
     "subtitle": "동일품목 원단위 절감", "pattern": "DIFF",
     "formula": "(개선 전 원단위 − 개선 후 원단위) × 단가 × 생산량",
     "expr": [[{"d": ["개선 전 원단위", "개선 후 원단위"]}, {"v": "단가"}, {"v": "생산량"}]],
     "varsDef": [_v("개선 전 원단위", "kg/톤", "생산 DW 원단위 실적 (기준기간)", [12, 40], dec=2), _v("개선 후 원단위", "kg/톤", "생산 DW 원단위 실적 (검증기간)", [12, 40], dec=2),
                 _v("단가", "원/kg", "ERP MM 구매단가 (기준월 고정)", [300, 1200], lock=True), _v("생산량", "톤", "생산 DW", [50000, 400000])],
     "solve": ["개선 전 원단위"],
     "keys": ["대상 품목 코드", "공장/공정/설비", "강종군"], "periodKey": "측정기간",
     "notes": ["동일 품목·동일 생산량 기준 비교 (품목 Mix 변화 효과 제외)", "단가는 기준월로 고정해 가격 변동 효과 배제"],
     "history": ["v1 2025-01", "v2 2025-09 에너지 원단위 포함", "v3 2026-04 단가 기준월 고정"]},
    {"id": "RB-B3-001", "type": "B-3", "ver": "v1", "status": "승인", "period": "2026-01-01 ~", "source": "생산 DW · ERP MM",
     "subtitle": "저가원료 대체 ① (성분보정)", "pattern": "ADJ",
     "formula": "(개선 후 저가품 원단위 − 개선 전 저가품 원단위) × 성분대체율 × 단가차 × 생산량",
     "expr": [[{"d": ["개선 후 저가품 원단위", "개선 전 저가품 원단위"]}, {"v": "성분대체율"}, {"v": "단가차(고가−저가)"}, {"v": "생산량"}]],
     "varsDef": [_v("개선 후 저가품 원단위", "kg/톤", "생산 DW 원료 원단위 (검증기간)", [50, 300], dec=1), _v("개선 전 저가품 원단위", "kg/톤", "생산 DW 원료 원단위 (기준기간)", [50, 300], dec=1),
                 _v("성분대체율", "%", "기술 검증 보고 (성분 등가 환산)", [60, 95], dec=1, pct=True), _v("단가차(고가−저가)", "원/kg", "ERP MM 구매단가", [30, 200]), _v("생산량", "톤", "생산 DW", [100000, 500000])],
     "solve": ["개선 후 저가품 원단위"],
     "keys": ["고가/저가 원료코드", "대상 공정", "강종군"], "periodKey": "측정기간",
     "notes": ["성분대체율은 등가 환산 계수 — 기술 검증 보고에 근거하며 재무실 확인 대상", "품질 저하·정련 부하는 역효과(④)에서 차감"],
     "history": ["v1 2026-01 최초 제정"]},
    {"id": "RB-B32-001", "type": "B-3(2)", "ver": "v1", "status": "승인", "period": "2026-01-01 ~", "source": "생산 DW · ERP MM",
     "subtitle": "저가원료 대체 ② (배합비 변화)", "pattern": "ADJ",
     "formula": "(개선 후 사용비 − 개선 전 사용비) × 성분대체율 × 단가차 × 생산량",
     "expr": [[{"d": ["개선 후 사용비", "개선 전 사용비"]}, {"v": "성분대체율"}, {"v": "단가차(고가−저가)"}, {"v": "생산량"}]],
     "varsDef": [_v("개선 후 사용비", "%", "생산 DW 배합 실적 (검증기간)", [10, 50], dec=1, pct=True), _v("개선 전 사용비", "%", "생산 DW 배합 실적 (기준기간)", [10, 50], dec=1, pct=True),
                 _v("성분대체율", "%", "기술 검증 보고", [60, 95], dec=1, pct=True), _v("단가차(고가−저가)", "원/톤", "ERP MM 구매단가", [20000, 120000]), _v("생산량", "톤", "생산 DW", [100000, 500000])],
     "solve": ["개선 후 사용비"],
     "keys": ["배합 원료코드", "배합 공정", "강종군"], "periodKey": "측정기간",
     "notes": ["사용비는 배합 중 저가 원료 비율 — 부산물 활용 성과와 환경비용 절감 성과의 중복 확인"],
     "history": ["v1 2026-01 최초 제정"]},
    {"id": "RB-B4-001", "type": "B-4", "ver": "v1", "status": "승인", "period": "2026-01-01 ~", "source": "생산 DW · ERP CO",
     "subtitle": "변동가공비 원단위 절감", "pattern": "DIFF",
     "formula": "(개선 전 원단위 − 개선 후 원단위) × 단가 × 생산량",
     "expr": [[{"d": ["개선 전 원단위", "개선 후 원단위"]}, {"v": "단가"}, {"v": "생산량"}]],
     "varsDef": [_v("개선 전 원단위", "단위/톤", "생산 DW 변동가공비 항목 원단위 (기준기간)", [5, 60], dec=2), _v("개선 후 원단위", "단위/톤", "생산 DW (검증기간)", [5, 60], dec=2),
                 _v("단가", "원/단위", "CO 원가요소 단가 (기준월 고정)", [100, 2000], lock=True), _v("생산량", "톤", "생산 DW", [50000, 400000])],
     "solve": ["개선 전 원단위"],
     "keys": ["변동가공비 항목", "공장/공정"], "periodKey": "측정기간",
     "notes": ["항목(LNG/COG/용수/산세액/산소/약품 등)을 먼저 선택하고 원단위를 정의", "절감 운전에 따른 설비 부하는 역효과(④)에서 점검"],
     "history": ["v1 2026-01 최초 제정"]},
    {"id": "RB-B5-001", "type": "B-5", "ver": "v1", "status": "승인", "period": "2026-01-01 ~", "source": "ERP MM · CO",
     "subtitle": "변동가공비 단가 절감", "pattern": "DIFF",
     "formula": "(개선 전 단가 − 개선 후 단가) × 원단위 × 생산량",
     "expr": [[{"d": ["개선 전 단가", "개선 후 단가"]}, {"v": "원단위"}, {"v": "생산량"}]],
     "varsDef": [_v("개선 전 단가", "원/단위", "MM 계약단가·요금제 (기준기간)", [100, 2000]), _v("개선 후 단가", "원/단위", "MM 계약단가·요금제 (검증기간)", [100, 2000]),
                 _v("원단위", "단위/톤", "생산 DW (기준 원단위 고정)", [5, 60], dec=2, lock=True), _v("생산량", "톤", "생산 DW", [50000, 400000])],
     "solve": ["개선 전 단가"],
     "keys": ["변동가공비 항목", "공급 계약/요금제", "외주 항목"], "periodKey": "측정기간",
     "notes": ["요금제·계약 협상이 주요 요인이면 기여율 하향 조건(⑤)", "타 에너지원 전이는 역효과(④)에서 점검"],
     "history": ["v1 2026-01 최초 제정"]},
    {"id": "RB-B6-002", "type": "B-6", "ver": "v1", "status": "승인", "period": "2025-01-01 ~", "source": "생산 DW · ERP CO",
     "subtitle": "수율 개선 ① (고정비형)", "pattern": "RATIO",
     "formula": "(개선 후 수율 − 개선 전 수율) × 처리량 × 해당 공정 가공비",
     "expr": [[{"d": ["개선 후 수율", "개선 전 수율"]}, {"v": "처리량"}, {"v": "해당 공정 가공비"}]],
     "varsDef": [_v("개선 후 수율", "%", "생산 DW 수율/실수율 (검증기간)", [90, 97], dec=3, pct=True), _v("개선 전 수율", "%", "생산 DW 수율/실수율 (기준기간)", [88, 95], dec=3, pct=True),
                 _v("처리량", "톤", "생산 DW", [100000, 600000]), _v("해당 공정 가공비", "원/톤", "CO 공정원가 (잠금)", [150000, 400000], lock=True)],
     "solve": ["개선 후 수율"],
     "keys": ["공정코드", "설비번호", "강종군", "수율/실수율 코드"], "periodKey": "측정기간",
     "notes": ["증량분이 판매로 이어져 매출이익이 발생하면 B-6(2) 매출이익형으로 등록 (중복 금지)"],
     "history": ["v1 2025-01 최초 제정"]},
    {"id": "RB-B62-001", "type": "B-6(2)", "ver": "v1", "status": "검토중", "period": "2026-07-01 ~", "source": "생산 DW · ERP SD",
     "subtitle": "수율 개선 ② (매출이익형)", "pattern": "RATIO",
     "formula": "(개선 후 수율 − 개선 전 수율) × 처리량 × (FOB − 추가판매비 − Scrap 단가)",
     "expr": [[{"d": ["개선 후 수율", "개선 전 수율"]}, {"v": "처리량"}, {"v": "판매 마진(FOB−추가판매비−Scrap단가)"}]],
     "varsDef": [_v("개선 후 수율", "%", "생산 DW 수율 (검증기간)", [90, 97], dec=3, pct=True), _v("개선 전 수율", "%", "생산 DW 수율 (기준기간)", [88, 95], dec=3, pct=True),
                 _v("처리량", "톤", "생산 DW", [100000, 600000]), _v("판매 마진(FOB−추가판매비−Scrap단가)", "원/톤", "ERP SD 단가 · 판관비 · 스크랩 시세", [200000, 700000])],
     "solve": ["개선 후 수율"],
     "keys": ["공정코드", "설비번호", "강종제품 코드", "수율/실수율 코드", "판매연계 인증 데이터"], "periodKey": "측정기간",
     "notes": ["증량분이 실제 판매되었음을 판매연계 인증 데이터로 입증해야 적용 — 인증 데이터 정의 재무실 검토중", "B-6 고정비형과 동일 증량분 중복 계상 금지"],
     "history": ["v1 2026-07 제정안 (판매연계 인증 데이터 정의 검토중)"]},
    {"id": "RB-B7-001", "type": "B-7", "ver": "v1", "status": "승인", "period": "2025-01-01 ~", "source": "생산 DW · CO",
     "subtitle": "공정생략·변동가공비 절감", "pattern": "DIFF",
     "formula": "공정생략 처리량 × 생략공정 변동가공비",
     "expr": [[{"v": "공정생략 처리량"}, {"v": "생략공정 변동가공비"}]],
     "varsDef": [_v("공정생략 처리량", "톤", "생산 DW (생략 공정 통과 예정 물량)", [20000, 300000]), _v("생략공정 변동가공비", "원/톤", "CO 공정원가 (잠금)", [3000, 15000], lock=True)],
     "solve": ["공정생략 처리량"],
     "keys": ["생략 공정 코드", "대체 공정 코드", "강종제품"], "periodKey": "측정기간",
     "notes": ["대체 공정에서 늘어난 비용은 역효과(④) 후공정 부하 항목으로 차감"],
     "history": ["v1 2025-01 최초 제정"]},
    {"id": "RB-B8-001", "type": "B-8", "ver": "v2", "status": "검토중", "period": "2025-01-01 ~", "source": "ERP CO",
     "subtitle": "고정가공비 금액 절감", "pattern": "TOTAL",
     "formula": "개선 전 해당 비용 − 개선 후 해당 비용",
     "expr": [[{"d": ["개선 전 해당 비용", "개선 후 해당 비용"]}]],
     "varsDef": [_v("개선 전 해당 비용", "원", "CO 고정가공비 계정 (기준기간)", [1500000000, 6000000000]), _v("개선 후 해당 비용", "원", "CO 고정가공비 계정 (검증기간)", [1000000000, 5000000000])],
     "solve": ["개선 전 해당 비용"],
     "keys": ["비용항목코드", "비용센터", "원가계정", "대상 조직/설비"], "periodKey": "측정기간",
     "notes": ["v2 개정안: 수명연장 환산계수 도입 검토중 — 확정 전까지 v1(계정 전후차)로 산출", "예방정비 축소에 따른 고장 증가는 역효과(④)"],
     "history": ["v1 2025-01", "v2 2026-06 수명연장 환산계수 개정안(검토중)"]},
    {"id": "RB-B9-001", "type": "B-9", "ver": "v1", "status": "승인", "period": "2025-01-01 ~", "source": "생산 DW · CO",
     "subtitle": "생산량 증가", "pattern": "DIFF",
     "formula": "(개선 후 생산량 − 개선 전 생산량) × 단위당 고정비",
     "expr": [[{"d": ["개선 후 생산량", "개선 전 생산량"]}, {"v": "단위당 고정비"}]],
     "varsDef": [_v("개선 후 생산량", "톤", "생산 DW (검증기간)", [200000, 900000]), _v("개선 전 생산량", "톤", "생산 DW (기준기간)", [200000, 900000]),
                 _v("단위당 고정비", "원/톤", "CO 관리회계 (잠금)", [40000, 120000], lock=True)],
     "solve": ["개선 후 생산량"],
     "keys": ["공장/라인/설비번호", "강종군", "생산성 코드", "가동률", "작업률"], "periodKey": "측정기간",
     "notes": ["증산분이 재고로 남으면 성과 미인정 — 판매·가동률 Key로 확인", "병목 이동·설비 부하는 역효과(④)"],
     "history": ["v1 2025-01 최초 제정"]},
    {"id": "RB-C1-001", "type": "C-1", "ver": "v1", "status": "승인", "period": "2025-01-01 ~", "source": "ERP FI · SD",
     "subtitle": "판관비 절감 (단위형)", "pattern": "DIFF",
     "formula": "(개선 전 비용/톤 − 개선 후 비용/톤) × 판매량",
     "expr": [[{"d": ["개선 전 비용/톤", "개선 후 비용/톤"]}, {"v": "판매량"}]],
     "varsDef": [_v("개선 전 비용/톤", "원/톤", "FI 판관비 계정 ÷ 판매량 (기준기간)", [5000, 40000]), _v("개선 후 비용/톤", "원/톤", "FI 판관비 계정 ÷ 판매량 (검증기간)", [4000, 35000]),
                 _v("판매량", "톤", "ERP SD 판매실적", [20000, 300000])],
     "solve": ["개선 전 비용/톤"],
     "keys": ["판관비 항목", "대상 제품/고객/물류 경로"], "periodKey": "측정기간",
     "notes": ["포장 축소에 따른 파손·반품 증가는 역효과(④)", "총액으로 관리되는 외주·내재화 절감은 C-1(2)"],
     "history": ["v1 2025-01 최초 제정"]},
    {"id": "RB-C12-001", "type": "C-1(2)", "ver": "v1", "status": "승인", "period": "2026-01-01 ~", "source": "ERP FI · CO",
     "subtitle": "판관비 절감 (총액형)", "pattern": "TOTAL",
     "formula": "개선 전 연간비용 − 개선 후 연간비용",
     "expr": [[{"d": ["개선 전 연간비용", "개선 후 연간비용"]}]],
     "varsDef": [_v("개선 전 연간비용", "원", "FI 원가계정·비용센터 (기준기간)", [300000000, 3000000000]), _v("개선 후 연간비용", "원", "FI 원가계정·비용센터 (검증기간)", [100000000, 2500000000])],
     "solve": ["개선 전 연간비용"],
     "keys": ["원가계정", "비용센터", "Work Order/설비", "외주 계약 항목"], "periodKey": "측정기간",
     "notes": ["분석법·장치 제작 등 내재화 절감 — 내부 인력·유지보수 비용 증가는 역효과(④)"],
     "history": ["v1 2026-01 최초 제정"]},
    {"id": "RB-C2-001", "type": "C-2", "ver": "v1", "status": "승인", "period": "2026-01-01 ~", "source": "품질 DW · ERP SD",
     "subtitle": "클레임 비용 절감", "pattern": "DIFF",
     "formula": "(개선 전 톤당 클레임 − 개선 후 톤당 클레임) × 판매량",
     "expr": [[{"d": ["개선 전 톤당 클레임", "개선 후 톤당 클레임"]}, {"v": "판매량"}]],
     "varsDef": [_v("개선 전 톤당 클레임", "원/톤", "품질 DW 클레임 처리비 ÷ 판매량 (기준기간)", [1000, 15000]), _v("개선 후 톤당 클레임", "원/톤", "품질 DW (검증기간)", [500, 12000]),
                 _v("판매량", "톤", "ERP SD 판매실적", [20000, 300000])],
     "solve": ["개선 전 톤당 클레임"],
     "keys": ["클레임 코드", "결함 코드", "대상 제품/고객"], "periodKey": "측정기간",
     "notes": ["검사 강화·선별비 증가와 이연 클레임은 역효과(④)에서 위험추정으로 구분"],
     "history": ["v1 2026-01 최초 제정"]},
]
for _r in RULES:   # 호환 필드: vars [[변수, 원천]]
    _r["vars"] = [[v["n"], v["s"]] for v in _r["varsDef"]]
    for _k in _r["keys"] + [_r["periodKey"]]:
        assert _k in KEY_DICT, f"KEY_DICT 누락: {_k}"
RULE_BY_TYPE = {r["type"]: r for r in RULES}
EFFECT_TO_TYPE = {k: v[0] for k, v in EFFECT_MAP.items() if v}
EFFECT_TO_TYPE["실수율/품질향상"] = "B-6"   # 설계서 3.1 기본 추천 (목록 순서와 무관)

def tech_major(t):
    t = (t or "").strip()
    m = re.match(r"^\((.+?)\)", t)
    return m.group(1) if m else ("기타" if t in ("", "-") else t)
TECH_OF = {r["과제코드"]: tech_major(r.get("기술분류")) for r in a3 if r.get("과제코드")}
STATUSES = ["확정", "확정", "확정", "확정", "확정", "승인", "승인", "검토", "검토", "검토", "보완", "등록"]
KEY_BY_GROUP = {
    "A": "제품군·강종·고객사·품질등급·판매기간",
    "B": "공장·공정·품목코드·원단위 항목·기준/검증기간",
    "C": "비용계정·부서·클레임 유형·기간",
}
prng = random.Random(20260901)
a1_by_code = {r["과제코드"]: r for r in a1}
# 이상치 제외(연간기대이익 1~80억), 유형별 버킷 후 라운드로빈으로 유형 다양성 확보
buckets = defaultdict(list)
for p in sorted(completed, key=lambda x: -x["annual"]):
    if not (1e8 <= p["annual"] <= 8e9) or p["roi"] <= 0:
        continue
    r = a1_by_code.get(p["code"])
    eff = re.split(r"[,\s]", ((r or {}).get("정량효과유형") or "기타").strip())[0]
    ptype = EFFECT_TO_TYPE.get(eff)
    if ptype and ptype in RULE_BY_TYPE:
        buckets[ptype].append((p, eff))
TYPE_ORDER = ["B-6", "A-1", "B-2", "B-9", "B-7", "B-8", "A-4", "B-3(2)", "C-1", "A-2"]
picked = []
ri = 0
while len(picked) < 12 and any(buckets.get(t) for t in TYPE_ORDER):
    t = TYPE_ORDER[ri % len(TYPE_ORDER)]
    ri += 1
    if buckets.get(t):
        picked.append(buckets[t].pop(0))
regs = []
for p, eff in picked:
    ptype = EFFECT_TO_TYPE[eff]
    gross = p["annual"]
    ero_pair = EROSION_CATALOG.get(ptype)
    erosion = round(gross * prng.uniform(0.06, 0.22)) if ero_pair else 0
    contrib = int(p.get("roi", 0) and 0) or 0
    contrib_pct = None
    for r in a1:
        if r["과제코드"] == p["code"]:
            contrib_pct = money(r.get("연구기여도", "")) or 70
            break
    contrib_pct = contrib_pct or 70
    direct = round(gross * prng.uniform(0.01, 0.05))
    net = round((gross - erosion) * contrib_pct / 100 - direct)
    rule = RULE_BY_TYPE[ptype]
    status = STATUSES[len(regs)]
    regs.append({
        "id": f"PF-2026-{len(regs)+1:03d}", "code": p["code"], "name": short(p["name"], 30),
        "effect": eff, "type": ptype, "status": status,
        "contrib": round(contrib_pct), "persist": round(p["persist"]),
        "grossEok": eok(gross), "erosionEok": eok(erosion), "directEok": eok(direct),
        "netEok": eok(net), "rule": rule["id"], "ruleVer": rule["ver"],
        "match": prng.randint(180, 2400), "period": "2025-09 ~ 2026-08",
        "key": KEY_BY_GROUP[ptype[0]],
        "erosionName": ero_pair[0] if ero_pair else "해당 역효과 없음",
        "dept": p["useDept"], "slaDay": prng.randint(1, 9), "costEok": eok(p["cost"]),
        "tech": TECH_OF.get(p["code"], "기타"), "act": classify(p["code"]),
        "utilY1": prng.choice(["활용중", "활용중", "부분활용"]),
    })


# ── 연구 기여율: 유형별 표준 기여율 테이블 (⑥ 기여율 기준 데이터, 재무실 고시 v1)
#    std 표준 · down 하향(활용부서장 판단) · up 상향(재무실 승인) · up 이 [min,max]면 범위 입력
CONTRIB_TABLE = [
    {"type": "A-1", "std": 50, "down": 30, "downCond": "판매·마케팅 주도로 수주하고, 연구는 품질 대응을 수행한 경우",
     "up": [70, 100], "upCond": "고객이 해당 기술 때문에 발주했음을 입증한 경우"},
    {"type": "A-2", "std": 50, "down": 30, "downCond": "가격 협상력이 주요 요인인 경우",
     "up": 70, "upCond": "Extra 코드가 개발 기술에 직접 연동됨을 입증한 경우"},
    {"type": "A-3", "std": 40, "down": 20, "downCond": "판매전략 주도의 Mix 전환인 경우",
     "up": 60, "upCond": "신강종 개발이 Mix 전환의 직접 원인인 경우"},
    {"type": "A-4", "std": 40, "down": 20, "downCond": "조업 조건 개선이 병행된 경우",
     "up": 60, "upCond": "연구기술 단독 적용으로 개선되었음을 입증한 경우"},
    {"type": "B-1", "std": 30, "down": 10, "downCond": "구매협상이 주요 요인이고, 연구는 대체 가능성을 검증한 경우",
     "up": 50, "upCond": "연구가 대체재 검증표준 개정을 주도한 경우"},
    {"type": "B-2", "std": 30, "down": 15, "downCond": "조업 최적화 활동이 병행된 경우",
     "up": 50, "upCond": "연구기술에 의한 모델 또는 소재 변경이 단독 원인인 경우"},
    {"type": "B-3", "std": 40, "down": 20, "downCond": "구매 주도의 원료 전환인 경우",
     "up": 60, "upCond": "연구의 배합성분 기술이 대체를 가능하게 한 경우"},
    {"type": "B-3(2)", "std": 40, "down": 20, "downCond": "구매 주도의 원료·배합 전환인 경우 (B-3 준용)",
     "up": 60, "upCond": "연구의 배합성분 기술이 변경을 가능하게 한 경우 (B-3 준용)", "note": "B-3 기준 준용"},
    {"type": "B-4", "std": 30, "down": 15, "downCond": "설비 투자 또는 조업 개선이 병행된 경우",
     "up": 50, "upCond": "연구기술을 단독 적용한 경우"},
    {"type": "B-5", "std": 20, "down": 10, "downCond": "요금제 또는 계약 협상이 주요 요인인 경우",
     "up": 40, "upCond": "연구의 기술 검증이 단가 인하의 전제인 경우"},
    {"type": "B-6", "std": 40, "down": 20, "downCond": "설비 교체 또는 조업표준 개정이 병행된 경우",
     "up": 60, "upCond": "연구모델 또는 연구기술이 직접 원인인 경우", "note": "적용 전후 비교 가능"},
    {"type": "B-6(2)", "std": 40, "down": 20, "downCond": "설비 교체 또는 조업표준 개정이 병행된 경우 (B-6 준용)",
     "up": 60, "upCond": "연구모델 또는 연구기술이 직접 원인인 경우 (B-6 준용)", "note": "매출이익형 · B-6 기준 준용"},
    {"type": "B-7", "std": 50, "down": 30, "downCond": "설비 투자가 동반된 공정 생략인 경우",
     "up": 70, "upCond": "연구기술만으로 공정 생략을 달성한 경우"},
    {"type": "B-8", "std": 30, "down": 15, "downCond": "조직 또는 예산 효율화가 병행된 경우",
     "up": 50, "upCond": "연구기술이 비용 구조를 직접 변경한 경우"},
    {"type": "B-9", "std": 30, "down": 15, "downCond": "설비 증설 또는 조업 개선이 병행된 경우",
     "up": 50, "upCond": "연구기술에 의한 모델 또는 조업조건 최적화가 직접 원인인 경우"},
    {"type": "C-1", "std": 30, "down": 15, "downCond": "물류구매 협상이 병행된 경우",
     "up": 50, "upCond": "연구기술 또는 포장 사양 등이 직접 원인인 경우", "note": "단위형 (물류·포장 등 단위비 절감)"},
    {"type": "C-1(2)", "std": 40, "down": 20, "downCond": "외주 계약 조정이 병행된 경우",
     "up": 70, "upCond": "연구가 내재화 기술을 단독 개발한 경우", "note": "총액형 (분석법·장치 제작 등 외주 내재화)"},
    {"type": "C-2", "std": 40, "down": 20, "downCond": "검사 강화 또는 공정관리가 병행된 경우",
     "up": 60, "upCond": "연구의 품질기술이 결함 원인을 직접 제거한 경우"},
]
CONTRIB_BY_TYPE = {c["type"]: c for c in CONTRIB_TABLE}
assert set(CONTRIB_BY_TYPE) == {t[0] for t in PERF_TYPES}, "표준 기여율 테이블과 재무성과 코드 불일치"

# 등록 성과 12건의 기여율을 표준표 기준으로 재산정 (a1 연구기여도는 참고값으로만 보존). 별도 시드 → 기존 난수열 불변
cprng = random.Random(20260903)
CONTRIB_MODES = ["STANDARD"] * 7 + ["DOWN"] * 3 + ["UP"] * 2
cprng.shuffle(CONTRIB_MODES)
for r, mode in zip(regs, CONTRIB_MODES):
    tbl = CONTRIB_BY_TYPE[r["type"]]
    a1_ref = r["contrib"]
    if mode == "DOWN":
        applied = tbl["down"]
        decision = {"mode": "DOWN", "applied": applied, "reason": f"하향 조건 해당 — {tbl['downCond']}",
                    "judgedBy": f"{r['dept']} 부서장", "judgedAt": None, "evidence": "활용부서 판단서(과제 완료보고 첨부)"}
    elif mode == "UP":
        up = tbl["up"]
        applied = cprng.choice([80, 90]) if isinstance(up, list) else up
        approved = r["status"] in ("승인", "확정")   # 성과 승인과 함께 기여율 상향도 승인된 것으로 간주
        decision = {"mode": "UP", "applied": applied, "reason": f"상향 조건 입증 — {tbl['upCond']}",
                    "evidence": "고객 발주 사유서·기술 적용 확인서" if r["type"][0] == "A" else "적용 전후 조업 데이터·기술 적용 확인서",
                    "approval": {"status": "승인" if approved else "승인대기", "requestedAt": None, "decidedAt": None, "by": "재무실"}}
    else:
        applied = tbl["std"]
        decision = {"mode": "STANDARD", "applied": applied, "reason": "", "evidence": ""}
    decision.update({"standard": tbl["std"], "a1Ref": a1_ref})
    # 상향은 재무실 승인 전까지 표준 기여율이 유효값
    effective = tbl["std"] if (mode == "UP" and decision["approval"]["status"] != "승인") else applied
    decision["effective"] = effective
    r["contrib"] = effective
    r["contribution"] = decision
    r["netEok"] = eok((r["grossEok"] - r["erosionEok"]) * 1e8 * effective / 100 - r["directEok"] * 1e8)

# ── 산출 근거 추적(Lineage) 데이터: 성과 등록별 스냅샷·변수값·재계산·승인 이력·연차·건전성 (시드 고정)
lprng = random.Random(20260902)
STEP_ORDER = ["등록", "검토", "보완", "승인", "확정"]
STEP_ACTOR = {"등록": "연구책임자 (과제 부서)", "검토": "재무실 검토자", "보완": "연구책임자 (과제 부서)",
              "승인": "재무실 팀장", "확정": "재무실 (월마감)"}
STEP_NOTE = {"등록": "성과 등록·입력 Key 지정, ERP 스냅샷 자동 생성", "검토": "Rule 변수·역효과 첨부 검토",
             "보완": "역효과 산정 근거 보완 요청 → 재제출", "승인": "재계산 일치 확인, 기여율 적용 승인", "확정": "월마감 반영·누적성과 편입"}

def _doc_ids(src, n):
    pre = {"SD": "SD", "DW": "PD", "CO": "CO", "FI": "FI", "MM": "MM", "QD": "QD"}[src]
    out = []
    for _ in range(n):
        m = lprng.randint(1, 12)
        out.append(f"{pre}-2026{m:02d}-{lprng.randint(100000, 999999)}")
    return out

def _rnd(x, dec):
    return round(x, dec) if dec else int(round(x))

def _eval_expr(rule, val):
    """expr(Σ Π term) 평가. pct 변수는 /100. 반환: 총액(원), 곱셈항별 [값]"""
    pct = {v["n"] for v in rule["varsDef"] if v.get("pct")}
    f = lambda n: val[n] / 100 if n in pct else val[n]
    prods = []
    for terms in rule["expr"]:
        p = 1.0
        for t in terms:
            p *= (f(t["d"][0]) - f(t["d"][1])) if "d" in t else f(t["v"])
        prods.append(p)
    return sum(prods), prods

def _calc(r, gross):
    """산식 정의(expr·varsDef)를 읽어 성과총액이 재현되도록 변수값을 역산. 반환: (vars, steps, recomputed 원, 원천코드)"""
    rule = RULE_BY_TYPE[r["type"]]
    vd = {v["n"]: v for v in rule["varsDef"]}
    pct = {n for n, v in vd.items() if v.get("pct")}
    val = {}
    # 1) 역산 대상이 아닌 변수는 표본 범위에서 추출 (차이항의 '전' 값 포함)
    for v in rule["varsDef"]:
        val[v["n"]] = _rnd(lprng.uniform(*v["r"]), v["dec"])
    # 2) 곱셈항별 성과 배분 (가산형은 85:15)
    n_prod = len(rule["expr"])
    shares = [gross] if n_prod == 1 else [gross * 0.85, gross * 0.15]
    for terms, solve, share in zip(rule["expr"], rule["solve"], shares):
        others = 1.0
        target = None
        for t in terms:
            if "d" in t and solve in t["d"]:
                target = t
            elif "v" in t and t["v"] == solve:
                target = t
            else:
                x = (val[t["d"][0]] - val[t["d"][1]]) if "d" in t else val[t["v"]]
                if "d" in t:
                    x = (val[t["d"][0]] / 100 - val[t["d"][1]] / 100) if (t["d"][0] in pct) else x
                elif t["v"] in pct:
                    x = x / 100
                others *= x
        need = share / others           # 역산 대상 항의 값 (비율 변수는 소수)
        if solve in pct:
            need *= 100
        dec = vd[solve]["dec"]
        if "d" in target:               # 차이항: solve = 다른 쪽 ± need
            a, b = target["d"]
            if solve == a:
                val[a] = _rnd(val[b] + need, dec)
            else:
                val[b] = _rnd(val[a] - need, dec)
        else:
            val[solve] = _rnd(need, dec)
        # 반올림 오차가 허용치(0.5%)를 넘으면 소수 자릿수를 늘려 재역산
        rec, _ = _eval_expr(rule, val)
        if abs(rec - gross) > gross * 0.004 and n_prod == 1:
            dec += 2
            if "d" in target:
                a, b = target["d"]
                if solve == a: val[a] = _rnd(val[b] + need, dec)
                else: val[b] = _rnd(val[a] - need, dec)
            else:
                val[solve] = _rnd(need, dec)
    recomputed, prods = _eval_expr(rule, val)
    vars_ = [[v["n"], val[v["n"]], v["u"], v["s"]] for v in rule["varsDef"]]
    steps = []
    for terms, pv in zip(rule["expr"], prods):
        parts, subs = [], []
        for t in terms:
            if "d" in t:
                a, b = t["d"]
                d = val[a] - val[b]
                steps.append([f"{a} − {b}", f"{val[a]:,} − {val[b]:,}", _rnd(d, vd[a]["dec"]), vd[a]["u"] + ("p" if a in pct else "")])
                parts.append(f"({a} − {b})"); subs.append(f"{_rnd(d, vd[a]['dec']):,}" + ("%" if a in pct else ""))
            else:
                parts.append(t["v"]); subs.append(f"{val[t['v']]:,}" + ("%" if t["v"] in pct else ""))
        steps.append([" × ".join(parts), " × ".join(subs), int(round(pv)), "원"])
    if len(prods) > 1:
        steps.append(["합계 (곱셈항 합)", " + ".join(f"{int(round(p)):,}" for p in prods), int(round(recomputed)), "원"])
    src = {"A": "SD", "B": "DW", "C": "FI"}[r["type"][0]]
    if r["type"] in ("B-8",): src = "CO"
    if r["type"] in ("A-4",): src = "QD"
    return vars_, steps, int(round(recomputed)), src

for r, (p, eff) in zip(regs, picked):
    gross = p["annual"]
    vars_, steps, recomputed, src = _calc(r, gross)
    rule = RULE_BY_TYPE[r["type"]]
    # 승인 이력: 등록일부터 현재 상태까지, 각 단계 수일 간격
    reg_day = date(2026, lprng.randint(3, 7), lprng.randint(1, 28))
    upto = STEP_ORDER.index(r["status"]) + 1
    if r["status"] == "확정":
        upto = 5
    hist, d = [], reg_day
    for stp in STEP_ORDER[:upto]:
        if stp == "보완" and r["status"] in ("승인", "확정") and lprng.random() < 0.5:
            continue  # 보완 없이 승인된 건
        hist.append([stp, STEP_ACTOR[stp], d.isoformat(), STEP_NOTE[stp]])
        d = d + timedelta(days=lprng.randint(2, 9))
    frozen = f"{reg_day.isoformat()} 02:{lprng.randint(10,59):02d}"
    snap_id = f"SNAP-{reg_day.strftime('%Y%m%d')}-{r['id'][-3:]}"
    has_snapshot = r["status"] != "등록"
    drift = lprng.choice([0, 0, 0, lprng.randint(3, 40)])  # 스냅샷 이후 원천 변경 감지(일부 건)
    diff = recomputed - gross
    recompute_ok = abs(diff) <= max(gross * 0.005, 1)
    checks = [
        ["ERP 스냅샷 동결", "ok" if has_snapshot else "warn", f"{snap_id} · {frozen}" if has_snapshot else "등록 단계 — 스냅샷 미생성"],
        ["산식 버전 잠금", "ok" if rule["status"] == "승인" else "warn", f"{rule['id']} {rule['ver']} 잠금" if rule["status"] == "승인" else f"{rule['id']} {rule['ver']} 개정 검토중 — 잠금 전"],
        ["재계산 일치", "ok" if recompute_ok else "warn", f"재계산 {eok(recomputed)}억 vs 등록 {r['grossEok']}억 (차이 {eok(diff):+.1f}억)"],
        ["원천 변경 감지", "ok" if drift == 0 else "info", "스냅샷 이후 원천 변경 없음" if drift == 0 else f"현재 ERP 재조회 {r['match']+drift:,}건 (스냅샷 {r['match']:,}건, +{drift}) — 산출은 스냅샷 기준 유지"],
        ["승인 기록", "ok" if r["status"] in ("승인", "확정") else "info" if r["status"] in ("검토", "보완") else "warn",
         f"{r['status']} · {hist[-1][2]}" if hist else "기록 없음"],
    ]
    years = []
    for y in range(1, r["persist"] + 1):
        if y == 1:
            years.append([1, r["utilY1"], r["netEok"] if r["status"] in ("승인", "확정") else None, "1년차 실적" if r["status"] in ("승인", "확정") else "승인 전 — 산출값 미확정"])
        else:
            years.append([y, "예정", None, f"{2026+y-1}년 활용평가 예정"])
    c = r["contribution"]
    if c["mode"] == "DOWN":
        c["judgedAt"] = hist[0][2] if hist else reg_day.isoformat()
    if c["mode"] == "UP":
        c["approval"]["requestedAt"] = hist[0][2] if hist else reg_day.isoformat()
        c["approval"]["decidedAt"] = hist[-1][2] if c["approval"]["status"] == "승인" and len(hist) > 1 else None
    r["lineage"] = {
        "snapshot": {"id": snap_id if has_snapshot else None, "frozenAt": frozen if has_snapshot else None, "source": rule["source"],
                     "records": r["match"], "currentRecords": r["match"] + drift, "period": r["period"],
                     "samples": _doc_ids(src, 10) if has_snapshot else []},
        "keyValues": [[k, (r["dept"] if ("공장" in k or "조직" in k or "센터" in k) else f"{lprng.randint(1, 6)}개 지정"), KEY_DICT[k][0]] for k in rule["keys"]]
                     + [[rule["periodKey"], r["period"], KEY_DICT[rule["periodKey"]][0]]],
        "calc": {"vars": vars_, "steps": steps, "recomputedEok": eok(recomputed), "diffEok": eok(diff), "ok": recompute_ok},
        "approval": hist,
        "years": years,
        "checks": checks,
        "registeredAt": reg_day.isoformat(),
    }

# ── ① 워크벤치 신규 등록 후보: 완료과제 중 미등록 건 (연간기대이익 1~80억, 상위 40건). a1 참고값 포함
_reg_codes = {r["code"] for r in regs}
candidates = []
for p in sorted(completed, key=lambda x: -x["annual"]):
    if p["code"] in _reg_codes or not (1e8 <= p["annual"] <= 8e9):
        continue
    r1 = a1_by_code.get(p["code"]) or {}
    eff = re.split(r"[,\s]", (r1.get("정량효과유형") or "기타").strip())[0] or "기타"
    candidates.append({"code": p["code"], "name": short(p["name"], 40), "dept": p["useDept"], "effect": eff,
                       "annualEok": eok(p["annual"]), "costEok": eok(p["cost"]), "tech": TECH_OF.get(p["code"], "기타"), "act": classify(p["code"]), "persist": max(1, round(p["persist"])) if p["persist"] else 3,
                       "a1Contrib": round(money(r1.get("연구기여도", "")) or 70)})
    if len(candidates) >= 40:
        break

# ── CTO Dashboard 데이터: 기술분류 × 성과유형, 기술분류별 전환율, 활동군별 실현 추이, 탐색→전략 후속화, Watch List
_tech_cell = defaultdict(lambda: {"exp": 0.0, "n": 0})
_tech_conv = defaultdict(lambda: {"n": 0, "exp": 0.0, "real": 0.0})
_act_year = defaultdict(lambda: defaultdict(float))
for pr in proj_results:
    tmaj = TECH_OF.get(pr["code"], "기타")
    ptype = EFFECT_TO_TYPE.get(pr["effect"])
    if ptype:
        c = _tech_cell[(tmaj, ptype)]; c["exp"] += pr["exp"]; c["n"] += 1
    tc = _tech_conv[tmaj]; tc["n"] += 1; tc["exp"] += pr["exp"]; tc["real"] += pr["real"]
    _act_year[pr["cy"]][pr["act"]] += pr["real"]
tech_rows = [t for t, v in sorted(_tech_conv.items(), key=lambda x: -x[1]["exp"]) if v["n"] >= 3][:9]
# 탐색(N/L) 완료과제 → 이후 동일 연구부서·기술분류에서 착수한 전략 과제 존재 여부 (근사 후속화율)
_strat_starts = defaultdict(list)
for r in a3:
    if classify(r["과제코드"]) == 1 and r.get("착수일"):
        _strat_starts[(dept_short(r.get("연구부서")), TECH_OF.get(r["과제코드"], "기타"))].append(r["착수일"])
explore_done = [p for p in completed if classify(p["code"]) == 4]
followed = 0
for p in explore_done:
    key = (dept_short(p.get("rdept")), TECH_OF.get(p["code"], "기타"))
    done_at = f"{p['cy']}-12-31"
    if any(st > done_at for st in _strat_starts.get(key, [])):
        followed += 1
_watch_unused = sorted([pr for pr in proj_results if pr["status"] == "미활용"], key=lambda x: -x["cost"])[:6]
_watch_drop = sorted([pr for pr in proj_results if len(pr["traj"]) >= 2 and pr["traj"][-1] != "활용중" and pr["traj"][-2] == "활용중"], key=lambda x: -x["exp"])[:6]
cto = {
    "techRows": tech_rows,
    "matrix": [[t, pt, round(v["exp"], 1), v["n"]] for (t, pt), v in _tech_cell.items() if t in tech_rows],
    "techConv": [[t, _tech_conv[t]["n"], round(_tech_conv[t]["exp"], 1), round(_tech_conv[t]["real"], 1),
                  round(100 * _tech_conv[t]["real"] / max(1e-9, _tech_conv[t]["exp"]))] for t in tech_rows],
    "actYears": sorted(y for y in _act_year if y >= CUR_YEAR - 6),
    "actSeries": {str(a): [round(_act_year[y].get(a, 0.0), 1) for y in sorted(y for y in _act_year if y >= CUR_YEAR - 6)] for a in (1, 3, 4)},
    "followUp": {"explore": len(explore_done), "followed": followed, "rate": round(100 * followed / max(1, len(explore_done)))},
    "watchUnused": [[pr["code"], pr["name"], pr["dept"], pr["cost"], pr["exp"], "·".join(pr["traj"])] for pr in _watch_unused],
    "watchDrop": [[pr["code"], pr["name"], pr["dept"], pr["cost"], pr["exp"], "·".join(pr["traj"])] for pr in _watch_drop],
}

appr_counts = Counter(r["status"] for r in regs)
type_amounts = defaultdict(float)
for r in regs:
    if r["status"] in ("승인", "확정"):
        type_amounts[r["type"]] += r["netEok"]
perf = {
    "types": PERF_TYPES,
    "effectMap": EFFECT_MAP,
    "rules": RULES,
    "keyDict": KEY_DICT,
    "contribTable": CONTRIB_TABLE,
    "candidates": candidates,
    "cto": cto,
    "regs": regs,
    "approval": {
        "wait": appr_counts.get("검토", 0) + appr_counts.get("보완", 0) + appr_counts.get("등록", 0),
        "done": appr_counts.get("승인", 0) + appr_counts.get("확정", 0),
        "rejected": 1, "avgDays": 7.2,
        "amountDone": round(sum(r["netEok"] for r in regs if r["status"] in ("승인", "확정")), 1),
        "funnel": [["등록", len(regs)], ["검토", sum(appr_counts[s] for s in ("검토", "보완", "승인", "확정"))],
                    ["보완", appr_counts.get("보완", 0)],
                    ["승인", appr_counts.get("승인", 0) + appr_counts.get("확정", 0)],
                    ["확정", appr_counts.get("확정", 0)]],
        "byType": sorted(type_amounts.items(), key=lambda x: -x[1]),
    },
}

mwpage = {
    "orgStack": org_stack,
    "heatOrgs": heat_orgs, "heatYms": heat_yms, "heatmap": heatmap,
    "people": people_table,
    "latestYear": latest_year,
    "personYearAvg": home["balance"]["mwPerPerson"],
    "peopleN": len(person),
}

DATA_OUT = {
    "meta": {"asOf": str(TODAY), "note": "활용평가 실적은 시드 고정 시뮬레이션(DEMO)이며, 실운영 시 PRIDE 활용평가 모듈 데이터로 대체됩니다.",
             "actNames": ACT, "rows": {"a1": len(a1), "a2": len(a2), "a3": len(a3),
                                        "a4": len(a4), "a5": len(a5), "a6": len(a6)}},
    "home": home, "support": support, "knowledge": knowledge, "promotion": promotion,
    "longterm": longterm, "mw": mwpage,   # executive: Executive 탭은 perf.regs 확정 기준으로 직접 계산
    "detail": detail, "sim": sim, "me": me, "perf": perf,
}

out = BASE / "demo_data.js"
with open(out, "w", encoding="utf-8") as f:
    f.write("// 자동생성: python3 demo/etl.py — 직접 수정 금지\n")
    f.write("window.DEMO_DATA = ")
    json.dump(DATA_OUT, f, ensure_ascii=False, separators=(",", ":"))
    f.write(";\n")

print(f"OK → {out}  ({out.stat().st_size/1024:.0f} KB)")
print(f"a1 {len(a1)} | a2 {len(a2)} | a3 {len(a3)} | a4 {len(a4)} | a5 {len(a5)} | a6 {len(a6)}")
print(f"MW 합계: 전략 {mw_a1:.0f} / 현업 {mw_a3:.0f} / 탐색 {mw_a4:.0f} (탐색비중 {explore_share}%)")
print(f"장기성과: 추적 {len(tracked)} 활용률 {util_rate}% Achv {achievement}% 누적실현 {eok(total_real)}억")
print(f"현업지원: 완료율 {support['doneRate']}% 평균리드 {support['avgLead']}일 지연 {support['delayedOpen']}건")
