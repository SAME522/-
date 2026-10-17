# -*- coding: utf-8 -*-
"""급식 월드컵: 8강 → 4강 → 결승, 대결별 Supabase 저장 확인."""

import random
from uuid import uuid4
from html import escape

import streamlit as st
import plotly.graph_objects as go
from supabase import create_client

MENUS = (
    "제육볶음",
    "간장찜닭",
    "가자미순살튀김",
    "돈육불백",
    "미트볼데리야끼볶음",
    "수육",
    "진미채고추장볶음",
    "치즈떡닭갈비",
)
TOTAL_DUELS = 7
RETURNING_COLUMNS = "id,game_id,round,left_menu,right_menu,winner,created_at"


def start_game() -> dict:
    """새 게임마다 후보를 한 번 섞고, 게임별 고유 ID를 만든다."""
    candidates = list(MENUS)
    random.SystemRandom().shuffle(candidates)
    return {
        "game_id": uuid4().hex,
        "participants": candidates,
        "winners": [],
        "match_index": 0,
        "history": [],
        "phase": "ready",  # ready, locked, done
        "pending": None,
        "champion": None,
        "last_result": None,
        "round_intro": None,
        "celebrated": False,
    }


def round_name(count: int) -> str:
    return {8: "8강", 4: "4강", 2: "결승"}[count]


def current_pair(game: dict) -> tuple[str, str]:
    index = game["match_index"] * 2
    players = game["participants"]
    return players[index], players[index + 1]


def is_confirmed(data: object, expected: dict) -> bool:
    """서버가 실제로 반환한 삽입 행이 요청과 일치해야만 진행한다."""
    if not isinstance(data, list) or len(data) != 1:
        return False
    row = data[0]
    if not isinstance(row, dict):
        return False
    if not all(row.get(name) == value for name, value in expected.items()):
        return False
    # DB 기본값으로 생성되는 id 및 created_at도 확인한다.
    return (
        isinstance(row.get("id"), int)
        and not isinstance(row.get("id"), bool)
        and row["id"] > 0
        and isinstance(row.get("created_at"), str)
        and bool(row["created_at"].strip())
    )


def save_and_advance(winner: str) -> None:
    """저장 확인 전에는 승자를 다음 단계로 올리지 않는다."""
    game = st.session_state["meal_worldcup"]
    if game["phase"] != "ready":
        return

    left, right = current_pair(game)
    if left == right or winner not in (left, right):
        return

    payload = {
        "game_id": game["game_id"],
        "round": round_name(len(game["participants"])),
        "left_menu": left,
        "right_menu": right,
        "winner": winner,
    }

    # 버튼이 다시 눌리거나 오류가 발생해도 같은 대결을 자동 재전송하지 않는다.
    game["phase"] = "locked"
    game["pending"] = payload

    try:
        client = create_client(
            st.secrets["SUPABASE_URL"],
            st.secrets["SUPABASE_KEY"],
        )
        response = (
            client.table("menu_duels")  # 기본 public 스키마, 스키마 이름을 붙이지 않음
            .insert(payload)
            .select(RETURNING_COLUMNS)
            .execute()
        )
        if not is_confirmed(response.data, payload):
            return
    except Exception:
        # 네트워크 오류는 서버에서 저장했지만 응답만 유실된 경우일 수도 있다.
        # 따라서 재시도하거나 다른 승자를 선택할 수 없도록 잠근다.
        return

    # 여기부터는 저장 결과가 확인된 경우에만 실행한다.
    game["history"].append(payload)
    game["winners"].append(winner)
    game["match_index"] += 1
    game["pending"] = None
    game["last_result"] = winner

    matches_this_round = len(game["participants"]) // 2
    if game["match_index"] < matches_this_round:
        game["phase"] = "ready"
        return

    advancing = game["winners"]
    if len(advancing) == 1:
        game["champion"] = advancing[0]
        game["phase"] = "done"
        game["round_intro"] = "우승 확정"
    else:
        game["participants"] = advancing
        game["winners"] = []
        game["match_index"] = 0
        game["phase"] = "ready"
        game["round_intro"] = f"{round_name(len(advancing))} 진출"



