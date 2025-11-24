import pandas as pd
import json, re, os, logging
from datetime import datetime
from collections import defaultdict
import ollama
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from pydantic import BaseModel
from typing import Literal

load_dotenv()
MODEL = "qwen2.5:3b"  
LOG_FILE = "trade_parser.log"
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True) if os.path.dirname(LOG_FILE) else None


logging.basicConfig(
    filename=LOG_FILE,
    filemode='w',  # overwrite each run
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)


# ============================================================================
# PYDANTIC MODELS FOR STRUCTURED OUTPUT
# ============================================================================



class Asset(BaseModel):
    type: Literal["player", "pick", "cash"]  # Enforce exact values
    name: str = None  # for players
    year: str = None  # for picks - just the year like "2004"
    round: Literal[1, 2] = None  # for picks - ONLY 1 or 2
    team: str = None  # for picks (which team's pick)
    amount: str = None  # for cash (optional)

class SimpleTransfer(BaseModel):
    """One atomic A->B transfer"""
    from_team: str
    to_team: str
    asset: Asset

class TransferList(BaseModel):
    transfers: list[SimpleTransfer]

class Player(BaseModel):
    type: str = "player"
    name: str

class Pick(BaseModel):
    type: str = "pick"
    year: str
    round: int
    team: str  # Which team owns/controls the pick

class Cash(BaseModel):
    type: str = "cash"

class Team(BaseModel):
    team: str
    sent: list[Player | Pick | Cash]
    acquired: list[Player | Pick | Cash]

class Trade(BaseModel):
    is_multi_team: bool
    num_teams: int
    teams: list[Team]

def preprocess_trade_text(text):
    """Clean up text to help the model parse it better"""
    # Remove parentheticals entirely (they're just context/noise)
    text = re.sub(r'\([^)]*\)', '', text)
    
    # Split on semicolons to isolate clauses
    clauses = [c.strip() for c in text.split(';')]
    
    # Remove "In a X-team trade," prefix - it's metadata
    clauses = [re.sub(r'^In a \d+-team trade,?\s*', '', c) for c in clauses]
    
   # Remove everything from "conditional" onwards (case-insensitive)
    cleaned_clauses = []
    for c in clauses:
        sentences = [s.strip() for s in c.split('.') if s.strip()]
        sentences = [s for s in sentences if not re.search(r'\btrade exception\b', s, flags=re.IGNORECASE)]
        c = '. '.join(sentences)
        cond_match = re.search(r'\bconditional\b', c, flags=re.IGNORECASE)
        trade_exception_match = re.search(r'\trade exception\b', c, flags=re.IGNORECASE)
        if cond_match:
            c = c[:cond_match.start()].strip()
        if trade_exception_match:
            c = c[:trade_exception_match.start()].strip()
        cleaned_clauses.append(c)
    
    cleaned_clauses = [c.rstrip('.') for c in cleaned_clauses if c and len(c) > 10]
    
    return cleaned_clauses



# ============================================================================
# SYSTEM PROMPT (OPTIMIZED FOR SMALLER MODEL)
# ============================================================================
SYSTEM_PROMPT = """Parse NBA trade clause into atomic transfers.

PATTERN: "X traded A to Y for B"
→ X sends A to Y
→ Y sends B to X

ASSETS:
- Player: {"type": "player", "name": "Full Name"}
- Pick: {"type": "pick", "year": "YYYY", "round": 1 or 2, "team": "Owner Team Name"}
- Cash: {"type": "cash"}

PICK OWNERSHIP:
"Lakers 2024 1st" → team="Los Angeles Lakers"
"their own 2024 1st" → team=TEAM_TRADING_IT
No owner mentioned → team=TEAM_TRADING_IT

IGNORE: trade exceptions, protections, conditionals

EXAMPLES:

"Hawks traded Glenn Robinson to 76ers"
→ [{"from_team": "Atlanta Hawks", "to_team": "Philadelphia 76ers", "asset": {"type": "player", "name": "Glenn Robinson"}}]

"Lakers traded cash to Wizards"
→ [{"from_team": "Los Angeles Lakers", "to_team": "Washington Wizards", "asset": {"type": "cash"}}]

"Lakers traded Nunn to Wizards for Hachimura"
→ [{"from_team": "Los Angeles Lakers", "to_team": "Washington Wizards", "asset": {"type": "player", "name": "Kendrick Nunn"}},
   {"from_team": "Washington Wizards", "to_team": "Los Angeles Lakers", "asset": {"type": "player", "name": "Rui Hachimura"}}]

"Pistons traded 2025 2nd to Knicks for cash"
→ [{"from_team": "Detroit Pistons", "to_team": "New York Knicks", "asset": {"type": "pick", "year": "2025", "round": 2, "team": "Detroit Pistons"}},
   {"from_team": "New York Knicks", "to_team": "Detroit Pistons", "asset": {"type": "cash"}}]

"Heat traded Lakers 2026 1st to Celtics"
→ [{"from_team": "Miami Heat", "to_team": "Boston Celtics", "asset": {"type": "pick", "year": "2026", "round": 1, "team": "Los Angeles Lakers"}}]

Return JSON only."""


