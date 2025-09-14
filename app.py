
Brad DeVore <bradadevore@gmail.com>
5:51 AM (0 minutes ago)
to me

import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import google.generativeai as genai

# -------------------------------
# SETUP GEMINI WITH STREAMLIT SECRETS
# -------------------------------
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-1.5-flash")

# -------------------------------
# SCRAPE PLAYER DATA (FantasyPros example)
# -------------------------------
def get_player_data(player_name):
    search_url = f"https://www.fantasypros.com/nfl/players/{player_name.replace(' ', '-')}.php"
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(search_url, headers=headers)

    if response.status_code != 200:
        return None

    soup = BeautifulSoup(response.text, "html.parser")

    # Example scrape: projections table
    table = soup.find("table", {"id": "proj-stats"})
    if not table:
        return None

    df = pd.read_html(str(table))[0]
    return df

# -------------------------------
# AI SUMMARY (Gemini)
# -------------------------------
@st.cache_data(show_spinner=False)
def generate_ai_summary(player_stats_dict):
    prompt = "You are an expert fantasy football analyst. Compare these players using the tables below:\n\n"
    for player, df in player_stats_dict.items():
        if df is not None:
            prompt += f"\n### {player}\n{df.to_string(index=False)}\n"

    prompt += "\nGive a clear summary of who has the best outlook this week and why. Keep it concise but insightful."

    response = model.generate_content(prompt)
    return response.text

# -------------------------------
# STREAMLIT APP
# -------------------------------
st.title("🏈 Fantasy Football Player Evaluator")
st.write("Scraped stats + **AI-powered reasoning** with Gemini.")

# Input players
players = st.text_input("Enter player names (comma separated):", "Patrick Mahomes, Josh Allen")

if st.button("Evaluate Players"):
    player_list = [p.strip() for p in players.split(",")]
    player_stats = {}

    for player in player_list:
        st.subheader(player)
        df = get_player_data(player.lower())
        if df is not None:
            st.dataframe(df)
        else:
            st.warning(f"No data found for {player}")
        player_stats[player] = df

    # AI Summary
    with st.spinner("Analyzing with AI..."):
        ai_summary = generate_ai_summary(player_stats)

    st.markdown("## 🤖 AI Summary (Gemini)")
    st.write(ai_summary)