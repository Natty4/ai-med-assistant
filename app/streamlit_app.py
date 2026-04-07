# app/streamlit_app.py
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import streamlit as st
from src.synthesis.response_generator import ResponseGenerator
import traceback

st.set_page_config(
    page_title="🩺 Personal Medical Assistant",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🩺 Your Personal Medical Assistant")
st.caption("700+ Symptom • Personalized • Safe • Powered Ai")

# Initialize generator safely (only once)
@st.cache_resource
def load_generator():
    return ResponseGenerator()

if "generator" not in st.session_state:
    status = st.empty()
    status.info("🚀 Initializing AI assistant (first run may take ~30–60 seconds)...")

    try:
        with st.spinner("🔄 Loading models, embeddings, and medical index..."):
            st.session_state.generator = load_generator()

        status.success("✅ Assistant ready!")

    except Exception as e:
        st.error(f"❌ Failed to initialize assistant: {e}")
        st.stop()

generator = st.session_state.generator

# Sidebar Profile
with st.sidebar:
    st.header("🧑‍⚕️ Your Health Profile")
    age = st.number_input("Age", min_value=0, max_value=120, value=generator.profile.get("age", 35))
    chronic_options = ["Diabetes", "Hypertension", "Asthma", "Heart disease", "None"]
    chronic = st.multiselect("Chronic conditions", chronic_options, 
                             default=generator.profile.get("chronic_conditions", []))
    
    if st.button("💾 Update Profile"):
        generator.profile["age"] = age
        generator.profile["chronic_conditions"] = [c for c in chronic if c != "None"]
        generator.save_profile()
        st.success("Profile updated successfully!")

    st.subheader("Recent Symptoms")
    st.write(generator.profile.get("recent_symptoms", ["None yet"]))

# Chat Interface
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Hello! I'm your personal health assistant. How are you feeling today? Describe any symptoms."}
    ]

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("e.g. I have a mild headache since this morning"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.spinner("Analyzing..."):
        try:
            response = generator.generate(prompt)
            st.session_state.messages.append({"role": "assistant", "content": response})
            
            with st.chat_message("assistant"):
                st.markdown(response)
            
            # Optional: Show sources
            with st.expander("📚 Sources & Transparency"):
                st.info("Response is grounded in official NHS symptom pages. "
                        "Always consult a healthcare professional for medical advice.")

        except Exception as e:
            error_msg = f"⚠️ Sorry, I encountered an error while processing your query.\n\n**Details:** {str(e)}"
            st.session_state.messages.append({"role": "assistant", "content": error_msg})
            with st.chat_message("assistant"):
                st.error(error_msg)
            st.error("Traceback (for debugging):")
            st.code(traceback.format_exc())

# Footer
st.divider()
st.caption("✅ Evidence-based • Personalized • Safety-first • Not a substitute for professional medical advice")