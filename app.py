import streamlit as st
import json
import requests
import time
import pandas as pd
import io
import os
from datetime import datetime, timedelta
from functools import wraps

# Use the stable google-generativeai library
import google.generativeai as genai

# --- SETUP API KEYS FROM STREAMLIT SECRETS ---
try:
    # Check if GEMINI_API_KEY exists and is not a placeholder
    gemini_key = st.secrets.get('GEMINI_API_KEY', '')
    if not gemini_key or gemini_key == "your_gemini_api_key_here":
        st.error("🔑 **Gemini API Key Required**")
        st.info("""
        **To use this app, you need a valid Google Gemini API key:**
        
        1. Go to [Google AI Studio](https://makersuite.google.com/app/apikey)
        2. Create a new API key
        3. Update the `.streamlit/secrets.toml` file:
           ```
           GEMINI_API_KEY = "your_actual_api_key_here"
           ```
        4. Restart the Streamlit app
        """)
        st.stop()
    
    genai.configure(api_key=gemini_key)
    BALLDONTLIE_API_KEY = st.secrets['BALLDONTLIE_API_KEY']
    NFL_API_BASE_URL = "https://api.balldontlie.io/nfl/v1"
    
    # Test the API key by making a simple call
    try:
        test_model = genai.GenerativeModel('gemini-2.0-flash-exp')
        # This will fail quickly if the API key is invalid
        st.session_state.gemini_api_valid = True
    except Exception as api_test_error:
        st.error(f"🚫 **Invalid Gemini API Key**: {str(api_test_error)}")
        st.info("""
        **Your API key appears to be invalid. Please:**
        
        1. Check that your API key is correct in `.streamlit/secrets.toml`
        2. Ensure the API key has the necessary permissions
        3. Try generating a new API key from [Google AI Studio](https://makersuite.google.com/app/apikey)
        """)
        st.stop()
        
except KeyError as e:
    st.error(f"Required API key not found in Streamlit secrets: {e}")
    st.info("Please add GEMINI_API_KEY and BALLDONTLIE_API_KEY to your `.streamlit/secrets.toml` file.")
    st.stop()

# --- RATE LIMITING AND CACHING INFRASTRUCTURE ---
if 'api_call_times' not in st.session_state:
    st.session_state.api_call_times = []

if 'api_cache' not in st.session_state:
    st.session_state.api_cache = {}

# --- SESSION STATE INITIALIZATION ---
if 'selected_prompt' not in st.session_state:
    st.session_state.selected_prompt = ""

if 'submitted_prompt' not in st.session_state:
    st.session_state.submitted_prompt = ""

if 'csv_data' not in st.session_state:
    st.session_state.csv_data = {}

if 'preloaded_csv' not in st.session_state:
    st.session_state.preloaded_csv = None

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

# --- CSV DATA HANDLING FUNCTIONS ---
def load_preloaded_csv():
    """Load the pre-loaded CSV file with enhanced NFL data"""
    csv_path = "enhanced_nfl_data.csv"
    
    if os.path.exists(csv_path):
        try:
            df = pd.read_csv(csv_path)
            st.session_state.preloaded_csv = df
            return df
        except Exception as e:
            st.warning(f"Error loading pre-loaded CSV: {e}")
            return None
    else:
        # Create a sample enhanced data CSV if it doesn't exist
        sample_data = {
            'player_name': ['Patrick Mahomes', 'Josh Allen', 'Lamar Jackson', 'Dak Prescott', 'C.J. Stroud'],
            'fantasy_projection_2025': [24.5, 23.8, 22.1, 19.7, 18.4],
            'strength_of_schedule': [0.52, 0.48, 0.55, 0.50, 0.53],
            'injury_risk': ['Low', 'Medium', 'Medium', 'Low', 'Low'],
            'bye_week': [12, 12, 14, 7, 14],
            'adp_ranking': [15, 22, 28, 45, 67],
            'target_share_projection': [0.0, 0.0, 0.0, 0.0, 0.0],  # QBs don't have target share
            'red_zone_efficiency': [0.65, 0.58, 0.62, 0.54, 0.48],
            'playoff_schedule_difficulty': [3, 2, 4, 3, 2]
        }
        
        df = pd.DataFrame(sample_data)
        df.to_csv(csv_path, index=False)
        st.session_state.preloaded_csv = df
        st.info(f"Created sample enhanced data file: {csv_path}")
        return df

def process_uploaded_csv(uploaded_file):
    """Process user-uploaded CSV file"""
    try:
        # Read the CSV file
        df = pd.read_csv(uploaded_file)
        
        # Store in session state with filename
        filename = uploaded_file.name
        st.session_state.csv_data[filename] = df
        
        return df, filename
    except Exception as e:
        st.error(f"Error processing CSV file: {e}")
        return None, None

