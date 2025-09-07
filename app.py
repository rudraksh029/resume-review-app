
import os
import io
import json
import textwrap
import streamlit as st
from PyPDF2 import PdfReader
from PIL import Image
from groq import Groq
from dotenv import load_dotenv
from fpdf import FPDF

# ---------------------------
# Step 1: Load API key securely
# ---------------------------
load_dotenv()  # looks for .env in current folder
groq_api_key = os.getenv("GROQ_API_KEY")

if not groq_api_key:
    st.error("❌ Missing GROQ_API_KEY in .env file")
    st.stop()

# Step 2: Initialize Groq client
client = Groq(api_key=groq_api_key)

# App settings
MAX_PREVIEW_CHARS = 3000

# ---------------------------
# Helpers
# ---------------------------
def extract_text_from_pdf(uploaded_file):
    try:
        reader = PdfReader(uploaded_file)
        texts = [page.extract_text() for page in reader.pages if page.extract_text()]
        return "\n\n".join(texts).strip()
    except Exception:
        return ""

def generate_prompt_for_llm(resume_text, job_role, job_desc):
    return f"""
You are an expert career coach and resume editor. Output a JSON object with keys:
- skills: list of relevant skills
- improvements: short suggestions for wording, formatting, clarity
- tailored_examples: list of 3 short edits (1-2 lines)
- scoring: object with keys (relevance, clarity, format, overall) 0-10
- improved_resume: professionally formatted resume
- highlights: keywords found or suggested

Role: {job_role}
Job description: {job_desc if job_desc else "None"}
Resume Text:
{resume_text}
"""

def call_groq_with_prompt(prompt):
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
    )
    # Safely handle SDK return format
    msg = response.choices[0].message
    return msg["content"] if isinstance(msg, dict) else msg.content

def parse_json_from_model(text):
    try:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1:
            return None
        return json.loads(text[start:end+1])
    except Exception:
        return None

def fallback_mock_feedback(resume_text, job_role, job_desc):
    return {
        "skills": ["communication", "teamwork", "problem solving"],
        "improvements": [
            "Quantify achievements.",
            "Use active verbs.",
            "Move education below experience if experienced."
        ],
        "tailored_examples": [
            "Led a 3-person team to build a recommendation engine.",
            "Improved ETL pipeline latency by 40%.",
            "Designed A/B tests increasing activation by 8%."
        ],
        "scoring": {"relevance": 7, "clarity": 7, "format": 6, "overall": 7},
        "improved_resume": "Header: Name | Email\nSummary: Data-focused...\nExperience: ...\nSkills: Python, SQL, ML",
        "highlights": ["Python", "SQL", "ML", job_role]
    }

def create_pdf_from_text(text, title="Improved_Resume"):
    pdf = FPDF()
    pdf.set_auto_page_break(True, margin=15)
    pdf.add_page()
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, title, ln=True, align='C')
    pdf.ln(4)
    pdf.set_font("Arial", size=11)
    for line in text.split("\n"):
        wrapped = textwrap.wrap(line, width=95)
        if not wrapped:
            pdf.ln(5)
        for w in wrapped:
            pdf.multi_cell(0, 6, w)
    return io.BytesIO(pdf.output(dest="S").encode("latin1"))

# ---------------------------
# Streamlit UI
# ---------------------------
st.set_page_config(page_title="Smart Resume Reviewer", layout="wide")
st.markdown("<h1 style='text-align:center'>🧠 Smart Resume Reviewer</h1>", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### Settings")
    use_mock = st.checkbox("Use mock mode (no Groq calls)", value=False)
    show_raw_model = st.checkbox("Show raw model output", value=False)
    download_pdf_name = st.text_input("Download PDF filename", value="improved_resume")

st.markdown("### 1) Upload Resume & Context")
col1, col2 = st.columns([2, 1])

with col1:
    resume_input_method = st.radio("Resume input", ["Upload PDF", "Paste text"])
    resume_text = ""
    if resume_input_method == "Upload PDF":
        uploaded_pdf = st.file_uploader("Upload your resume (PDF)", type=["pdf"])
        if uploaded_pdf:
            resume_text = extract_text_from_pdf(uploaded_pdf)
            if not resume_text:
                st.warning("Could not extract text from PDF.")
    else:
        resume_text = st.text_area("Paste your resume text here", height=260)

with col2:
    st.markdown("*Upload supporting images (optional)*")
    uploaded_images = st.file_uploader("Images", type=["png","jpg","jpeg"], accept_multiple_files=True)
    if uploaded_images:
        cols = st.columns(2)
        for i, f in enumerate(uploaded_images):
            try:
                img = Image.open(f)
                cols[i % 2].image(img, caption=f.name, use_column_width=True)
            except Exception:
                st.write("Could not open:", f.name)

st.markdown("### 2) Job Role & Description")
job_role = st.text_input("Target job role", "")
job_desc = st.text_area("Optional: Job description", height=160)

if st.button("▶ Analyze / Review"):
    if not resume_text or not job_role:
        st.error("Please provide both resume and target job role.")
    else:
        with st.spinner("Generating feedback..."):
            if use_mock or not groq_api_key:
                st.info("Using MOCK feedback mode.")
                result = fallback_mock_feedback(resume_text, job_role, job_desc)
                raw_text = None
            else:
                try:
                    prompt = generate_prompt_for_llm(resume_text, job_role, job_desc)
                    raw_text = call_groq_with_prompt(prompt)
                    if show_raw_model:
                        st.expander("Raw model output").write(raw_text)
                    parsed = parse_json_from_model(raw_text)
                    result = parsed if parsed else fallback_mock_feedback(resume_text, job_role, job_desc)
                except Exception as e:
                    st.error("Groq API error: " + str(e))
                    result = fallback_mock_feedback(resume_text, job_role, job_desc)

        # Results
        st.markdown("### ✅ Results")
        left, right = st.columns([2, 1])
        with left:
            st.markdown(f"*Role:* {job_role}")
            if job_desc:
                with st.expander("Job description"):
                    st.write(job_desc)
            st.markdown("#### 🔎 Skills / Keywords")
            st.write(", ".join(result.get("skills", [])))
            st.markdown("#### ✍ Improvements")
            for s in result.get("improvements", []):
                st.markdown(f"- {s}")
            st.markdown("#### 🛠 Tailored Examples")
            for ex in result.get("tailored_examples", []):
                st.markdown(f"- {ex}")

        with right:
            st.markdown("#### 📊 Scores")
            scoring = result.get("scoring", {})
            st.metric("Overall", f"{scoring.get('overall',0)}/10")
            st.write(f"Relevance: {scoring.get('relevance',0)}/10")
            st.write(f"Clarity: {scoring.get('clarity',0)}/10")
            st.write(f"Format: {scoring.get('format',0)}/10")

        st.markdown("### 🧾 Improved Resume")
        improved_text = result.get("improved_resume", "")
        st.text_area("Improved resume (editable)", value=improved_text, height=300, key="improved_preview")

        # Downloads
        improved_final_text = st.session_state.get("improved_preview", improved_text)
        if improved_final_text:
            b = io.BytesIO()
            b.write(improved_final_text.encode("utf-8"))
            b.seek(0)
            st.download_button("Download TXT", data=b, file_name=f"{download_pdf_name}.txt", mime="text/plain")
            pdf_bio = create_pdf_from_text(improved_final_text, title=f"Improved Resume - {job_role}")
            st.download_button("Download PDF", data=pdf_bio, file_name=f"{download_pdf_name}.pdf", mime="application/pdf")

        st.success("✅ Done — Your improved resume is ready!")