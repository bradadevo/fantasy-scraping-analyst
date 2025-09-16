import streamlit as st
import json
import requests
import google.generativeai as genai
import asyncio
import mcp
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from urllib.parse import urlencode

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
# This function is used once to populate the multiselect in the UI
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
    
    # New code to use the Authorization header for authentication
    headers = {
        "Authorization": f"Bearer {st.secrets['BALLDONTLIE_API_KEY']}",
        "Accept": "application/json, text/event-stream"
    }
    
    # The URL no longer needs a query parameter for the API key
    url = st.secrets['MCP_SERVER_URL']

    # Pass the headers directly to the client
    async with streamablehttp_client(url, headers=headers) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            result = await session.call_tool(tool_name=tool_name, input=kwargs)
            return result.content

def get_player_stats_from_mcp(league: str, firstName: str, lastName: str):
    """
    Python function that calls the Smithery MCP get_players tool.
    This function is the "tool" that Gemini will be instructed to call.
    """
    try:
        data = asyncio.run(call_mcp_tool(
            tool_name='get_players',
            league=league,
            firstName=firstName,
            lastName=lastName
        ))
        
        if not data:
            st.error(f"MCP server returned no data for {firstName} {lastName}.")
            return json.dumps([])
        
        if not isinstance(data, list) or len(data) == 0:
            st.error(f"MCP server returned an invalid data format for {firstName} {lastName}.")
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
                        "firstName": {
                            "type": "string",
                            "description": "The first name of the player."
                        },
                        "lastName": {
                            "type": "string",
                            "description": "The last name of the player."
                        }
                    },
                    "required": ["league", "firstName", "lastName"]
                }
            }
        ]
    }
]

# --- STREAMLIT APP LAYOUT ---
st.set_page_config(page_title="Fantasy Football Analyst", layout="wide")
st.title("🏈 Fantasy Football Player Analyst")
st.write("Ask a question about an NFL player's fantasy football stats, and Gemini will find the data and provide an analysis.")

# --- The Natural Language Input Field ---
user_prompt = st.text_input(
    "Enter your question here:",
    placeholder="e.g., What were the stats for Travis Kelce last season?",
)

if user_prompt:
    with st.spinner("Analyzing your request and generating report..."):
        try:
            # Add context to the prompt to guide Gemini's behavior
            context_prompt = (
                "You are a top-tier fantasy football analyst. Your task is to analyze the user's question, "
                "and if it requires player statistics, use the `get_player_stats_from_mcp` tool. "
                "The tool's league is always 'NFL'. "
                "Once you have the data, provide a concise analysis of each player's fantasy football value for the remainder of the season. "
                "If you find no statistics for a player, state that you cannot perform the analysis and explain why. "
                "Your analysis must include a single, comprehensive data table with the following columns: "
                "Player Name, Team, Position, Receptions, ReceivingYards, ReceivingTouchdowns, RushingYards, RushingTouchdowns, FumblesLost, and OverallFantasyFootballValue. "
                "Sort the table by highest to lowest ReceivingYards. "
                f"\n\nUser Question: {user_prompt}"
            )

            # Start a chat session with the model and tools
            model = genai.GenerativeModel('gemini-1.5-flash', tools=tool_declarations)
            response = model.generate_content(context_prompt)
            
            function_call = response.candidates[0].content.parts[0].function_call

            if function_call:
                tool_output = get_player_stats_from_mcp(
                    league="NFL",
                    firstName=function_call.args['firstName'],
                    lastName=function_call.args['lastName']
                )
                
                response_with_tool_output = model.generate_content(
                    genai.types.FunctionResponse(
                        name="get_player_stats_from_mcp",
                        response={"content": tool_output}
                    )
                )
                
                st.markdown("---")
                st.subheader(f"Report based on your question:")
                st.markdown(response_with_tool_output.text)
                
            else:
                st.error("Gemini could not fulfill the request using its tools. Here is its direct response:")
                st.markdown(response.text)

        except Exception as e:
            st.error(f"An error occurred: {e}")
