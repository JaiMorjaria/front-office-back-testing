import pandas as pd
import numpy as np
import sqlite3
import json
from pathlib import Path

common_keys = ['player', 'team', 'age', 'pos', 'min', 'season']
playoff_teams = {}
with open('playoff_teams.json', 'r') as f:
    playoff_teams = json.load(f)
def load_seasons_to_db(merged_csv_dir, db_path='nba_stats.db'):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS player_season_stats")

    csv_files = sorted(Path(merged_csv_dir).glob('merged_*.csv'))
    
    print(f"Found {len(csv_files)} CSV files")
    
    all_data = []
    
    for csv_file in csv_files:
        print(f"Loading {csv_file.name}...")
        
        season = csv_file.stem.replace('merged_', '')
        
        df = pd.read_csv(csv_file)

        df['season'] = season
        
        all_data.append(df)
    
    combined_df = pd.concat(all_data, ignore_index=True)
    regexes = ["_all_", "all_three", "all_mid", "2p%", "3p%", "sfld%", "ffld%", "and1%", "diff", "%_of_plays", "_freq_", "pts/play", "psa_rank"]
    
    # drop all columns matching the regexes
    for regex in regexes:
        combined_df.drop(list(combined_df.filter(regex=regex)), axis=1, inplace=True)

    shooting_zones = ['rim', 'short_mid', 'long_mid', 'corner_three', 'non_corner']
    for zone in shooting_zones:
        # use regex to find zone frequency and accuracy columns
        freq_col_regexes = [f'{zone}_frequency', f'_frequency:_{zone}']
        acc_col_regexes = [f'{zone}_accuracy', f'_team_fg%:_{zone}']
        freq_cols = []
        acc_cols = []
        
        for i in range(len(freq_col_regexes)):
            freq_col_regex = freq_col_regexes[i]
            acc_col_regex = acc_col_regexes[i]
            print(acc_col_regex)
            freq_cols += list(combined_df.filter(regex=freq_col_regex))
            acc_cols += list(combined_df.filter(regex=acc_col_regex))
            print(list(combined_df.filter(regex=acc_col_regex)))
        print(zone, freq_cols, acc_cols, "\n")
        # create zone impact column (geometric mean of frequency and accuracy) using regex to find frequency and accuracy columns
        for f_col, a_col in zip(freq_cols, acc_cols):
            impact_col_name = f"{f_col.replace('_frequency','')}_impact"
            combined_df[impact_col_name] = round(np.sqrt(combined_df[f_col] * combined_df[a_col]), 2)
            # drop the original frequency and accuracy columns
            combined_df.drop(columns=[f_col, a_col], inplace=True)
    
    combined_df.to_sql('player_season_stats', conn, if_exists='replace', index=False)
    
    cursor = conn.cursor()
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_player_season ON player_season_stats (player, season, team)")
    conn.commit()

    conn.close()
    
    combined_df.to_csv('all_player_season_stats.csv', index=False)
    return combined_df


def aggregate_to_team_level(db_path='nba_stats.db', output_csv='team_aggregated_stats.csv'):
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query("SELECT * FROM player_season_stats", conn)
    
    print(f"Loaded {len(df)} player-season records")
    
    rank_cols = [col for col in df.columns if col not in common_keys]
    
    print(f"Found {len(rank_cols)} stat columns to aggregate")
    
    teams = df['team'].unique()
    seasons = df['season'].unique()
    
    team_stats = []

    for team in teams:
        for season in seasons:
            team_season_df = df[(df['team'] == team) & (df['season'] == season)]
            team_row = {
                'Team': team,
                'Season': season,
            }
            
            total_team_minutes = team_season_df['min'].sum()
            
            for rank_col in rank_cols:
                rank_values = team_season_df[rank_col]

                max_value = rank_values.max()
                team_row[f'{rank_col}_highest'] = max_value
                
                top2_values = rank_values.nlargest(2)
                avg_top2 = round(top2_values.mean(), 2)
                team_row[f'{rank_col}_top2_avg'] = avg_top2
                
                players_with_rank = team_season_df[team_season_df[rank_col].notna()]
                
                weighted_sum = 0
                for _, player in players_with_rank.iterrows():
                    player_rank = player[rank_col]
                    player_minutes = player['min']
                    weight = player_minutes / total_team_minutes
                    weighted_sum += player_rank * weight
                    
                team_row[f'{rank_col}_weighted'] = round(weighted_sum, 2)

            team_stats.append(team_row)
    
    # Create final dataframe
    team_df = pd.DataFrame(team_stats)
    

    team_df.to_sql('team_aggregated_stats', conn, if_exists='replace', index=False)
    
    team_df.to_csv(output_csv, index=False)
    print(f"\n✓ Saved to database and {output_csv}")
    
    conn.close()
    
    return team_df

def label_df(df, output_csv='team_aggregated_stats_labeled.csv'):
    labels = []
    for _, row in df.iterrows():
        season = row['Season']
        team = row['Team']
        if team in playoff_teams[season]:
            labels.append(1)
        else:
            labels.append(0)
    df['playoffs'] = labels
    df.to_csv(output_csv, index=False)
    print(f"\nLabeled data saved to {output_csv}")
    return df

if __name__ == "__main__":
    MERGED_CSV_DIR = 'merged_csvs'  
    DB_PATH = 'nba_stats.db'

    player_df = load_seasons_to_db(MERGED_CSV_DIR, DB_PATH)
    aggregate_to_team_level()
    read_df = pd.read_csv('team_aggregated_stats.csv')
    label_df(read_df)
    duplicates = [col for col in read_df.columns if str(col)[-2] == "."]
    print(duplicates)