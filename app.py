import streamlit as st
import json
import requests
import time
from datetime import datetime, timedelta
from functools import wraps

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

# --- RATE LIMITING AND CACHING INFRASTRUCTURE ---
if 'api_call_times' not in st.session_state:
    st.session_state.api_call_times = []

if 'api_cache' not in st.session_state:
    st.session_state.api_cache = {}

def rate_limit_decorator(func):
    """Decorator to enforce rate limiting of 60 requests per minute"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        current_time = time.time()
        
        # Remove API calls older than 1 minute
        st.session_state.api_call_times = [
            call_time for call_time in st.session_state.api_call_times 
            if current_time - call_time < 60
        ]
        
        # Check if we're at the rate limit
        if len(st.session_state.api_call_times) >= 55:  # Keep buffer of 5 requests
            wait_time = 60 - (current_time - st.session_state.api_call_times[0])
            if wait_time > 0:
                st.warning(f"⏱️ Rate limit approaching. Waiting {wait_time:.1f} seconds to avoid hitting the 60 req/min limit...")
                time.sleep(wait_time)
                # Clean up old calls after waiting
                current_time = time.time()
                st.session_state.api_call_times = [
                    call_time for call_time in st.session_state.api_call_times 
                    if current_time - call_time < 60
                ]
        
        # Record this API call
        st.session_state.api_call_times.append(current_time)
        
        return func(*args, **kwargs)
    return wrapper

def get_cache_key(endpoint, params):
    """Generate a cache key for API requests"""
    return f"{endpoint}_{hash(str(sorted(params.items())) if params else '')}"

def get_cached_response(endpoint, params):
    """Get cached response if available and not expired"""
    cache_key = get_cache_key(endpoint, params)
    if cache_key in st.session_state.api_cache:
        cached_data, timestamp = st.session_state.api_cache[cache_key]
        # Cache expires after 5 minutes
        if time.time() - timestamp < 300:
            st.info(f"📋 Using cached data for {endpoint}")
            return cached_data
    return None

def cache_response(endpoint, params, response_data):
    """Cache API response"""
    cache_key = get_cache_key(endpoint, params)
    st.session_state.api_cache[cache_key] = (response_data, time.time())

@rate_limit_decorator
def make_api_request(endpoint, params=None):
    """Make rate-limited API request with caching"""
    # Check cache first
    cached_response = get_cached_response(endpoint, params)
    if cached_response:
        return cached_response
    
    # Make the actual API request
    headers = {
        "Authorization": f"Bearer {BALLDONTLIE_API_KEY}",
        "Content-Type": "application/json"
    }
    
    url = f"{NFL_API_BASE_URL}/{endpoint}"
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    
    response_data = response.json()
    
    # Cache the response
    cache_response(endpoint, params, response_data)
    
    return response_data

# --- STREAMLIT APP LAYOUT ---
st.set_page_config(page_title="NFL Player Analyst", layout="wide", page_icon="🏈")

# Custom CSS for better table styling and visual enhancements
st.markdown("""
<style>
    /* Custom styling for better visual experience */
    .main-header {
        text-align: center;
        color: #1f4e79;
        font-size: 3em;
        margin-bottom: 20px;
    }
    
    /* Enhanced table styling */
    .stMarkdown table {
        width: 100%;
        border-collapse: collapse;
        margin: 20px 0;
        font-size: 14px;
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
        border-radius: 10px;
        overflow: hidden;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    
    .stMarkdown table th {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        font-weight: bold;
        padding: 15px 12px;
        text-align: left;
        border-bottom: 2px solid #ddd;
    }
    
    .stMarkdown table td {
        padding: 12px;
        border-bottom: 1px solid #ddd;
        background-color: rgba(255, 255, 255, 0.8);
    }
    
    .stMarkdown table tr:hover td {
        background-color: rgba(102, 126, 234, 0.1);
        transition: background-color 0.3s ease;
    }
    
    /* Metric cards styling */
    .metric-card {
        background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        padding: 20px;
        border-radius: 15px;
        color: white;
        text-align: center;
        margin: 10px 0;
        box-shadow: 0 8px 16px rgba(0, 0, 0, 0.1);
    }
    
    /* Enhanced button styling */
    .stButton > button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 25px;
        padding: 10px 20px;
        font-weight: bold;
        transition: all 0.3s ease;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 12px rgba(0, 0, 0, 0.2);
    }
    
    /* Special styling for the Analyze button */
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #FF6B6B 0%, #4ECDC4 50%, #45B7D1 100%);
        background-size: 200% 200%;
        animation: gradientShift 3s ease infinite;
        font-size: 1.1em;
        font-weight: bold;
        padding: 12px 25px;
        border-radius: 30px;
        box-shadow: 0 8px 15px rgba(255, 107, 107, 0.3);
        position: relative;
        overflow: hidden;
    }
    
    .stButton > button[kind="primary"]:hover {
        transform: translateY(-3px) scale(1.05);
        box-shadow: 0 12px 20px rgba(255, 107, 107, 0.4);
        animation: gradientShift 1s ease infinite, pulse 0.5s ease;
    }
    
    .stButton > button[kind="primary"]:active {
        animation: rocket-launch 0.6s ease-out;
    }
    
    @keyframes gradientShift {
        0% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }
    
    @keyframes pulse {
        0% { transform: translateY(-3px) scale(1.05); }
        50% { transform: translateY(-3px) scale(1.1); }
        100% { transform: translateY(-3px) scale(1.05); }
    }
    
    @keyframes rocket-launch {
        0% { transform: translateY(-3px) scale(1.05); }
        20% { transform: translateY(-8px) scale(1.1) rotate(5deg); }
        40% { transform: translateY(-15px) scale(1.15) rotate(-3deg); }
        60% { transform: translateY(-10px) scale(1.1) rotate(2deg); }
        80% { transform: translateY(-5px) scale(1.05) rotate(-1deg); }
        100% { transform: translateY(-3px) scale(1.05) rotate(0deg); }
    }
    
    /* Info boxes styling */
    .stInfo {
        background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%);
        border-left: 5px solid #667eea;
        border-radius: 10px;
    }
    
    /* Success boxes styling */
    .stSuccess {
        background: linear-gradient(135deg, #d299c2 0%, #fef9d7 100%);
        border-left: 5px solid #28a745;
        border-radius: 10px;
    }
</style>
""", unsafe_allow_html=True)

st.title("🏈 NFL Player Analyst")

# --- The Natural Language Input Field ---
def get_nfl_teams(division=None, conference=None):
    """Get NFL teams with optional filtering by division or conference"""
    try:
        params = {}
        if division:
            params["division"] = division
        if conference:
            params["conference"] = conference
            
        return make_api_request("teams", params)
    except Exception as e:
        st.error(f"Error fetching teams: {e}")
        return {"error": str(e)}

def get_nfl_games(seasons=None, team_ids=None, weeks=None, postseason=None, per_page=25):
    """Get NFL games with filtering options"""
    try:
        params = {"per_page": per_page}
        if seasons:
            params["seasons[]"] = seasons if isinstance(seasons, list) else [seasons]
        if team_ids:
            params["team_ids[]"] = team_ids if isinstance(team_ids, list) else [team_ids]
        if weeks:
            params["weeks[]"] = weeks if isinstance(weeks, list) else [weeks]
        if postseason is not None:
            params["postseason"] = postseason
            
        return make_api_request("games", params)
    except Exception as e:
        st.error(f"Error fetching games: {e}")
        return {"error": str(e)}

def get_nfl_standings(season):
    """Get NFL standings for a specific season"""
    try:
        params = {"season": season}
        return make_api_request("standings", params)
    except Exception as e:
        st.error(f"Error fetching standings: {e}")
        return {"error": str(e)}

def get_nfl_season_stats(season, player_ids=None, team_id=None, postseason=None, sort_by=None):
    """Get NFL season stats with comprehensive filtering"""
    try:
        params = {"season": season}
        if player_ids:
            params["player_ids[]"] = player_ids if isinstance(player_ids, list) else [player_ids]
        if team_id:
            params["team_id"] = team_id
        if postseason is not None:
            params["postseason"] = postseason
        if sort_by:
            params["sort_by"] = sort_by
            
        return make_api_request("season_stats", params)
    except Exception as e:
        st.error(f"Error fetching season stats: {e}")
        return {"error": str(e)}



def get_nfl_player_injuries(team_ids=None, player_ids=None, per_page=25):
    """Get NFL player injury information"""
    try:
        params = {"per_page": per_page}
        if team_ids:
            params["team_ids[]"] = team_ids if isinstance(team_ids, list) else [team_ids]
        if player_ids:
            params["player_ids[]"] = player_ids if isinstance(player_ids, list) else [player_ids]
            
        return make_api_request("player_injuries", params)
    except Exception as e:
        st.error(f"Error fetching player injuries: {e}")
        return {"error": str(e)}

def get_nfl_player_weekly_stats(firstName: str, lastName: str, season: int, weeks: list = None):
    """
    Get player stats for specific weeks of a season
    """
    try:
        with st.expander("📅 Weekly Stats Fetching Details", expanded=False):
            st.info(f"🏈 Fetching weekly stats for {firstName} {lastName} in {season}...")
            
            # First get the player to find their ID
            player_data = get_player_stats_from_api(firstName, lastName, include_stats=False)
            players = json.loads(player_data)
            
            if isinstance(players, dict) and players.get('error'):
                return player_data  # Return the error
            
            if not players or len(players) == 0:
                return json.dumps({"error": "No player found to get weekly stats for"})
            
            player = players[0]  # Use first match
            player_id = player.get('id')
            
            if not player_id:
                return json.dumps({"error": "Player ID not found"})
            
            # Build parameters for weekly stats query
            params = {
                "player_ids[]": player_id,
                "seasons[]": str(season)
            }
            
            if weeks:
                params["weeks[]"] = weeks if isinstance(weeks, list) else [weeks]
                st.info(f"📅 Fetching stats for weeks: {weeks}")
            else:
                st.info(f"📅 Fetching all weekly stats for {season} season")
            
            # Make API call for stats
            stats_data = make_api_request("stats", params)
            
            if stats_data.get('data') and len(stats_data['data']) > 0:
                st.success(f"✅ Found {len(stats_data['data'])} weekly stat records!")
                
                # Organize stats by week
                weekly_stats = {}
                for stat in stats_data['data']:
                    week = stat.get('week', 'Unknown')
                    if week not in weekly_stats:
                        weekly_stats[week] = []
                    weekly_stats[week].append(stat)
                
                result = {
                    "player": player,
                    "season": season,
                    "weekly_stats": weekly_stats,
                    "total_weeks": len(weekly_stats)
                }
                
                st.info(f"📊 Weekly breakdown: {list(weekly_stats.keys())}")
                return json.dumps(result)
            else:
                return json.dumps({
                    "player": player,
                    "season": season,
                    "weekly_stats": {},
                    "message": f"No weekly statistics available for {firstName} {lastName} in {season}"
                })
            
    except Exception as e:
        st.error(f"Error fetching weekly stats: {e}")
        return json.dumps({"error": str(e)})

def get_comprehensive_player_analysis(firstName: str, lastName: str):
    """
    Get comprehensive player analysis including stats, team info, games, and metrics
    OPTIMIZED: Reduced API calls by combining requests and using smart caching
    """
    try:
        with st.expander("🔍 API Call Details & Debug Info", expanded=False):
            st.info(f"🔍 Performing comprehensive analysis for {firstName} {lastName}...")
            
            # First get basic player info
            player_data = get_player_stats_from_api(firstName, lastName, include_stats=True)
            players = json.loads(player_data)
            
            if isinstance(players, dict) and players.get('error'):
                return player_data
                
            if not players or len(players) == 0:
                return json.dumps({"error": "No player found"})
                
            player = players[0]
            player_id = player.get('id')
            team_info = player.get('team', {})
            team_id = team_info.get('id') if team_info else None
            
            comprehensive_data = {
                "player": player,
                "additional_data": {}
            }
            
            if player_id:
                # OPTIMIZATION: Only fetch the most recent season stats to reduce API calls
                st.info("📊 Fetching recent season statistics...")
                # Try 2025 first, then 2024 as fallback - only make 1-2 calls instead of 3
                for season in [2025, 2024]:
                    season_stats = get_nfl_season_stats(season, player_ids=[player_id])
                    if season_stats.get('data') and len(season_stats['data']) > 0:
                        comprehensive_data["additional_data"][f"season_{season}_stats"] = season_stats
                        st.success(f"✅ Found {season} season data, skipping older seasons to save API calls")
                        break  # Stop after finding the first available season
                        
                # Get injury information (1 API call)
                st.info("🏥 Checking injury status...")
                injuries = get_nfl_player_injuries(player_ids=[player_id])
                if injuries.get('data'):
                    comprehensive_data["additional_data"]["injuries"] = injuries
                    
            if team_id:
                # OPTIMIZATION: Use cached team data via our rate-limited function
                st.info("🏈 Fetching team information...")
                try:
                    team_response = make_api_request(f"teams/{team_id}")
                    comprehensive_data["additional_data"]["team_details"] = team_response
                except:
                    pass  # Team details are optional
                    
            st.success("✅ Comprehensive analysis complete!")
            
        return json.dumps(comprehensive_data)
        
    except Exception as e:
        st.error(f"Error in comprehensive analysis: {e}")
        return json.dumps({"error": str(e)})
def get_player_stats_from_api(firstName: str, lastName: str, include_stats: bool = True):
    """
    Function that calls the Ball Don't Lie NFL API directly to get player information and optionally their stats.
    OPTIMIZED: Reduced API calls by limiting search strategies and stats attempts
    """
    try:
        with st.expander("🔍 Player Search & API Details", expanded=False):
            st.info(f"🔍 Searching for NFL player {firstName} {lastName}...")
            
            # OPTIMIZATION: Reduce search strategies to 2 most effective ones
            search_strategies = [
                f"{firstName} {lastName}",  # Full name (most likely to work)
                lastName                     # Last name only (fallback)
            ]
            
            found_players = []
            
            for search_term in search_strategies:
                st.info(f"🔍 Trying search strategy: '{search_term}'")
                
                # Make direct API call to NFL endpoint using our rate-limited function
                params = {"search": search_term}
                
                data = make_api_request("players", params)
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
                        # OPTIMIZATION: Reduce stats attempts to 2 most recent seasons only
                        stats_attempts = [
                            {"player_ids[]": player_id, "seasons[]": "2025"},  # Try 2025 season specifically (current)
                            {"player_ids[]": player_id, "seasons[]": "2024"},  # Try 2024 season 
                        ]
                        
                        all_stats = []
                        
                        for attempt_params in stats_attempts:
                            try:
                                st.info(f"🔍 Trying stats query with params: {attempt_params}")
                                stats_data = make_api_request("stats", attempt_params)
                                st.info(f"📊 Stats response for attempt: {str(stats_data)[:200]}...")
                                
                                if stats_data.get('data') and len(stats_data['data']) > 0:
                                    st.success(f"✅ Found {len(stats_data['data'])} stat records with these parameters!")
                                    all_stats.extend(stats_data['data'])
                                    
                                    # Check what seasons we got
                                    seasons = set([stat.get('season') for stat in stats_data['data'] if stat.get('season')])
                                    st.info(f"📅 Available seasons in this response: {sorted(seasons)}")
                                    
                                    # If we found 2025 or 2024 data, that's good enough
                                    recent_stats = [stat for stat in stats_data['data'] if stat.get('season') in ['2025', '2024']]
                                    if recent_stats:
                                        st.success(f"🎯 Found {len(recent_stats)} recent season records!")
                                        break  # Stop after finding recent data
                                        
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
    OPTIMIZED: Reduced API calls by limiting stats attempts to recent seasons only
    """
    try:
        with st.expander("📈 Stats Fetching Details", expanded=False):
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
            
            # OPTIMIZATION: Reduce stats attempts to 2 most recent seasons only
            stats_attempts = [
                {"player_ids[]": player_id, "seasons[]": "2025"},  # Try 2025 season specifically (current)
                {"player_ids[]": player_id, "seasons[]": "2024"},  # Try 2024 season
            ]
            
            all_stats = []
            
            for attempt_params in stats_attempts:
                try:
                    st.info(f"🔍 Trying stats query with params: {attempt_params}")
                    stats_data = make_api_request("stats", attempt_params)
                    st.info(f"📊 Stats response for attempt: {str(stats_data)[:200]}...")
                    
                    if stats_data.get('data') and len(stats_data['data']) > 0:
                        st.success(f"✅ Found {len(stats_data['data'])} stat records with these parameters!")
                        all_stats.extend(stats_data['data'])
                        
                        # Check what seasons we got
                        seasons = set([stat.get('season') for stat in stats_data['data'] if stat.get('season')])
                        st.info(f"📅 Available seasons in this response: {sorted(seasons)}")
                        
                        # If we found 2025 or 2024 data, that's good enough
                        recent_stats = [stat for stat in stats_data['data'] if stat.get('season') in ['2025', '2024']]
                        if recent_stats:
                            st.success(f"🎯 Found {len(recent_stats)} recent season records!")
                            break  # Stop after finding recent data
                            
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
            },
            {
                "name": "get_comprehensive_player_analysis",
                "description": "Gets the most comprehensive analysis of an NFL player including basic stats, season stats, advanced metrics, injury status, and team information. Use this for in-depth player analysis questions.",
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
            },
            {
                "name": "get_nfl_teams",
                "description": "Gets information about NFL teams, with optional filtering by division or conference.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "division": {
                            "type": "string",
                            "description": "Filter by division (e.g., 'AFC East', 'NFC West')"
                        },
                        "conference": {
                            "type": "string",
                            "description": "Filter by conference ('AFC' or 'NFC')"
                        }
                    },
                    "required": []
                }
            },
            {
                "name": "get_nfl_standings",
                "description": "Gets NFL standings for a specific season.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "season": {
                            "type": "integer",
                            "description": "The NFL season year (e.g., 2025, 2024, 2023)"
                        }
                    },
                    "required": ["season"]
                }
            },
            {
                "name": "get_nfl_season_stats",
                "description": "Gets comprehensive season statistics for players with filtering options.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "season": {
                            "type": "integer",
                            "description": "The NFL season year"
                        },
                        "player_ids": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "List of player IDs to filter by"
                        },
                        "team_id": {
                            "type": "integer",
                            "description": "Team ID to filter by"
                        },
                        "postseason": {
                            "type": "boolean",
                            "description": "Whether to include postseason stats"
                        }
                    },
                    "required": ["season"]
                }
            },
            {
                "name": "get_nfl_player_weekly_stats",
                "description": "Gets player statistics for specific weeks of a season. Use this when users ask about week 1, week 2, specific weeks, or weekly performance data.",
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
                        "season": {
                            "type": "integer",
                            "description": "The NFL season year (e.g., 2025, 2024, 2023)"
                        },
                        "weeks": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "List of week numbers to get stats for (e.g., [1, 2, 3] for weeks 1-3). If not provided, gets all weeks."
                        }
                    },
                    "required": ["firstName", "lastName", "season"]
                }
            },
            {
                "name": "get_nfl_games",
                "description": "Gets NFL games with filtering options including specific weeks, seasons, teams. Use this for game schedules, matchups, and game-specific data.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "seasons": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "List of seasons to filter by"
                        },
                        "team_ids": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "List of team IDs to filter by"
                        },
                        "weeks": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "List of week numbers to filter by (e.g., [1, 2, 3])"
                        },
                        "postseason": {
                            "type": "boolean",
                            "description": "Whether to include postseason games"
                        }
                    },
                    "required": []
                }
            },
        ]
    }
]


