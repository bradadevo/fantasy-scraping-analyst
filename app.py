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
            return json.dumps([])
        
        if not isinstance(data, list) or len(data) == 0:
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
                            "
