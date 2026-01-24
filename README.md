---
title: SkatiesVideo
emoji: 📉
colorFrom: green
colorTo: red
sdk: gradio
sdk_version: 5.42.0
app_file: app.py
pinned: false
short_description: Generates Questions on Videos form kids.
---

Check out the configuration reference at https://huggingface.co/docs/hub/spaces-config-reference

## Running the app locally with Streamlit

To run the Watch-Ask app locally using Streamlit, follow these steps:

1. **Install Python and Streamlit**
   Make sure you have Python installed (version 3.7 or higher). Then install Streamlit:
   ```bash
   pip install streamlit
   ```

2. **Clone the repository**
   ```bash
   git clone https://github.com/Viktors-Vinogradovs/Watch-Ask.git
   cd Watch-Ask
   ```

3. **Install dependencies**
   You may have a `requirements.txt` file. If so, install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the app**
   Find the main Streamlit script (usually named `app.py` or `main.py`) and run:
   ```bash
   streamlit run app.py
   ```
   If your main file is named differently, adjust the command accordingly.

5. **Access the app**
   The app will open in your browser at `http://localhost:8501`.

---

**Troubleshooting:**  
- If you encounter missing dependency errors, ensure all required packages are installed as listed in `requirements.txt`.
- For help, see the [Streamlit documentation](https://docs.streamlit.io/).
