import pandas as pd
import os
from pathlib import Path

def combine_csv_files(dir_path, output_file):    
    file_list = [f for f in os.listdir(dir_path) if f.endswith('_Regular_Season.csv')]
    first_file_path = Path(dir_path) / file_list[0]
    master_df = pd.DataFrame(pd.read_csv(first_file_path))
    common_keys = ['Player', 'Team', 'Age', 'Pos', 'MIN']
    shooting_common_keys = ['eFG%', 'eFG% Rank', 'FT%', 'FT% Rank']


    for i in range(1, len(file_list)):
        file = file_list[i]
        file_path = Path(dir_path) / file
        df = pd.read_csv(file_path)
        df = df.drop(columns=common_keys)
        for key in shooting_common_keys:
            if key in df.columns and key in master_df.columns:
                df = df.drop(columns=key)
        if "OnOff" in file:
            for key in shooting_common_keys:
                if key in df.columns:
                    df = df.drop(columns=key)
            if "Team" in file:
                if "Halfcourt" in file:
                    df = df.add_prefix(f"OnOff_Team_HalfCourt_")
                elif "Transition" in file:
                    df = df.add_prefix(f"OnOff_Team_Transition_")
                else:
                    df = df.add_prefix(f"OnOff_Team_")
            elif "Opp" in file:
                if "Halfcourt" in file:
                    df = df.add_prefix(f"OnOff_Opp_HalfCourt_")
                elif "Transition" in file:
                    df = df.add_prefix(f"OnOff_Opp_Transition_")
                else:
                    df = df.add_prefix(f"OnOff_Opp_")
        else:
            if "Shooting" in file:
                shooting_category = file.split('_')[1]
                df = df.rename(columns={
                    col: f"{col.replace(' Rank', '')}_{shooting_category}_Rank" if col != "eFG%" and col != "eFG% Rank" and col.endswith("Rank") else col for col in df.columns
                })
                shooting_cols_to_drop = [col for col in df.columns if col not in shooting_common_keys and not col.endswith("Rank")]
                df = df.drop(shooting_cols_to_drop, axis=1)
        master_df = pd.concat([master_df, df], axis=1)

    cols_to_keep = common_keys + [col for col in master_df.columns if col.endswith('Rank')]
    master_df = master_df[cols_to_keep]
    print(f"Total columns in master dataframe: {len(master_df.columns)}")    
    master_df.columns = master_df.columns.str.lower().str.replace(' ', '_')
    master_df.to_csv(f"merged_csvs/{output_file}", index=False)


for year in range(2003, 2024):
    season = f"{year}-{str(year+1)[-2:]}"
    dir_path = Path(f"CTG_CSV_Data\\{season}")
    if not dir_path.exists():
        print(f"Directory for season {season} does not exist. Skipping...")
        continue
    output_filename = f"merged_{season}.csv"
    combine_csv_files(dir_path, output_filename)
    print(f"Combined CSV for season {season} saved as {output_filename}")
# season = f"{2003}-{str(2003+1)[-2:]}"
# dir_path = Path(f"CTG_CSV_Data\\{season}")
# if not dir_path.exists():
#     print(f"Directory for season {season} does not exist. Skipping...")
# output_filename = f"merged_{season}.csv"
# combine_csv_files(dir_path, output_filename)
# print(f"Combined CSV for season {season} saved as {output_filename}")