def show_class_analysis():
    st.subheader("📊 학급 전체 급식 월드컵 분석")
    if st.button("🔄 결과 다시 불러오기", key="reload_stats"):
        st.session_state.pop("class_stats", None)
    if "class_stats" not in st.session_state:
        try:
            client = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
            rows, last_id = [], 0
            while True:
                batch = (client.table("menu_duels")
                         .select("id,game_id,round,left_menu,right_menu,winner")
                         .gt("id", last_id).order("id").limit(1000).execute().data)
                if not isinstance(batch, list):
                    raise ValueError("조회 결과 형식 오류")
                if not batch:
                    break
                for item in batch:
                    if type(item.get("id")) is not int or item["id"] <= last_id:
                        raise ValueError("대결 ID 오류")
                    last_id = item["id"]
                    rows.append(item)
                if len(batch) < 1000:
                    break
            st.session_state["class_stats"] = ("ok", rows)
        except Exception:
            st.session_state["class_stats"] = ("error", [])
    state, rows = st.session_state["class_stats"]
    if state == "error":
        st.error("대결 기록 조회에 실패했습니다. Supabase 접속 정보와 SELECT 권한을 확인한 뒤 다시 불러오세요.")
        return
    if not rows:
        st.info("아직 저장된 대결 기록이 없습니다. 첫 대결이 저장되면 분석이 시작됩니다.")
    games = {str(r["game_id"]) for r in rows if r.get("game_id")}
    a, b = st.columns(2)
    a.metric("집계 대결 기록", f"{len(rows):,}건")
    b.metric("집계 판 수", f"{len(games):,}판")
    st.caption("대결 기록 수와 참여 인원은 다릅니다. 진행 중인 판에서 저장된 대결도 집계됩니다. 판 수는 서로 다른 game_id 기준이며 참여 인원 수가 아닙니다.")
    data = {m: {"반찬": m, "대결 수": 0, "승리 수": 0, "우승 횟수": 0} for m in MENUS}
    for r in rows:
        left, right, winner = r.get("left_menu"), r.get("right_menu"), r.get("winner")
        if left in data:
            data[left]["대결 수"] += 1
        if right in data:
            data[right]["대결 수"] += 1
        if winner in data:
            data[winner]["승리 수"] += 1
            if r.get("round") == "결승":
                data[winner]["우승 횟수"] += 1
    ranking = sorted(data.values(), key=lambda x: (-(x["승리 수"] / x["대결 수"] if x["대결 수"] else -1), -x["승리 수"], x["반찬"]))
    table = [{**d, "승률": f'{100*d["승리 수"]/d["대결 수"]:.1f}%' if d["대결 수"] else "아직 알 수 없음"} for d in ranking]
    st.dataframe(table, use_container_width=True, hide_index=True, column_order=["반찬", "대결 수", "승리 수", "승률", "우승 횟수"])
    st.caption("대결 기록이 없는 후보는 승률을 아직 알 수 없어 그래프에서 수치가 표시되지 않습니다.")
    fig = go.Figure(go.Bar(
        x=[100*d["승리 수"]/d["대결 수"] if d["대결 수"] else None for d in ranking[::-1]],
        y=[d["반찬"] for d in ranking[::-1]],
        orientation="h",
        text=[f'{100*d["승리 수"]/d["대결 수"]:.1f}%' if d["대결 수"] else "기록 없음" for d in ranking[::-1]],
        textposition="auto",
        marker=dict(color="#a77bff"),
        hovertemplate="%{y}: %{text}<extra></extra>",
    ))
    fig.update_layout(title="반찬별 승률 비교", xaxis_title="승률 (%)", yaxis_title="", xaxis=dict(range=[0, 105], ticksuffix="%"), height=480, template="plotly_dark", margin=dict(l=15, r=15, t=65, b=35))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


MENU_STYLE = {
    "제육볶음": ("🔥", "불맛의 챔피언", "HOT & SPICY"),
    "간장찜닭": ("🍗", "달콤짭짤 강자", "SWEET & SAVORY"),
    "가자미순살튀김": ("🐟", "바삭함의 정석", "CRISPY MASTER"),
    "돈육불백": ("🥩", "밥도둑의 귀환", "RICE THIEF"),
    "미트볼데리야끼볶음": ("🍡", "소스의 마법사", "SAUCE BOSS"),
    "수육": ("🍖", "부드러움의 제왕", "TENDER KING"),
    "진미채고추장볶음": ("🌶️", "매콤한 역전 카드", "SPICY WILDCARD"),
    "치즈떡닭갈비": ("🧀", "치즈 폭발 에이스", "CHEESE LEGEND"),
}


def background_effects() -> str:
    rng = random.Random(20261017)
    particles = []
    for _ in range(33):
        particles.append(
            '<i class="space-dust" style="'
            f'--x:{rng.randint(1, 98)}%;'
            f'--delay:{rng.uniform(-23, 0):.2f}s;'
            f'--duration:{rng.uniform(11, 27):.2f}s;'
            f'--size:{rng.randint(2, 6)}px"></i>'
        )
    return (
        '<div class="world-bg" aria-hidden="true">'
        '<div class="world-grid"></div>'
        '<div class="world-aura aura-one"></div>'
        '<div class="world-aura aura-two"></div>'
        + "".join(particles) + "</div>"
    )


def confetti_effects() -> str:
    rng = random.Random(8008)
    pieces = []
    for i in range(74):
        pieces.append(
            '<i class="victory-confetti" style="'
            f'--x:{rng.randint(0, 100)}%;'
            f'--delay:{rng.uniform(-9, 0):.2f}s;'
            f'--duration:{rng.uniform(4, 9):.2f}s;'
            f'--rot:{rng.randint(180, 900)}deg;'
            f'--hue:{[35, 46, 180, 270, 326][i % 5]}"></i>'
        )
    return '<div class="confetti-layer" aria-hidden="true">' + "".join(pieces) + "</div>"


