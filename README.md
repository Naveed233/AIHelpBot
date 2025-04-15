# 🧠 AIHelpBot

An AI-powered programming assistant for students that offers up to 15 daily hints per user. Built with Streamlit and Firebase.

## 🚀 Features

- 🔐 User login & signup (with email + password)
- 📬 Forgot password recovery via email
- 🧠 Tiered hints (3 levels per question)
- ⏱️ Daily quota: 15 hints reset at 8AM Tokyo time
- 💬 Encourages sharing questions on [Discourse](https://forum.ms1.com/latest)
- 📚 Personal hint history (collapsible)

## 📦 Tech Stack

- Frontend: Streamlit
- Backend: OpenAI API
- Auth & DB: Firebase (Authentication + Firestore)
- Deployment: Streamlit Cloud

## 🛠️ Setup

1. Clone the repo  
2. Create a `.streamlit/secrets.toml` with:
   ```toml
   OPENAI_API_KEY = "your-openai-key"
   FIREBASE_API_KEY = "your-firebase-web-api-key"

   firebase_service_account = """
   { ...your firebase service account JSON... }
   """
Install dependencies:
   pip install -r requirements.txt

Run the app:
   streamlit run app.py
