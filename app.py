import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import google.generativeai as genai
from datetime import datetime

# -------------------------------
# SETUP GEMINI WITH STREAMLIT SECRETS
# -------------------------------
try:
    genai.configure(api_key=st.secrets['GEMINI_API_KEY'])
    model = genai.GenerativeModel("gemini-1.5-flash")
except KeyError:
    st.error("GEMINI_API_KEY not found. Please add it to your Streamlit secrets.")
    st.stop()

# -------------------------------
# SCRAPE PLAYER DATA (more robust version)
# -------------------------------
@st.cache_data(ttl=3600)
def get_player_data(player_name):
    formatted_name = player_name.lower().replace(' ', '-')
    search_url = f"https://www.fantasypros.com/nfl/players/{formatted_name}.php"
    
    headers = {"User-Agent": "Mozilla/5.0"}
    
    try:
        response = requests.get(search_url, headers=headers)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching data for {player_name}: {e}")
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    table = soup.find("table", {"id": "proj-stats"})

    if not table:
        # Fallback to look for a different table if the primary one isn't found.
        # This is often needed for QB pages, which might have different table IDs.
        st.warning(f"Could not find the main stats table for {player_name}. Searching for an alternative.")
        table = soup.find("div", {"id": "data-grid-container"})
        if table:
            # If an alternative is found, try to extract the table from its HTML content
            try:
                df = pd.read_html(str(table))[0]
                return df
            except:
                return None
        return None
    try:
        df = pd.read_html(str(table))[0]
        return df
    except IndexError:
        st.warning(f"No tables found on the page for {player_name}.")
        return None
    except Exception as e:
        st.error(f"An error occurred while parsing the table for {player_name}: {e}")
        return None

# -------------------------------
# AI SUMMARY (Gemini)
# -------------------------------
@st.cache_data(show_spinner=False)
def generate_ai_summary(player_stats_dict):
    prompt = "You are an expert fantasy football analyst. Compare these players using the tables below:\n\n"
    
    valid_players = {player: df for player, df in player_stats_dict.items() if df is not None}
    
    if not valid_players:
        return "No player data was found to generate an AI summary."
        
    for player, df in valid_players.items():
        if not df.empty:
            prompt += f"\n### {player}\n{df.to_string(index=False)}\n"

    prompt += "\nGive a clear summary of who has the best outlook this week and why. Keep it concise but insightful."

    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"An error occurred while generating the AI summary: {e}"

# -------------------------------
# STREAMLIT APP LAYOUT
# -------------------------------
st.title("🏈 Fantasy Football Player Evaluator")
st.write("Scraped stats + **AI-powered reasoning** with Gemini.")

players_input = st.text_input("Enter player names (comma separated):", "Patrick Mahomes, Josh Allen")

if st.button("Evaluate Players"):
    player_list = [p.strip() for p in players_input.split(",")]
    player_stats = {}

    for player in player_list:
        st.subheader(player)
        df = get_player_data(player)
        if df is not None:
            st.dataframe(df)
        player_stats[player] = df

    with st.spinner("Analyzing with AI..."):
        ai_summary = generate_ai_summary(player_stats)

    st.markdown("---")
    st.markdown("## AI Summary (Gemini)")
    st.write(ai_summary)