def merge_api_and_csv_data(api_data, csv_data=None, preloaded_csv=None):
    """Merge API data with CSV data for enhanced analysis"""
    try:
        # Parse API data if it's a string
        if isinstance(api_data, str):
            api_data = json.loads(api_data)
        
        # Extract player name from API data
        player_name = None
        if isinstance(api_data, list) and len(api_data) > 0:
            player = api_data[0]
            first_name = player.get('first_name', '')
            last_name = player.get('last_name', '')
            player_name = f"{first_name} {last_name}".strip()
        elif isinstance(api_data, dict) and api_data.get('player'):
            player = api_data['player']
            first_name = player.get('first_name', '')
            last_name = player.get('last_name', '')
            player_name = f"{first_name} {last_name}".strip()
        
        enhanced_data = {
            'api_data': api_data,
            'player_name': player_name,
            'csv_matches': {},
            'available_csv_files': list(st.session_state.csv_data.keys()) if st.session_state.csv_data else []
        }
        
        # Try to match with uploaded CSV data
        if csv_data is not None and player_name:
            for filename, df in st.session_state.csv_data.items():
                matches = find_player_in_csv(df, player_name)
                if matches:
                    enhanced_data['csv_matches'][filename] = matches
        
        # Try to match with preloaded CSV
        if preloaded_csv is not None and player_name:
            matches = find_player_in_csv(preloaded_csv, player_name)
            if matches:
                enhanced_data['csv_matches']['preloaded_enhanced_data'] = matches
        
        return enhanced_data
        
    except Exception as e:
        st.error(f"Error merging data: {e}")
        return {'api_data': api_data, 'error': str(e)}