def parse_trade_step1(trade_text: str) -> TransferList:
    """
    Step 1: Extract primitive A->B transfers from the trade text.
    Parse each clause individually for better accuracy.
    """
    
    # Preprocess to isolate clauses
    clauses = preprocess_trade_text(trade_text)
    all_transfers = [] 
    
    # Parse each clause individually
    for clause in clauses:
        clause = clause.encode('utf-8', errors='ignore').decode('utf-8')

        user_prompt = f"Parse this clause into transfers:\n{clause}"
        
        messages = [
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': user_prompt}
        ]
        
        response = ollama.chat(
            messages=messages,
            model=MODEL,
            format=TransferList.model_json_schema(),
            options={
                'num_thread': 6,      # Use CPU cores
                'temperature': 0,     # Deterministic
            }
        )

        transfer_list = TransferList.model_validate_json(response['message']['content'])
        
        # Validate and fix common errors
        valid_transfers = []
        for transfer in transfer_list.transfers:
            # Fix type errors
            if transfer.asset.type == "draft_pick":
                transfer.asset.type = "pick"
            
            # Skip if type is still invalid
            if transfer.asset.type not in ["player", "pick", "cash"]:
                logging.warning(f"Invalid asset type: {transfer.asset.type}, skipping")
                continue
            
            # Fix year format errors for picks
            if transfer.asset.type == "pick":
                if transfer.asset.year:
                    # Extract just the year number (4 digits)
                    year_match = re.search(r'(\d{4})', str(transfer.asset.year))
                    if year_match:
                        transfer.asset.year = year_match.group(1)
                    else:
                        logging.warning(f"Bad year format: {transfer.asset.year}, skipping transfer")
                        continue
                
                # Ensure round is 1 or 2
                if transfer.asset.round not in [1, 2]:
                    logging.warning(f"Invalid round: {transfer.asset.round}, skipping transfer")
                    continue
            
            valid_transfers.append(transfer)
        
        transfer_list.transfers = valid_transfers
               
        # Normalize team names immediately after parsing
        for transfer in transfer_list.transfers:
            transfer.from_team = normalize_team_name(transfer.from_team)
            transfer.to_team = normalize_team_name(transfer.to_team)
            if transfer.asset.team:
                transfer.asset.team = normalize_team_name(transfer.asset.team)
            # Default pick ownership to from_team if not specified
            elif transfer.asset.type == "pick" and not transfer.asset.team:
                transfer.asset.team = transfer.from_team
        
        all_transfers.extend(transfer_list.transfers)
    
    # Return combined transfer list
    return TransferList(transfers=all_transfers)


def normalize_team_name(team_name: str) -> str:
    """Convert full team names to 3-letter NBA abbreviations"""
    mapping = {
        # Current teams
        "atlanta hawks": "ATL",
        "boston celtics": "BOS",
        "brooklyn nets": "BKN",
        "new jersey nets": "BKN",
        "charlotte hornets": "CHA",
        "charlotte bobcats": "CHA",
        "chicago bulls": "CHI",
        "cleveland cavaliers": "CLE",
        "dallas mavericks": "DAL",
        "denver nuggets": "DEN",
        "detroit pistons": "DET",
        "golden state warriors": "GSW",
        "houston rockets": "HOU",
        "indiana pacers": "IND",
        "los angeles clippers": "LAC",
        "los angeles lakers": "LAL",
        "memphis grizzlies": "MEM",
        "miami heat": "MIA",
        "milwaukee bucks": "MIL",
        "minnesota timberwolves": "MIN",
        "new orleans pelicans": "NOP",
        "new orleans hornets": "NOP",
        "new orleans/oklahoma city hornets": "NOP",
        "new york knicks": "NYK",
        "oklahoma city thunder": "OKC",
        "seattle supersonics": "OKC",
        "orlando magic": "ORL",
        "philadelphia 76ers": "PHI",
        "phoenix suns": "PHX",
        "portland trail blazers": "POR",
        "sacramento kings": "SAC",
        "san antonio spurs": "SAS",
        "toronto raptors": "TOR",
        "utah jazz": "UTA",
        "washington wizards": "WAS",
        "washington bullets": "WAS",
    }
    
    key = team_name.lower().strip()
    return mapping.get(key, team_name.upper()[:3])