# --- The Natural Language Input Field ---
if 'selected_prompt' not in st.session_state:
    st.session_state.selected_prompt = ""

if 'submitted_prompt' not in st.session_state:
    st.session_state.submitted_prompt = ""

# Enhanced input field styling
st.markdown("""
<div style="
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    padding: 20px;
    border-radius: 15px;
    margin: 20px 0;
    text-align: center;
    color: white;
    box-shadow: 0 8px 16px rgba(0, 0, 0, 0.1);
">
    <h3 style="margin: 0; font-size: 1.8em;">🔍 Ask Your NFL Question</h3>
    <p style="margin: 10px 0 0 0; font-size: 1.1em; opacity: 0.9;">Get instant analysis on any NFL player, team, or stat</p>
</div>
""", unsafe_allow_html=True)

# Create a form to handle submission properly
with st.form(key="query_form", clear_on_submit=False):
    user_prompt = st.text_input(
        "",
        placeholder="e.g., What were the stats for Patrick Mahomes last season?",
        value=st.session_state.selected_prompt,
        help="Ask about any NFL player stats, team performance, weekly data, or league standings"
    )
    
    col1, col2 = st.columns([1, 4])
    with col1:
        submit_button = st.form_submit_button("� Analyze", use_container_width=True, type="primary")
    with col2:
        if st.form_submit_button("🗑️ Clear", use_container_width=True):
            st.session_state.selected_prompt = ""
            st.session_state.submitted_prompt = ""
            st.rerun()