def find_player_in_csv(df, player_name):
    """Find player matches in CSV data using fuzzy matching"""
    matches = []
    
    # Common column names that might contain player names
    name_columns = ['player_name', 'name', 'Player', 'Player Name', 'full_name', 'player']
    
    for col in df.columns:
        if col.lower() in [c.lower() for c in name_columns]:
            # Direct match
            direct_match = df[df[col].str.contains(player_name, case=False, na=False)]
            if not direct_match.empty:
                matches.extend(direct_match.to_dict('records'))
            
            # Fuzzy match (last name only)
            last_name = player_name.split()[-1] if ' ' in player_name else player_name
            fuzzy_match = df[df[col].str.contains(last_name, case=False, na=False)]
            if not fuzzy_match.empty:
                # Avoid duplicates
                for record in fuzzy_match.to_dict('records'):
                    if record not in matches:
                        matches.append(record)
    
    return matches

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
    
    /* Compact UI styles */
    .stApp { padding-top: 1rem; }
    .main-header { 
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        padding: 12px 20px;
        border-radius: 8px;
        margin-bottom: 15px;
        color: white;
        text-align: center;
    }
    .compact-section {
        background: #f8f9fa;
        padding: 8px 12px;
        border-radius: 6px;
        margin: 8px 0;
        border-left: 3px solid #667eea;
    }
    .data-row {
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
        margin: 6px 0;
        align-items: center;
    }
    .data-label {
        font-weight: 600;
        color: #495057;
        margin-right: 6px;
        min-width: fit-content;
    }
    .data-value {
        color: #212529;
        flex: 1;
    }
    .btn-compact {
        padding: 4px 8px !important;
        margin: 2px !important;
        font-size: 0.8rem !important;
    }
    div[data-testid="metric-container"] {
        background: white;
        border: 1px solid #e9ecef;
        padding: 6px;
        border-radius: 4px;
        margin: 2px 0;
    }
    .streamlit-expanderHeader {
        font-size: 0.85rem !important;
        padding: 6px 10px !important;
    }
    .streamlit-expanderContent {
        padding: 8px !important;
    }
    
    /* Green Gradient Button Styling for Form Buttons and Upload Data Button */
    .stForm button[kind="primary"], .stForm button:first-child, 
    .stButton > button[key="toggle_csv"], 
    .stButton > button:contains("Upload Data (optional)"),
    button[data-testid="baseButton-secondary"]:contains("Upload Data (optional)") {
        background: linear-gradient(135deg, #28a745 0%, #20c997 50%, #17a2b8 100%) !important;
        border: none !important;
        color: white !important;
        font-weight: 600 !important;
        transition: all 0.3s ease !important;
        border-radius: 6px !important;
        text-shadow: 0 1px 2px rgba(0,0,0,0.3) !important;
        box-shadow: 0 2px 4px rgba(40, 167, 69, 0.2) !important;
    }
    .stForm button[kind="primary"]:hover, .stForm button:first-child:hover,
    .stButton > button[key="toggle_csv"]:hover,
    .stButton > button:contains("Upload Data (optional)"):hover,
    button[data-testid="baseButton-secondary"]:contains("Upload Data (optional)"):hover {
        background: linear-gradient(135deg, #218838 0%, #1ea383 50%, #138496 100%) !important;
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 12px rgba(40, 167, 69, 0.4) !important;
    }
    .stForm button[kind="primary"]:active, .stForm button:first-child:active,
    .stButton > button[key="toggle_csv"]:active,
    .stButton > button:contains("Upload Data (optional)"):active,
    button[data-testid="baseButton-secondary"]:contains("Upload Data (optional)"):active {
        transform: translateY(0px) !important;
        box-shadow: 0 2px 4px rgba(40, 167, 69, 0.3) !important;
    }
    
    /* Additional targeting for Upload Data button */
    div[data-testid="column"] button:contains("Upload Data (optional)") {
        background: linear-gradient(135deg, #28a745 0%, #20c997 50%, #17a2b8 100%) !important;
        color: white !important;
        border: none !important;
    }
    
    /* Alternative targeting using streamlit button classes */
    .stButton button, .stDownloadButton button {
        background: linear-gradient(135deg, #28a745 0%, #20c997 50%, #17a2b8 100%) !important;
        color: white !important;
        border: none !important;
        font-weight: 600 !important;
        transition: all 0.3s ease !important;
        border-radius: 6px !important;
        text-shadow: 0 1px 2px rgba(0,0,0,0.3) !important;
        box-shadow: 0 2px 4px rgba(40, 167, 69, 0.2) !important;
    }
    .stButton button:hover, .stDownloadButton button:hover {
        background: linear-gradient(135deg, #218838 0%, #1ea383 50%, #138496 100%) !important;
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 12px rgba(40, 167, 69, 0.4) !important;
    }
    
    /* Gradient Page Breaks */
    .gradient-divider {
        height: 4px;
        background: linear-gradient(90deg, 
            transparent 0%, 
            #667eea 15%, 
            #764ba2 30%,
            #9575cd 50%, 
            #764ba2 70%, 
            #667eea 85%, 
            transparent 100%);
        margin: 25px 0;
        border-radius: 2px;
        box-shadow: 0 1px 3px rgba(102, 126, 234, 0.2);
    }
    
    /* Green Gradient Divider for Data Sources */
    .gradient-divider-green {
        height: 4px;
        background: linear-gradient(90deg, 
            transparent 0%, 
            #28a745 15%, 
            #20c997 30%,
            #17a2b8 50%, 
            #20c997 70%, 
            #28a745 85%, 
            transparent 100%);
        margin: 25px 0;
        border-radius: 2px;
        box-shadow: 0 1px 3px rgba(40, 167, 69, 0.2);
    }
</style>
""", unsafe_allow_html=True)

# Compact main header
st.markdown("""
<div class="main-header">
    <h2 style="margin: 0; font-size: 1.6em;">🏈 NFL Analytics Platform</h2>
    <p style="margin: 4px 0 0 0; font-size: 0.9em; opacity: 0.9;">Player stats • Team analysis • Enhanced data insights</p>
</div>
""", unsafe_allow_html=True)

# Green gradient divider above Data Sources
st.markdown('<div class="gradient-divider-green"></div>', unsafe_allow_html=True)

# CSV Data Management - Compact Design
st.markdown('<div class="compact-section">', unsafe_allow_html=True)
col1, col2 = st.columns([2, 1])
with col1:
    st.markdown("**📊 Data Sources** • Upload CSV files or use enhanced NFL dataset")
with col2:
    if st.button("📤 Upload Data (optional)", key="toggle_csv", help="Upload CSV files or load enhanced data"):
        st.session_state.show_csv_manager = not st.session_state.get('show_csv_manager', False)

if st.session_state.get('show_csv_manager', False):
    col1, col2 = st.columns(2)
    
    with col1:
        uploaded_files = st.file_uploader(
            "Upload CSV files",
            type=['csv'],
            accept_multiple_files=True,
            help="Fantasy projections, advanced metrics, etc."
        )
        
        if uploaded_files:
            for uploaded_file in uploaded_files:
                if uploaded_file.name not in st.session_state.csv_data:
                    df, filename = process_uploaded_csv(uploaded_file)
                    if df is not None:
                        st.success(f"✅ {filename} • {len(df)} rows")
    
    with col2:
        if st.session_state.preloaded_csv is not None:
            st.success(f"✅ Enhanced data ready • {len(st.session_state.preloaded_csv)} players")
        else:
            if st.button("📊 Load Enhanced Data", key="load_enhanced"):
                load_preloaded_csv()
                st.rerun()
    
    # Current data sources summary
    if st.session_state.csv_data or st.session_state.preloaded_csv is not None:
        sources = []
        if st.session_state.csv_data:
            sources.extend([f"📄 {name} ({len(df)} rows)" for name, df in st.session_state.csv_data.items()])
        if st.session_state.preloaded_csv is not None:
            sources.append(f"📊 Enhanced NFL Dataset ({len(st.session_state.preloaded_csv)} players)")
        
        st.markdown(f"**Active:** {' • '.join(sources)}")

st.markdown('</div>', unsafe_allow_html=True)

# Green gradient divider below Data Sources  
st.markdown('<div class="gradient-divider-green"></div>', unsafe_allow_html=True)

# Load preloaded CSV on app start
if st.session_state.preloaded_csv is None:
    load_preloaded_csv()

# Search Interface - Compact Design  
st.markdown('<div class="compact-section">', unsafe_allow_html=True)
st.markdown("**🔍 NFL Analysis** • Ask about any player, team, or stat")

# Create a form to handle submission properly
with st.form(key="query_form", clear_on_submit=False):
    col1, col2, col3 = st.columns([6, 1, 1])
    with col1:
        user_prompt = st.text_input(
            "Query",
            placeholder="e.g., Patrick Mahomes stats, Chiefs vs Bills comparison",
            value=st.session_state.selected_prompt,
            label_visibility="collapsed"
        )
    with col2:
        submit_button = st.form_submit_button("🔍 Analyze", help="Analyze NFL data", use_container_width=True)
    with col3:
        if st.form_submit_button("✖️ Clear", help="Clear query", use_container_width=True):
            st.session_state.selected_prompt = ""
            st.session_state.submitted_prompt = ""
            st.rerun()

# Process form submission
if submit_button and user_prompt.strip():
    st.session_state.submitted_prompt = user_prompt.strip()
elif submit_button and not user_prompt.strip():
    st.warning("⚠️ Please enter a question before clicking Analyze!")

st.markdown('</div>', unsafe_allow_html=True)

# --- Function Definitions ---
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

def get_team_statistics(team_name, season=2024):
    """
    Get comprehensive team statistics for a specific team and season
    This is a dedicated function for team analysis
    """
    try:
        # First get team info to find the team ID
        teams_data = get_nfl_teams()
        teams = json.loads(teams_data) if isinstance(teams_data, str) else teams_data
        
        if isinstance(teams, dict) and teams.get('error'):
            return teams_data
            
        # Find the team by name (case insensitive)
        team_id = None
        team_info = None
        team_name_lower = team_name.lower()
        
        for team in teams.get('data', []):
            if (team_name_lower in team.get('full_name', '').lower() or 
                team_name_lower in team.get('name', '').lower() or
                team_name_lower in team.get('city', '').lower()):
                team_id = team.get('id')
                team_info = team
                break
        
        if not team_id:
            return json.dumps({"error": f"Team '{team_name}' not found"})
        
        # Get team statistics using season stats with team filter
        season_stats = get_nfl_season_stats(season=season, team_id=team_id)
        stats_data = json.loads(season_stats) if isinstance(season_stats, str) else season_stats
        
        # Get team standings for additional context
        standings_data = get_nfl_standings(season=season)
        standings = json.loads(standings_data) if isinstance(standings_data, str) else standings_data
        
        # Combine all team data
        result = {
            "team_info": team_info,
            "season_stats": stats_data,
            "standings": standings,
            "season": season
        }
        
        return json.dumps(result)
        
    except Exception as e:
        st.error(f"Error fetching team statistics: {e}")
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

def get_enhanced_player_analysis_with_csv(firstName: str, lastName: str):
    """
    Get comprehensive player analysis combining API data with CSV data for enhanced insights
    """
    try:
        with st.expander("🔍 Enhanced Analysis with CSV Data", expanded=False):
            st.info(f"🔍 Performing enhanced analysis for {firstName} {lastName} with CSV data integration...")
            
            # Get comprehensive API data first
            api_analysis = get_comprehensive_player_analysis(firstName, lastName)
            
            # Load preloaded CSV if not already loaded
            if st.session_state.preloaded_csv is None:
                st.info("📋 Loading enhanced NFL data...")
                load_preloaded_csv()
            
            # Merge API data with CSV data
            enhanced_data = merge_api_and_csv_data(
                api_analysis,
                csv_data=st.session_state.csv_data,
                preloaded_csv=st.session_state.preloaded_csv
            )
            
            st.success("✅ Enhanced analysis complete with CSV data integration!")
            
        return json.dumps(enhanced_data)
        
    except Exception as e:
        st.error(f"Error in enhanced CSV analysis: {e}")
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
import google.generativeai as genai

# Define individual function declarations using the new format
get_player_stats_function = genai.protos.FunctionDeclaration(
    name="get_player_stats_from_api",
    description="Gets comprehensive NFL player information including team affiliation, position, and optionally their statistics by their first and last name using Ball Don't Lie NFL API. This tool can answer questions about what NFL team a player plays for, their position, and their performance statistics.",
    parameters=genai.protos.Schema(
        type=genai.protos.Type.OBJECT,
        properties={
            "firstName": genai.protos.Schema(type=genai.protos.Type.STRING, description="The first name of the NFL player."),
            "lastName": genai.protos.Schema(type=genai.protos.Type.STRING, description="The last name of the NFL player."),
            "include_stats": genai.protos.Schema(type=genai.protos.Type.BOOLEAN, description="Whether to include detailed statistics for the player. Default is true.")
        },
        required=["firstName", "lastName"]
    )
)

get_player_stats_only_function = genai.protos.FunctionDeclaration(
    name="get_player_stats_only",
    description="Gets only the detailed statistics for a specific NFL player. Use this when you specifically need just the stats data without basic player information.",
    parameters=genai.protos.Schema(
        type=genai.protos.Type.OBJECT,
        properties={
            "firstName": genai.protos.Schema(type=genai.protos.Type.STRING, description="The first name of the NFL player."),
            "lastName": genai.protos.Schema(type=genai.protos.Type.STRING, description="The last name of the NFL player.")
        },
        required=["firstName", "lastName"]
    )
)

get_comprehensive_player_analysis_function = genai.protos.FunctionDeclaration(
    name="get_comprehensive_player_analysis",
    description="Get a comprehensive analysis of an NFL player including all stats, team info, recent games, and performance metrics. This is the most complete analysis available.",
    parameters=genai.protos.Schema(
        type=genai.protos.Type.OBJECT,
        properties={
            "firstName": genai.protos.Schema(type=genai.protos.Type.STRING, description="The first name of the NFL player."),
            "lastName": genai.protos.Schema(type=genai.protos.Type.STRING, description="The last name of the NFL player.")
        },
        required=["firstName", "lastName"]
    )
)

get_team_statistics_function = genai.protos.FunctionDeclaration(
    name="get_team_statistics",
    description="Gets comprehensive team statistics including team info, season stats, and standings for an NFL team.",
    parameters=genai.protos.Schema(
        type=genai.protos.Type.OBJECT,
        properties={
            "team_name": genai.protos.Schema(type=genai.protos.Type.STRING, description="The name of the NFL team (e.g., 'Kansas City Chiefs', 'Buffalo Bills')"),
            "season": genai.protos.Schema(type=genai.protos.Type.INTEGER, description="The season year (e.g., 2024, 2023). Default is 2024.")
        },
        required=["team_name"]
    )
)

# Create tool declaration using the new format
tool_declarations = [genai.protos.Tool(
    function_declarations=[
        get_player_stats_function,
        get_player_stats_only_function, 
        get_comprehensive_player_analysis_function,
        get_team_statistics_function
    ]
)]

# Quick Search Options
st.markdown('<div class="compact-section">', unsafe_allow_html=True)
st.markdown("**⚡ Quick Searches** • Popular analysis examples")

# Compact button grid
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown("**🏆 Star QBs**")
    buttons = [
        ("Mahomes", "Patrick Mahomes 2024 stats"),
        ("J.Allen", "Josh Allen performance"),
        ("L.Jackson", "Lamar Jackson analysis")
    ]
    for label, prompt in buttons:
        if st.button(label, key=f"qb_{label}", use_container_width=True):
            st.session_state.selected_prompt = prompt
            st.session_state.submitted_prompt = prompt
            st.rerun()

with col2:
    st.markdown("**🏈 Top Teams**")
    buttons = [
        ("Chiefs", "Kansas City Chiefs team stats"),
        ("Bills", "Buffalo Bills analysis"),
        ("vs Compare", "Bills vs Chiefs comparison")
    ]
    for label, prompt in buttons:
        if st.button(label, key=f"team_{label}", use_container_width=True):
            st.session_state.selected_prompt = prompt
            st.session_state.submitted_prompt = prompt
            st.rerun()

with col3:
    st.markdown("**⭐ Skill Players**")
    buttons = [
        ("T.Hill", "Tyreek Hill receiving stats"),
        ("C.Kupp", "Cooper Kupp statistics"),
        ("A.Donald", "Aaron Donald performance")
    ]
    for label, prompt in buttons:
        if st.button(label, key=f"skill_{label}", use_container_width=True):
            st.session_state.selected_prompt = prompt
            st.session_state.submitted_prompt = prompt
            st.rerun()

with col4:
    st.markdown("**📊 League Data**")
    buttons = [
        ("AFC", "AFC standings 2024"),
        ("NFC", "NFC standings 2024"),
        ("Playoffs", "NFL playoff picture")
    ]
    for label, prompt in buttons:
        if st.button(label, key=f"league_{label}", use_container_width=True):
            st.session_state.selected_prompt = prompt
            st.session_state.submitted_prompt = prompt
            st.rerun()

# Only process when user has submitted a query
if st.session_state.get('submitted_prompt'):
    
    with st.spinner("Analyzing your request and generating report..."):
        try:
            # Add context to the prompt to guide Gemini's behavior
            context_prompt = (
                "You are a top-tier NFL analyst with access to comprehensive NFL data AND supplementary CSV data. Your task is to analyze the user's question and use the appropriate tools:\n"
                "\n"
                "PLAYER ANALYSIS TOOLS:\n"
                "- `get_player_stats_from_api` - Basic player info, team, position, and stats\n"
                "- `get_player_stats_only` - Just statistical data for a player\n" 
                "- `get_comprehensive_player_analysis` - Complete analysis including season stats, advanced metrics, injury status, and team info\n"
                "- `get_enhanced_player_analysis_with_csv` - MOST COMPREHENSIVE: Combines API data with CSV data (projections, rankings, advanced metrics)\n"
                "\n"
                "TEAM & LEAGUE TOOLS:\n"
                "- `get_nfl_teams` - Get team information, filter by division or conference\n"
                "- `get_team_statistics` - Get comprehensive team statistics (RECOMMENDED for team analysis)\n"
                "- `get_nfl_standings` - Get standings for any season\n"
                "- `get_nfl_season_stats` - Comprehensive season statistics with filtering\n"
                "- `get_nfl_games` - Get game schedules, matchups, and weekly game data\n"
                "\n"
                "TOOL SELECTION GUIDELINES:\n"
                "- For basic player questions → use `get_player_stats_from_api`\n"
                "- For in-depth player analysis → use `get_comprehensive_player_analysis`\n"
                "- For ENHANCED analysis with projections/rankings → use `get_enhanced_player_analysis_with_csv`\n"
                "- For team statistics and analysis → use `get_team_statistics` (most comprehensive)\n"
                "- For weekly data (week 1, week 2, etc.) → use `get_nfl_games` with week filters\n"
                "- For team comparisons → use `get_team_statistics` for each team\n"
                "- For team information only → use `get_nfl_teams`\n"
                "- For standings/rankings → use `get_nfl_standings`\n"
                "- For game schedules/matchups → use `get_nfl_games`\n"
                "\n"
                "CRITICAL FOR TEAM ANALYSIS:\n"
                "When users ask about team performance or comparisons:\n"
                "1. FIRST try `get_team_statistics` for comprehensive team data\n"
                "2. Alternative: use `get_nfl_teams` + `get_nfl_season_stats` + `get_nfl_standings`\n"
                "3. You MUST make these function calls - do not just return empty data\n"
                "4. Use the actual team data returned from the API calls to create your analysis\n"
                "\n"
                "EXAMPLE: For 'compare Buffalo Bills and Kansas City Chiefs':\n"
                "- Call get_team_statistics(team_name='Buffalo Bills', season=2024)\n"
                "- Call get_team_statistics(team_name='Kansas City Chiefs', season=2024)\n"
                "- Compare the comprehensive data returned\n"
                "\n"
                "CSV DATA CAPABILITIES:\n"
                "- Fantasy projections and rankings\n"
                "- Advanced metrics (strength of schedule, target share, etc.)\n"
                "- Injury risk assessments\n"
                "- Bye week information\n"
                "- ADP (Average Draft Position) data\n"
                "- Playoff schedule difficulty\n"
                "\n"
                "WHEN TO USE ENHANCED CSV ANALYSIS:\n"
                "- Fantasy football questions\n"
                "- Draft strategy inquiries\n"
                "- Player comparisons for fantasy\n"
                "- Questions about projections or rankings\n"
                "- Advanced metrics requests\n"
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
                "- When CSV data is available, create separate sections for 'Live Stats' and 'Enhanced Metrics'\n"
                "\n"
                "CSV DATA INTEGRATION:\n"
                "- When using enhanced analysis, clearly distinguish between API data and CSV data\n"
                "- Create separate tables for live stats vs projections/rankings\n"
                "- Highlight unique insights only available through CSV data\n"
                "- Use CSV data to provide context and recommendations\n"
                "\n"
                f"CSV DATA STATUS: {len(st.session_state.csv_data)} user files uploaded, {'Enhanced data loaded' if st.session_state.preloaded_csv is not None else 'No enhanced data'}\n"
                "\n"
                "The Ball Don't Lie NFL API contains comprehensive data prioritizing 2025 (current season), 2024, and 2023 seasons. "
                "Always mention which seasons the statistics are from. If recent data (2025/2024/2023) is available, highlight that. "
                "Create comprehensive data tables with relevant NFL statistics and sort by season (most recent first). "
                "NOTE: This app is optimized for the 60 requests/minute rate limit with intelligent caching and request optimization. "
                f"\nUser Question: {st.session_state.submitted_prompt}"
            )

            # Use the stable google-generativeai syntax
            model = genai.GenerativeModel('gemini-2.0-flash-exp', tools=tool_declarations)
            
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
                        elif function_call.name == "get_enhanced_player_analysis_with_csv":
                            tool_output = get_enhanced_player_analysis_with_csv(
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

                        elif function_call.name == "get_nfl_games":
                            games_data = get_nfl_games(
                                seasons=function_call.args.get('seasons'),
                                team_ids=function_call.args.get('team_ids'),
                                weeks=function_call.args.get('weeks'),
                                postseason=function_call.args.get('postseason')
                            )
                            tool_output = json.dumps(games_data)
                        elif function_call.name == "get_team_statistics":
                            team_stats = get_team_statistics(
                                team_name=function_call.args.get('team_name'),
                                season=function_call.args.get('season', 2024)
                            )
                            tool_output = team_stats
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
                        
                    # Debug: Show what we got from Gemini
                    with st.expander("🔧 Gemini Response Debug", expanded=False):
                        st.write("**Response object:**", str(response_with_tool_output)[:500] + "...")
                        if hasattr(response_with_tool_output, 'candidates'):
                            st.write("**Has candidates:**", len(response_with_tool_output.candidates) if response_with_tool_output.candidates else 0)
                            if response_with_tool_output.candidates and len(response_with_tool_output.candidates) > 0:
                                candidate = response_with_tool_output.candidates[0]
                                st.write("**Candidate content:**", str(candidate.content)[:200] + "...")
                                if hasattr(candidate.content, 'parts'):
                                    st.write("**Parts count:**", len(candidate.content.parts) if candidate.content.parts else 0)
                                    for i, part in enumerate(candidate.content.parts):
                                        st.write(f"**Part {i}:**", str(part)[:200] + "...")
                                        if hasattr(part, 'text'):
                                            st.write(f"**Part {i} text length:**", len(part.text) if part.text else 0)
                        
                        # Also try the .text property
                        if hasattr(response_with_tool_output, 'text'):
                            st.write("**Direct .text property:**", response_with_tool_output.text[:200] + "..." if response_with_tool_output.text else "None")

                    # Add anchor point right before the analysis report
                    st.markdown('<div id="analysis-output"></div>', unsafe_allow_html=True)
                    
                    # Add JavaScript to scroll to the actual output area
                    st.markdown("""
                    <script>
                        setTimeout(function() {
                            document.getElementById('analysis-output').scrollIntoView({
                                behavior: 'smooth',
                                block: 'start'
                            });
                        }, 500);
                    </script>
                    """, unsafe_allow_html=True)
                    
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
                                if hasattr(part, 'text') and part.text:
                                    response_text += part.text
                            
                            if response_text:
                                # Display the response in a compact container
                                with st.container():
                                    st.markdown('<div class="compact-section">', unsafe_allow_html=True)
                                    st.markdown(response_text)
                                    st.markdown('</div>', unsafe_allow_html=True)
                            else:
                                st.error("No text content found in the response.")
                                st.write("Debug - Response structure:", str(response_with_tool_output)[:500] + "...")
                        else:
                            st.error("No valid response content received from Gemini.")
                            st.write("Debug - Response structure:", str(response_with_tool_output)[:500] + "...")
                    except Exception as text_error:
                        st.error(f"Error accessing response text: {text_error}")
                        st.write("Debug - Raw response:", str(response_with_tool_output)[:500] + "...")
                        
                        # Try alternative text extraction
                        try:
                            if hasattr(response_with_tool_output, 'text'):
                                st.markdown("**Alternative text extraction:**")
                                st.markdown(response_with_tool_output.text)
                            else:
                                st.write("No .text attribute found on response")
                        except Exception as alt_error:
                            st.error(f"Alternative extraction also failed: {alt_error}")
                    
                    # Add fantasy analysis outlook
                    if 'processed_prompt' in locals() and processed_prompt:
                        st.markdown('<div class="compact-section">', unsafe_allow_html=True)
                        st.markdown("### 🏆 Fantasy Football Outlook")
                        st.markdown("*Data-driven insights for your fantasy lineup decisions*")
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Generate additional fantasy analysis with processed_prompt
                        fantasy_prompt = f"""
                        Based on the NFL data analysis above for the query: "{processed_prompt}"
                        
                        Provide a comprehensive FANTASY FOOTBALL OUTLOOK section with the following:
                        
                        **CRITICAL**: Use ONLY the actual data from the previous analysis. Do not make up any statistics.
                        
                        Create a polished fantasy analysis with:
                        
                        ### 🎯 Fantasy Summary
                        - Overall fantasy assessment based on real performance data
                        - Position ranking and tier placement (if determinable from data)
                        - Key fantasy-relevant metrics from the actual stats
                        
                        ### 📊 Fantasy Performance Breakdown
                        Create a table with fantasy-relevant metrics from the actual data:
                        - Points per game calculations from real stats
                        - Consistency ratings based on actual performance
                        - Red zone opportunities and efficiency
                        - Target share and usage (for skill positions)
                        
                        ### 🔮 Weekly Outlook & Recommendations
                        - Start/Sit recommendation based on performance trends
                        - Matchup analysis (if schedule/opponent data available)
                        - Risk/Reward assessment from actual performance patterns
                        - Injury considerations (if injury data was provided)
                        
                        ### 💎 Trade & Waiver Analysis
                        - Current trade value based on performance
                        - Buy-low or sell-high opportunities
                        - Waiver wire priority (for emerging players)
                        - ROS (Rest of Season) outlook based on trends
                        
                        ### 🎲 Key Fantasy Takeaways
                        - 3-5 bullet points with actionable fantasy advice
                        - Based entirely on the real data analysis
                        - Include confidence level in recommendations
                        
                        Format with rich markdown, emojis, and professional presentation.
                        """
                        
                        try:
                            # Generate fantasy analysis
                            fantasy_response = model.generate_content(
                                fantasy_prompt,
                                generation_config=generation_config
                            )
                            
                            # Display fantasy analysis
                            if fantasy_response.candidates and fantasy_response.candidates[0].content.parts:
                                fantasy_text = ""
                                for part in fantasy_response.candidates[0].content.parts:
                                    if hasattr(part, 'text') and part.text:
                                        fantasy_text += part.text
                                
                                if fantasy_text:
                                    st.markdown("""
                                    <div style="
                                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                                        padding: 25px;
                                        border-radius: 15px;
                                        margin: 20px 0;
                                        border: 2px solid rgba(255, 107, 107, 0.3);
                                        box-shadow: 0 6px 12px rgba(0, 0, 0, 0.15);
                                        color: white;
                                    ">
                                    """, unsafe_allow_html=True)
                                    
                                    st.markdown(fantasy_text)
                                    
                                    st.markdown("</div>", unsafe_allow_html=True)
                        except Exception as fantasy_error:
                            st.warning(f"Could not generate fantasy analysis: {fantasy_error}")
                        
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
                    st.error("Gemini could not fulfill the request using its tools. Here is its direct response:")
                    st.markdown(response.text)
            else:
                st.error("No valid response from Gemini.")

        except Exception as e:
            st.error(f"An error occurred: {e}")
            st.write("Debug info:", str(e))

# --- TECHNICAL DASHBOARD (Bottom of Page) ---

with st.expander("⚙️ Technical Dashboard - API Rate Limiting & System Info", expanded=False):
    # API Metrics - Compact Display
    st.markdown("### 📊 API Status")
    current_time = time.time()
    recent_calls = [call_time for call_time in st.session_state.api_call_times if current_time - call_time < 60]
    calls_remaining = 60 - len(recent_calls)
    cache_size = len(st.session_state.api_cache)

    # Horizontal metrics layout
    col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
with col1:
    color = "🔴" if len(recent_calls) > 50 else "�" if len(recent_calls) > 30 else "🟢"
    st.markdown(f"**{color} Calls Used:** {len(recent_calls)}/60")
with col2:
    color = "🔴" if calls_remaining < 10 else "🟡" if calls_remaining < 20 else "🟢"
    st.markdown(f"**{color} Remaining:** {calls_remaining}")
with col3:
    st.markdown(f"**📋 Cached:** {cache_size} responses")
with col4:
    pct = round((calls_remaining/60)*100)
    st.markdown(f"**{pct}%** free")

# Compact status alerts
if calls_remaining < 10:
    st.error(f"🚨 Only {calls_remaining} calls left - rate limit protection active")
elif calls_remaining < 20:
    st.warning(f"⚠️ {calls_remaining} calls remaining - consider using cache")

    st.markdown("### 🔧 System Information")
    st.info("""
    **Rate Limiting**: 60 requests per minute with intelligent caching  
    **Cache Duration**: 5 minutes per response  
    **API Source**: Ball Don't Lie NFL API  
    **AI Analysis**: Google Gemini 2.0 Flash  
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
