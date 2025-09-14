import requests
import json
from datetime import datetime

# You will need to copy the functions get_all_players_data() and get_player_stats()
# from your app.py file into this script to run it.
# Make sure your API key is also defined here.

# --- DATA FETCHING FROM SPORTSDATA.IO ---
# IMPORTANT: Use a SportsData.io API key here
SPORTS_DATA_API_KEY = "YOUR_SPORTS_DATA_API_KEY"

# These functions are copied from your app.py for testing
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
        print(f"Error fetching all players: {e}")
        return []

def get_player_stats(selected_players, all_players):
    """
    Fetches detailed statistics for selected players by making a new API call
    for each player's stats.
    """
    player_stats_data = {}
    player_lookup = {f'{p.get("Name")} ({p.get("Team")})': p for p in all_players}

    try:
        for player_full_name in selected_players:
            player_info = player_lookup.get(player_full_name)
            if not player_info:
                continue

            player_id = player_info.get("PlayerID")
            if not player_id:
                continue

            # This is the correct endpoint for seasonal statistics
            # The year is hardcoded to 2024 for testing purposes
            stats_url = f"https://api.sportsdata.io/v3/nfl/scores/json/PlayerSeasonStatsByPlayerID/{2024}/{player_id}"
            headers = {
                'Ocp-Apim-Subscription-Key': SPORTS_DATA_API_KEY,
            }
            stats_response = requests.get(stats_url, headers=headers)
            stats_response.raise_for_status()
            stats_data = stats_response.json()

            if stats_data:
                combined_stats = {
                    "Player Name": player_info.get("Name"),
                    "Team": player_info.get("Team"),
                    "Position": player_info.get("Position"),
                    "Receptions": stats_data.get("Receptions", 0),
                    "ReceivingYards": stats_data.get("ReceivingYards", 0),
                    "ReceivingTouchdowns": stats_data.get("ReceivingTouchdowns", 0),
                    "RushingYards": stats_data.get("RushingYards", 0),
                    "RushingTouchdowns": stats_data.get("RushingTouchdowns", 0),
                    "FumblesLost": stats_data.get("FumblesLost", 0),
                }
                player_stats_data[player_full_name] = combined_stats

    except requests.exceptions.RequestException as e:
        print(f"Error fetching stats: {e}")
        return {}
    
    return player_stats_data

# Main block to run the test
if __name__ == "__main__":
    if SPORTS_DATA_API_KEY == "YOUR_SPORTS_DATA_API_KEY":
        print("Error: Please replace 'YOUR_SPORTS_DATA_API_KEY' with your actual API key.")
    else:
        print("Starting API connection test...")
        all_players = get_all_players_data()
        
        if all_players:
            # Select two players for testing
            test_players = ["DK Metcalf (SEA)", "Travis Kelce (KC)"]
            
            print(f"Testing stats for players: {test_players}")
            stats = get_player_stats(test_players, all_players)
            
            if stats:
                print("\nTest Successful! Received the following stats:")
                print(json.dumps(stats, indent=4))
            else:
                print("\nTest Failed. Could not retrieve stats for the selected players.")
        else:
            print("\nTest Failed. Could not retrieve the initial player list.")
