# ---------- CONFIG ----------
import streamlit as st
import os
import pytz
import json
import requests
import csv
from datetime import datetime, timedelta
from google.oauth2 import service_account
import firebase_admin
from firebase_admin import firestore
from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam
from google.cloud.firestore_v1.base_query import FieldFilter

st.set_page_config(page_title="TSBC", layout="centered")
tokyo_tz = pytz.timezone("Asia/Tokyo")

# Set API Keys using secrets
openai_api_key = st.secrets["OPENAI_API_KEY"]
client = OpenAI(api_key=openai_api_key)
FIREBASE_API_KEY = st.secrets["FIREBASE_API_KEY"]

# ---------- FIREBASE INIT VIA CACHE ----------
@st.cache_resource(show_spinner=False)
def get_firestore_client():
    firebase_info = json.loads(st.secrets["firebase_service_account"])
    os.environ["GOOGLE_CLOUD_PROJECT"] = firebase_info.get("project_id", "tmbc2025-e0646")
    cred = service_account.Credentials.from_service_account_info(firebase_info)
    try:
        app = firebase_admin.get_app("firestore_app")
    except ValueError:
        app = firebase_admin.initialize_app(cred, {"projectId": firebase_info.get("project_id", "tmbc2025-e0646")}, name="firestore_app")
    return firestore.client(app=app)

db = get_firestore_client()
os.makedirs("logs", exist_ok=True)

# ---------- SESSION ----------
for k, v in {
    "user_email": "",
    "authenticated": False,
    "hint_number": 0,
    "last_hint": "",
    "user_name": "",
    "user_language": ""
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ---------- AUTH ----------
def firebase_auth_request(endpoint, payload):
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:{endpoint}?key={FIREBASE_API_KEY}"
    return requests.post(url, data=payload)

def login_ui():
    st.subheader("Login / Sign Up")
    action = st.radio("Select", ["Login", "Sign Up", "Forgot Password"])
    email = st.text_input("Email")
    password = st.text_input("Password", type="password") if action != "Forgot Password" else ""

    if action == "Sign Up":
        name = st.text_input("Your Name")
        lang = st.text_input("Your Programming Language (e.g., Python)")

    if st.button(action):
        if action == "Login":
            payload = {"email": email, "password": password, "returnSecureToken": True}
            r = firebase_auth_request("signInWithPassword", payload)
            if r.status_code == 200:
                st.session_state.update({
                    "user_email": email,
                    "authenticated": True
                })
                doc = db.collection("users").document(email).get()
                if doc.exists:
                    user_data = doc.to_dict()
                    st.session_state["user_name"] = user_data.get("name", "")
                    st.session_state["user_language"] = user_data.get("language", "")
                st.rerun()
            else:
                st.error("Invalid credentials.")
        elif action == "Sign Up":
            if not name or not lang:
                st.warning("Please enter name and programming language.")
                return
            payload = {"email": email, "password": password, "returnSecureToken": True}
            r = firebase_auth_request("signUp", payload)
            if r.status_code == 200:
                db.collection("users").document(email).set({
                    "name": name,
                    "language": lang,
                    "created": datetime.now(tokyo_tz)
                })
                st.success("Account created! Please log in.")
            else:
                st.error("Sign-up failed. Email may already be used.")
        elif action == "Forgot Password":
            payload = {"requestType": "PASSWORD_RESET", "email": email}
            r = firebase_auth_request("sendOobCode", payload)
            st.success("Reset email sent." if r.status_code == 200 else "Error sending reset email.")

def logout():
    for key in ["user_email", "authenticated", "hint_number", "last_hint", "user_name", "user_language"]:
        st.session_state[key] = "" if isinstance(st.session_state[key], str) else False
    st.success("Logged out.")


def get_today_hint_count(email):
    now = datetime.now(tokyo_tz)
    reset_time = now.replace(hour=8, minute=0, second=0, microsecond=0)
    if now < reset_time:
        reset_time -= timedelta(days=1)
    
    try:
        # First get all docs with matching email
        docs = db.collection("hint_logs").filter(filter=FieldFilter("email", "==", email)).stream()
        # Then filter in memory for timestamp
        reset_time_iso = reset_time.isoformat()
        return sum(1 for doc in docs if doc.to_dict().get("timestamp", "") >= reset_time_iso)
    except Exception as e:
        st.error(f"⚠️ Database error: {str(e)}")
        st.stop()

def get_all_hints_for_user(email):
    docs = db.collection("hint_logs")\
        .filter(filter=FieldFilter("email", "==", email))\
        .order_by("timestamp", direction=firestore.Query.DESCENDING)\
        .stream()
    return list(docs)

def create_hint(question: str, hint_number: int, lang: str) -> str:
    styles = [
        "Provide the FIRST hint. A general nudge. No full solution.",
        "Provide the SECOND hint. More guidance + similar example.",
        "Provide the THIRD hint. Half-code. Encourage Discourse discussion."
    ]
    if hint_number > 3:
        return (
            "You've used all 15 hints for today.\n\n"
            "🕗 Your limit resets at 8AM Tokyo time tomorrow.\n"
            "Please consider posting your question on the Discourse forum: https://forum.ms1.com/latest"
        )
    instruction = "Japanese first, then English." if lang.startswith("日本語") else "English first, then Japanese."
    return (
        f"You are a helpful Python teacher. Provide the hint in {instruction}\n"
        f"{styles[hint_number - 1]}\n\n"
        f"Question: {question}\n\nHint:"
    )

def get_gpt_hint(question, hint_number, lang):
    prompt = create_hint(question, hint_number, lang)
    if hint_number > 3:
        return prompt
    res = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        max_tokens=300
    )
    return res.choices[0].message.content

