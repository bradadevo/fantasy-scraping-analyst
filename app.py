import streamlit as st
import os
import json
import requests
import google.generativeai as genai
from datetime import datetime

# --- SETUP GEMINI WITH STREAMLIT SECRETS ---
try:
    genai.configure(api_key=st.secrets['GEMINI_API_KEY'])
except KeyError:
    st.error("GEMINI_API_KEY not found. Please add it to your Streamlit secrets.")
    st.stop()

# --- DATA FETCHING FROM ESPN FANTASY API ---
@st.cache_data(ttl=3600)
def get_all_players_data():
    """
    Fetches a comprehensive list of all active NFL players with stats from ESPN's unofficial API.
    Returns: A list of dictionaries, where each dictionary is a player's profile.
    """
    current_year = datetime.now().year
    url = f"https://fantasy.espn.com/apis/v3/games/ffl/seasons/{current_year}/players"
    headers = {
        'User-Agent': 'Mozilla/5.0',
        'X-Fantasy-Filter': '{"players":{"limit":1000,"filterActive":{"value":true}}}'
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        # FIX: Check if the response content is not empty before parsing
        if response.content:
            try:
                # Check if the content is valid JSON
                players_data = response.json().get('players', [])
                
                # The JSON structure for this endpoint is different
                return [p for p in players_data if 'stats' in p]
            except json.JSONDecodeError:
                st.error("The API returned an invalid JSON response. This may be a temporary issue with the endpoint.")
                return []
        else:
            st.error("The API returned an empty response. It may be temporarily unavailable.")
            return []
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching player data from ESPN API: {e}")
        return []

# --- Function to Get Player List for Multiselect (remains unchanged) ---
def get_player_list_options(all_players):
    """Filters the full player data for WRs and TEs to populate the multiselect."""
    wr_te_players = [
        f'{player.get("fullName")} ({player.get("proTeamId")})'
        for player in all_players
        if player.get("defaultPositionId") in [3, 5]
    ]
    wr_te_players.sort()
    return wr_te_players

# --- Function to Get Detailed Player Stats for AI Prompt ---
def get_player_stats(selected_players, all_players):
    """Filters the all_players data to get detailed stats for selected players."""
    player_stats_data = {}
    
    player_lookup = {f'{p.get("fullName")} ({p.get("proTeamId")})': p for p in all_players}
    
    for player_full_name in selected_players:
        stats = player_lookup.get(player_full_name)
        if stats:
            reformatted_stats = {
                "Player Name": stats.get("fullName"),
                "Team": stats.get("proTeamId"),
                "Position": stats.get("position"),
                "Receptions": stats.get("stats", {}).get("21", 0),
                "ReceivingYards": stats.get("stats", {}).get("42", 0),
                "ReceivingTouchdowns": stats.get("stats", {}).get("45", 0),
                "RushingYards": stats.get("stats", {}).get("4", 0),
                "RushingTouchdowns": stats.get("stats", {}).get("5", 0),
                "FumblesLost": stats.get("stats", {}).get("24", 0),
            }
            player_stats_data[player_full_name] = reformatted_stats
        
    return player_stats_data

# --- AI SUMMARY (Gemini) ---
def generate_ai_summary(player_stats_dict):
    """Generates an AI summary comparing player stats."""
    prompt = "You are an expert fantasy football analyst. Compare these players using the tables below:\n\n"
    
    valid_players = {player: df for player, df in player_stats_dict.items() if df is not None}
    
    if not valid_players:
        return "No player data was found to generate an AI summary."
        
    for player, stats in valid_players.items():
        df = pd.DataFrame([stats])
        prompt += f"\n### {player}\n{df.to_string(index=False)}\n"

    prompt += "\nGive a clear summary of who has the best outlook this week and why. Keep it concise but insightful."

    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"An error occurred while generating the AI summary: {e}"

# --- STREAMLIT APP LAYOUT ---
st.set_page_config(page_title="Fantasy Football Analyst", layout="wide")
st.title("🏈 Fantasy Football Player Analyst")
st.write("Using ESPN data with **AI-powered reasoning** by Gemini.")

all_players_data = get_all_players_data()

if not all_players_data:
    st.warning("Could not load the full player list. The ESPN API may be temporarily down or its structure has changed. Please try again later.")
    st.stop()
else:
    PLAYER_OPTIONS = get_player_list_options(all_players_data)
    
    selected_players = st.multiselect(
        "Choose one or more wide receivers or tight ends:",
        options=PLAYER_OPTIONS,
        placeholder="Select players..."
    )

    if st.button("Generate Report", use_container_width=True):
        if not selected_players:
            st.warning("Please select at least one player to generate a report.")
        else:
            with st.spinner("Analyzing players and generating your report..."):
                try:
                    detailed_stats = get_player_stats(selected_players, all_players_data)
                    
                    if not detailed_stats:
                        st.error("No statistics were found for the selected players. The API may not have data for them yet.")
                        st.stop()
                    
                    ai_summary = generate_ai_summary(detailed_stats)
                    
                    st.markdown("### Detailed Report")
                    st.markdown(ai_summary)

                except Exception as e:
                    st.error(f"An error occurred: {e}")
