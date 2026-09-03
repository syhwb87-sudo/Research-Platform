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
            "cost": eok(p["cost"]), "status": last_status or "미평가",
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
    ["B-6", "B", "수율 개선"], ["B-7", "B", "공정생략"], ["B-8", "B", "고정가공비 절감"], ["B-9", "B", "생산량 증가"],
    ["C-1", "C", "판관비 절감"], ["C-1(2)", "C", "판관비 절감(총액형)"], ["C-2", "C", "클레임 비용 절감"],
]
# 연구효과 14종 → 재무성과 후보 매핑 (설계서 3.1)
EFFECT_MAP = {
    "신수요창출": ["A-1", "A-2", "A-3"],
    "제품개발/수입대체": ["A-1", "B-1", "B-3", "C-1"],
    "실수율/품질향상": ["A-4", "B-6", "C-2"],
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
RULES = [
    {"id": "RB-A1-003", "type": "A-1", "ver": "v2",
     "formula": "성과총액 = (검증기간 판매량 − 기준기간 판매량) × 톤당 한계이익",
     "vars": [["Q_v 검증기간 판매량", "ERP SD 판매실적 (지정 Key 필터)"],
              ["Q_b 기준기간 판매량", "동일 Key · 착수 직전 12개월"],
              ["CM_ton 톤당 한계이익", "CO 관리회계 공식값 (재무실 잠금)"]],
     "period": "2026-01-01 ~", "source": "ERP SD · CO", "status": "승인",
     "history": ["v1 2025-01 최초 제정", "v2 2026-03 기준기간 정의 변경(재무실)"]},
    {"id": "RB-A2-001", "type": "A-2", "ver": "v1",
     "formula": "성과총액 = (검증기간 FOB − 기준기간 FOB) × 판매량",
     "vars": [["FOB", "ERP SD 수출 단가"], ["판매량", "ERP SD 판매실적"]],
     "period": "2025-01-01 ~", "source": "ERP SD", "status": "승인",
     "history": ["v1 2025-01 최초 제정"]},
    {"id": "RB-A4-001", "type": "A-4", "ver": "v1",
     "formula": "성과총액 = 주문외 전환량 × (정품 판매가 − 주문외 판매가)",
     "vars": [["전환량", "품질 DW 주문외 실적"], ["가격차", "ERP SD 단가"]],
     "period": "2025-07-01 ~", "source": "품질 DW · ERP SD", "status": "승인",
     "history": ["v1 2025-07 최초 제정"]},
    {"id": "RB-B2-002", "type": "B-2", "ver": "v3",
     "formula": "성과총액 = (개선전 원단위 − 개선후 원단위) × 단가 × 생산량",
     "vars": [["원단위", "생산 DW 원단위 실적"], ["단가", "MM 구매단가 (잠금)"], ["생산량", "생산 DW"]],
     "period": "2026-04-01 ~", "source": "생산 DW · ERP MM", "status": "승인",
     "history": ["v1 2025-01", "v2 2025-09 에너지 원단위 포함", "v3 2026-04 단가 기준월 고정"]},
    {"id": "RB-B6-002", "type": "B-6", "ver": "v1",
     "formula": "성과총액 = 실수율 개선폭 × 생산량 × (판매가 − 스크랩가)",
     "vars": [["실수율", "생산 DW 실수율"], ["가격차", "ERP SD·스크랩 시세"]],
     "period": "2025-01-01 ~", "source": "생산 DW · ERP SD", "status": "승인",
     "history": ["v1 2025-01 최초 제정"]},
    {"id": "RB-B7-001", "type": "B-7", "ver": "v1",
     "formula": "성과총액 = 생략 공정 처리량 × 공정 단위비용",
     "vars": [["처리량", "생산 DW"], ["단위비용", "CO 공정원가 (잠금)"]],
     "period": "2025-01-01 ~", "source": "생산 DW · CO", "status": "승인",
     "history": ["v1 2025-01 최초 제정"]},
    {"id": "RB-B8-001", "type": "B-8", "ver": "v2",
     "formula": "성과총액 = 절감 인시·수명연장 환산액 (고정비 계정 기준)",
     "vars": [["고정비", "CO 고정가공비 계정"], ["환산계수", "재무실 고시"]],
     "period": "2025-01-01 ~", "source": "ERP CO", "status": "검토중",
     "history": ["v1 2025-01", "v2 2026-06 수명연장 환산계수 개정안(검토중)"]},
    {"id": "RB-B9-001", "type": "B-9", "ver": "v1",
     "formula": "성과총액 = 증산량 × 톤당 한계이익 × 가동 기여계수",
     "vars": [["증산량", "생산 DW"], ["CM_ton", "CO 관리회계 (잠금)"]],
     "period": "2025-01-01 ~", "source": "생산 DW · CO", "status": "승인",
     "history": ["v1 2025-01 최초 제정"]},
    {"id": "RB-C1-001", "type": "C-1", "ver": "v1",
     "formula": "성과총액 = 대체된 외부 용역·분석 비용 실적",
     "vars": [["비용계정", "ERP FI 판관비 계정"]],
     "period": "2025-01-01 ~", "source": "ERP FI", "status": "승인",
     "history": ["v1 2025-01 최초 제정"]},
]
RULE_BY_TYPE = {r["type"]: r for r in RULES}
EFFECT_TO_TYPE = {k: v[0] for k, v in EFFECT_MAP.items() if v}
EFFECT_TO_TYPE["실수율/품질향상"] = "B-6"   # 설계서 3.1 기본 추천 (목록 순서와 무관)

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
        "dept": p["useDept"], "slaDay": prng.randint(1, 9),
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

def _calc(r, gross):
    """Rule 산식에 실제 대입되는 변수값을 생성해 성과총액이 재현되도록 한다. 반환: (vars, steps, recomputed 원)"""
    t = r["type"]
    if t == "A-1":
        cm = lprng.randint(120, 300) * 1000; dq = round(gross / cm); qb = lprng.randint(8000, 60000)
        v = [["Q_v 검증기간 판매량", qb + dq, "톤", "ERP SD 판매실적 (스냅샷)"], ["Q_b 기준기간 판매량", qb, "톤", "ERP SD 착수 직전 12개월"], ["CM_ton 톤당 한계이익", cm, "원/톤", "CO 관리회계 (재무실 잠금)"]]
        st = [["ΔQ = Q_v − Q_b", f"{qb+dq:,} − {qb:,}", dq, "톤"], ["성과총액 = ΔQ × CM_ton", f"{dq:,} × {cm:,}", dq * cm, "원"]]
        return v, st, dq * cm, "SD"
    if t == "A-2":
        d = lprng.randint(8000, 40000); q = round(gross / d); fb = lprng.randint(900000, 1500000)
        v = [["FOB_v 검증기간 단가", fb + d, "원/톤", "ERP SD 수출 단가"], ["FOB_b 기준기간 단가", fb, "원/톤", "ERP SD 수출 단가"], ["판매량", q, "톤", "ERP SD 판매실적"]]
        st = [["ΔFOB = FOB_v − FOB_b", f"{fb+d:,} − {fb:,}", d, "원/톤"], ["성과총액 = ΔFOB × 판매량", f"{d:,} × {q:,}", d * q, "원"]]
        return v, st, d * q, "SD"
    if t == "A-4":
        gap = lprng.randint(30000, 90000); q = round(gross / gap); pn = lprng.randint(1000000, 1400000)
        v = [["전환량 (주문외→정품)", q, "톤", "품질 DW 주문외 실적"], ["정품 판매가", pn, "원/톤", "ERP SD 단가"], ["주문외 판매가", pn - gap, "원/톤", "ERP SD 단가"]]
        st = [["가격차 = 정품가 − 주문외가", f"{pn:,} − {pn-gap:,}", gap, "원/톤"], ["성과총액 = 전환량 × 가격차", f"{q:,} × {gap:,}", q * gap, "원"]]
        return v, st, q * gap, "QD"
    if t == "B-2":
        price = lprng.randint(300, 1200); qty = lprng.randint(50000, 400000); du = round(gross / (price * qty), 2); ub = round(lprng.uniform(12, 40), 2)
        v = [["개선전 원단위", ub, "kg/톤", "생산 DW 원단위 실적 (기준기간)"], ["개선후 원단위", round(ub - du, 2), "kg/톤", "생산 DW 원단위 실적 (검증기간)"], ["단가", price, "원/kg", "MM 구매단가 (기준월 고정)"], ["생산량", qty, "톤", "생산 DW"]]
        rec = round(du * price * qty)
        st = [["Δ원단위 = 개선전 − 개선후", f"{ub} − {round(ub-du,2)}", du, "kg/톤"], ["성과총액 = Δ원단위 × 단가 × 생산량", f"{du} × {price:,} × {qty:,}", rec, "원"]]
        return v, st, rec, "DW"
    if t == "B-6":
        gap = lprng.randint(150000, 400000); qty = lprng.randint(100000, 600000); dy = round(gross / (qty * gap) * 100, 3); yb = round(lprng.uniform(90, 95), 2)
        v = [["개선전 실수율", yb, "%", "생산 DW 실수율 (기준기간)"], ["개선후 실수율", round(yb + dy, 3), "%", "생산 DW 실수율 (검증기간)"], ["생산량", qty, "톤", "생산 DW"], ["판매가 − 스크랩가", gap, "원/톤", "ERP SD · 스크랩 시세"]]
        rec = round(dy / 100 * qty * gap)
        st = [["개선폭 = 개선후 − 개선전", f"{round(yb+dy,3)} − {yb}", dy, "%p"], ["성과총액 = 개선폭 × 생산량 × 가격차", f"{dy}% × {qty:,} × {gap:,}", rec, "원"]]
        return v, st, rec, "DW"
    if t == "B-7":
        uc = lprng.randint(3000, 15000); q = round(gross / uc)
        v = [["생략 공정 처리량", q, "톤", "생산 DW"], ["공정 단위비용", uc, "원/톤", "CO 공정원가 (잠금)"]]
        st = [["성과총액 = 처리량 × 단위비용", f"{q:,} × {uc:,}", q * uc, "원"]]
        return v, st, q * uc, "DW"
    if t == "B-8":
        k = round(lprng.uniform(0.3, 0.8), 2); fc = round(gross / k)
        v = [["절감 고정비 (계정 실적)", fc, "원", "CO 고정가공비 계정"], ["환산계수", k, "", "재무실 고시 (v2 개정 검토중)"]]
        st = [["성과총액 = 고정비 × 환산계수", f"{fc:,} × {k}", round(fc * k), "원"]]
        return v, st, round(fc * k), "CO"
    if t == "B-9":
        cm = lprng.randint(80000, 200000); k = round(lprng.uniform(0.5, 0.9), 2); q = round(gross / (cm * k))
        v = [["증산량", q, "톤", "생산 DW"], ["CM_ton 톤당 한계이익", cm, "원/톤", "CO 관리회계 (잠금)"], ["가동 기여계수", k, "", "생산기술 산정"]]
        rec = round(q * cm * k)
        st = [["성과총액 = 증산량 × CM_ton × 기여계수", f"{q:,} × {cm:,} × {k}", rec, "원"]]
        return v, st, rec, "DW"
    # C-1
    prev = gross + lprng.randint(200000000, 900000000)
    v = [["기준기간 외부 용역·분석비", prev, "원", "ERP FI 판관비 계정"], ["검증기간 외부 용역·분석비", prev - gross, "원", "ERP FI 판관비 계정"]]
    st = [["성과총액 = 기준기간 − 검증기간", f"{prev:,} − {prev-gross:,}", gross, "원"]]
    return v, st, gross, "FI"

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
        ["Rule 버전 잠금", "ok" if rule["status"] == "승인" else "warn", f"{rule['id']} {rule['ver']} 잠금" if rule["status"] == "승인" else f"{rule['id']} {rule['ver']} 개정 검토중 — 잠금 전"],
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
        "keyValues": [[k, v] for k, v in zip(KEY_BY_GROUP[r["type"][0]].split("·"),
                      [r["dept"], f"{r['type']} 대상 {lprng.randint(2, 9)}개 코드", f"{lprng.randint(1, 4)}개 지정", "등록 시 지정", r["period"]])],
        "calc": {"vars": vars_, "steps": steps, "recomputedEok": eok(recomputed), "diffEok": eok(diff), "ok": recompute_ok},
        "approval": hist,
        "years": years,
        "checks": checks,
        "registeredAt": reg_day.isoformat(),
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
    "contribTable": CONTRIB_TABLE,
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
    "longterm": longterm, "executive": executive, "mw": mwpage,
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
