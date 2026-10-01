import os
import json
from google import genai
from google.genai import types
from prompts import SYSTEM_PROMPT, WELCOME_PROMPT, WHATSAPP_SUMMARY_PROMPT
from twilio.rest import Client as TwilioClient


import streamlit as st

GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
TWILIO_ACCOUNT_SID = st.secrets["TWILIO_ACCOUNT_SID"]
TWILIO_AUTH_TOKEN = st.secrets["TWILIO_AUTH_TOKEN"]
TWILIO_CONTENT_SID = st.secrets["TWILIO_CONTENT_SID"]
# TWILIO_CONTENT_VARIABLES = st.secrets["TWILIO_CONTENT_VARIABLES"]
TWILLIO_WHATSAPP_FROM = st.secrets["TWILLIO_WHATSAPP_FROM"]

@st.cache_resource
def get_gemini_client():
    return genai.Client(api_key=GEMINI_API_KEY)

@st.cache_resource
def get_twilio_client():
    return TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


twilio_client = get_twilio_client()
gemini_client = get_gemini_client()

def render_messages(message):
    with st.chat_message(message["role"]):
        if message["kind"] == "text":
            st.markdown(message["content"])
        elif message["kind"] == "image":
            st.image(message["content"])
        elif message["kind"] == "file":
            st.download_button("Download File", data=message["content"]["data"], file_name=message["content"]["name"])

def add_message(role, kind, content):
    message = {
        "role": role,
        "kind": kind,
        "content": content
    }
    st.session_state.messages.append(message)
    render_messages(message)

def ask_gemini(parts):
    try:
        return st.session_state.chat.send_message(parts).text
    except Exception as e:
        return f"Sorry, there was an error processing your request: {str(e)}"

def clean_whatsapp_text(text):
    if not text:
        return "No summary available."
    text = " ".join(text.split())
    return text[:1500] + "..." if len(text) > 1500 else text


def send_whatsapp_message(whatsapp_number, name, summary):
    try:
        content_variables = json.dumps({"1": name, "2":clean_whatsapp_text(summary)}, ensure_ascii=False)
        message = twilio_client.messages.create(
            from_ = TWILLIO_WHATSAPP_FROM,
            to = f"whatsapp:{whatsapp_number}",
            content_sid = TWILIO_CONTENT_SID,
            content_variables = content_variables,
        )
        return True, message.sid
    except Exception as e:
        return False, str(e)
    
# step1: onboarding (Username and Phone number)
if 'onboarded' not in st.session_state:

    st.title("Snap & Study")
    st.caption("Upload an image of your notes, textbook page, or study material, and I will analyze it, explain the content clearly, summarize the topic, generate questions and answers, and give quick revision notes and study tips.")

    with st.form("onboarding_form"):
        name = st.text_input("Enter your name")
        whatsapp_number = st.text_input("Enter your WhatsApp number (with country code)",
                                        placeholder="+91 1234567890",
                                        help="This number will be used to send you the study summary via WhatsApp." 
                                    )
        submitted = st.form_submit_button("Submit")

    if submitted:
        if not name.strip() or not whatsapp_number.strip():
            st.warning("Please enter both your name and WhatsApp number.")
        else:
            st.session_state.name = name.strip()
            st.session_state.whatsapp_number = whatsapp_number.strip()
            #activate my ai
            st.session_state.chat = gemini_client.chats.create(
                model = "gemini-2.5-flash",
                config = types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT)
            )
            st.session_state.messages = []
            st.session_state.onboarded = True
            st.rerun()
    st.stop()

# create chat interface
head_col, button_col = st.columns([5,2], vertical_alignment="center")

with head_col:
    st.title(f"Hello {st.session_state.name}, welcome to Snap & Study!")
    st.caption("Upload an image of your notes, textbook page, or study material, and I will analyze it, explain the content clearly, summarize the topic, generate questions and answers, and give quick revision notes and study tips.")

with button_col:
    send_disabled = len(st.session_state.messages) <= 1
    if st.button("Send Summary to WhatsApp", disabled=send_disabled, use_container_width=True):
        with st.spinner("Sending summary to WhatsApp..."):
            summary = ask_gemini([WHATSAPP_SUMMARY_PROMPT])
        success, info = send_whatsapp_message(st.session_state.whatsapp_number,st.session_state.name, summary)
        if success:
            st.success("Summary sent successfully to given whatsapp number!")
        else:
            st.error(f"Failed to send summary: {info}")

st.caption(f"Logged in as {st.session_state.name} - updates are sent to {st.session_state.whatsapp_number}")

if not st.session_state.messages:
    add_message("assistant", "text", WELCOME_PROMPT.format(name=st.session_state.name))
else:
    for message in st.session_state.messages:
        render_messages(message)


user_input = st.chat_input("Type your message here...", accept_file=True, file_type=["jpg", "jpeg", "png"])

if user_input:
    photo = user_input.files[0] if user_input.files else None
    text = user_input.text
    parts = []

    if photo is not None:
        photo_bytes = photo.getvalue()
        add_message("user", "image", photo_bytes)
        parts.append(types.Part.from_bytes(data=photo_bytes, mime_type=photo.type))
    if text:
        add_message("user", "text", text)
        parts.append(text)
    elif photo is not None:
        parts.append("what do you want to learn? And give me the topics you want to focus on.")

    with st.spinner("Analyzing the image and generating study material..."):
        answer = ask_gemini(parts)
    add_message("assistant", "text", answer)
