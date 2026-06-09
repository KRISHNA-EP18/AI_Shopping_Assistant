import os
import tempfile

import streamlit as st

from ai_agent import run_agent

st.set_page_config(page_title="AI Shopping Assistant", page_icon="🛒", layout="wide")

st.title("🛒 AI Shopping Assistant")
st.caption("Tell me what you want — I'll search, rate, and order the best match for you.")

with st.sidebar:
    st.header("⚙️ My Preferences")
    st.caption("These are remembered across sessions.")

    prefer_organic = st.toggle("Always prefer organic products", value=False)
    max_price      = st.number_input("Max price ($)", min_value=0.0, value=0.0, step=1.0,
                                     help="Set to 0 to apply no price limit.")

    if st.button("Save Preferences", use_container_width=True):
        prefs = []
        if prefer_organic:
            prefs.append({"role": "user", "content": "Remember: I always prefer organic products."})
        if max_price > 0:
            prefs.append({"role": "user", "content": f"Remember: never show me items over ${max_price:.2f}."})
        if prefs:
            try:
                for pref_msg in prefs:
                    run_agent([pref_msg])
                st.success("Preferences saved!")
            except ValueError as e:
                st.warning(str(e))
        else:
            st.info("No preferences to save.")

    st.divider()

    st.header("🖼️ Shop by Image")
    st.caption("Upload a photo of a product and I'll find similar items in our store.")

    uploaded_file = st.file_uploader("Upload product image", type=["jpg", "jpeg", "png", "webp"])

    if uploaded_file:
        st.image(uploaded_file, use_column_width=True)

    if uploaded_file and st.button("Find similar products", use_container_width=True):
        suffix = os.path.splitext(uploaded_file.name)[1] or ".jpg"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded_file.getvalue())
            image_path = tmp.name

        prompt = (
            f"I uploaded a product image. Please analyze it and find similar "
            f"products in the store. Image path: {image_path}"
        )
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.session_state.pending_image      = uploaded_file.name
        st.session_state.pending_image_path = image_path
        st.rerun()

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "user" and msg["content"].startswith("I uploaded a product image"):
            filename = msg["content"].split("Image path:")[-1].strip()
            st.markdown(f"Searching by image: **{os.path.basename(filename)}**")
        else:
            st.markdown(msg["content"].replace("$", r"\$"))

if (
    st.session_state.messages
    and st.session_state.messages[-1]["role"] == "user"
    and "pending_image" in st.session_state
):
    with st.chat_message("assistant"):
        with st.spinner("Analyzing image and searching…"):
            try:
                response = run_agent(st.session_state.messages).replace("`", "")
            except ValueError as e:
                response = str(e)
        st.markdown(response.replace("$", r"\$"))

    st.session_state.messages.append({"role": "assistant", "content": response})

    tmp_path = st.session_state.pop("pending_image_path", None)
    if tmp_path and os.path.exists(tmp_path):
        os.unlink(tmp_path)

    del st.session_state.pending_image
    st.rerun()

if prompt := st.chat_input("e.g. I want organic honey under $15 with 4+ rating"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            try:
                response = run_agent(st.session_state.messages).replace("`", "")
            except ValueError as e:
                response = str(e)
        st.markdown(response.replace("$", r"\$"))

    st.session_state.messages.append({"role": "assistant", "content": response})
    st.rerun()