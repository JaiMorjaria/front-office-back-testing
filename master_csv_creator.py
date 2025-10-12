import pandas as pd
import os
from pathlib import Path

def combine_csv_files(file_list, output_file):    
    master_df = pd.DataFrame(pd.read_csv(Path("CTG_CSV_Data\\2003-04") / file_list[0]))

    for i in range(1, len(file_list)):
        file = file_list[i]
        file_path = Path("CTG_CSV_Data\\2003-04") / file
        df = pd.read_csv(file_path)
        if "_Team_" in file:
            df = df.add_prefix('Team_')
        elif "_Opponent_" in file:
            df = df.add_prefix('Opp_')
        df = df.drop(columns=[col for col in df.columns if col in master_df.columns])
        master_df = pd.concat([master_df, df], axis=1)


    # duplicate_cols = master_df.columns[master_df.columns.duplicated()]
    # print(f"Duplicate columns found: {duplicate_cols.tolist()}")
    # print(master_df.columns.tolist())
    # print(len(master_df.columns.tolist()))
    # master_df = master_df.drop(columns=duplicate_cols)
    print(f"Total columns in master dataframe: {len(master_df.columns)}")    
    master_df.to_csv(output_file, index=False)
                 
files_to_combine = [file for file in os.listdir("CTG_CSV_Data\\2003-04") if file.endswith('Regular_Season.csv')]
print(files_to_combine)
combine_csv_files(files_to_combine, "merged.csv")