# Process form submission
if submit_button and user_prompt.strip():
    st.session_state.submitted_prompt = user_prompt.strip()
elif submit_button and not user_prompt.strip():
    st.warning("⚠️ Please enter a question before clicking Analyze!")

# --- RECOMMENDATION BUTTONS ---
st.markdown("""
<div style="
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    padding: 15px;
    border-radius: 15px;
    margin: 20px 0;
    text-align: center;
    color: white;
    box-shadow: 0 6px 12px rgba(0, 0, 0, 0.1);
">
    <h3 style="margin: 0; font-size: 1.5em;">💡 Popular NFL Searches</h3>
    <p style="margin: 5px 0 0 0; opacity: 0.9;">Click any button below for instant analysis</p>
</div>
""", unsafe_allow_html=True)

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("**🏆 Star Players**")
    if st.button("📊 Patrick Mahomes Stats", use_container_width=True):
        st.session_state.selected_prompt = "What are Patrick Mahomes' stats for the 2024 season?"
        st.session_state.submitted_prompt = "What are Patrick Mahomes' stats for the 2024 season?"
        st.rerun()
    if st.button("🏃 Josh Allen Performance", use_container_width=True):
        st.session_state.selected_prompt = "Show me Josh Allen's performance this season"
        st.session_state.submitted_prompt = "Show me Josh Allen's performance this season"
        st.rerun()
    if st.button("🎯 Lamar Jackson Analysis", use_container_width=True):
        st.session_state.selected_prompt = "Give me a comprehensive analysis of Lamar Jackson"
        st.session_state.submitted_prompt = "Give me a comprehensive analysis of Lamar Jackson"
        st.rerun()
    if st.button("🔥 Dak Prescott Stats", use_container_width=True):
        st.session_state.selected_prompt = "How has Dak Prescott been performing this year?"
        st.session_state.submitted_prompt = "How has Dak Prescott been performing this year?"
        st.rerun()