def aggregate_transfers(transfers: list[SimpleTransfer]) -> Trade:
    """Pure Python aggregation - no LLM needed!"""
    
    team_data = defaultdict(lambda: {"sent": [], "acquired": []})
    team_names = set()
    
    for transfer in transfers:
        from_team = transfer.from_team
        to_team = transfer.to_team
        
        team_names.add(from_team)
        team_names.add(to_team)
        
        # Build asset objects based on type
        if transfer.asset.type == "player":
            asset_obj = Player(name=transfer.asset.name)
        elif transfer.asset.type == "cash":
            asset_obj = Cash(amount=transfer.asset.amount)
        elif transfer.asset.type == "pick":
            asset_obj = Pick(
                year=transfer.asset.year,
                round=transfer.asset.round,
                team=transfer.asset.team or from_team  # Fallback to from_team
            )
        else:
            continue
        
        team_data[from_team]["sent"].append(asset_obj)
        team_data[to_team]["acquired"].append(asset_obj)
    
    teams = [
        Team(
            team=team,
            sent=team_data[team]["sent"],
            acquired=team_data[team]["acquired"]
        )
        for team in sorted(team_names)
    ]
    
    return Trade(
        is_multi_team=len(team_names) > 2,
        num_teams=len(team_names),
        teams=teams
    )


def validate_trade(trade: Trade) -> bool:
    """Check if trade looks valid"""
    # At least one team should have sent/acquired something
    has_activity = False
    for team in trade.teams:
        if team.sent or team.acquired:
            has_activity = True
            break
    return has_activity


def is_actual_trade(text: str) -> bool:
    """Only parse if contains 'traded'"""
    return "traded" in text.lower()


def parse_trade(trade_text: str) -> str:
    """
    Two-step parsing:
    Step 1: Extract primitive transfers (LLM)
    Step 2: Aggregate into team view (Python)
    """
    try:
        # Step 1: Let the LLM do simple extraction
        transfer_list = parse_trade_step1(trade_text)

        logging.debug(f"Got {len(transfer_list.transfers)} transfers from LLM")
        
        # Step 2: Pure Python aggregation
        trade = aggregate_transfers(transfer_list.transfers)
        
        # Step 3: Validate
        if not validate_trade(trade):
            logging.warning(f"⚠️  Trade validation failed (empty): {trade_text[:80]}...")
            return None
        
        return trade.model_dump_json(indent=2)
    except Exception as e:
        logging.error(f"Error parsing trade: {e}")
        logging.error(f"Trade text: {trade_text[:80]}...")
        return None


def parse_trade_htmls():
    # Checkpoint directory
    CHECKPOINT_DIR = "trade_checkpoints"
    os.makedirs(CHECKPOINT_DIR, exist_ok=True)
    
    all_trades = {}
    # Define 5-year increments
    year_ranges = [
        range(2004, 2009),  # 2004-2008
        range(2009, 2015),  # 2009-2014
        range(2015, 2020),  # 2014-2018
        range(2020, 2025),  # 2019-2023
    ]
    
    for year_range in year_ranges:
        range_start = year_range.start
        range_end = year_range.stop - 1
        range_checkpoint = f"trades_{range_start}_{range_end}.json"
        
        logging.info("=" * 80)
        logging.info(f"📅 Processing years {range_start}-{range_end}")
        logging.info("=" * 80)
        
        if os.path.exists(range_checkpoint):
            logging.info(f"Range {range_start}-{range_end} already complete, loading from {range_checkpoint}\n")
            with open(range_checkpoint) as f:
                range_data = json.load(f)
                all_trades.update(range_data)
            continue
        
        range_trades = {}
        
        for year in year_range:
            # Check for individual year checkpoint
            logging.info(f"Starting parsing for {year}")
            year_checkpoint = f"{CHECKPOINT_DIR}/{year}.json"
            if os.path.exists(year_checkpoint):
                logging.info(f"{year} already exists, loading existing files")
                with open(year_checkpoint) as f:
                    range_trades[year] = json.load(f)
                continue
            
            html_file = f"bbref_htmls/{year}.html"
            
            if not os.path.exists(html_file):
                range_trades[year] = []
                continue
                
            with open(html_file, 'r', encoding='utf-8') as f:
                html = f.read() 

            soup = BeautifulSoup(html, 'html.parser')
            trades = []
            
            for p_tag in soup.find_all('p'):
                trade_text = ' '.join(p_tag.get_text().split())
                
                if not is_actual_trade(trade_text):
                    continue
                
                parsed = parse_trade(trade_text)
                if parsed:
                    trades.append(json.loads(parsed))
            
            range_trades[year] = trades
            
            # Save individual year checkpoint
            with open(year_checkpoint, "w") as f:
                json.dump(trades, f, indent=2)
        
        # Save 5-year range checkpoint
        with open(range_checkpoint, "w") as f:
            json.dump(range_trades, f, indent=2)
        
        all_trades.update(range_trades)
        
        total_in_range = sum(len(trades) for trades in range_trades.values())
        logging.info(f"\n Range {range_start}-{range_end} complete: {total_in_range} trades total")
        logging.info(f" Saved to {range_checkpoint}\n")
    
    # Save final output
    with open("trades.json", "w") as f:
        json.dump(all_trades, f, indent=2)
    
    logging.info("=" * 80)
    logging.info("🎉 ALL DONE!")
    total_trades = sum(len(trades) for trades in all_trades.values())
    logging.info(f"Total trades parsed: {total_trades}")

if __name__ == "__main__":
    parse_trade_htmls()