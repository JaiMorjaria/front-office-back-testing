import os
import glob
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
import json
from selenium.webdriver.chrome.service import Service
import pandas as pd

no_data_mapping = {}
     
def get_last_filename_and_rename(save_folder, year, new_filename, selected_season_phase):
    files = glob.glob(save_folder +  '/*.csv')
    if not files:
        return None  
    max_file = max(files, key=os.path.getctime)
    filename = max_file.split("/")[-1].split(".")[0] 
    new_path = os.path.join(save_folder, f"{str(year)}-{str(year + 1)[2:4]}\\{new_filename}_{selected_season_phase.replace(" ", "_")}.csv")
    os.rename(max_file, new_path)  
    return new_path

def download_by_year(driver, year, selected_season_phase="Regular Season", url="https://cleaningtheglass.com/stats/players"):    
    download_folder = os.getcwd() + f"\\CTG_CSV_Data"

    categories = {
        "Offensive Overview": "offensive_overview",
        "Shooting Overall": "shooting_overall",
        "Shooting Frequency": "shooting_frequency",
        "Shooting Accuracy": "shooting_accuracy",
        "Defense and Rebounding": "defense_rebounding",
        "Foul Drawing": "foul_drawing",
        "OnOff Efficiency and Four Factors": "onoff_efficiency",
        "OnOff Team Shooting Frequency": "onoff_team_shooting_frequency",
        "OnOff Team Shooting Accuracy": "onoff_team_shooting_accuracy",
        "OnOff Team Halfcourt & Putbacks": "onoff_team_halfcourt_putbacks",
        "OnOff Team Transition": "onoff_team_transition",
        "OnOff Opponent Shooting Frequency": "onoff_opponent_shooting_frequency",
        "OnOff Opponent Shooting Accuracy": "onoff_opponent_shooting_accuracy",
        "OnOff Opponent Halfcourt & Putbacks": "onoff_opponent_halfcourt_putbacks",
        "OnOff Opponent Transition": "onoff_opponent_transition"
    }

    no_data_categories = []

    for category_name, category_slug in categories.items():
        print(f"{category_name.replace(" ", "_")}_{selected_season_phase.replace(" ", "_")}.csv")
        if f"{category_name.replace(" ", "_")}_{selected_season_phase.replace(" ", "_")}.csv" in os.listdir(f"{download_folder}/{str(year)}-{str(year + 1)[2:4]}"):
            print(f"File for {category_name} already exists. Skipping download.")
            continue
        else:
            category_url = f"{url}?season={year}&stat_category={category_slug}"
            driver.get(category_url)
            try:
                dropdowns = driver.find_elements(By.CSS_SELECTOR, "div.year_nav__selector")
                season_type_select = Select(dropdowns[1].find_element(By.TAG_NAME, "select"))
                current_option = season_type_select.first_selected_option.text
                if current_option != selected_season_phase:
                    season_type_select.select_by_visible_text(selected_season_phase)
                    time.sleep(2)  # Wait for the page to update
                downloadButton = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//a[@class='download_button']"))
                )
                downloadButton.click()
                time.sleep(5) 
                downloaded_file = get_last_filename_and_rename(download_folder, year, f"{category_name.replace(' ', '_')}", selected_season_phase.replace(' ', '_'))
                if downloaded_file:
                    print(f"Renamed file: {downloaded_file}")
                else:
                    print(f"No file found for {category_name}.")
            
            except Exception as e:
                print(f"Error downloading {category_name}: {e}")
                no_data_categories.append(category_slug)
                continue

    if len(no_data_categories) > 0:
        no_data_mapping[f"{year}_{selected_season_phase.replace(' ', '_')}"] = no_data_categories

def get_ctg_data(url):
    download_folder = os.getcwd() + "\\CTG_CSV_Data"
    prefs = {
        "download.default_directory": download_folder,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    }

    options = webdriver.ChromeOptions()
    options.add_experimental_option("prefs", prefs)

    driver = webdriver.Chrome(options=options)

    driver.get(url)

    input("Press Enter after logging in and navigating to the stats page...")
    for year in range(2003, 2024):
        download_by_year(driver, year, "Regular Season")
        download_by_year(driver, year, "Playoffs")

def get_all_playoff_teams(url="https://www.basketball-reference.com/playoffs/series.html"):
    # Read all HTML tables on the page
    tables = pd.read_html(url)
    
    # The main playoff series table is the first one
    df = tables[0]
        
    # Drop completely blank rows
    df = df.dropna(how="all")
    # Clean up columns
    df.columns = [col[1] if isinstance(col, tuple) else col for col in df.columns]
    
    
    # Translation for team codes that changed
    team_translations = {
        "SEA": "OKC",
        "NJN": "BKN",
        "NOH": "NOP",
        "CHA": "CHO"
    }
    
    playoff_teams = {}
    for _, row in df.iterrows():
        if pd.isna(row["Yr"]) or row["Yr"] == "Yr" or pd.isna(row["Favorite"]) or pd.isna(row["Underdog"]):
            continue
        year_end = int(row["Yr"])
        row["Yr"] = f"{year_end - 1}-{str(year_end)[-2:]}"
        year = str(row["Yr"])
        favorite = row["Favorite"].strip()[:3]
        underdog = row["Underdog"].strip()[:3]
        
        # Normalize acronyms
        favorite = team_translations.get(favorite, favorite)
        underdog = team_translations.get(underdog, underdog)
        
        # Initialize year list if needed
        if year not in playoff_teams:
            playoff_teams[year] = set()
        
        playoff_teams[year].update([favorite, underdog])
    
    # Convert sets to sorted lists
    playoff_teams = {
        year: sorted(list(teams))
        for year, teams in playoff_teams.items() 
        if int(year[0:4]) >= 2003
        and int(year[0:4]) <= 2023
    }
    with open("playoff_teams.json", "w") as f:
        json.dump(playoff_teams, f, indent=4)

if __name__ == "__main__":
    # get_ctg_data(url = "https://cleaningtheglass.com/stats/players")
    get_all_playoff_teams(url = "https://www.basketball-reference.com/playoffs/series.html")