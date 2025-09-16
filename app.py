import streamlit as st
import json
import requests

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

# --- HTTP MCP CLIENT ---
def call_mcp_tool(tool_name: str, **kwargs):
    """Call an MCP tool using direct HTTP requests"""
    try:
        # Prepare the MCP request payload
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": kwargs
            }
        }
        
        headers = {
            "Authorization": f"Bearer {BALLDONTLIE_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # Make HTTP request to MCP server
        response = requests.post(MCP_SERVER_URL, json=payload, headers=headers)
        response.raise_for_status()
        
        result = response.json()
        
        if "error" in result:
            st.error(f"MCP server error: {result['error']}")
            return None
            
        return result.get("result", {}).get("content", [])
        
    except Exception as e:
        st.error(f"Error calling MCP tool {tool_name}: {e}")
        return None

def get_player_stats_from_api(league: str, firstName: str, lastName: str):
    """
    Function that calls the Ball Don't Lie MCP server to get player information.
    This function is the "tool" that Gemini will be instructed to call.
    """
    try:
        st.info(f"🔍 Searching for {firstName} {lastName} in {league}...")
        
        # Call the MCP get_players tool
        data = call_mcp_tool(
            tool_name='get_players',
            league=league,
            firstName=firstName,
            lastName=lastName
        )
        
        if not data:
            error_msg = f"❌ No data returned from MCP server for {firstName} {lastName} in {league}."
            st.error(error_msg)
            return json.dumps({"error": error_msg, "suggestion": "Try a different player name or check if the player exists in the database."})
        
        st.info(f"📊 Raw response from MCP server: {str(data)[:200]}...")
        
        if not isinstance(data, list) or len(data) == 0:
            error_msg = f"❌ No players found matching {firstName} {lastName} in {league}."
            st.warning(error_msg)
            st.info("💡 Tip: Try using a more common player name or check the spelling. Ball Don't Lie API primarily has NBA data.")
            return json.dumps({"error": error_msg, "raw_data": data, "suggestion": "Ball Don't Lie API might not have this player in their database."})

        st.success(f"✅ Found {len(data)} result(s) for {firstName} {lastName}!")
        return json.dumps(data)
    except Exception as e:
        st.error(f"An error occurred while fetching from MCP: {e}")
        return json.dumps({"error": str(e)})

# --- TOOL DECLARATION FOR GEMINI ---
tool_declarations = [
    {
        "function_declarations": [
            {
                "name": "get_player_stats_from_api",
                "description": "Gets detailed player statistics for a player from a given league by their first and last name using Ball Don't Lie MCP API.",
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
st.set_page_config(page_title="Sports Player Analyst", layout="wide")
st.title("🏀 Sports Player Analyst")
st.write("Ask a question about NBA or NFL player stats, and Gemini will find the data and provide an analysis.")
st.info("💡 **Note**: This app uses the Ball Don't Lie MCP API which has comprehensive NBA data. NFL data may be limited.")

# --- The Natural Language Input Field ---
user_prompt = st.text_input(
    "Enter your question here:",
    placeholder="e.g., What were the stats for LeBron James last season?",
)

if user_prompt:
    with st.spinner("Analyzing your request and generating report..."):
        try:
            # Add context to the prompt to guide Gemini's behavior
            context_prompt = (
                "You are a top-tier sports analyst. Your task is to analyze the user's question, "
                "and if it requires player statistics, use the `get_player_stats_from_api` tool. "
                "IMPORTANT: The Ball Don't Lie API primarily contains NBA basketball data. If the user asks about NFL players, "
                "try the tool first, but if no data is found, explain that the database may not contain that NFL player's information. "
                "For NBA players, the tool should work well. Use 'NBA' as the league for basketball players and 'NFL' for football players. "
                "Once you have the data, provide a detailed analysis of the player's performance and value. "
                "If you find no statistics for a player, explain that the player may not be in the Ball Don't Lie database and suggest they try an NBA player instead. "
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
                    
                    with st.status("Calling Ball Don't Lie MCP API...", expanded=True) as status:
                        status.update(label=f"Requesting data for {function_call.args.get('firstName')} {function_call.args.get('lastName')}...")
                        
                        tool_output = get_player_stats_from_api(
                            league=function_call.args.get('league', 'NBA'),  # Default to NBA since it has better data
                            firstName=function_call.args['firstName'],
                            lastName=function_call.args['lastName']
                        )

                        status.update(label=f"Received data from Ball Don't Lie MCP API for {function_call.args.get('firstName')} {function_call.args.get('lastName')}!", state="complete")
                        
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