with col2:
    st.markdown("**🏈 Team & League Info**")
    if st.button("🦅 Eagles Team Info", use_container_width=True):
        st.session_state.selected_prompt = "Tell me about the Philadelphia Eagles team"
        st.session_state.submitted_prompt = "Tell me about the Philadelphia Eagles team"
        st.rerun()
    if st.button("📈 AFC Standings", use_container_width=True):
        st.session_state.selected_prompt = "Show me the current AFC standings for 2025"
        st.session_state.submitted_prompt = "Show me the current AFC standings for 2025"
        st.rerun()
    if st.button("🏆 Chiefs Season Stats", use_container_width=True):
        st.session_state.selected_prompt = "What are the Kansas City Chiefs' season statistics?"
        st.session_state.submitted_prompt = "What are the Kansas City Chiefs' season statistics?"
        st.rerun()
    if st.button("🔥 Bills vs Chiefs Comparison", use_container_width=True):
        st.session_state.selected_prompt = "Compare the Buffalo Bills and Kansas City Chiefs teams"
        st.session_state.submitted_prompt = "Compare the Buffalo Bills and Kansas City Chiefs teams"
        st.rerun()

with col3:
    st.markdown("**⭐ Rising Stars & Legends**")
    if st.button("🌟 C.J. Stroud Stats", use_container_width=True):
        st.session_state.selected_prompt = "Enter your search criteria here!"
        st.session_state.submitted_prompt = "Enter your search criteria here!"
        st.rerun()
    if st.button("💨 Tyreek Hill Analysis", use_container_width=True):
        st.session_state.selected_prompt = "Show me Tyreek Hill's receiving stats"
        st.session_state.submitted_prompt = "Show me Tyreek Hill's receiving stats"
        st.rerun()
    if st.button("🛡️ Aaron Donald Performance", use_container_width=True):
        st.session_state.selected_prompt = "Give me Aaron Donald's defensive stats"
        st.session_state.submitted_prompt = "Give me Aaron Donald's defensive stats"
        st.rerun()
    if st.button("⚡ Cooper Kupp Stats", use_container_width=True):
        st.session_state.selected_prompt = "What are Cooper Kupp's receiving statistics?"
        st.session_state.submitted_prompt = "What are Cooper Kupp's receiving statistics?"
        st.rerun()

