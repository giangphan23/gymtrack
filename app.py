import json
import time
from pathlib import Path
from typing import Optional

import streamlit as st

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Simple Strength",
    page_icon="🏋️",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ── Mobile-friendly CSS ───────────────────────────────────────────────────────
st.markdown(
    """
    <style>
        /* Bigger tap targets for gym use */
        .stButton > button {
            height: 3.5rem;
            font-size: 1.1rem;
            font-weight: 600;
            border-radius: 10px;
        }
        /* Muted done-set buttons */
        .stButton > button:disabled {
            opacity: 0.45;
        }
        /* Timer display */
        .timer-box {
            text-align: center;
            padding: 1rem 0 0.5rem;
        }
        .timer-number {
            font-size: 5rem;
            font-weight: 900;
            line-height: 1;
            color: #FF4B4B;
        }
        .timer-label {
            font-size: 1rem;
            color: #888;
            margin-top: 0.25rem;
        }
        /* Metric labels */
        [data-testid="metric-container"] {
            background: #1e1e2e;
            border-radius: 10px;
            padding: 0.75rem 1rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Config ────────────────────────────────────────────────────────────────────
CONFIG_PATH = Path(__file__).parent / "config.json"


@st.cache_data
def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as fh:
        return json.load(fh)


config = load_config()
workout_names = list(config.keys())


def first_exercise(workout_name: str) -> str:
    return list(config[workout_name].keys())[0]


# ── Session-state initialisation ──────────────────────────────────────────────
if "active_workout" not in st.session_state:
    st.session_state.active_workout = workout_names[0]

if "active_exercise" not in st.session_state:
    st.session_state.active_exercise = first_exercise(st.session_state.active_workout)

if "sets_done" not in st.session_state:
    st.session_state.sets_done: list[int] = []

if "last_set_time" not in st.session_state:
    st.session_state.last_set_time: Optional[float] = None

# ── Title ─────────────────────────────────────────────────────────────────────
st.title("🏋️ Simple Strength")

# ── Workout selector ──────────────────────────────────────────────────────────
selected_workout: str = st.radio(
    "Workout",
    options=workout_names,
    index=workout_names.index(st.session_state.active_workout),
    horizontal=True,
    label_visibility="collapsed",
)

# Reset progress whenever the user switches workout
if selected_workout != st.session_state.active_workout:
    st.session_state.active_workout = selected_workout
    st.session_state.active_exercise = first_exercise(selected_workout)
    st.session_state.sets_done = []
    st.session_state.last_set_time = None

exercise_names = list(config[st.session_state.active_workout].keys())

# Ensure active_exercise is valid for the current workout
if st.session_state.active_exercise not in exercise_names:
    st.session_state.active_exercise = exercise_names[0]

# ── Exercise selector ─────────────────────────────────────────────────────────
selected: str = st.selectbox(
    "Exercise",
    options=exercise_names,
    index=exercise_names.index(st.session_state.active_exercise),
    label_visibility="collapsed",
    key=f"exercise_selector_{st.session_state.active_workout}",
)

# Guard against None or stale selectbox session state for the current workout
if not selected or selected not in config[st.session_state.active_workout]:
    selected = first_exercise(st.session_state.active_workout)
    st.session_state.active_exercise = selected
    st.session_state[f"exercise_selector_{st.session_state.active_workout}"] = selected

# Reset progress whenever the user switches exercise
if selected != st.session_state.active_exercise:
    st.session_state.active_exercise = selected
    st.session_state.sets_done = []
    st.session_state.last_set_time = None

ex = config[st.session_state.active_workout][selected]
total_sets: int = ex["sets"]
reps: int = ex["reps"]
weight: float = ex["weight"]
rest_seconds: int = ex["rest_seconds"]

# ── Dashboard metrics ─────────────────────────────────────────────────────────
c1, c2, c3 = st.columns(3)
c1.metric("Weight", f"{weight} kg")
c2.metric("Sets × Reps", f"{total_sets} × {reps}")
c3.metric("Rest", f"{rest_seconds} s")

st.divider()

# ── Set buttons ───────────────────────────────────────────────────────────────
st.subheader("Sets")
button_cols = st.columns(total_sets)

for i in range(total_sets):
    done = i in st.session_state.sets_done
    label = f"✅ {i + 1}" if done else f"Set {i + 1}"
    if button_cols[i].button(
        label,
        key=f"set_{i}",
        disabled=done,
        use_container_width=True,
    ):
        st.session_state.sets_done.append(i)
        st.session_state.last_set_time = time.time()
        st.rerun()

# ── Rest timer ────────────────────────────────────────────────────────────────
st.divider()

if st.session_state.last_set_time is not None:
    elapsed = time.time() - st.session_state.last_set_time
    remaining = rest_seconds - elapsed

    if remaining > 0:
        st.markdown(
            f"""
            <div class="timer-box">
                <div class="timer-number">⏱ {int(remaining)}</div>
                <div class="timer-label">seconds remaining — rest up</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        # Progress bar (empties as rest elapses)
        st.progress(remaining / rest_seconds)
        time.sleep(1)
        st.rerun()
    else:
        sets_left = total_sets - len(st.session_state.sets_done)
        if sets_left > 0:
            st.success(f"✅ Rest complete — {sets_left} set(s) remaining. Go!")
        else:
            st.balloons()
            st.success("🎉 All sets complete! Great work.")

# ── Reset ─────────────────────────────────────────────────────────────────────
st.divider()
if st.button("🔄 Reset Session", use_container_width=True):
    st.session_state.sets_done = []
    st.session_state.last_set_time = None
    st.rerun()