# ---------- MAIN APP ----------
def main_app():
    st.title("TSBC")
    question = st.text_area("Enter your programming question")
    hints_today = get_today_hint_count(st.session_state["user_email"])
    hints_left = 15 - hints_today
    st.info(f"Hints remaining today: {hints_left}")

    if st.session_state["last_hint"] == "":
        if st.button("💬 Discourse フォーラムに質問を投稿して、他の仲間の助けになろう！"):
            st.markdown("[→ Discourse に投稿する](https://forum.ms1.com/latest)", unsafe_allow_html=True)

    if hints_left <= 0:
        st.warning("⛔ Your hint quota is finished for the day. It will reset at 8AM Tokyo time tomorrow.")
        st.markdown("👉 Please consider sharing your question on the [Discourse forum](https://forum.ms1.com/latest)")
        return

    if st.button("Get Hint"):
        current = st.session_state["hint_number"] + 1
        st.session_state["hint_number"] = current
        hint = get_gpt_hint(question, current, st.session_state["user_language"])
        st.session_state["last_hint"] = hint

        timestamp = datetime.now(tokyo_tz)

        db.collection("hint_logs").add({
            "email": st.session_state["user_email"],
            "name": st.session_state["user_name"],
            "language": st.session_state["user_language"],
            "question": question,
            "hint_text": hint,
            "hint_number": current,
            "timestamp": timestamp
        })

        with open("logs/chat_log.csv", "a", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerow([
                st.session_state["user_email"],
                st.session_state["user_name"],
                st.session_state["user_language"],
                question.replace("\n", " "),
                hint.replace("\n", " "),
                current,
                timestamp.isoformat()
            ])

    if st.session_state["last_hint"]:
        st.markdown("### 🧠 Hint")
        st.markdown(st.session_state["last_hint"])
        st.markdown("---")
        st.success("💬 同じような疑問を持っている仲間のためにも、この質問を [Discourse フォーラム](https://forum.ms1.com/latest) に投稿してみましょう！")

    with st.expander("🕘 My Hint History"):
        history = get_all_hints_for_user(st.session_state["user_email"])
        if not history:
            st.info("No hint history found yet.")
        else:
            for doc in history:
                data = doc.to_dict()
                st.markdown(f"""
                **🗓 Date:** {data['timestamp'][:10]}  
                **📌 Question:** {data['question']}  
                **💡 Hint:** {data['hint_text']}  
                ---
                """)

    if st.button("Logout"):
        logout()

# ---------- ENTRY ----------
if not st.session_state["authenticated"]:
    login_ui()
else:
    main_app()
