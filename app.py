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
def get_player_stats_from_api(firstName: str, lastName: str, include_stats: bool = True):
    """
    Function that calls the Ball Don't Lie NFL API directly to get player information and optionally their stats.
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
        
        found_players = []
        
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
                    found_players = exact_matches
                    st.success(f"✅ Found {len(exact_matches)} exact match(es) for {firstName} {lastName}!")
                    break
                elif data['data']:
                    found_players = data['data'][:1]  # Use first match
                    st.info(f"📋 Found {len(data['data'])} partial match(es), using first result")
                    break
        
        if not found_players:
            # If no results found with any strategy
            error_msg = f"❌ No NFL players found matching {firstName} {lastName}."
            st.warning(error_msg)
            st.info("💡 Tip: Try using a different player name or check the spelling. Make sure the player is currently in the NFL.")
            return json.dumps({"error": error_msg, "suggestion": "Try searching for current NFL players like Patrick Mahomes, Josh Allen, or Tom Brady."})
        
        # If include_stats is True, fetch stats for the found players
        if include_stats and found_players:
            st.info("📈 Fetching player statistics...")
            
            for player in found_players:
                player_id = player.get('id')
                if player_id:
                    # Fetch stats for this player - try multiple approaches for recent data
                    stats_url = f"{NFL_API_BASE_URL}/stats"
                    
                    # Try different parameter combinations to get recent data
                    stats_attempts = [
                        {"player_ids[]": player_id, "seasons[]": "2025"},  # Try 2025 season specifically (current)
                        {"player_ids[]": player_id, "seasons[]": "2024"},  # Try 2024 season 
                        {"player_ids[]": player_id, "seasons[]": "2023"},  # Try 2023 season
                        {"player_ids[]": player_id},  # Default query
                        {"player_ids[]": player_id, "per_page": 100},  # More results
                    ]
                    
                    found_stats = False
                    all_stats = []
                    
                    for attempt_params in stats_attempts:
                        try:
                            st.info(f"🔍 Trying stats query with params: {attempt_params}")
                            stats_response = requests.get(stats_url, headers=headers, params=attempt_params)
                            stats_response.raise_for_status()
                            
                            stats_data = stats_response.json()
                            st.info(f"📊 Stats response for attempt: {str(stats_data)[:200]}...")
                            
                            if stats_data.get('data') and len(stats_data['data']) > 0:
                                st.success(f"✅ Found {len(stats_data['data'])} stat records with these parameters!")
                                all_stats.extend(stats_data['data'])
                                found_stats = True
                                
                                # Check what seasons we got
                                seasons = set([stat.get('season') for stat in stats_data['data'] if stat.get('season')])
                                st.info(f"📅 Available seasons in this response: {sorted(seasons)}")
                                
                                # If we found 2025, 2024 or 2023 data, prefer that
                                recent_stats = [stat for stat in stats_data['data'] if stat.get('season') in ['2025', '2024', '2023']]
                                if recent_stats:
                                    st.success(f"🎯 Found {len(recent_stats)} recent season records!")
                                    break
                                    
                        except Exception as attempt_error:
                            st.warning(f"❌ Attempt failed: {attempt_error}")
                            continue
                    
                    # Remove duplicates and sort by season (most recent first)
                    if all_stats:
                        unique_stats = []
                        seen_ids = set()
                        for stat in sorted(all_stats, key=lambda x: x.get('season', ''), reverse=True):
                            stat_id = (stat.get('id'), stat.get('season'), stat.get('week'))
                            if stat_id not in seen_ids:
                                unique_stats.append(stat)
                                seen_ids.add(stat_id)
                        
                        player['stats'] = unique_stats
                        st.success(f"✅ Final result: {len(unique_stats)} unique stat records for {firstName} {lastName}!")
                        
                        # Show season breakdown
                        season_breakdown = {}
                        for stat in unique_stats:
                            season = stat.get('season', 'Unknown')
                            season_breakdown[season] = season_breakdown.get(season, 0) + 1
                        st.info(f"📊 Stats by season: {dict(sorted(season_breakdown.items(), reverse=True))}")
                        
                    else:
                        st.info(f"📊 No stats found for {firstName} {lastName} (player ID: {player_id})")
                        player['stats'] = []
        
        return json.dumps(found_players)
        
    except Exception as e:
        st.error(f"An error occurred while fetching from NFL API: {e}")
        return json.dumps({"error": str(e)})

def get_player_stats_only(firstName: str, lastName: str):
    """
    Function that fetches only the statistics for a specific NFL player.
    """
    try:
        st.info(f"📈 Fetching statistics for NFL player {firstName} {lastName}...")
        
        # First get the player to find their ID
        player_data = get_player_stats_from_api(firstName, lastName, include_stats=False)
        players = json.loads(player_data)
        
        if isinstance(players, dict) and players.get('error'):
            return player_data  # Return the error
        
        if not players or len(players) == 0:
            return json.dumps({"error": "No player found to get stats for"})
        
        player = players[0]  # Use first match
        player_id = player.get('id')
        
        if not player_id:
            return json.dumps({"error": "Player ID not found"})
        
        # Set up headers for the API request
        headers = {
            "Authorization": f"Bearer {BALLDONTLIE_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # Fetch stats for this player with multiple attempts for recent data
        stats_url = f"{NFL_API_BASE_URL}/stats"
        
        # Try different parameter combinations to get recent data
        stats_attempts = [
            {"player_ids[]": player_id, "seasons[]": "2025"},  # Try 2025 season specifically (current)
            {"player_ids[]": player_id, "seasons[]": "2024"},  # Try 2024 season
            {"player_ids[]": player_id, "seasons[]": "2023"},  # Try 2023 season
            {"player_ids[]": player_id},  # Default query
            {"player_ids[]": player_id, "per_page": 100},  # More results
        ]
        
        all_stats = []
        
        for attempt_params in stats_attempts:
            try:
                st.info(f"🔍 Trying stats query with params: {attempt_params}")
                stats_response = requests.get(stats_url, headers=headers, params=attempt_params)
                stats_response.raise_for_status()
                
                stats_data = stats_response.json()
                st.info(f"📊 Stats response for attempt: {str(stats_data)[:200]}...")
                
                if stats_data.get('data') and len(stats_data['data']) > 0:
                    st.success(f"✅ Found {len(stats_data['data'])} stat records with these parameters!")
                    all_stats.extend(stats_data['data'])
                    
                    # Check what seasons we got
                    seasons = set([stat.get('season') for stat in stats_data['data'] if stat.get('season')])
                    st.info(f"📅 Available seasons in this response: {sorted(seasons)}")
                    
                    # If we found 2025, 2024 or 2023 data, prefer that
                    recent_stats = [stat for stat in stats_data['data'] if stat.get('season') in ['2025', '2024', '2023']]
                    if recent_stats:
                        st.success(f"🎯 Found {len(recent_stats)} recent season records!")
                        break
                        
            except Exception as attempt_error:
                st.warning(f"❌ Attempt failed: {attempt_error}")
                continue
        
        # Remove duplicates and sort by season (most recent first)
        if all_stats:
            unique_stats = []
            seen_ids = set()
            for stat in sorted(all_stats, key=lambda x: x.get('season', ''), reverse=True):
                stat_id = (stat.get('id'), stat.get('season'), stat.get('week'))
                if stat_id not in seen_ids:
                    unique_stats.append(stat)
                    seen_ids.add(stat_id)
            
            st.success(f"✅ Final result: {len(unique_stats)} unique stat records for {firstName} {lastName}!")
            
            # Show season breakdown
            season_breakdown = {}
            for stat in unique_stats:
                season = stat.get('season', 'Unknown')
                season_breakdown[season] = season_breakdown.get(season, 0) + 1
            st.info(f"📊 Stats by season: {dict(sorted(season_breakdown.items(), reverse=True))}")
            
            return json.dumps({
                "player": player,
                "stats": unique_stats
            })
        else:
            st.info(f"📊 No stats found for {firstName} {lastName}")
            return json.dumps({
                "player": player,
                "stats": [],
                "message": "No statistics available for this player"
            })
        
    except Exception as e:
        st.error(f"An error occurred while fetching stats: {e}")
        return json.dumps({"error": str(e)})



# --- TOOL DECLARATION FOR GEMINI ---
tool_declarations = [
    {
        "function_declarations": [
            {
                "name": "get_player_stats_from_api",
                "description": "Gets comprehensive NFL player information including team affiliation, position, and optionally their statistics by their first and last name using Ball Don't Lie NFL API. This tool can answer questions about what NFL team a player plays for, their position, and their performance statistics.",
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
                        },
                        "include_stats": {
                            "type": "boolean",
                            "description": "Whether to include detailed statistics for the player. Default is true."
                        }
                    },
                    "required": ["firstName", "lastName"]
                }
            },
            {
                "name": "get_player_stats_only",
                "description": "Gets only the detailed statistics for a specific NFL player. Use this when you specifically need just the stats data without basic player information.",
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
                "and if it requires ANY NFL player information, use the appropriate tool: "
                "- Use `get_player_stats_from_api` for general player information including team, position, and optionally statistics "
                "- Use `get_player_stats_only` when you specifically need just the statistical data for a player "
                "IMPORTANT: These tools can answer questions like 'What team does [player] play for?', 'What position does [player] play?', and statistical questions. "
                "The Ball Don't Lie NFL API contains comprehensive NFL football data including detailed player statistics. "
                "The API will attempt to fetch the most recent available data, prioritizing 2025 (current season), 2024, and 2023 seasons. "
                "If the user asks for 'last season' or 'recent stats', focus on the most recent season data available. "
                "Once you have the data, provide a detailed analysis of the player's performance and value focusing on NFL statistics like passing yards, rushing yards, touchdowns, receptions, etc. "
                "Always mention which seasons the statistics are from, and if recent data (2025/2024/2023) is available, highlight that. "
                "If only older data is available, mention this limitation and suggest the user that the API may have limited recent data. "
                "When presenting statistics, create comprehensive data tables with relevant NFL statistics such as: "
                "Player Name, Team, Position, Season, Passing Yards, Passing Touchdowns, Rushing Yards, Rushing Touchdowns, Receptions, Receiving Yards, Receiving Touchdowns, and Fantasy Football Value. "
                "Sort statistics by season (most recent first) and highlight the most recent season's performance. "
                f"\n\nUser Question: {user_prompt}"
            )

            # Use the stable google-generativeai syntax
            model = genai.GenerativeModel('gemini-1.5-flash', tools=tool_declarations)
            
            # Configure generation to use ANY function calling mode for better reliability
            generation_config = genai.types.GenerationConfig(
                temperature=0.1,
                top_p=1,
                top_k=32,
                max_output_tokens=4096,
            )
            
            response = model.generate_content(
                context_prompt,
                generation_config=generation_config,
                tool_config={'function_calling_config': {'mode': 'ANY'}}
            )
            
            # Check if response has function call
            if response.candidates and response.candidates[0].content.parts:
                part = response.candidates[0].content.parts[0]
                if hasattr(part, 'function_call') and part.function_call:
                    function_call = part.function_call
                    
                    with st.status("Calling Ball Don't Lie NFL API...", expanded=True) as status:
                        status.update(label=f"Requesting NFL data for {function_call.args.get('firstName')} {function_call.args.get('lastName')}...")
                        
                        # Handle different function calls
                        if function_call.name == "get_player_stats_from_api":
                            tool_output = get_player_stats_from_api(
                                firstName=function_call.args['firstName'],
                                lastName=function_call.args['lastName'],
                                include_stats=function_call.args.get('include_stats', True)
                            )
                        elif function_call.name == "get_player_stats_only":
                            tool_output = get_player_stats_only(
                                firstName=function_call.args['firstName'],
                                lastName=function_call.args['lastName']
                            )
                        else:
                            tool_output = json.dumps({"error": f"Unknown function: {function_call.name}"})

                        status.update(label=f"Received NFL data from Ball Don't Lie API for {function_call.args.get('firstName')} {function_call.args.get('lastName')}!", state="complete")
                        
                    with st.status("Sending data back to Gemini for analysis...", expanded=True) as status:
                        # Generate final response with the tool output data
                        final_prompt = f"""
                        Based on the user's question: "{user_prompt}"
                        
                        And the following data about the player:
                        {tool_output}
                        
                        Please provide a comprehensive analysis answering the user's question about this player.
                        """
                        
                        response_with_tool_output = model.generate_content(
                            final_prompt,
                            generation_config=generation_config
                        )
                        status.update(label="Report generated!", state="complete")

                    st.markdown("---")
                    st.subheader(f"Report based on your question:")
                    
                    # Safely access the response text
                    try:
                        if response_with_tool_output.candidates and response_with_tool_output.candidates[0].content.parts:
                            response_text = ""
                            for part in response_with_tool_output.candidates[0].content.parts:
                                if hasattr(part, 'text'):
                                    response_text += part.text
                            
                            if response_text:
                                st.markdown(response_text)
                            else:
                                st.error("No text content found in the response.")
                        else:
                            st.error("No valid response content received from Gemini.")
                    except Exception as text_error:
                        st.error(f"Error accessing response text: {text_error}")
                        st.write("Raw response:", str(response_with_tool_output)[:500] + "...")
                else:
                    st.error("Gemini could not fulfill the request using its tools. Here is its direct response:")
                    st.markdown(response.text)
            else:
                st.error("No valid response from Gemini.")

        except Exception as e:
            st.error(f"An error occurred: {e}")
            st.write("Debug info:", str(e))
