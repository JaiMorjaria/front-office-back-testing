import pandas as pd
import numpy as np
import sqlite3
from pathlib import Path


def load_seasons_to_db(merged_csv_dir, db_path='nba_stats.db'):
    conn = sqlite3.connect(db_path)
    
    csv_files = sorted(Path(merged_csv_dir).glob('merged_*.csv'))
    
    print(f"Found {len(csv_files)} CSV files")
    
    all_data = []
    
    for csv_file in csv_files:
        print(f"Loading {csv_file.name}...")
        
        season = csv_file.stem.replace('merged_', '')
        
        df = pd.read_csv(csv_file)
        df['Season'] = season
        
        all_data.append(df)
    
    combined_df = pd.concat(all_data, ignore_index=True)
    
    combined_df.to_sql('player_season_stats', conn, if_exists='replace', index=False)
    
    cursor = conn.cursor()
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_player_season ON player_season_stats (Player, Season, Team)")
    conn.commit()

    conn.close()
    
    combined_df.to_csv('all_player_season_stats.csv', index=False)
    return combined_df



if __name__ == "__main__":
    MERGED_CSV_DIR = 'merged_csvs'  
    DB_PATH = 'nba_stats.db'

    player_df = load_seasons_to_db(MERGED_CSV_DIR, DB_PATH)
