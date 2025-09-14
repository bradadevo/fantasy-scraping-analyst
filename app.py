import streamlit as st
import json
import requests
import google.generativeai as genai

# --- Load API Keys from Streamlit Secrets ---
try:
    genai.configure(api_key=st.secrets['GEMINI_API_KEY'])
    SPORTS_DATA_API_KEY = st.secrets['SPORTS_DATA_API_KEY']
except KeyError:
    st.error("API keys not found. Please add them to your Streamlit secrets.")
    st.stop()


# --- Function to Get All Players from SportsData.io ---
@st.cache_data(ttl=86400)
def get_player_list():
    try:
        url = "https://api.sportsdata.io/v3/nfl/scores/json/Players"
        headers = {
            'Ocp-Apim-Subscription-Key': SPORTS_DATA_API_KEY,
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        player_data = response.json()
        
        wr_te_players = {
            f'{player.get("Name")} ({player.get("Team")})': player.get("PlayerID")
            for player in player_data
            if player.get("Position") in ["WR", "TE"] and player.get("Status") == "Active"
        }
        
        sorted_player_names = sorted(wr_te_players.keys())
        return sorted_player_names, wr_te_players
        
    except requests.exceptions.RequestException as e:
        if e.response is not None:
            st.error(f"HTTP Error: Status Code {e.response.status_code} - URL: {e.request.url}")
        else:
            st.error(f"Network Error: {e}")
        return [], {}

# --- New Function to Get Detailed Player Stats ---
def get_detailed_stats(player_ids):
    detailed_stats_list = []
    
    for player_id in player_ids:
        try:
            # Endpoint for player details/stats
            url = f"https://api.sportsdata.io/v3/nfl/stats/json/PlayerSeasonStats/2023/{player_id}"
            headers = {
                'Ocp-Apim-Subscription-Key': SPORTS_DATA_API_KEY
            }
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            player_stats = response.json()
            detailed_stats_list.append(player_stats)
        except requests.exceptions.RequestException as e:
            st.warning(f"Could not retrieve data for player ID {player_id}. Error: {e}")
            continue
            
    return detailed_stats_list

# --- Page Setup and Title ---
st.set_page_config(page_title="Fantasy Football Analyst", layout="wide")
st.title("🏈 Fantasy Football Player Analyst")
st.write("Get a data-driven report on players for the rest of the season.")

# --- User Input Section ---
st.markdown("### Select Players to Analyze")
sorted_player_names, player_id_map = get_player_list()

if not sorted_player_names:
    st.warning("Could not load the player list. Please check your API key and try again later.")
else:
    selected_players = st.multiselect(
        "Choose one or more wide receivers or tight ends:",
        options=sorted_player_names,
        placeholder="Select players..."
    )

    # --- Button to Trigger Analysis ---
    if st.button("Generate Report", use_container_width=True):
        if not selected_players:
            st.warning("Please select at least one player to generate a report.")
        else:
            with st.spinner("Analyzing players and generating your report..."):
                try:
                    selected_player_ids = [player_id_map[name] for name in selected_players]
                    
                    # Fetch detailed stats for selected players from the API
                    detailed_stats = get_detailed_stats(selected_player_ids)
                    
                    if not detailed_stats:
                        st.error("Failed to retrieve detailed player stats. Please try again.")
                    else:
                        # Your Gemini prompt logic
                        prompt_text = (
                            "Act as a top-tier fantasy football analyst. I have compiled the following up-to-date player data for the current NFL season: "
                            "Player data: {provided_player_data}. "
                            "Using this data, provide a concise analysis of each player's fantasy football value for the remainder of the season. Focus on their current production and how it compares to other players at their position based on the provided statistics. "
                            "Your analysis must include: "
                            "* A quick overview of each player's statistical performance based on the provided data. "
                            "* A brief commentary on their potential fantasy football value (e.g., \"High-End WR1\", \"Mid-Range TE2\"). "
                            "After the analysis, present all of the information in a single, comprehensive data table with the following columns in this exact order: "
                            "Player Name, Team, Position, Receptions, ReceivingYards, ReceivingTouchdowns, RushingYards, RushingTouchdowns, FumblesLost, and OverallFantasyFootballValue. "
                            "Sort the table by highest to lowest ReceivingYards. Ensure all data in the table is directly from the provided JSON. Do not add any new projections or statistics beyond what you are given."
                            f"\n\nHere is the raw, factual data for the analysis: {json.dumps(detailed_stats)}"
                        )
                        
                        # Call the Gemini API
                        model = genai.GenerativeModel('gemini-1.5-flash')
                        response = model.generate_content(prompt_text)
                        
                        # Display the final report
                        st.markdown("### Detailed Report")
                        st.markdown(response.text)

                except Exception as e:
                    st.error(f"An error occurred: {e}")
