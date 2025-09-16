import streamlit as st
import json
import requests
import asyncio
import mcp
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from urllib.parse import urlencode

# Use the stable google-generativeai library
import google.generativeai as genai

# --- SETUP API KEYS FROM STREAMLIT SECRETS ---
try:
    genai.configure(api_key=st.secrets['GEMINI_API_KEY'])
    MCP_SERVER_URL = st.secrets['MCP_SERVER_URL']
    BALLDONTLIE_API_KEY = st.secrets['BALLDONTLIE_API_KEY']
except KeyError as e:
    st.error(f"Required API key not found in Streamlit secrets: {e}")
    st.info("Please add GEMINI_API_KEY, MCP_SERVER_URL, and BALLDONTLIE_API_KEY to your `.streamlit/secrets.toml` file.")
    st.stop()

# --- MCP TOOL INTEGRATION ---
async def call_mcp_tool(tool_name: str, **kwargs):
    """A helper function to call an MCP tool asynchronously."""
    
    headers = {
        "Authorization": f"Bearer {st.secrets['BALLDONTLIE_API_KEY']}",
        "Accept": "application/json, text/event-stream"
    }
    
    url = st.secrets['MCP_SERVER_URL']

    async with streamablehttp_client(url, headers=headers) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            result = await session.call_tool(tool_name=tool_name, input=kwargs)
            return result.content

def get_player_stats_from_mcp(league: str, firstName: str, lastName: str):
    """
    Python function that calls the MCP get_players tool.
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

            # Use the stable google-generativeai syntax
            model = genai.GenerativeModel('gemini-1.5-flash', tools=tool_declarations)
            response = model.generate_content(context_prompt)
            
            # Check if response has function call
            if response.candidates and response.candidates[0].content.parts:
                part = response.candidates[0].content.parts[0]
                if hasattr(part, 'function_call') and part.function_call:
                    function_call = part.function_call
                    
                    with st.status("Calling MCP server...", expanded=True) as status:
                        status.update(label=f"Requesting data for {function_call.args.get('firstName')} {function_call.args.get('lastName')}...")
                        
                        tool_output = get_player_stats_from_mcp(
                            league="NFL",
                            firstName=function_call.args['firstName'],
                            lastName=function_call.args['lastName']
                        )

                        status.update(label=f"Received data from MCP for {function_call.args.get('firstName')} {function_call.args.get('lastName')}!", state="complete")
                        
                    with st.status("Sending data back to Gemini for analysis...", expanded=True) as status:
                        # Generate final response with the tool output data
                        final_prompt = f"""
                        Based on the user's question: "{user_prompt}"
                        
                        And the following data about the player:
                        {tool_output}
                        
                        Please provide a comprehensive analysis answering the user's question about this player.
                        """
                        
                        response_with_tool_output = model.generate_content(final_prompt)
                        status.update(label="Report generated!", state="complete")

                    st.markdown("---")
                    st.subheader(f"Report based on your question:")
                    st.markdown(response_with_tool_output.text)
                else:
                    st.error("Gemini could not fulfill the request using its tools. Here is its direct response:")
                    st.markdown(response.text)
            else:
                st.error("No valid response from Gemini.")

        except Exception as e:
            st.error(f"An error occurred: {e}")
            st.write("Debug info:", str(e))
