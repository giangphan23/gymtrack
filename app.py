import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

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


def save_config(updated_config: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
        json.dump(updated_config, fh, indent=2)


def build_set_event_payload(
    *,
    session_id: str,
    workout: str,
    exercise: str,
    set_number: int,
    total_sets: int,
    reps: int,
    weight: float,
    rest_seconds: int,
    event_id: str,
) -> dict:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "workout": workout,
        "exercise": exercise,
        "set_number": set_number,
        "total_sets": total_sets,
        "reps": reps,
        "weight": weight,
        "rest_seconds": rest_seconds,
        "session_id": session_id,
        "event_id": event_id,
    }


def log_set_to_gsheet(payload: dict) -> bool:
    try:
        webhook_url = st.secrets.get("gsheet_webhook_url")
    except StreamlitSecretNotFoundError:
        return False

    if not webhook_url:
        return False

    # Retry once for transient network failures.
    for _ in range(2):
        try:
            resp = requests.post(webhook_url, json=payload, timeout=3)
            if resp.ok:
                return True
        except requests.RequestException:
            continue

    return False


config = load_config()
workout_names = list(config.keys())


def first_exercise(workout_name: str) -> str:
    return list(config[workout_name].keys())[0]


def reset_session() -> None:
    st.session_state.sets_done = []
    st.session_state.last_set_time = None
    st.session_state.logged_event_ids = set()


# ── Session-state initialisation ──────────────────────────────────────────────
if "active_workout" not in st.session_state:
    st.session_state.active_workout = workout_names[0]

if "active_exercise" not in st.session_state:
    st.session_state.active_exercise = first_exercise(st.session_state.active_workout)

if "sets_done" not in st.session_state:
    st.session_state.sets_done = []

if "last_set_time" not in st.session_state:
    st.session_state.last_set_time = None

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "logged_event_ids" not in st.session_state:
    st.session_state.logged_event_ids = set()

if "workout_finished" not in st.session_state:
    st.session_state.workout_finished = False

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
    reset_session()

# ── Exercise editor ───────────────────────────────────────────────────────────
with st.expander("Edit Exercises", expanded=False):
    st.caption("Quickly add, rename, or update exercises for this workout.")

    current_workout_data = config[st.session_state.active_workout]
    editor_rows = [
        {
            "exercise": name,
            "weight": details["weight"],
            "sets": details["sets"],
            "reps": details["reps"],
            "rest_seconds": details["rest_seconds"],
        }
        for name, details in current_workout_data.items()
    ]

    edited_rows = st.data_editor(
        editor_rows,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key=f"exercise_editor_{st.session_state.active_workout}",
        column_config={
            "exercise": st.column_config.TextColumn("Exercise", required=True),
            "weight": st.column_config.NumberColumn("Weight (kg)", min_value=0.0, step=2.5),
            "sets": st.column_config.NumberColumn("Sets", min_value=1, step=1),
            "reps": st.column_config.NumberColumn("Reps", min_value=1, step=1),
            "rest_seconds": st.column_config.NumberColumn("Rest (s)", min_value=0, step=5),
        },
    )

    if st.button("Save Exercise Changes", use_container_width=True):
        updated_workout: dict[str, dict] = {}
        seen_names: set[str] = set()
        validation_errors: list[str] = []

        for idx, row in enumerate(edited_rows, start=1):
            name = str(row.get("exercise", "")).strip()
            if not name:
                validation_errors.append(f"Row {idx}: exercise name cannot be empty.")
                continue
            if name in seen_names:
                validation_errors.append(f"Row {idx}: duplicate exercise name '{name}'.")
                continue
            seen_names.add(name)

            try:
                updated_workout[name] = {
                    "weight": float(row.get("weight", 0)),
                    "sets": int(row.get("sets", 0)),
                    "reps": int(row.get("reps", 0)),
                    "rest_seconds": int(row.get("rest_seconds", 0)),
                }
            except (TypeError, ValueError):
                validation_errors.append(f"Row {idx}: invalid numeric values.")

        if not updated_workout:
            validation_errors.append("A workout must have at least one exercise.")

        if validation_errors:
            for msg in validation_errors:
                st.error(msg)
        else:
            config[st.session_state.active_workout] = updated_workout
            save_config(config)
            load_config.clear()

            if st.session_state.active_exercise not in updated_workout:
                st.session_state.active_exercise = next(iter(updated_workout))
            reset_session()

            st.success("Exercise changes saved.")
            st.rerun()

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
    reset_session()

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
        event_id = (
            f"{st.session_state.session_id}:"
            f"{st.session_state.active_workout}:{selected}:{i + 1}"
        )
        if event_id not in st.session_state.logged_event_ids:
            payload = build_set_event_payload(
                session_id=st.session_state.session_id,
                workout=st.session_state.active_workout,
                exercise=selected,
                set_number=i + 1,
                total_sets=total_sets,
                reps=reps,
                weight=weight,
                rest_seconds=rest_seconds,
                event_id=event_id,
            )
            if log_set_to_gsheet(payload):
                st.session_state.logged_event_ids.add(event_id)

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

# ── Finish Workout ────────────────────────────────────────────────────────────
if st.session_state.workout_finished:
    st.balloons()
    st.success("🏁 Workout finished! Great effort today.")
    st.session_state.workout_finished = False

# ── Reset ─────────────────────────────────────────────────────────────────────
st.divider()
col_finish, col_reset = st.columns(2)
if col_finish.button("🏁 Finish Workout", use_container_width=True, type="primary"):
    reset_session()
    st.session_state.workout_finished = True
    st.rerun()
if col_reset.button("🔄 Reset Session", use_container_width=True):
    reset_session()
    st.rerun()
