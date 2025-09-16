import streamlit as st
import json
import requests
import google.generativeai as genai
import asyncio
import mcp
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from urllib.parse import urlencode
import pandas as pd
from datetime import datetime

# --- SETUP API KEYS FROM STREAMLIT SECRETS ---
try:
    genai.configure(api_key=st.secrets['GEMINI_API_KEY'])
    SPORTS_DATA_API_KEY = st.secrets['SPORTS_DATA_API_KEY']
    MCP_SERVER_URL = st.secrets['MCP_SERVER_URL']
    BALLDONTLIE_API_KEY = st.secrets['BALLDONTLIE_API_KEY']
except KeyError as e:
    st.error(f"Required API key not found in Streamlit secrets: {e}")
    st.info("Please add GEMINI_API_KEY, SPORTS_DATA_API_KEY, MCP_SERVER_URL, and BALLDONTLIE_API_KEY to your `.streamlit/secrets.toml` file.")
    st.stop()

# --- SPORTSDATA.IO FOR PLAYER LIST ONLY ---
@st.cache_data(ttl=86400)
def get_all_players_data():
    """Fetches a complete list of all NFL players from SportsData.io."""
    try:
        url = "https://api.sportsdata.io/v3/nfl/scores/json/Players"
        headers = {
            'Ocp-Apim-Subscription-Key': SPORTS_DATA_API_KEY,
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching player list from SportsData.io: {e}")
        return []

def get_player_list_options(all_players):
    """Filters the full player data for WRs and TEs to populate the multiselect."""
    player_list = [
        f'{player.get("Name")} ({player.get("Team")})'
        for player in all_players
        if player.get("Position") in ["WR", "TE"] and player.get("Status") == "Active"
    ]
    player_list.sort()
    return player_list

# --- SMITHERY MCP TOOL INTEGRATION ---
async def call_mcp_tool(tool_name: str, **kwargs):
    """A helper function to call an MCP tool asynchronously."""
    
    params = {"api_key": st.secrets['BALLDONTLIE_API_KEY']}
    url = f"{st.secrets['MCP_SERVER_URL']}?{urlencode(params)}"
    
    async with streamablehttp_client(url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            result = await session.call_tool(tool_name=tool_name, input=kwargs)
            return result.content

def get_player_stats_from_mcp(league: str, first_name: str, last_name: str):
    """
    Python function that calls the Smithery MCP get_players tool.
    This function is the "tool" that Gemini will be instructed to call.
    """
    try:
        data = asyncio.run(call_mcp_tool(
            tool_name='get_players',
            league=league,
            firstName=first_name,
            lastName=last_name
        ))
        
        if not data:
            st.error(f"MCP server returned no data for {first_name} {last_name}.")
            return json.dumps([])
        
        if not isinstance(data, list) or len(data) == 0:
            st.error(f"MCP server returned an invalid data format for {first_name} {last_name}.")
            st.write("Raw data from MCP server:", data)
            return json.dumps([])

        return json.dumps(data)
    except Exception as e:
        st.error(f"An error occurred while fetching from MCP: {e}")
        return json.dumps([])

# --- TOOL DECLARATION FOR GEMINI ---
tool_declarations = [
    {
        "function_declarations": [
            {
                "name": "get_player_stats_from_mcp",
                "description": "Gets detailed player statistics for a player from a given league by their first and last name.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "league": {
                            "type": "string",
                            "enum": ["NBA", "NFL", "MLB"],
                            "description": "The sports league (NBA, NFL, or MLB)."
                        },
                        "first_name": {
                            "type": "string",
                            "description": "The first name of the player."
                        },
                        "last_name": {
                            "type": "string",
                            "description": "The last name of the player."
                        }
                    },
                    "required": ["league", "first_name", "last_name"]
                }
            }
        ]
    }
]

# --- STREAMLIT APP LAYOUT ---
st.set_page_config(page_title="Fantasy Football Analyst", layout="wide")
st.title("🏈 Fantasy Football Player Analyst")
st.write("Using SportsData.io for player selection with **AI-powered analysis** by Gemini, via a **Smithery MCP server**.")

all_players_data = get_all_players_data()

if not all_players_data:
    st.warning("Could not load the full player list from SportsData.io. Please check your API key and try again.")
    st.stop()
else:
    sorted_player_names = get_player_list_options(all_players_data)

    selected_players = st.multiselect(
        "Choose one or more wide receivers or tight ends:",
        options=sorted_player_names,
        placeholder="Select players..."
    )

    if st.button("Generate Report", use_container_width=True):
        if not selected_players:
            st.warning("Please select at least one player to generate a report.")
        else:
            with st.spinner("Analyzing players and generating your report..."):
                try:
                    for player_name in selected_players:
                        # Robust parsing of player name
                        full_name = player_name.split(' (')[0]
                        name_parts = full_name.split()

                        first_name = name_parts[0] if len(name_parts) > 0 else ""
                        last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ""

                        # --- The Prompt to Trigger Gemini's Tool Call ---
                        prompt_text = (
                            f"Act as a fantasy football analyst. I have provided player statistics for the NFL player {full_name}. If no statistics were found, state that you cannot perform the analysis and briefly explain why. Otherwise, use the provided data to analyze their fantasy value for the remainder of the season. Present the information in a single, comprehensive data table with the following columns: Player Name, Team, Position, Receptions, ReceivingYards, ReceivingTouchdowns, RushingYards, RushingTouchdowns, FumblesLost, and OverallFantasyFootballValue. Sort the table by highest to lowest ReceivingYards."
                        )

                        # Start a chat session with the model and tools
                        model = genai.GenerativeModel('gemini-1.5-flash', tools=tool_declarations)

                        # Send the prompt and get a response
                        response = model.generate_content(prompt_text)
                        
                        # Handle the potential function call
                        function_call = response.candidates[0].content.parts[0].function_call

                        if function_call:
                            # --- Execute the tool and get data from MCP ---
                            tool_output = get_player_stats_from_mcp(
                                league="NFL",
                                first_name=first_name,
                                last_name=last_name
                            )
                            
                            # --- Send the tool output back to Gemini for final reasoning ---
                            response_with_tool_output = model.generate_content(
                                gen