def stages_bar(completed: int) -> str:
    parts = []
    for index, (name, threshold, end) in enumerate(
        (("8강", 0, 4), ("4강", 4, 6), ("결승", 6, 7))
    ):
        state = (
            "complete" if completed >= end
            else "active" if completed >= threshold
            else "future"
        )
        mark = "✓" if state == "complete" else str(index + 1).zfill(2)
        parts.append(
            f'<div class="step {state}"><div class="step-number">{mark}</div>'
            f'<div class="step-title">{name}</div></div>'
        )
        if index < 2:
            parts.append('<div class="step-connector"></div>')
    return '<div class="stages">' + "".join(parts) + "</div>"


def duel_card(menu: str, side: str) -> str:
    icon, description, english = MENU_STYLE[menu]
    number = "01" if side == "left" else "02"
    return f"""
    <div class="fighter fighter-{side}">
        <div class="fighter-topline">
            <span class="fighter-number">{number}</span>
            <span class="fighter-tag">CHALLENGER</span>
        </div>
        <div class="fighter-icon">{icon}</div>
        <div class="fighter-eng">{escape(english)}</div>
        <div class="fighter-name">{escape(menu)}</div>
        <div class="fighter-sub">{escape(description)}</div>
        <div class="fighter-bottom">★ 급식 레전드 후보 ★</div>
    </div>
    """


def winner_history(game: dict) -> str:
    tiles = []
    for i, row in enumerate(game["history"], 1):
        winner = row["winner"]
        tiles.append(
            '<div class="history-tile">'
            f'<div class="history-index">MATCH {i:02}</div>'
            f'<div class="history-emoji">{MENU_STYLE[winner][0]}</div>'
            f'<div class="history-title">{escape(winner)}</div>'
            f'<div class="history-round">{escape(row["round"])} 승리</div>'
            "</div>"
        )
    return '<div class="history-grid">' + "".join(tiles) + "</div>"


