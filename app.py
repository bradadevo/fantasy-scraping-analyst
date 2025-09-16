import streamlit as st
import json
import requests

# Use the stable google-generativeai library
import google.generativeai as genai

# --- SETUP API KEYS FROM STREAMLIT SECRETS ---
try:
    genai.configure(api_key=st.secrets['GEMINI_API_KEY'])
    BALLDONTLIE_API_KEY = st.secrets['BALLDONTLIE_API_KEY']
    NFL_API_BASE_URL = "https://api.balldontlie.io/nfl/v1"
except KeyError as e:
    st.error(f"Required API key not found in Streamlit secrets: {e}")
    st.info("Please add GEMINI_API_KEY and BALLDONTLIE_API_KEY to your `.streamlit/secrets.toml` file.")
    st.stop()

# --- DIRECT NFL API CLIENT ---
def get_player_stats_from_api(firstName: str, lastName: str):
    """
    Function that calls the Ball Don't Lie NFL API directly to get player information.
    This function is the "tool" that Gemini will be instructed to call.
    """
    try:
        st.info(f"🔍 Searching for NFL player {firstName} {lastName}...")
        
        # Set up headers for the API request
        headers = {
            "Authorization": f"Bearer {BALLDONTLIE_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # Try multiple search strategies for better results
        search_strategies = [
            f"{firstName} {lastName}",  # Full name
            firstName,                   # First name only
            lastName                     # Last name only
        ]
        
        for search_term in search_strategies:
            st.info(f"🔍 Trying search strategy: '{search_term}'")
            
            # Make direct API call to NFL endpoint
            url = f"{NFL_API_BASE_URL}/players"
            params = {"search": search_term}
            
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            st.info(f"📊 API response for '{search_term}': {str(data)[:200]}...")
            
            # Check if we found any players
            if data.get('data') and len(data['data']) > 0:
                # Filter results to find exact matches
                exact_matches = []
                for player in data['data']:
                    player_first = player.get('first_name', '').lower()
                    player_last = player.get('last_name', '').lower()
                    
                    if (firstName.lower() in player_first or player_first in firstName.lower()) and \
                       (lastName.lower() in player_last or player_last in lastName.lower()):
                        exact_matches.append(player)
                
                if exact_matches:
                    st.success(f"✅ Found {len(exact_matches)} exact match(es) for {firstName} {lastName}!")
                    return json.dumps(exact_matches)
                elif data['data']:
                    st.info(f"📋 Found {len(data['data'])} partial match(es), using first result")
                    return json.dumps(data['data'][:1])  # Return first match
        
        # If no results found with any strategy
        error_msg = f"❌ No NFL players found matching {firstName} {lastName}."
        st.warning(error_msg)
        st.info("💡 Tip: Try using a different player name or check the spelling. Make sure the player is currently in the NFL.")
        return json.dumps({"error": error_msg, "suggestion": "Try searching for current NFL players like Patrick Mahomes, Josh Allen, or Tom Brady."})
        
    except Exception as e:
        st.error(f"An error occurred while fetching from NFL API: {e}")
        return json.dumps({"error": str(e)})



# --- TOOL DECLARATION FOR GEMINI ---
tool_declarations = [
    {
        "function_declarations": [
            {
                "name": "get_player_stats_from_api",
                "description": "Gets comprehensive NFL player information including team affiliation, position, and statistics by their first and last name using Ball Don't Lie NFL API. This tool can answer questions about what NFL team a player plays for, their position, and their performance statistics.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "firstName": {
                            "type": "string",
                            "description": "The first name of the NFL player."
                        },
                        "lastName": {
                            "type": "string",
                            "description": "The last name of the NFL player."
                        }
                    },
                    "required": ["firstName", "lastName"]
                }
            }
        ]
    }
]

# --- STREAMLIT APP LAYOUT ---
st.set_page_config(page_title="NFL Player Analyst", layout="wide")
st.title("� NFL Player Analyst")
st.write("Ask a question about NFL player stats, and Gemini will find the data and provide an analysis.")
st.info("💡 **Note**: This app uses the Ball Don't Lie NFL API to provide comprehensive NFL player data and statistics.")

# --- The Natural Language Input Field ---
user_prompt = st.text_input(
    "Enter your question here:",
    placeholder="e.g., What were the stats for Patrick Mahomes last season?",
)

if user_prompt:
    with st.spinner("Analyzing your request and generating report..."):
        try:
            # Add context to the prompt to guide Gemini's behavior
            context_prompt = (
                "You are a top-tier NFL analyst. Your task is to analyze the user's question, "
                "and if it requires ANY NFL player information (including team affiliation, position, or statistics), use the `get_player_stats_from_api` tool. "
                "IMPORTANT: This tool can answer questions like 'What team does [player] play for?', 'What position does [player] play?', and statistical questions. "
                "The Ball Don't Lie NFL API contains comprehensive NFL football data. "
                "Once you have the data, provide a detailed analysis of the player's performance and value focusing on NFL statistics like passing yards, rushing yards, touchdowns, receptions, etc. "
                "If you find no statistics for a player, explain that the player may not be in the Ball Don't Lie NFL database and suggest they try a different NFL player. "
                "Your analysis must include a comprehensive data table with relevant NFL statistics such as: "
                "Player Name, Team, Position, Passing Yards, Passing Touchdowns, Rushing Yards, Rushing Touchdowns, Receptions, Receiving Yards, Receiving Touchdowns, and Overall Fantasy Football Value. "
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
                    
                    with st.status("Calling Ball Don't Lie NFL API...", expanded=True) as status:
                        status.update(label=f"Requesting NFL data for {function_call.args.get('firstName')} {function_call.args.get('lastName')}...")
                        
                        tool_output = get_player_stats_from_api(
                            firstName=function_call.args['firstName'],
                            lastName=function_call.args['lastName']
                        )

                        status.update(label=f"Received NFL data from Ball Don't Lie API for {function_call.args.get('firstName')} {function_call.args.get('lastName')}!", state="complete")
                        
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
