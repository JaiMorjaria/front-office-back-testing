import pandas as pd
import numpy as np
import sqlite3
from pathlib import Path

common_keys = ['player', 'team', 'age', 'pos', 'min', 'season']
conf_finals_and_up_corrected = {
    '2023-24': ['BOS', 'IND', 'DAL', 'MIN'],    
    '2022-23': ['BOS', 'MIA', 'DEN', 'LAL'],    
    '2021-22': ['BOS', 'GSW', 'MIA', 'DAL'],    
    '2020-21': ['MIL', 'PHX', 'ATL', 'LAC'],    
    '2019-20': ['LAL', 'MIA', 'BOS', 'DEN'],    
    '2018-19': ['TOR', 'GSW', 'MIL', 'BOS'],    
    '2017-18': ['CLE', 'GSW', 'HOU', 'BOS'],    
    '2016-17': ['CLE', 'GSW', 'SAS', 'BOS'],    
    '2015-16': ['CLE', 'GSW', 'TOR', 'OKC'],    
    '2014-15': ['GSW', 'CLE', 'ATL', 'HOU'],    
    '2013-14': ['MIA', 'SAS', 'OKC', 'POR'],    
    '2012-13': ['MIA', 'SAS', 'OKC', 'MEM'],    
    '2011-12': ['MIA', 'OKC', 'LAC', 'BOS'],    
    '2010-11': ['DAL', 'MIA', 'OKC', 'MEM'],    
    '2009-10': ['LAL', 'BOS', 'PHO', 'ATL'],    
    '2008-09': ['LAL', 'ORL', 'DEN', 'NOP'],    
    '2007-08': ['BOS', 'LAL', 'HOU', 'UTA'],    
    '2006-07': ['CLE', 'DET', 'SAS', 'UTA'],    
    '2005-06': ['MIA', 'DET', 'DAL', 'PHX'],    
    '2004-05': ['DET', 'MIA', 'SAS', 'PHX'],    
    '2003-04': ['DET', 'IND', 'LAL', 'MIN']
}
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
    
    combined_df.drop(list(combined_df.filter(regex='_all_')), axis=1, inplace=True)
    combined_df.drop(list(combined_df.filter(regex='all_three')), axis=1, inplace=True)
    combined_df.drop(list(combined_df.filter(regex='all_mid')), axis=1, inplace=True)
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
    
    print(f"Found {len(rank_cols)} `stat columns to` aggregate")
    
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
        if season in conf_finals_and_up_corrected and team in conf_finals_and_up_corrected[season]:
            labels.append(1)
        else:
            labels.append(0)
    df['conf_finals_and_up'] = labels
    df.to_csv(output_csv, index=False)
    print(f"\n✓ Labeled data saved to {output_csv}")
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