STYLE = '\n<style>\n:root{color-scheme:dark;}\nhtml{scroll-behavior:smooth;}\n[data-testid="stAppViewContainer"]{\n  background:#080b1c!important;color:#f6f4ff!important;\n  background-image:radial-gradient(ellipse at 50% 10%,#1d174b 0%,#080b1c 65%)!important;\n  overflow-x:hidden;\n}\n[data-testid="stHeader"]{background:transparent!important;}\n[data-testid="stToolbar"], [data-testid="stDecoration"]{opacity:.36;}\n[data-testid="stMainBlockContainer"]{max-width:1120px!important;padding-top:2.3rem!important;padding-bottom:4rem!important;position:relative;z-index:2;}\nsection.main h1,section.main h2,section.main h3, p, span, label {font-family: \'Pretendard\',\'Noto Sans KR\',\'Malgun Gothic\',sans-serif;}\n[data-testid="stAppViewContainer"] p {color:#e5e3fa;}\n.world-bg{position:fixed;inset:0;z-index:0;overflow:hidden;pointer-events:none;}\n.world-grid{position:absolute;inset:0;opacity:.23;background-image:linear-gradient(#6956be26 1px,transparent 1px),linear-gradient(90deg,#6956be26 1px,transparent 1px);background-size:58px 58px;transform:perspective(500px) rotateX(20deg) scale(1.6);animation:gridFlow 26s linear infinite;mask-image:linear-gradient(transparent 0%,#000 35%,transparent 95%);}\n.world-aura{position:absolute;width:51vw;height:51vw;filter:blur(80px);border-radius:50%;opacity:.19;animation:auraFloat 12s ease-in-out infinite alternate;}\n.aura-one{top:-24vw;left:-17vw;background:#bc2bfa;}\n.aura-two{right:-23vw;bottom:-21vw;background:#06d9e5;animation-delay:-7s;}\n.space-dust{position:absolute;display:block;left:var(--x);bottom:-5vh;width:var(--size);height:var(--size);border-radius:100%;background:#a9c5ff;box-shadow:0 0 12px 3px #a88bff80;opacity:0;animation:dustRise var(--duration) linear var(--delay) infinite;}\n.hero-shell{position:relative;overflow:hidden;border:1px solid #927aff68;border-radius:27px;padding:34px 24px 28px;text-align:center;background:linear-gradient(135deg,#24204cdb 0%,#111632ef 48%,#222045db 100%);box-shadow:0 26px 70px #0008, inset 0 0 40px #604ebf12;isolation:isolate;}\n.hero-shell::before{content:"";position:absolute;inset:-100%;background:conic-gradient(transparent 0deg,transparent 175deg,#9d80ff60 197deg,transparent 220deg,transparent 360deg);animation:rotateBeam 10s linear infinite;z-index:-2;}\n.hero-shell::after{content:"";position:absolute;inset:2px;background:linear-gradient(132deg,#252047 4%,#11152c 56%,#1a1940 100%);border-radius:25px;z-index:-1;}\n.hero-kicker{display:inline-flex;gap:9px;align-items:center;color:#72edff!important;font-size:11px;letter-spacing:4px;font-weight:900;border:1px solid #62d5f844;border-radius:99px;padding:8px 16px;background:#1c447035;animation:gentlePulse 2.5s ease-in-out infinite;}\n.hero-crown{font-size:50px;display:block;filter:drop-shadow(0 0 25px #fcbe67);animation:crownFloat 3.6s ease-in-out infinite;margin:8px auto 0;}\n.hero-title{font-size:clamp(2.6rem,6.9vw,4.5rem)!important;line-height:1.18;font-weight:1000;letter-spacing:-3px;margin:8px 0 7px!important;background:linear-gradient(100deg,#f9f5ff 2%,#fa99fe 28%,#9fefff 64%,#ffe2a3 95%);background-size:220% auto;-webkit-background-clip:text;background-clip:text;color:transparent!important;animation:titleGlide 8s linear infinite;text-shadow:0 10px 50px #9d7bff33;}\n.hero-desc{color:#bdc3e1!important;font-size:clamp(.82rem,1.5vw,1rem);line-height:1.7;margin:0!important;word-break:keep-all;}\n.hero-sheen{position:absolute;top:-50%;left:-55%;width:30%;height:200%;transform:rotate(22deg);background:linear-gradient(90deg,transparent,#fff2,transparent);animation:shineMove 8s ease-in-out infinite;pointer-events:none;}\n.pill-row{display:flex;justify-content:center;align-items:center;flex-wrap:wrap;gap:10px;margin-top:21px;}\n.mini-pill{border-radius:99px;padding:8px 12px;font-size:11px;letter-spacing:1px;font-weight:800;color:#c8c8e5;background:#ffffff0d;border:1px solid #ffffff1b;}\n.mini-pill span{color:#f4c579;}\n.hud{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:19px 0 13px;}\n.hud-box{border:1px solid #7476be4a;background:linear-gradient(130deg,#232342aa,#121831b3);padding:15px 18px;border-radius:17px;box-shadow:inset 0 1px 0 #fff1;}\n.hud-label{color:#9eacd0;font-size:10px;font-weight:900;letter-spacing:2px;margin-bottom:5px;}\n.hud-value{color:#fff;font-weight:900;font-size:clamp(16px,2.5vw,23px);}\n.hud-box:nth-child(2) .hud-value{color:#91f4ff;}\n.hud-box:nth-child(3) .hud-value{color:#ffdc91;}\n.stages{display:flex;align-items:center;justify-content:center;margin:17px auto 20px;max-width:630px;gap:11px;}\n.step{display:flex;gap:9px;align-items:center;opacity:.41;white-space:nowrap;}\n.step.active,.step.complete{opacity:1;}\n.step-number{display:grid;place-items:center;width:33px;height:33px;border:1px solid #7d76af80;background:#1b2242;border-radius:50%;font-size:11px;font-weight:950;color:#aaacd3;}\n.step-title{font-size:12px;font-weight:900;color:#d9d5f6;}\n.step.active .step-number{color:#0a1124;background:linear-gradient(135deg,#78e7f8,#dd9aff);border-color:transparent;box-shadow:0 0 19px #9cf6ff77;animation:gentlePulse 1.6s ease-in-out infinite;}\n.step.complete .step-number{background:#62dfb345;color:#9affd6;border-color:#74e8bb66;}\n.step-connector{height:1px;flex:1;max-width:80px;background:linear-gradient(90deg,#57548b,#aa80df88);}\n[data-testid="stProgress"]{margin-top:-10px;}\n[data-testid="stProgress"] [data-testid="stProgressBar"]{height:10px;border-radius:90px;background:#ffffff12;}\n[data-testid="stProgress"] [role="progressbar"]>div{background:linear-gradient(90deg,#746fff,#df82ff,#80ecff)!important;border-radius:90px;box-shadow:0 0 16px #9b99ffaa;}\n.section-eyebrow{letter-spacing:3px;color:#7eeeff;font-weight:950;font-size:11px;text-align:center;margin-top:31px;}\n.section-title{text-align:center;font-weight:1000;font-size:clamp(1.5rem,3.4vw,2.3rem);margin:8px 0;color:#fff;}\n.section-sub{text-align:center;color:#919abb!important;font-size:12px;margin-bottom:14px;}\n.vs-area{text-align:center;position:relative;padding:4px 0 11px;margin:0 auto -68px;transform:translateY(150px);z-index:5;pointer-events:none;}\n.vs-core{display:inline-grid;place-items:center;position:relative;width:86px;height:86px;border-radius:50%;color:#fff;font-weight:1000;font-size:30px;font-style:italic;letter-spacing:-2px;background:linear-gradient(145deg,#f337ab,#603cdd 52%,#05bfd8);border:3px solid #d9b8ff;box-shadow:0 0 0 8px #ad72f01b, 0 0 40px #f25edc7c;text-shadow:0 4px 14px #000a;animation:vsThrob 2.3s ease-in-out infinite;}\n.vs-core::before,.vs-core::after{content:"";position:absolute;inset:-10px;border:1px dashed #83e5ff66;border-radius:50%;animation:rotateBeam 7s linear infinite;}\n.vs-core::after{inset:-21px;border-color:#ce78ff44;animation-duration:12s;animation-direction:reverse;}\n.fighter{position:relative;text-align:center;overflow:hidden;border-radius:22px 22px 10px 10px;padding:24px 9px 21px;min-height:308px;border:1px solid #ffffff25;background:radial-gradient(ellipse at 50% 19%,#8241c955 0%,transparent 64%),linear-gradient(155deg,#26204f,#11162f);box-shadow:inset 0 1px 0 #ffffff24, 0 17px 35px #0509146b;isolation:isolate;animation:enterLeft .6s cubic-bezier(.1,.8,.2,1) both;}\n.fighter-right{background:radial-gradient(ellipse at 50% 19%,#138fa54f 0%,transparent 65%),linear-gradient(155deg,#172c4e,#11162f);animation-name:enterRight;}\n.fighter::after{content:"";position:absolute;inset:0;pointer-events:none;background:linear-gradient(111deg,transparent 31%,#ffffff0c 50%,transparent 67%);background-size:250% 100%;animation:cardSweep 6s ease-in-out infinite;z-index:2;}\n.fighter::before{content:"";position:absolute;inset:0;border-radius:inherit;pointer-events:none;box-shadow:inset 0 0 38px #a062ff12;}\n.fighter-right::before{box-shadow:inset 0 0 38px #65deff10;}\n.fighter-topline{position:relative;z-index:1;display:flex;justify-content:space-between;align-items:center;padding:0 14px;}\n.fighter-number{font-size:13px;color:#b7b3ed;font-weight:1000;letter-spacing:3px;}\n.fighter-tag{font-size:8px;letter-spacing:2px;font-weight:950;color:#bcb3e4;padding:5px 9px;background:#ffffff0e;border-radius:80px;border:1px solid #ffffff21;}\n.fighter-icon{font-size:clamp(66px,10vw,98px);line-height:1.4;margin-top:11px;filter:drop-shadow(0 12px 19px #0008);animation:iconFloat 3s ease-in-out infinite;}\n.fighter-right .fighter-icon{animation-delay:-1.4s;}\n.fighter-eng{font-size:10px;color:#f0b5ff;font-weight:1000;letter-spacing:2.4px;}\n.fighter-right .fighter-eng{color:#7ae9ff;}\n.fighter-name{font-weight:1000;font-size:clamp(1.2rem,2.5vw,1.7rem);line-height:1.4;margin:7px 0 5px;color:#faf8ff;word-break:keep-all;min-height:2.1em;display:grid;place-items:center;}\n.fighter-sub{color:#aaaaca;font-size:12px;font-weight:700;}\n.fighter-bottom{border-top:1px solid #ffffff1a;padding-top:12px;margin:18px 13px 0;color:#827fa8;font-size:10px;letter-spacing:2px;}\n[data-testid="stVerticalBlockBorderWrapper"]{border-color:#8e8acd55!important;border-radius:23px!important;background:#0f142d99;box-shadow:0 14px 33px #0005;transition:transform .25s ease,border-color .25s ease;}\n[data-testid="stVerticalBlockBorderWrapper"]:hover{border-color:#a88affbb!important;transform:translateY(-3px);}\n[data-testid="stButton"] > button{background:linear-gradient(90deg,#8c52f7,#bf47d9)!important;color:white!important;border:1px solid #ebcaff80!important;border-radius:14px!important;font-weight:950!important;min-height:54px!important;box-shadow:0 7px 21px #8a56ee50, inset 0 1px 0 #fff4!important;transition:transform .16s ease,filter .2s ease,box-shadow .2s ease!important;white-space:normal!important;word-break:keep-all!important;}\n[data-testid="stButton"] > button:hover{transform:translateY(-3px) scale(1.012);filter:brightness(1.15);box-shadow:0 12px 32px #c068ff70!important;}\n[data-testid="stButton"] > button:active{transform:translateY(1px) scale(.98);}\n[data-testid="stButton"] > button:focus-visible{outline:3px solid #8ef6ff!important;outline-offset:3px;}\n[data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(2) [data-testid="stButton"] > button{background:linear-gradient(90deg,#117fd7,#2ac5c9)!important;box-shadow:0 7px 21px #24b8da50!important;}\n.hint-note{text-align:center;font-size:11px;color:#858bb4;margin-top:15px;letter-spacing:1px;}\n.win-flash{position:relative;text-align:center;overflow:hidden;padding:16px;border:1px solid #69e8c78b;background:linear-gradient(100deg,#143c4799,#1a304599);border-radius:15px;margin:15px 0;color:#c7ffea;font-weight:850;animation:messagePop .62s cubic-bezier(.2,1.5,.4,1) both;box-shadow:0 0 25px #69f8d71a;}\n.win-flash strong{color:#fff;font-size:1.15em;}\n.round-transition{position:fixed;inset:0;z-index:999;display:grid;place-items:center;pointer-events:none;background:radial-gradient(circle,#592d9bd9,#050a18db);animation:transitionOut 1.9s ease-out forwards;}\n.transition-text{font-weight:1000;font-size:clamp(2.6rem,9vw,7rem);color:#fff;text-shadow:0 0 17px #fa91ff,0 0 80px #7de3ff;transform:scale(.45) rotate(-5deg);animation:transitionIn 1.6s ease-out forwards;letter-spacing:-2px;}\n.confetti-layer{position:fixed;inset:0;overflow:hidden;z-index:8;pointer-events:none;}\n.victory-confetti{position:absolute;top:-15vh;left:var(--x);width:9px;height:16px;border-radius:2px;background:hsl(var(--hue),95%,70%);box-shadow:0 0 8px currentColor;opacity:0;animation:confettiFall var(--duration) linear var(--delay) infinite;}\n.champion-wrap{position:relative;overflow:hidden;text-align:center;padding:55px 20px 43px;margin:25px 0 18px;border:1px solid #fdd98c96;border-radius:28px;background:radial-gradient(ellipse at 50% 0%,#ae682947,transparent 70%),linear-gradient(140deg,#31234d,#17152d 55%,#332146);box-shadow:0 0 45px #ffb65b2b,0 27px 80px #050814a1;}\n.champion-wrap::before{content:"";position:absolute;inset:-50%;z-index:0;background:conic-gradient(from 0deg,transparent,#ffe3a614,transparent,#ffd19e19,transparent);animation:rotateBeam 12s linear infinite;}\n.champion-content{position:relative;z-index:1;}\n.champion-crown{font-size:90px;line-height:1.4;filter:drop-shadow(0 7px 24px #ffdb8d);animation:crownFloat 3s ease-in-out infinite;}\n.champion-mini{font-size:12px;font-weight:1000;letter-spacing:6px;color:#f6d99e;}\n.champion-name{font-size:clamp(2rem,7vw,4rem);line-height:1.25;margin:10px 0;font-weight:1000;color:#fff6cf;text-shadow:0 0 30px #e9ae64a0;word-break:keep-all;animation:championShine 3s ease-in-out infinite;}\n.champion-desc{color:#dfcfb2!important;font-size:13px;}\n.trophy-divider{height:2px;width:140px;margin:20px auto;background:linear-gradient(90deg,transparent,#ffd88a,transparent);}\n.history-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin-top:15px;}\n.history-tile{text-align:center;border-radius:13px;padding:13px 9px;background:linear-gradient(150deg,#232446,#111a32);border:1px solid #ffffff20;animation:messagePop .48s ease-out both;}\n.history-index{color:#8a91c0;font-weight:900;font-size:9px;letter-spacing:1.8px;}\n.history-emoji{font-size:29px;margin:7px 0;}\n.history-title{font-size:12px;color:#fff;font-weight:900;word-break:keep-all;min-height:2em;}\n.history-round{font-size:10px;color:#9becd8;margin-top:5px;}\n.status-panel{padding:21px;border-radius:19px;background:#402939;border:1px solid #ff809a70;color:#fce4e8;box-shadow:0 0 32px #ff607d19;}\n.status-panel h3{margin:0 0 8px;font-size:19px;color:#ffdbe4;}\n.game-id{font-size:13px;color:#a7aacd;text-align:center;margin-top:17px;letter-spacing:1px;}\n[data-testid="stExpander"]{border:1px solid #6c73a04b!important;border-radius:14px!important;background:#161b33ad;}\n[data-testid="stExpander"] summary{color:#eef1ff!important;font-weight:850;}\n@keyframes gridFlow{to{background-position:0 58px,58px 0;}}\n@keyframes auraFloat{to{transform:translate(17%,18%) scale(1.15);}}\n@keyframes dustRise{0%{transform:translate3d(0,0,0);opacity:0}12%{opacity:.7}88%{opacity:.7}100%{transform:translate3d(25px,-115vh,0);opacity:0}}\n@keyframes rotateBeam{to{transform:rotate(360deg);}}\n@keyframes crownFloat{0%,100%{transform:translateY(0) rotate(-4deg)}50%{transform:translateY(-10px) rotate(5deg)}}\n@keyframes titleGlide{to{background-position:220% center;}}\n@keyframes gentlePulse{50%{filter:brightness(1.3);box-shadow:0 0 21px #92c5ff4d;}}\n@keyframes shineMove{0%,35%{left:-55%}65%,100%{left:140%}}\n@keyframes vsThrob{0%,100%{transform:scale(1) rotate(-4deg)}50%{transform:scale(1.1) rotate(4deg)}}\n@keyframes iconFloat{0%,100%{transform:translateY(0) rotate(-4deg)}50%{transform:translateY(-8px) rotate(3deg)}}\n@keyframes cardSweep{0%,38%{background-position:250% 0}75%,100%{background-position:-250% 0}}\n@keyframes enterLeft{from{transform:translateX(-34px) rotate(-3deg);opacity:0}to{transform:translateX(0) rotate(0);opacity:1}}\n@keyframes enterRight{from{transform:translateX(34px) rotate(3deg);opacity:0}to{transform:translateX(0) rotate(0);opacity:1}}\n@keyframes messagePop{from{transform:scale(.9) translateY(12px);opacity:0}to{transform:scale(1) translateY(0);opacity:1}}\n@keyframes transitionOut{0%,68%{opacity:1}100%{opacity:0;visibility:hidden}}\n@keyframes transitionIn{0%{transform:scale(.3) rotate(-9deg);opacity:0}33%{transform:scale(1.13) rotate(2deg);opacity:1}55%,100%{transform:scale(1) rotate(0);opacity:1}}\n@keyframes confettiFall{0%{transform:translate3d(0,-15vh,0) rotate(0);opacity:0}10%{opacity:1}90%{opacity:1}100%{transform:translate3d(115px,120vh,0) rotate(var(--rot));opacity:0}}\n@keyframes championShine{50%{filter:brightness(1.3)}}\n@media(max-width:650px){\n [data-testid="stMainBlockContainer"]{padding-top:1rem!important;padding-left:13px!important;padding-right:13px!important;}\n .hero-shell{padding:25px 10px 20px;border-radius:19px;}\n .hero-title{letter-spacing:-1.8px;}\n .hero-kicker{font-size:9px;letter-spacing:2px;}\n .hud{gap:6px;}\n .hud-box{padding:11px 7px;border-radius:12px;}\n .hud-label{font-size:8px;letter-spacing:1px;}\n .hud-value{font-size:14px;}\n .stages{gap:6px;}\n .step{gap:4px;}\n .step-number{width:25px;height:25px;font-size:9px;}\n .step-title{font-size:10px;}\n .fighter{padding:17px 3px 15px;min-height:242px;}\n .fighter-topline{padding:0 5px;}\n .fighter-tag{letter-spacing:0;font-size:7px;}\n .fighter-icon{font-size:55px;margin-top:7px;}\n .fighter-eng{font-size:8px;letter-spacing:1px;}\n .fighter-name{font-size:clamp(.93rem,3.7vw,1.35rem);min-height:2.5em;}\n .fighter-sub{font-size:10px;}\n .fighter-bottom{font-size:8px;letter-spacing:0;margin:11px 2px 0;}\n .vs-area{transform:translateY(120px);margin-bottom:-50px;}\n .vs-core{width:62px;height:62px;font-size:22px;}\n [data-testid="stButton"] > button{font-size:11px!important;padding:.65rem .22rem!important;}\n}\n@media(prefers-reduced-motion:reduce){\n *,*::before,*::after{animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important;scroll-behavior:auto!important;}\n .world-bg,.confetti-layer,.round-transition{display:none!important;}\n}\n</style>\n'


