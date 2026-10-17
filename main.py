# -*- coding: utf-8 -*-
"""급식 월드컵: 8강 → 4강 → 결승, 대결별 Supabase 저장 확인."""

import random
from uuid import uuid4

import streamlit as st
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

    matches_this_round = len(game["participants"]) // 2
    if game["match_index"] < matches_this_round:
        game["phase"] = "ready"
        return

    advancing = game["winners"]
    if len(advancing) == 1:
        game["champion"] = advancing[0]
        game["phase"] = "done"
    else:
        game["participants"] = advancing
        game["winners"] = []
        game["match_index"] = 0
        game["phase"] = "ready"


st.set_page_config(
    page_title="급식 월드컵 | 최고의 반찬",
    page_icon="🍚",
    layout="wide",
)

st.markdown(
    """
    <style>
    .block-container {max-width: 1000px; padding-top: 2rem;}
    .hero {
        border-radius: 20px; padding: 26px 30px;
        background: linear-gradient(115deg, #fff5e6, #f4f5ff);
        border: 1px solid #ebe4d9; margin-bottom: 20px;
        color: #222;
    }
    .hero h1 {margin: 0; font-size: 2.15rem; color: #282438;}
    .hero p {margin: 8px 0 0; color: #625e6d;}
    .food-name {
        font-size: clamp(1.35rem, 3vw, 2rem);
        font-weight: 800;
        text-align: center;
        min-height: 4.2rem;
        display: flex; align-items: center; justify-content: center;
        word-break: keep-all;
    }
    .versus {text-align: center; color: #8a8296; font-size: 1.1rem; margin: 12px 0;}
    .winner-panel {
        padding: 24px; border-radius: 18px; text-align: center;
        background: linear-gradient(125deg, #fff2c4, #fffaf0);
        color: #352a10; border: 1px solid #ebd894;
    }
    .winner-panel .name {font-size: 2rem; font-weight: 900; margin-top: 8px;}
    </style>
    """,
    unsafe_allow_html=True,
)

if "meal_worldcup" not in st.session_state:
    st.session_state["meal_worldcup"] = start_game()

game = st.session_state["meal_worldcup"]

st.markdown(
    """
    <div class="hero">
      <h1>🍚 급식 반찬 월드컵</h1>
      <p>여덟 반찬 중 최고의 한 가지를 골라 보세요. 총 7번의 선택으로 우승이 결정돼요.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

saved = len(game["history"])
st.progress(saved / TOTAL_DUELS, text=f"저장 확인 완료: {saved} / {TOTAL_DUELS}대결")

if game["phase"] == "locked":
    st.error("⚠️ 저장 결과를 확인하지 못했습니다. 이 대결은 잠겼으며 재선택할 수 없습니다.")
    st.info(
        "교사에게 아래 게임 ID를 알려 주고 `menu_duels` 표의 저장 여부를 확인받으세요. "
        "응답이 없어도 실제로 저장되었을 수 있으므로 자동 재시도하지 않습니다."
    )
    st.code(game["game_id"], language=None)
    pending = game["pending"]
    if pending:
        st.write(
            f"확인이 필요한 대결: **{pending['round']}** · "
            f"**{pending['left_menu']}** vs **{pending['right_menu']}** · "
            f"선택: **{pending['winner']}**"
        )
    st.stop()

if game["phase"] == "done":
    st.markdown(
        f"""
        <div class="winner-panel">
          <div>🏆 급식 월드컵 최종 우승 🏆</div>
          <div class="name">{game["champion"]}</div>
          <div>7번의 대결을 모두 저장하고 결과를 확인했어요!</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.write("")
    if st.button("🔄 새 월드컵 시작", type="primary", use_container_width=True):
        st.session_state["meal_worldcup"] = start_game()
        st.rerun()
    st.stop()

# 정상 진행 중: 같은 라운드의 승자만 다음 라운드로 간다.
left_menu, right_menu = current_pair(game)
stage = round_name(len(game["participants"]))
round_match = game["match_index"] + 1
round_total = len(game["participants"]) // 2

st.subheader(f"🏁 {stage} · {round_match} / {round_total} 대결")
st.caption(f"전체 {saved + 1}번째 선택 · 더 먹고 싶은 반찬을 골라 주세요.")
col_left, col_right = st.columns(2, gap="large")

with col_left:
    with st.container(border=True):
        st.markdown("#### 🍽️ 왼쪽 후보")
        st.markdown(
            f'<div class="food-name">{left_menu}</div>',
            unsafe_allow_html=True,
        )
        choose_left = st.button(
            f"👈 {left_menu} 선택",
            key=f"{game['game_id']}-{saved}-left",
            use_container_width=True,
            type="primary",
        )

with col_right:
    with st.container(border=True):
        st.markdown("#### 🍱 오른쪽 후보")
        st.markdown(
            f'<div class="food-name">{right_menu}</div>',
            unsafe_allow_html=True,
        )
        choose_right = st.button(
            f"{right_menu} 선택 👉",
            key=f"{game['game_id']}-{saved}-right",
            use_container_width=True,
            type="primary",
        )

st.markdown('<div class="versus">VS · 한 대결당 한 번만 투표할 수 있어요</div>', unsafe_allow_html=True)
st.caption("이름·학번·비밀번호는 받지 않아요. 선택 결과만 Supabase에 UTF-8 문자열로 기록해요.")

if choose_left or choose_right:
    selected = left_menu if choose_left else right_menu
    with st.spinner("대결을 기록하고 저장 결과를 확인하는 중..."):
        save_and_advance(selected)
    st.rerun()