st.markdown("---")

# Only process when user has submitted a query
if st.session_state.get('submitted_prompt'):
    with st.spinner("Analyzing your request and generating report..."):
        try:
            # Add context to the prompt to guide Gemini's behavior
            context_prompt = (
                "You are a top-tier NFL analyst with access to comprehensive NFL data. Your task is to analyze the user's question and use the appropriate tools:\n"
                "\n"
                "PLAYER ANALYSIS TOOLS:\n"
                "- `get_player_stats_from_api` - Basic player info, team, position, and stats\n"
                "- `get_player_stats_only` - Just statistical data for a player\n" 
                "- `get_comprehensive_player_analysis` - Complete analysis including season stats, advanced metrics, injury status, and team info\n"
                "- `get_nfl_player_weekly_stats` - Get player stats for specific weeks (USE THIS for week 1, week 2, etc. questions)\n"
                "\n"
                "TEAM & LEAGUE TOOLS:\n"
                "- `get_nfl_teams` - Get team information, filter by division or conference\n"
                "- `get_nfl_standings` - Get standings for any season\n"
                "- `get_nfl_season_stats` - Comprehensive season statistics with filtering\n"
                "- `get_nfl_games` - Get game schedules, matchups, and weekly game data\n"
                "\n"
                "TOOL SELECTION GUIDELINES:\n"
                "- For basic player questions → use `get_player_stats_from_api`\n"
                "- For in-depth player analysis → use `get_comprehensive_player_analysis`\n"
                "- For WEEKLY DATA (week 1, week 2, etc.) → use `get_nfl_player_weekly_stats`\n"
                "- For team comparisons → use `get_nfl_teams` and `get_nfl_season_stats`\n"
                "- For standings/rankings → use `get_nfl_standings`\n"
                "- For game schedules/matchups → use `get_nfl_games`\n"
                "\n"
                "DATA PRESENTATION REQUIREMENTS:\n"
                "- ALWAYS format statistical data as markdown tables with proper headers\n"
                "- Use emojis and formatting to make data visually appealing (🏈 📊 🎯 ⭐ 🔥 💪 🏃‍♂️ 🛡️ etc.)\n"
                "- Create separate tables for different stat categories (passing, rushing, receiving, defense)\n"
                "- Include season year prominently in table headers\n"
                "- Sort data by most relevant metrics (recent season first, highest stats, etc.)\n"
                "- Add summary insights and key highlights after each table\n"
                "- Use bold formatting for standout numbers and achievements\n"
                "- Include comparative context (league averages, rankings, etc.) when relevant\n"
                "\n"
                "VISUAL FORMATTING EXAMPLES:\n"
                "```\n"
                "## 🏈 Patrick Mahomes - 2024 Season Stats\n"
                "\n"
                "### 📊 Passing Statistics\n"
                "| Stat | Value | Rank |\n"
                "|------|-------|------|\n"
                "| **Passing Yards** | **4,183** | 🥇 #1 |\n"
                "| **Touchdowns** | **31** | 🥈 #2 |\n"
                "| **Completion %** | **67.8%** | 🥉 #3 |\n"
                "\n"
                "### 🎯 Key Highlights\n"
                "- 🔥 **Elite Performance**: Led league in passing yards\n"
                "- ⭐ **Consistency**: 67.8% completion rate shows accuracy\n"
                "```\n"
                "\n"
                "The Ball Don't Lie NFL API contains comprehensive data prioritizing 2025 (current season), 2024, and 2023 seasons. "
                "Always mention which seasons the statistics are from. If recent data (2025/2024/2023) is available, highlight that. "
                "Create comprehensive data tables with relevant NFL statistics and sort by season (most recent first). "
                "NOTE: This app is optimized for the 60 requests/minute rate limit with intelligent caching and request optimization. "
                f"\nUser Question: {st.session_state.submitted_prompt}"
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
                        elif function_call.name == "get_comprehensive_player_analysis":
                            tool_output = get_comprehensive_player_analysis(
                                firstName=function_call.args['firstName'],
                                lastName=function_call.args['lastName']
                            )
                        elif function_call.name == "get_nfl_teams":
                            teams_data = get_nfl_teams(
                                division=function_call.args.get('division'),
                                conference=function_call.args.get('conference')
                            )
                            tool_output = json.dumps(teams_data)
                        elif function_call.name == "get_nfl_standings":
                            standings_data = get_nfl_standings(
                                season=function_call.args['season']
                            )
                            tool_output = json.dumps(standings_data)
                        elif function_call.name == "get_nfl_season_stats":
                            season_stats_data = get_nfl_season_stats(
                                season=function_call.args['season'],
                                player_ids=function_call.args.get('player_ids'),
                                team_id=function_call.args.get('team_id'),
                                postseason=function_call.args.get('postseason')
                            )
                            tool_output = json.dumps(season_stats_data)

                        else:
                            tool_output = json.dumps({"error": f"Unknown function: {function_call.name}"})

                        status.update(label=f"Received NFL data from Ball Don't Lie API for {function_call.args.get('firstName')} {function_call.args.get('lastName')}!", state="complete")
                        
                    with st.status("Sending data back to Gemini for analysis...", expanded=True) as status:
                        # Generate final response with the tool output data
                        final_prompt = f"""
                        Based on the user's question: "{st.session_state.submitted_prompt}"
                        
                        And the following NFL data:
                        {tool_output}
                        
                        Please provide a comprehensive analysis with the following formatting requirements:
                        
                        1. **VISUAL PRESENTATION**: Use emojis, headers, and markdown formatting extensively
                        2. **DATA TABLES**: Present ALL statistical data in well-formatted markdown tables
                        3. **TABLE STRUCTURE**: Include headers, proper alignment, and use | separators
                        4. **HIGHLIGHT KEY STATS**: Use **bold** for standout numbers and achievements
                        5. **SEASONAL ORGANIZATION**: Group data by season with clear headers (🏈 2025 Season, 📊 2024 Season, etc.)
                        6. **PERFORMANCE INSIGHTS**: Add bullet points with key takeaways after each table
                        7. **COMPARATIVE CONTEXT**: Include rankings, percentiles, or league context when possible
                        8. **EMOJI USAGE**: Use relevant sports emojis (🏈 📊 🎯 ⭐ 🔥 💪 🏃‍♂️ 🛡️ 🥇 🥈 🥉) throughout
                        
                        EXAMPLE TABLE FORMAT:
                        ```
                        ## 🏈 [Player Name] - [Season] Statistics
                        
                        ### 📊 [Category] Stats
                        | Statistic | Value | Notes |
                        |-----------|-------|-------|
                        | **Yards** | **X,XXX** | 🔥 Season High |
                        | **TDs** | **XX** | ⭐ Elite Level |
                        
                        ### 🎯 Key Performance Highlights
                        - 🏆 **Achievement 1**: Description
                        - 💪 **Strength**: Analysis
                        - 📈 **Trend**: Insight
                        ```
                        
                        Make the analysis engaging, informative, and visually rich. Answer the user's specific question comprehensively.
                        """
                        
                        response_with_tool_output = model.generate_content(
                            final_prompt,
                            generation_config=generation_config
                        )
                        status.update(label="Report generated!", state="complete")

                    st.markdown("---")
                    
                    # Enhanced header with styling
                    st.markdown("""
                    <div style="
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        padding: 20px;
                        border-radius: 15px;
                        margin: 20px 0;
                        text-align: center;
                        color: white;
                        box-shadow: 0 8px 16px rgba(0, 0, 0, 0.1);
                    ">
                        <h2 style="margin: 0; font-size: 2em;">📊 NFL Analysis Report</h2>
                        <p style="margin: 10px 0 0 0; font-size: 1.1em; opacity: 0.9;">Comprehensive data analysis powered by Ball Don't Lie API</p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Display the user's question in a styled info box
                    st.markdown(f"""
                    <div style="
                        background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%);
                        padding: 15px;
                        border-radius: 10px;
                        border-left: 5px solid #667eea;
                        margin: 15px 0;
                    ">
                        <strong>🔍 Your Question:</strong> {st.session_state.submitted_prompt}
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Clear the submitted prompt after processing to prevent re-running
                    processed_prompt = st.session_state.submitted_prompt
                    st.session_state.submitted_prompt = ""
                    
                    # Safely access the response text
                    try:
                        if response_with_tool_output.candidates and response_with_tool_output.candidates[0].content.parts:
                            response_text = ""
                            for part in response_with_tool_output.candidates[0].content.parts:
                                if hasattr(part, 'text'):
                                    response_text += part.text
                            
                            if response_text:
                                # Display the response in a styled container
                                with st.container():
                                    st.markdown("""
                                    <div style="
                                        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
                                        padding: 25px;
                                        border-radius: 15px;
                                        margin: 20px 0;
                                        border: 1px solid rgba(102, 126, 234, 0.2);
                                        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                                    ">
                                    """, unsafe_allow_html=True)
                                    
                                    st.markdown(response_text)
                                    
                                    st.markdown("</div>", unsafe_allow_html=True)
                                    
                                # Add a footer with additional info
                                st.markdown("""
                                <div style="
                                    text-align: center;
                                    padding: 15px;
                                    margin-top: 20px;
                                    background: rgba(102, 126, 234, 0.1);
                                    border-radius: 10px;
                                    font-size: 0.9em;
                                    color: #666;
                                ">
                                    📊 <strong>Data Source:</strong> Ball Don't Lie NFL API | 
                                    🤖 <strong>Analysis:</strong> Google Gemini AI | 
                                    ⚡ <strong>Optimized:</strong> Smart caching & rate limiting
                                </div>
                                """, unsafe_allow_html=True)
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

# --- TECHNICAL DASHBOARD (Bottom of Page) ---
st.markdown("---")
st.markdown("---")

with st.expander("⚙️ Technical Dashboard - API Rate Limiting & System Info", expanded=False):
    st.markdown("### 📊 API Rate Limiting Dashboard")
    current_time = time.time()
    recent_calls = [call_time for call_time in st.session_state.api_call_times if current_time - call_time < 60]
    calls_remaining = 60 - len(recent_calls)

    col1, col2, col3 = st.columns(3)
    with col1:
        # Color code based on usage
        delta_color = "normal" if len(recent_calls) < 30 else "inverse"
        st.metric(
            "🔥 API Calls (Last Minute)", 
            len(recent_calls), 
            delta=f"of 60 max",
            delta_color=delta_color,
            help="Number of API calls made in the last 60 seconds"
        )
    with col2:
        # Color code remaining calls
        remaining_color = "normal" if calls_remaining > 20 else "inverse"
        st.metric(
            "⚡ Calls Remaining", 
            calls_remaining, 
            delta=f"{round((calls_remaining/60)*100)}% available",
            delta_color=remaining_color,
            help="Remaining API calls before rate limit"
        )
    with col3:
        cache_size = len(st.session_state.api_cache)
        st.metric(
            "📋 Cached Responses", 
            cache_size, 
            delta="saves API calls",
            help="Number of cached API responses (reduces future calls)"
        )

    # Visual status indicators
    if calls_remaining < 10:
        st.error(f"🚨 **CRITICAL**: Only {calls_remaining} API calls remaining this minute! The app will automatically wait to avoid rate limits.")
    elif calls_remaining < 20:
        st.warning(f"⚠️ **WARNING**: {calls_remaining} API calls remaining this minute. Consider using cached data.")
    elif calls_remaining < 40:
        st.info(f"🟡 **MODERATE**: {calls_remaining} API calls remaining this minute.")
    else:
        st.success(f"🟢 **HEALTHY**: {calls_remaining} API calls remaining this minute. Ready for queries!")
    
    st.markdown("### 🔧 System Information")
    st.info("""
    **Rate Limiting**: 60 requests per minute with intelligent caching  
    **Cache Duration**: 5 minutes per response  
    **API Source**: Ball Don't Lie NFL API  
    **AI Analysis**: Google Gemini 1.5 Flash  
    **Optimization**: Smart request batching and response caching
    """)

# Footer
st.markdown("""
<div style="
    text-align: center;
    padding: 20px;
    margin-top: 30px;
    background: rgba(102, 126, 234, 0.05);
    border-radius: 10px;
    border-top: 2px solid rgba(102, 126, 234, 0.2);
    font-size: 0.9em;
    color: #666;
">
    🏈 <strong>NFL Player Analyst</strong> | 
    📊 Powered by Ball Don't Lie API & Google Gemini | 
    ⚡ Optimized for performance with smart caching
</div>
""", unsafe_allow_html=True)