st.set_page_config(
    page_title="급식 월드컵 | ULTIMATE FOOD ARENA",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="collapsed",
)
st.markdown(STYLE, unsafe_allow_html=True)
st.markdown(background_effects(), unsafe_allow_html=True)

if "meal_worldcup" not in st.session_state:
    st.session_state["meal_worldcup"] = start_game()

game = st.session_state["meal_worldcup"]
completed = len(game["history"])

st.markdown(
    """
    <div class="hero-shell">
      <div class="hero-sheen" aria-hidden="true"></div>
      <div class="hero-kicker">✦ THE ULTIMATE LUNCH BATTLE ✦</div>
      <div class="hero-crown" aria-hidden="true">🏆</div>
      <h1 class="hero-title">급식 월드컵</h1>
      <p class="hero-desc">오늘의 밥도둑, 최후의 생존자는 누구?
      <br>단 한 가지 반찬만 왕좌에 오른다!</p>
      <div class="pill-row">
        <span class="mini-pill">⚡ <span>8</span> CHALLENGERS</span>
        <span class="mini-pill">⚔️ <span>7</span> BATTLES</span>
        <span class="mini-pill">👑 <span>1</span> CHAMPION</span>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

if game["phase"] == "done":
    stage = "우승"
elif game["phase"] == "locked" and game["pending"]:
    stage = game["pending"]["round"]
else:
    stage = round_name(len(game["participants"]))

status = (
    "🏆 완료" if game["phase"] == "done"
    else "🔒 확인 필요" if game["phase"] == "locked"
    else "⚡ 진행 중"
)
st.markdown(
    '<div class="hud">'
    f'<div class="hud-box"><div class="hud-label">CURRENT ROUND</div>'
    f'<div class="hud-value">{escape(stage)}</div></div>'
    f'<div class="hud-box"><div class="hud-label">VERIFIED WINS</div>'
    f'<div class="hud-value">{completed} / 7</div></div>'
    f'<div class="hud-box"><div class="hud-label">MATCH STATUS</div>'
    f'<div class="hud-value">{status}</div></div>'
    '</div>',
    unsafe_allow_html=True,
)
st.markdown(stages_bar(completed), unsafe_allow_html=True)
st.progress(completed / TOTAL_DUELS, text=f"저장 확인된 대결 {completed} / 7")

tab_game, tab_stats = st.tabs(["⚔️ 월드컵 대결", "📊 학급 전체 분석"])
with tab_stats:
    show_class_analysis()

with tab_game:
    if game["phase"] == "locked":
        pending = game["pending"]
        st.markdown(
            '<div class="status-panel"><h3>🔒 대결이 안전하게 잠겼어요</h3>'
            '저장 결과를 확인하지 못했습니다. 재선택과 진행을 제한합니다.'
            '<br>교사에게 게임 ID와 대결 정보를 알려 확인받으세요.</div>',
            unsafe_allow_html=True,
        )
        if pending:
            st.error(
                f"확인할 대결: {pending['round']} · "
                f"{pending['left_menu']} VS {pending['right_menu']} · "
                f"선택: {pending['winner']}"
            )
        st.code(game["game_id"], language=None)
        st.caption("서버에서 저장했으나 응답만 유실되었을 수도 있어 자동 재전송하지 않습니다.")

    elif game["phase"] == "done":
        if not game["celebrated"]:
            st.balloons()
            game["celebrated"] = True
        st.markdown(confetti_effects(), unsafe_allow_html=True)
        icon = MENU_STYLE[game["champion"]][0]
        st.markdown(
            '<div class="champion-wrap"><div class="champion-content">'
            '<div class="champion-mini">THE ONE AND ONLY WINNER</div>'
            '<div class="champion-crown">👑</div>'
            f'<div class="champion-name">{icon} {escape(game["champion"])} {icon}</div>'
            '<div class="trophy-divider"></div>'
            '<p class="champion-desc">🏆 일곱 번의 승부를 모두 저장 확인했어요!</p>'
            '</div></div>',
            unsafe_allow_html=True,
        )
        if st.button("🔁 새로운 월드컵 시작하기", use_container_width=True, type="primary"):
            st.session_state["meal_worldcup"] = start_game()
            st.rerun()
        with st.expander("🏅 이번 월드컵의 승리 기록 (7경기)", expanded=True):
            st.markdown(winner_history(game), unsafe_allow_html=True)
        st.markdown(
            f'<div class="game-id">GAME ID · {escape(game["game_id"][:12])}</div>',
            unsafe_allow_html=True,
        )

    else:
        if game["round_intro"]:
            st.markdown(
                '<div class="round-transition" aria-hidden="true">'
                f'<div class="transition-text">⚡ {escape(game["round_intro"])} ⚡</div>'
                '</div>',
                unsafe_allow_html=True,
            )
            game["round_intro"] = None

        if game["last_result"]:
            st.markdown(
                f'<div class="win-flash">✨ <strong>{escape(game["last_result"])}</strong>'
                ' 승리! &nbsp; | &nbsp; 저장 확인 완료 ✅</div>',
                unsafe_allow_html=True,
            )

        left_menu, right_menu = current_pair(game)
        round_title = round_name(len(game["participants"]))
        match_no = game["match_index"] + 1
        match_total = len(game["participants"]) // 2

        st.markdown(
            f'<div class="section-eyebrow">⚡ ROUND {escape(round_title)} · '
            f'FIGHT {match_no:02}/{match_total:02} ⚡</div>'
            '<div class="section-title">누가 다음 라운드에 진출할까?</div>'
            f'<div class="section-sub">전체 {completed + 1}번째 선택 · '
            '마음에 드는 반찬 하나를 눌러 주세요</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="vs-area"><div class="vs-core">VS</div></div>',
            unsafe_allow_html=True,
        )

        left_col, right_col = st.columns(2, gap="medium")
        with left_col:
            with st.container(border=True):
                st.markdown(duel_card(left_menu, "left"), unsafe_allow_html=True)
                choose_left = st.button(
                    f"💜 {left_menu} 선택",
                    key=f"{game['game_id']}-{completed}-left",
                    use_container_width=True,
                    type="primary",
                )
        with right_col:
            with st.container(border=True):
                st.markdown(duel_card(right_menu, "right"), unsafe_allow_html=True)
                choose_right = st.button(
                    f"💠 {right_menu} 선택",
                    key=f"{game['game_id']}-{completed}-right",
                    use_container_width=True,
                    type="primary",
                )

        st.markdown(
            '<div class="hint-note">🛡️ 한 대결당 한 번만 투표 · '
            '저장 확인 후에만 다음 경기로 진출</div>',
            unsafe_allow_html=True,
        )
        if completed:
            with st.expander(f"📜 지금까지의 승리 기록 · {completed}대결"):
                st.markdown(winner_history(game), unsafe_allow_html=True)

        st.markdown(
            f'<div class="game-id">🔐 익명 게임 · ID {escape(game["game_id"][:12])}'
            ' · 개인 정보 입력 없음</div>',
            unsafe_allow_html=True,
        )

        if choose_left or choose_right:
            selected = left_menu if choose_left else right_menu
            with st.spinner("⚡ 기록 저장 및 승리 확인 중..."):
                save_and_advance(selected)
            st.rerun()
