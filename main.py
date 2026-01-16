"""
Pump.fun Token Monitor
A real-time monitoring tool for tracking new tokens on pump.fun

Requirements:
    pip install solana solders websockets aiohttp requests --break-system-packages
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import asyncio
import json
import time
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, Dict, List
import queue
import webbrowser
import sys
import io
import os

# Fix emoji encoding for Windows console
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Solana imports - these will be used when connecting to RPC
try:
    from solana.rpc.websocket_api import connect
    from solana.rpc.async_api import AsyncClient
    from solders.pubkey import Pubkey
    SOLANA_AVAILABLE = True
except ImportError:
    SOLANA_AVAILABLE = False
    print("Note: Install solana/solders for live data: pip install solana solders --break-system-packages")

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError as e:
    WEBSOCKETS_AVAILABLE = False
    print(f"Note: websockets not available ({e})")
    print("  Install: pip install websockets --break-system-packages")


# ============================================================================
# Configuration
# ============================================================================

PUMP_FUN_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
DEFAULT_RPC = "https://api.mainnet-beta.solana.com"

# Helius API Configuration - Set your API key here
HELIUS_API_KEY = "851d6c4a-e912-4958-93fa-65d7199f353d"  # <-- Add your Helius API key here
HELIUS_RPC = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
HELIUS_WSS = f"wss://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"

# Alert thresholds
ALERT_THRESHOLDS = {
    "min_market_cap": 5000,       # Minimum market cap in USD
    "max_market_cap": 50000,      # Maximum market cap (catch early)
    "min_holders": 10,            # Minimum holder count
    "min_volume_5m": 1000,        # Minimum 5-minute volume
    "buy_sell_ratio": 1.5,        # Minimum buy/sell ratio
}

# Token removal settings
REMOVAL_THRESHOLD = {
    "min_market_cap": 1000,       # Remove tokens below this market cap
}

# Refresh settings
REFRESH_INTERVAL = 8              # Seconds between refresh cycles
TOKENS_PER_REFRESH = 10           # Number of tokens to refresh per cycle

# Settings file path (same directory as script)
SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")

# ============================================================================
# Theme Definitions
# ============================================================================

THEMES = {
    # Dark Themes
    "Dark (Default)": {
        "bg_dark": "#0d1117",
        "bg_card": "#161b22",
        "bg_hover": "#21262d",
        "fg_primary": "#f0f6fc",
        "fg_secondary": "#8b949e",
        "accent_green": "#3fb950",
        "accent_red": "#f85149",
        "accent_blue": "#58a6ff",
        "accent_yellow": "#d29922",
    },
    "Dark Blue": {
        "bg_dark": "#0a1628",
        "bg_card": "#112240",
        "bg_hover": "#1d3461",
        "fg_primary": "#e6f1ff",
        "fg_secondary": "#8892b0",
        "accent_green": "#64ffda",
        "accent_red": "#ff6b6b",
        "accent_blue": "#57cbff",
        "accent_yellow": "#ffd93d",
    },
    "Dark Purple": {
        "bg_dark": "#13111c",
        "bg_card": "#1e1b2e",
        "bg_hover": "#2d2640",
        "fg_primary": "#e2e0f0",
        "fg_secondary": "#a09cb0",
        "accent_green": "#50fa7b",
        "accent_red": "#ff5555",
        "accent_blue": "#bd93f9",
        "accent_yellow": "#f1fa8c",
    },
    "Dark Teal": {
        "bg_dark": "#0d1518",
        "bg_card": "#142428",
        "bg_hover": "#1e3338",
        "fg_primary": "#e0f2f1",
        "fg_secondary": "#80cbc4",
        "accent_green": "#1de9b6",
        "accent_red": "#ff8a80",
        "accent_blue": "#18ffff",
        "accent_yellow": "#ffff8d",
    },
    "Dark Red": {
        "bg_dark": "#1a0a0a",
        "bg_card": "#2d1515",
        "bg_hover": "#3d2020",
        "fg_primary": "#ffeaea",
        "fg_secondary": "#d4a5a5",
        "accent_green": "#69f0ae",
        "accent_red": "#ff5252",
        "accent_blue": "#ff80ab",
        "accent_yellow": "#ffd740",
    },
    "Dark Green": {
        "bg_dark": "#0a1a0a",
        "bg_card": "#152515",
        "bg_hover": "#203520",
        "fg_primary": "#e8f5e9",
        "fg_secondary": "#a5d6a7",
        "accent_green": "#00e676",
        "accent_red": "#ff5252",
        "accent_blue": "#40c4ff",
        "accent_yellow": "#ffea00",
    },
    "Midnight": {
        "bg_dark": "#000000",
        "bg_card": "#0a0a0a",
        "bg_hover": "#1a1a1a",
        "fg_primary": "#ffffff",
        "fg_secondary": "#888888",
        "accent_green": "#00ff00",
        "accent_red": "#ff0000",
        "accent_blue": "#00bfff",
        "accent_yellow": "#ffff00",
    },
    "Dracula": {
        "bg_dark": "#282a36",
        "bg_card": "#44475a",
        "bg_hover": "#6272a4",
        "fg_primary": "#f8f8f2",
        "fg_secondary": "#6272a4",
        "accent_green": "#50fa7b",
        "accent_red": "#ff5555",
        "accent_blue": "#8be9fd",
        "accent_yellow": "#f1fa8c",
    },
    "Nord": {
        "bg_dark": "#2e3440",
        "bg_card": "#3b4252",
        "bg_hover": "#434c5e",
        "fg_primary": "#eceff4",
        "fg_secondary": "#d8dee9",
        "accent_green": "#a3be8c",
        "accent_red": "#bf616a",
        "accent_blue": "#81a1c1",
        "accent_yellow": "#ebcb8b",
    },
    "Monokai": {
        "bg_dark": "#272822",
        "bg_card": "#3e3d32",
        "bg_hover": "#49483e",
        "fg_primary": "#f8f8f2",
        "fg_secondary": "#75715e",
        "accent_green": "#a6e22e",
        "accent_red": "#f92672",
        "accent_blue": "#66d9ef",
        "accent_yellow": "#e6db74",
    },
    "Gruvbox Dark": {
        "bg_dark": "#282828",
        "bg_card": "#3c3836",
        "bg_hover": "#504945",
        "fg_primary": "#ebdbb2",
        "fg_secondary": "#a89984",
        "accent_green": "#b8bb26",
        "accent_red": "#fb4934",
        "accent_blue": "#83a598",
        "accent_yellow": "#fabd2f",
    },
    "Solarized Dark": {
        "bg_dark": "#002b36",
        "bg_card": "#073642",
        "bg_hover": "#094959",
        "fg_primary": "#839496",
        "fg_secondary": "#586e75",
        "accent_green": "#859900",
        "accent_red": "#dc322f",
        "accent_blue": "#268bd2",
        "accent_yellow": "#b58900",
    },
    "Ocean": {
        "bg_dark": "#1b2838",
        "bg_card": "#1e3a50",
        "bg_hover": "#2a4a62",
        "fg_primary": "#c7d5e0",
        "fg_secondary": "#8ba4b8",
        "accent_green": "#4ecca3",
        "accent_red": "#ff6b6b",
        "accent_blue": "#66c0f4",
        "accent_yellow": "#f7d354",
    },
    "Cyberpunk": {
        "bg_dark": "#0d0221",
        "bg_card": "#1a0a3e",
        "bg_hover": "#2d1b4e",
        "fg_primary": "#ff00ff",
        "fg_secondary": "#00ffff",
        "accent_green": "#39ff14",
        "accent_red": "#ff073a",
        "accent_blue": "#00f0ff",
        "accent_yellow": "#fff01f",
    },
    "Matrix": {
        "bg_dark": "#0d0208",
        "bg_card": "#003b00",
        "bg_hover": "#005500",
        "fg_primary": "#00ff41",
        "fg_secondary": "#008f11",
        "accent_green": "#00ff41",
        "accent_red": "#ff0000",
        "accent_blue": "#00ff41",
        "accent_yellow": "#ccff00",
    },
    # Light Themes
    "Light": {
        "bg_dark": "#ffffff",
        "bg_card": "#f5f5f5",
        "bg_hover": "#e8e8e8",
        "fg_primary": "#1a1a1a",
        "fg_secondary": "#666666",
        "accent_green": "#22863a",
        "accent_red": "#cb2431",
        "accent_blue": "#0366d6",
        "accent_yellow": "#b08800",
    },
    "Light Blue": {
        "bg_dark": "#e3f2fd",
        "bg_card": "#bbdefb",
        "bg_hover": "#90caf9",
        "fg_primary": "#0d47a1",
        "fg_secondary": "#1565c0",
        "accent_green": "#2e7d32",
        "accent_red": "#c62828",
        "accent_blue": "#1565c0",
        "accent_yellow": "#f57f17",
    },
    "Light Green": {
        "bg_dark": "#e8f5e9",
        "bg_card": "#c8e6c9",
        "bg_hover": "#a5d6a7",
        "fg_primary": "#1b5e20",
        "fg_secondary": "#2e7d32",
        "accent_green": "#2e7d32",
        "accent_red": "#c62828",
        "accent_blue": "#1565c0",
        "accent_yellow": "#f57f17",
    },
    "Light Purple": {
        "bg_dark": "#f3e5f5",
        "bg_card": "#e1bee7",
        "bg_hover": "#ce93d8",
        "fg_primary": "#4a148c",
        "fg_secondary": "#6a1b9a",
        "accent_green": "#2e7d32",
        "accent_red": "#c62828",
        "accent_blue": "#7b1fa2",
        "accent_yellow": "#f57f17",
    },
    "Light Pink": {
        "bg_dark": "#fce4ec",
        "bg_card": "#f8bbd9",
        "bg_hover": "#f48fb1",
        "fg_primary": "#880e4f",
        "fg_secondary": "#ad1457",
        "accent_green": "#2e7d32",
        "accent_red": "#c62828",
        "accent_blue": "#c2185b",
        "accent_yellow": "#f57f17",
    },
    "Light Orange": {
        "bg_dark": "#fff3e0",
        "bg_card": "#ffe0b2",
        "bg_hover": "#ffcc80",
        "fg_primary": "#e65100",
        "fg_secondary": "#f57c00",
        "accent_green": "#2e7d32",
        "accent_red": "#c62828",
        "accent_blue": "#ef6c00",
        "accent_yellow": "#ff8f00",
    },
    "Cream": {
        "bg_dark": "#fdf6e3",
        "bg_card": "#eee8d5",
        "bg_hover": "#ddd6c1",
        "fg_primary": "#657b83",
        "fg_secondary": "#93a1a1",
        "accent_green": "#859900",
        "accent_red": "#dc322f",
        "accent_blue": "#268bd2",
        "accent_yellow": "#b58900",
    },
    "Paper": {
        "bg_dark": "#f5f5dc",
        "bg_card": "#fffef0",
        "bg_hover": "#f0ead6",
        "fg_primary": "#3c3c3c",
        "fg_secondary": "#6b6b6b",
        "accent_green": "#228b22",
        "accent_red": "#b22222",
        "accent_blue": "#4169e1",
        "accent_yellow": "#daa520",
    },
    "Gruvbox Light": {
        "bg_dark": "#fbf1c7",
        "bg_card": "#ebdbb2",
        "bg_hover": "#d5c4a1",
        "fg_primary": "#3c3836",
        "fg_secondary": "#665c54",
        "accent_green": "#79740e",
        "accent_red": "#9d0006",
        "accent_blue": "#076678",
        "accent_yellow": "#b57614",
    },
    # Special Themes
    "Hacker": {
        "bg_dark": "#000000",
        "bg_card": "#0a0a0a",
        "bg_hover": "#1a1a1a",
        "fg_primary": "#33ff33",
        "fg_secondary": "#00aa00",
        "accent_green": "#33ff33",
        "accent_red": "#ff3333",
        "accent_blue": "#33ff33",
        "accent_yellow": "#ffff33",
    },
    "Sunset": {
        "bg_dark": "#1a1423",
        "bg_card": "#2d1f3d",
        "bg_hover": "#462b5c",
        "fg_primary": "#ffeaa7",
        "fg_secondary": "#dfe6e9",
        "accent_green": "#55efc4",
        "accent_red": "#ff7675",
        "accent_blue": "#74b9ff",
        "accent_yellow": "#ffeaa7",
    },
    "Coffee": {
        "bg_dark": "#1b1512",
        "bg_card": "#2c221b",
        "bg_hover": "#3d3028",
        "fg_primary": "#d4c4b5",
        "fg_secondary": "#a89585",
        "accent_green": "#7cb342",
        "accent_red": "#d84315",
        "accent_blue": "#8d6e63",
        "accent_yellow": "#ffb300",
    },
    "Mint": {
        "bg_dark": "#0b1f1c",
        "bg_card": "#133b34",
        "bg_hover": "#1d5249",
        "fg_primary": "#b2dfdb",
        "fg_secondary": "#80cbc4",
        "accent_green": "#00e676",
        "accent_red": "#ff5252",
        "accent_blue": "#00bcd4",
        "accent_yellow": "#ffeb3b",
    },
    "Rose": {
        "bg_dark": "#1f0a14",
        "bg_card": "#3d1428",
        "bg_hover": "#5c1f3c",
        "fg_primary": "#f8bbd9",
        "fg_secondary": "#f48fb1",
        "accent_green": "#69f0ae",
        "accent_red": "#ff4081",
        "accent_blue": "#f06292",
        "accent_yellow": "#ffd54f",
    },
    "Slate": {
        "bg_dark": "#1e293b",
        "bg_card": "#334155",
        "bg_hover": "#475569",
        "fg_primary": "#f1f5f9",
        "fg_secondary": "#94a3b8",
        "accent_green": "#4ade80",
        "accent_red": "#f87171",
        "accent_blue": "#60a5fa",
        "accent_yellow": "#fbbf24",
    },
    "High Contrast": {
        "bg_dark": "#000000",
        "bg_card": "#1a1a1a",
        "bg_hover": "#333333",
        "fg_primary": "#ffffff",
        "fg_secondary": "#cccccc",
        "accent_green": "#00ff00",
        "accent_red": "#ff0000",
        "accent_blue": "#00ffff",
        "accent_yellow": "#ffff00",
    },
}

DEFAULT_THEME = "Dark (Default)"

# ============================================================================
# Optimal Preset Configurations
# ============================================================================
# Based on pump.fun token behavior analysis:
# - Tokens graduate at ~$69k market cap
# - Early tokens have few holders but high volatility
# - Buy/sell ratio indicates momentum
# - Volume indicates liquidity and interest

PRESETS = {
    "Early Bird": {
        "description": "Catch tokens extremely early. High risk, high reward. Best for quick flips on brand new launches.",
        "risk_level": "Very High",
        "strategy": "Enter within first few minutes of launch, exit quickly on 2-5x",
        "alert_thresholds": {
            "min_market_cap": 1000,
            "max_market_cap": 10000,
            "min_holders": 3,
            "min_volume_5m": 200,
            "buy_sell_ratio": 1.2,
        },
        "removal_threshold": {
            "min_market_cap": 500,
        },
    },
    "Momentum Hunter": {
        "description": "Find tokens with strong buying pressure. Look for high buy/sell ratios indicating accumulation.",
        "risk_level": "High",
        "strategy": "Enter on momentum, ride the wave, exit before reversal",
        "alert_thresholds": {
            "min_market_cap": 5000,
            "max_market_cap": 35000,
            "min_holders": 15,
            "min_volume_5m": 1500,
            "buy_sell_ratio": 2.5,
        },
        "removal_threshold": {
            "min_market_cap": 2000,
        },
    },
    "Volume Chaser": {
        "description": "Focus on high-volume tokens with lots of trading activity. More liquidity = easier exits.",
        "risk_level": "Medium-High",
        "strategy": "Trade liquid tokens, use volume spikes as entry signals",
        "alert_thresholds": {
            "min_market_cap": 8000,
            "max_market_cap": 45000,
            "min_holders": 20,
            "min_volume_5m": 5000,
            "buy_sell_ratio": 1.5,
        },
        "removal_threshold": {
            "min_market_cap": 3000,
        },
    },
    "Graduation Play": {
        "description": "Target tokens approaching graduation ($69k). These have proven momentum and may pump on graduation.",
        "risk_level": "Medium",
        "strategy": "Enter at 60-80% progress, hold through graduation for potential listing pump",
        "alert_thresholds": {
            "min_market_cap": 45000,
            "max_market_cap": 68000,
            "min_holders": 50,
            "min_volume_5m": 3000,
            "buy_sell_ratio": 1.3,
        },
        "removal_threshold": {
            "min_market_cap": 35000,
        },
    },
    "Safe Play": {
        "description": "More established tokens with good holder distribution. Lower risk, steadier gains.",
        "risk_level": "Medium-Low",
        "strategy": "Look for organic growth patterns, avoid pump and dumps",
        "alert_thresholds": {
            "min_market_cap": 15000,
            "max_market_cap": 50000,
            "min_holders": 75,
            "min_volume_5m": 2000,
            "buy_sell_ratio": 1.2,
        },
        "removal_threshold": {
            "min_market_cap": 8000,
        },
    },
    "Holder Accumulation": {
        "description": "Focus on tokens gaining holders rapidly. Growing community = potential for sustained growth.",
        "risk_level": "Medium",
        "strategy": "Track holder growth rate, enter when accumulation is clear",
        "alert_thresholds": {
            "min_market_cap": 5000,
            "max_market_cap": 40000,
            "min_holders": 100,
            "min_volume_5m": 1000,
            "buy_sell_ratio": 1.4,
        },
        "removal_threshold": {
            "min_market_cap": 3000,
        },
    },
    "Balanced": {
        "description": "Well-rounded settings for general monitoring. Good starting point for most traders.",
        "risk_level": "Medium",
        "strategy": "Balanced approach, filter out noise while catching opportunities",
        "alert_thresholds": {
            "min_market_cap": 5000,
            "max_market_cap": 50000,
            "min_holders": 10,
            "min_volume_5m": 1000,
            "buy_sell_ratio": 1.5,
        },
        "removal_threshold": {
            "min_market_cap": 1000,
        },
    },
    "Whale Watcher": {
        "description": "Detect tokens with large buys. Whales often know something - follow the smart money.",
        "risk_level": "High",
        "strategy": "Look for sudden volume spikes and large single buys",
        "alert_thresholds": {
            "min_market_cap": 3000,
            "max_market_cap": 30000,
            "min_holders": 5,
            "min_volume_5m": 8000,
            "buy_sell_ratio": 3.0,
        },
        "removal_threshold": {
            "min_market_cap": 1500,
        },
    },
    "Sniper": {
        "description": "Ultra-aggressive settings for catching the very first trades. Requires fast execution.",
        "risk_level": "Extreme",
        "strategy": "Be among first buyers, take profits quickly at 2-3x",
        "alert_thresholds": {
            "min_market_cap": 500,
            "max_market_cap": 5000,
            "min_holders": 1,
            "min_volume_5m": 100,
            "buy_sell_ratio": 1.0,
        },
        "removal_threshold": {
            "min_market_cap": 200,
        },
    },
    "Conservative": {
        "description": "Very strict filters for quality over quantity. Fewer alerts but higher probability plays.",
        "risk_level": "Low",
        "strategy": "Wait for confirmation, only trade established patterns",
        "alert_thresholds": {
            "min_market_cap": 20000,
            "max_market_cap": 60000,
            "min_holders": 150,
            "min_volume_5m": 4000,
            "buy_sell_ratio": 1.8,
        },
        "removal_threshold": {
            "min_market_cap": 15000,
        },
    },
}


def save_settings_to_file(settings: dict):
    """Save settings to JSON file"""
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2)
        print(f"[SETTINGS] Saved to {SETTINGS_FILE}")
    except Exception as e:
        print(f"[SETTINGS] Error saving: {e}")


def load_settings_from_file() -> dict:
    """Load settings from JSON file"""
    default_settings = {
        "helius_api_key": HELIUS_API_KEY,
        "use_mock": True,
        "theme": DEFAULT_THEME,
        "alert_thresholds": ALERT_THRESHOLDS.copy(),
        "removal_threshold": REMOVAL_THRESHOLD.copy(),
    }

    if not os.path.exists(SETTINGS_FILE):
        return default_settings

    try:
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            loaded = json.load(f)
            # Merge with defaults to handle missing keys
            settings = default_settings.copy()
            settings.update(loaded)
            print(f"[SETTINGS] Loaded from {SETTINGS_FILE}")
            return settings
    except Exception as e:
        print(f"[SETTINGS] Error loading: {e}")
        return default_settings


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class Token:
    """Represents a pump.fun token being tracked"""
    address: str
    name: str = "Unknown"
    symbol: str = "???"
    created_at: float = field(default_factory=time.time)
    market_cap: float = 0.00
    volume_5m: float = 0.00
    volume_1h: float = 0.00
    holders: int = 0
    buys: int = 0
    sells: int = 0
    dev_sold: bool = False
    bonding_progress: float = 0.0  # 0-100%
    last_update: float = field(default_factory=time.time)
    
    @property
    def buy_sell_ratio(self) -> float:
        return self.buys / max(self.sells, 1)
    
    @property
    def age_minutes(self) -> float:
        return (time.time() - self.created_at) / 60
    
    def meets_alert_criteria(self, thresholds: dict) -> bool:
        """Check if token meets alert thresholds"""
        if self.market_cap < thresholds.get("min_market_cap", 0):
            return False
        if self.market_cap > thresholds.get("max_market_cap", float('inf')):
            return False
        if self.holders < thresholds.get("min_holders", 0):
            return False
        if self.volume_5m < thresholds.get("min_volume_5m", 0):
            return False
        if self.buy_sell_ratio < thresholds.get("buy_sell_ratio", 0):
            return False
        return True


# ============================================================================
# Helius WebSocket Client
# ============================================================================

class HeliusWebSocket:
    """WebSocket client for subscribing to pump.fun program events via Helius"""

    def __init__(self, api_key: str, update_queue: queue.Queue):
        self.api_key = api_key
        self.wss_url = f"wss://mainnet.helius-rpc.com/?api-key={api_key}"
        self.rpc_url = f"https://mainnet.helius-rpc.com/?api-key={api_key}"
        self.update_queue = update_queue
        self.ws = None
        self.running = False
        self.subscription_id = None
        self.known_tokens: Dict[str, Token] = {}

    async def connect(self):
        """Establish websocket connection and subscribe to pump.fun logs"""
        if not WEBSOCKETS_AVAILABLE:
            raise RuntimeError("websockets library not installed")

        print(f"Connecting to Helius WebSocket...")
        self.ws = await websockets.connect(
            self.wss_url,
            ping_interval=30,
            ping_timeout=10,
            close_timeout=10
        )
        print("Connected to Helius WebSocket")

        # Subscribe to pump.fun program logs
        subscribe_msg = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "logsSubscribe",
            "params": [
                {"mentions": [PUMP_FUN_PROGRAM_ID]},
                {"commitment": "confirmed"}
            ]
        }

        await self.ws.send(json.dumps(subscribe_msg))
        response = await self.ws.recv()
        result = json.loads(response)

        if "result" in result:
            self.subscription_id = result["result"]
            print(f"Subscribed to pump.fun logs (subscription ID: {self.subscription_id})")
        else:
            raise RuntimeError(f"Failed to subscribe: {result}")

    async def disconnect(self):
        """Unsubscribe and close websocket connection"""
        if self.ws and self.subscription_id:
            try:
                unsubscribe_msg = {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "logsUnsubscribe",
                    "params": [self.subscription_id]
                }
                await self.ws.send(json.dumps(unsubscribe_msg))
            except:
                pass

        if self.ws:
            await self.ws.close()
            self.ws = None

        self.subscription_id = None
        print("Disconnected from Helius WebSocket")

    def parse_pump_fun_logs(self, logs: List[str], signature: str) -> Optional[dict]:
        """Parse pump.fun program logs to extract event type and data"""
        event_info = {
            "type": None,
            "signature": signature,
            "mint": None,
        }

        for log in logs:
            # Detect token creation - pump.fun uses "Program log: Instruction: Create"
            if "Instruction: Create" in log:
                event_info["type"] = "create"
            elif "Instruction: Buy" in log:
                event_info["type"] = "buy"
            elif "Instruction: Sell" in log:
                event_info["type"] = "sell"

        # Debug: print first log line to see format (only occasionally)
        if logs and not hasattr(self, '_log_sample_printed'):
            self._log_sample_printed = True
            print(f"[DEBUG] Sample log lines from pump.fun:")
            for log in logs[:5]:
                print(f"  {log[:100]}...")

        return event_info if event_info["type"] else None

    def fetch_transaction_details(self, signature: str, retries: int = 3) -> Optional[dict]:
        """Fetch full transaction details via RPC to get token mint address"""
        if not REQUESTS_AVAILABLE:
            return None

        for attempt in range(retries):
            try:
                payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getTransaction",
                    "params": [
                        signature,
                        {
                            "encoding": "jsonParsed",
                            "maxSupportedTransactionVersion": 0,
                            "commitment": "confirmed"
                        }
                    ]
                }

                response = requests.post(self.rpc_url, json=payload, timeout=10)
                result = response.json()

                if "error" in result:
                    return None

                if "result" in result and result["result"]:
                    return result["result"]

                # Result is null - transaction not yet available
                if attempt < retries - 1:
                    time.sleep(3)

            except Exception as e:
                print(f"Error fetching transaction {signature}: {e}")

        return None

    def extract_mint_from_create_tx(self, tx_data: dict) -> Optional[str]:
        """Extract the mint address from a pump.fun create transaction"""
        try:
            # The mint is typically in the account keys of the transaction
            # For pump.fun, the mint is usually the 2nd or 3rd account
            accounts = tx_data.get("transaction", {}).get("message", {}).get("accountKeys", [])

            # Look through inner instructions for the InitializeMint instruction
            meta = tx_data.get("meta", {})
            inner_instructions = meta.get("innerInstructions", [])

            for inner in inner_instructions:
                for ix in inner.get("instructions", []):
                    if isinstance(ix, dict):
                        parsed = ix.get("parsed", {})
                        if isinstance(parsed, dict):
                            ix_type = parsed.get("type", "")
                            if ix_type == "initializeMint" or ix_type == "initializeMint2":
                                info = parsed.get("info", {})
                                mint = info.get("mint")
                                if mint:
                                    return mint

            # Fallback: check post token balances for new mints
            post_balances = meta.get("postTokenBalances", [])
            for balance in post_balances:
                mint = balance.get("mint")
                if mint and mint != "So11111111111111111111111111111111111111112":  # Exclude native SOL
                    return mint

        except Exception as e:
            print(f"Error extracting mint: {e}")

        return None

    def fetch_token_metadata(self, mint_address: str) -> dict:
        """Fetch token metadata from Helius DAS API"""
        metadata = {
            "name": "Unknown",
            "symbol": "???",
        }

        if not REQUESTS_AVAILABLE:
            return metadata

        try:
            # Use Helius DAS API for token metadata
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getAsset",
                "params": {"id": mint_address}
            }

            response = requests.post(self.rpc_url, json=payload, timeout=10)
            result = response.json()

            if "result" in result and result["result"]:
                asset = result["result"]
                content = asset.get("content", {})
                meta = content.get("metadata", {})

                metadata["name"] = meta.get("name", "Unknown")
                metadata["symbol"] = meta.get("symbol", "???")

        except Exception as e:
            print(f"Error fetching metadata for {mint_address}: {e}")

        return metadata

    def fetch_holder_count(self, mint_address: str) -> int:
        """Fetch holder count using Helius API"""
        if not REQUESTS_AVAILABLE:
            return 1

        try:
            # Use Helius getTokenAccounts to count holders
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTokenAccounts",
                "params": {
                    "mint": mint_address,
                    "limit": 1000,  # Get up to 1000 holders
                    "options": {
                        "showZeroBalance": False  # Only count non-zero balances
                    }
                }
            }

            response = requests.post(self.rpc_url, json=payload, timeout=10)
            result = response.json()

            if "result" in result and result["result"]:
                token_accounts = result["result"].get("token_accounts", [])
                holder_count = len(token_accounts)

                # Debug first successful holder fetch
                if not hasattr(self, '_holder_api_printed') and holder_count > 0:
                    self._holder_api_printed = True
                    print(f"[DEBUG] Helius holder count for {mint_address[:8]}: {holder_count}")

                return max(holder_count, 1)

        except Exception as e:
            if not hasattr(self, '_holder_error_printed'):
                self._holder_error_printed = True
                print(f"[DEBUG] Holder count error: {type(e).__name__}: {e}")

        return 1  # Default to 1 holder

    def fetch_bonding_curve_data(self, mint_address: str) -> dict:
        """Fetch token data from multiple APIs with fallback"""
        curve_data = {
            "market_cap": 0.0,
            "bonding_progress": 0.0,
            "volume_5m": 0.0,
            "volume_1h": 0.0,
            "holders": 1,
        }

        if not REQUESTS_AVAILABLE:
            return curve_data

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
        }

        # Try DexScreener API first (more reliable)
        try:
            dex_url = f"https://api.dexscreener.com/latest/dex/tokens/{mint_address}"
            response = requests.get(dex_url, headers=headers, timeout=10)

            if response.status_code == 200:
                data = response.json()
                pairs = data.get("pairs", [])

                if pairs:
                    # Get the first/main pair (usually highest liquidity)
                    pair = pairs[0]

                    # Market cap - use fdv (fully diluted valuation) as market cap
                    curve_data["market_cap"] = float(pair.get("fdv", 0) or 0)
                    if curve_data["market_cap"] == 0:
                        curve_data["market_cap"] = float(pair.get("marketCap", 0) or 0)

                    # Volume
                    volume = pair.get("volume", {})
                    curve_data["volume_5m"] = float(volume.get("m5", 0) or 0)
                    curve_data["volume_1h"] = float(volume.get("h1", 0) or 0)
                    # If no 5m volume, use 1h volume / 12 as estimate
                    if curve_data["volume_5m"] == 0 and curve_data["volume_1h"] > 0:
                        curve_data["volume_5m"] = curve_data["volume_1h"] / 12

                    # Transactions (buys/sells) from DexScreener
                    txns = pair.get("txns", {})
                    m5_txns = txns.get("m5", {})
                    curve_data["buys_5m"] = int(m5_txns.get("buys", 0) or 0)
                    curve_data["sells_5m"] = int(m5_txns.get("sells", 0) or 0)

                    # Progress based on market cap (pump.fun graduates at ~$69k)
                    curve_data["bonding_progress"] = min(100, (curve_data["market_cap"] / 69000) * 100)

                    # Debug: print first successful API response
                    if not hasattr(self, '_dex_api_printed'):
                        self._dex_api_printed = True
                        print(f"[DEBUG] DexScreener data for {mint_address[:8]}:")
                        print(f"  MCap=${curve_data['market_cap']:,.0f}, Vol5m=${curve_data['volume_5m']:,.0f}, Progress={curve_data['bonding_progress']:.1f}%")

                    # If we got data from DexScreener, return it
                    if curve_data["market_cap"] > 0:
                        return curve_data

        except Exception as e:
            if not hasattr(self, '_dex_error_printed'):
                self._dex_error_printed = True
                print(f"[DEBUG] DexScreener API error: {type(e).__name__}: {e}")

        # Fallback: Try Birdeye API
        try:
            birdeye_url = f"https://public-api.birdeye.so/defi/token_overview?address={mint_address}"
            birdeye_headers = {**headers, "x-chain": "solana"}
            response = requests.get(birdeye_url, headers=birdeye_headers, timeout=10)

            if response.status_code == 200:
                data = response.json()
                token_data = data.get("data", {})

                if token_data:
                    curve_data["market_cap"] = float(token_data.get("mc", 0) or 0)
                    curve_data["volume_5m"] = float(token_data.get("v24hUSD", 0) or 0) / 288  # Estimate 5m from 24h
                    curve_data["holders"] = int(token_data.get("holder", 1) or 1)
                    curve_data["bonding_progress"] = min(100, (curve_data["market_cap"] / 69000) * 100)

                    if not hasattr(self, '_birdeye_api_printed'):
                        self._birdeye_api_printed = True
                        print(f"[DEBUG] Birdeye data for {mint_address[:8]}:")
                        print(f"  MCap=${curve_data['market_cap']:,.0f}, Holders={curve_data['holders']}")

                    if curve_data["market_cap"] > 0:
                        return curve_data

        except Exception as e:
            pass  # Birdeye often requires API key, silently fail

        # Last resort: Try pump.fun API (often blocked by Cloudflare)
        try:
            api_url = f"https://frontend-api.pump.fun/coins/{mint_address}"
            response = requests.get(api_url, headers=headers, timeout=5)

            if response.status_code == 200:
                data = response.json()
                curve_data["market_cap"] = float(data.get("usd_market_cap", 0) or 0)
                curve_data["bonding_progress"] = min(100, (curve_data["market_cap"] / 69000) * 100)

                if not hasattr(self, '_pumpfun_api_printed'):
                    self._pumpfun_api_printed = True
                    print(f"[DEBUG] pump.fun API success for {mint_address[:8]}")

        except Exception:
            pass  # pump.fun often blocked, silently fail

        return curve_data

    def refresh_token_data(self, token: Token) -> Token:
        """Refresh token data from APIs"""
        curve_data = self.fetch_bonding_curve_data(token.address)

        # Update token metrics
        token.market_cap = curve_data["market_cap"]
        token.bonding_progress = curve_data["bonding_progress"]
        token.volume_5m = curve_data["volume_5m"]

        # Fetch holder count from Helius
        holder_count = self.fetch_holder_count(token.address)
        if holder_count > 0:
            token.holders = holder_count

        token.last_update = time.time()

        return token

    async def periodic_refresh(self):
        """Periodically refresh data for all known tokens"""
        refresh_count = 0

        while self.running:
            try:
                await asyncio.sleep(REFRESH_INTERVAL)

                if not self.known_tokens:
                    continue

                refresh_count += 1

                # Get all tokens sorted by last update (oldest first)
                all_tokens = sorted(
                    self.known_tokens.values(),
                    key=lambda t: t.last_update
                )

                # Refresh tokens that need updating
                tokens_refreshed = 0
                tokens_removed = 0

                for token in all_tokens:
                    if not self.running:
                        break

                    if tokens_refreshed >= TOKENS_PER_REFRESH:
                        break

                    # Skip tokens older than 30 minutes
                    if token.age_minutes > 30:
                        # Remove old tokens
                        if token.address in self.known_tokens:
                            del self.known_tokens[token.address]
                            self.update_queue.put(("remove", token))
                            tokens_removed += 1
                        continue

                    try:
                        updated_token = self.refresh_token_data(token)

                        # Check if token should be removed (below min market cap)
                        min_mcap = REMOVAL_THRESHOLD.get("min_market_cap", 0)
                        if updated_token.market_cap > 0 and updated_token.market_cap < min_mcap:
                            # Remove token below threshold
                            if token.address in self.known_tokens:
                                del self.known_tokens[token.address]
                                self.update_queue.put(("remove", token))
                                tokens_removed += 1
                                print(f"[REMOVE] {token.symbol} below ${min_mcap} (MCap: ${token.market_cap:,.0f})")
                        else:
                            self.update_queue.put(("update", updated_token))
                            tokens_refreshed += 1

                        await asyncio.sleep(0.5)  # Small delay between API calls

                    except Exception as e:
                        print(f"[REFRESH] Error refreshing {token.symbol}: {e}")

                # Log refresh stats periodically
                if refresh_count % 5 == 0:
                    print(f"[REFRESH] Cycle {refresh_count}: Updated {tokens_refreshed}, Removed {tokens_removed}, Tracking {len(self.known_tokens)} tokens")

            except Exception as e:
                print(f"[REFRESH] Periodic refresh error: {e}")

    async def listen(self):
        """Listen for incoming websocket messages"""
        self.running = True
        msg_count = 0

        while self.running and self.ws:
            try:
                message = await asyncio.wait_for(self.ws.recv(), timeout=60)
                data = json.loads(message)
                msg_count += 1

                # Process log notifications
                if "method" in data and data["method"] == "logsNotification":
                    if msg_count % 10 == 1:  # Log every 10th message
                        print(f"[WS] Received {msg_count} messages...")
                    await self.process_log_notification(data)

            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                if self.ws:
                    try:
                        pong = await self.ws.ping()
                        await asyncio.wait_for(pong, timeout=10)
                    except:
                        print("WebSocket ping failed, reconnecting...")
                        break
            except websockets.ConnectionClosed:
                print("WebSocket connection closed")
                break
            except Exception as e:
                print(f"WebSocket error: {e}")

    async def process_log_notification(self, data: dict):
        """Process a log notification from the websocket"""
        try:
            params = data.get("params", {})
            result = params.get("result", {})
            value = result.get("value", {})

            signature = value.get("signature", "")
            logs = value.get("logs", [])
            err = value.get("err")

            # Skip failed transactions
            if err:
                return

            # Parse the logs
            event = self.parse_pump_fun_logs(logs, signature)

            if event and event["type"] == "create":
                print(f"[CREATE] New token creation detected", flush=True)
                await self.handle_token_creation(signature)
            elif event and event["type"] in ("buy", "sell"):
                await self.handle_trade_event(signature, event["type"])

        except Exception as e:
            print(f"Error processing notification: {e}")

    async def handle_token_creation(self, signature: str):
        """Handle a new token creation event"""
        # Wait for transaction to be indexed
        await asyncio.sleep(2)

        # Fetch transaction details to get the mint address
        tx_data = self.fetch_transaction_details(signature, retries=3)
        if not tx_data:
            print(f"[DEBUG] Could not fetch tx details for {signature[:16]}")
            return

        mint_address = self.extract_mint_from_create_tx(tx_data)
        if not mint_address:
            print(f"[DEBUG] Could not extract mint from tx {signature[:16]}")
            return

        print(f"[DEBUG] Found mint: {mint_address[:16]}...")

        # Check if we already know this token
        if mint_address in self.known_tokens:
            return

        # Fetch token metadata
        metadata = self.fetch_token_metadata(mint_address)
        curve_data = self.fetch_bonding_curve_data(mint_address)
        holder_count = self.fetch_holder_count(mint_address)

        # Create token object
        token = Token(
            address=mint_address,
            name=metadata["name"],
            symbol=metadata["symbol"],
            created_at=time.time(),
            market_cap=curve_data["market_cap"],
            bonding_progress=curve_data["bonding_progress"],
            volume_5m=curve_data["volume_5m"],
            holders=holder_count if holder_count > 0 else 1,
            buys=0,
            sells=0,
        )

        self.known_tokens[mint_address] = token
        self.update_queue.put(("new", token))
        print(f"New token detected: {token.symbol} ({token.name}) - {mint_address[:8]}...")

    async def handle_trade_event(self, signature: str, trade_type: str):
        """Handle a buy/sell trade event"""
        # Fetch transaction to identify which token
        tx_data = self.fetch_transaction_details(signature)
        if not tx_data:
            return

        # Find mint from token balances
        meta = tx_data.get("meta", {})
        post_balances = meta.get("postTokenBalances", [])

        for balance in post_balances:
            mint = balance.get("mint")
            # Skip native SOL
            if not mint or mint == "So11111111111111111111111111111111111111112":
                continue

            if mint in self.known_tokens:
                # Update existing token
                token = self.known_tokens[mint]
                if trade_type == "buy":
                    token.buys += 1
                else:
                    token.sells += 1
                token.last_update = time.time()
                self.update_queue.put(("update", token))
            else:
                # New token discovered via trade - add it!
                print(f"[TRADE] New token from {trade_type}: {mint[:16]}...", flush=True)
                metadata = self.fetch_token_metadata(mint)
                curve_data = self.fetch_bonding_curve_data(mint)
                holder_count = self.fetch_holder_count(mint)

                token = Token(
                    address=mint,
                    name=metadata["name"],
                    symbol=metadata["symbol"],
                    created_at=time.time(),
                    market_cap=curve_data["market_cap"],
                    bonding_progress=curve_data["bonding_progress"],
                    volume_5m=curve_data["volume_5m"],
                    holders=holder_count if holder_count > 0 else 1,
                    buys=1 if trade_type == "buy" else 0,
                    sells=1 if trade_type == "sell" else 0,
                )
                self.known_tokens[mint] = token
                self.update_queue.put(("new", token))
                print(f"[NEW] {token.symbol} ({token.name}) - MCap: ${token.market_cap:,.0f}, Holders: {token.holders}", flush=True)

            break


# ============================================================================
# Data Fetcher (Mock + Real Implementation)
# ============================================================================

class PumpFunFetcher:
    """Fetches data from pump.fun / Solana"""

    def __init__(self, rpc_url: str = DEFAULT_RPC, helius_api_key: str = ""):
        self.rpc_url = rpc_url
        self.helius_api_key = helius_api_key
        self.tokens: Dict[str, Token] = {}
        self.running = False
        self.update_queue = queue.Queue()
        self.helius_ws: Optional[HeliusWebSocket] = None
        self.ws_thread: Optional[threading.Thread] = None
        
    def fetch_new_tokens_mock(self) -> List[Token]:
        """Generate mock tokens for testing without API"""
        import random
        
        # Simulate finding 0-2 new tokens
        new_tokens = []
        if random.random() < 0.3:  # 30% chance of new token
            names = ["DOGE2", "PEPE3", "WOJAK", "CHAD", "MOON", "PUMP", "FROG", "APE", "SHIB2", "FLOKI2"]
            name = random.choice(names) + str(random.randint(100, 999))
            
            token = Token(
                address=f"{''.join(random.choices('123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz', k=44))}",
                name=name,
                symbol=name[:4].upper(),
                created_at=time.time() - random.randint(0, 300),
                market_cap=random.uniform(1000, 30000),
                volume_5m=random.uniform(100, 5000),
                volume_1h=random.uniform(500, 20000),
                holders=random.randint(5, 100),
                buys=random.randint(10, 200),
                sells=random.randint(5, 100),
                bonding_progress=random.uniform(0, 50),
            )
            new_tokens.append(token)
            
        return new_tokens
    
    def update_token_mock(self, token: Token) -> Token:
        """Simulate token metric updates"""
        import random
        
        # Simulate price/volume changes
        change = random.uniform(-0.1, 0.15)
        token.market_cap *= (1 + change)
        token.volume_5m = random.uniform(100, 5000)
        token.holders += random.randint(-1, 5)
        token.holders = max(1, token.holders)
        token.buys += random.randint(0, 10)
        token.sells += random.randint(0, 5)
        token.bonding_progress = min(100, token.bonding_progress + random.uniform(0, 2))
        token.last_update = time.time()
        
        return token
    
    def start_monitoring(self, callback, use_mock: bool = True):
        """Start the monitoring loop in a background thread"""
        self.running = True

        if use_mock:
            self._start_mock_monitoring(callback)
        else:
            self._start_real_monitoring(callback)

    def _start_mock_monitoring(self, callback):
        """Start mock data monitoring loop"""
        def monitor_loop():
            while self.running:
                try:
                    # Fetch new tokens
                    new_tokens = self.fetch_new_tokens_mock()
                    for token in new_tokens:
                        if token.address not in self.tokens:
                            self.tokens[token.address] = token
                            self.update_queue.put(("new", token))

                    # Update existing tokens
                    for addr, token in list(self.tokens.items()):
                        updated = self.update_token_mock(token)
                        self.update_queue.put(("update", updated))

                        # Remove old tokens (> 30 min)
                        if updated.age_minutes > 30:
                            del self.tokens[addr]
                            self.update_queue.put(("remove", updated))

                    # Process queue
                    while not self.update_queue.empty():
                        action, token = self.update_queue.get_nowait()
                        callback(action, token)

                except Exception as e:
                    print(f"Monitor error: {e}")

                time.sleep(3)  # Update every 3 seconds

        thread = threading.Thread(target=monitor_loop, daemon=True)
        thread.start()
        return thread

    def _start_real_monitoring(self, callback):
        """Start real data monitoring via Helius WebSocket"""
        if not self.helius_api_key:
            print("ERROR: Helius API key not configured!")
            return None

        if not WEBSOCKETS_AVAILABLE:
            print("ERROR: websockets library not installed!")
            print("  Run: pip install websockets")
            return None

        # Create Helius WebSocket client
        self.helius_ws = HeliusWebSocket(self.helius_api_key, self.update_queue)

        def ws_thread_func():
            """Run the async websocket in a separate thread"""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def run_ws():
                try:
                    await self.helius_ws.connect()
                    print("Starting pump.fun token monitoring...")

                    # Start listener, queue processor, and periodic refresh concurrently
                    listener_task = asyncio.create_task(self.helius_ws.listen())
                    processor_task = asyncio.create_task(
                        self._process_queue_async(callback)
                    )
                    refresh_task = asyncio.create_task(self.helius_ws.periodic_refresh())

                    await asyncio.gather(listener_task, processor_task, refresh_task)

                except Exception as e:
                    print(f"WebSocket error: {e}")
                finally:
                    await self.helius_ws.disconnect()

            try:
                loop.run_until_complete(run_ws())
            except Exception as e:
                print(f"Event loop error: {e}")
            finally:
                loop.close()

        self.ws_thread = threading.Thread(target=ws_thread_func, daemon=True)
        self.ws_thread.start()
        return self.ws_thread

    async def _process_queue_async(self, callback):
        """Process update queue in async context"""
        while self.running:
            try:
                # Non-blocking queue check
                while not self.update_queue.empty():
                    action, token = self.update_queue.get_nowait()
                    self.tokens[token.address] = token
                    callback(action, token)

                    # Remove old tokens (> 30 min)
                    if token.age_minutes > 30:
                        if token.address in self.tokens:
                            del self.tokens[token.address]
                        callback("remove", token)

                await asyncio.sleep(1)

            except Exception as e:
                print(f"Queue processing error: {e}")
    
    def stop_monitoring(self):
        """Stop the monitoring loop"""
        self.running = False

        # Stop websocket if running
        if self.helius_ws:
            self.helius_ws.running = False


# ============================================================================
# GUI Application
# ============================================================================

class PumpFunMonitorApp:
    """Main GUI Application"""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Pump.fun Token Monitor")
        self.root.geometry("1200x800")
        self.root.configure(bg="#0d1117")

        # Load settings from file
        self.load_settings()

        # Data
        self.fetcher = PumpFunFetcher(helius_api_key=self.helius_api_key)
        self.tokens: Dict[str, Token] = {}
        self.alerts: List[str] = []
        self.monitoring = False

        # Configure styles
        self.setup_styles()

        # Build UI
        self.build_ui()

        # Bind close event
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def load_settings(self):
        """Load settings from file"""
        settings = load_settings_from_file()

        # Apply loaded settings
        self.use_mock = settings.get("use_mock", True)
        self.helius_api_key = settings.get("helius_api_key", HELIUS_API_KEY)
        self.current_theme = settings.get("theme", DEFAULT_THEME)

        # Validate theme exists
        if self.current_theme not in THEMES:
            self.current_theme = DEFAULT_THEME

        # Update global thresholds
        loaded_alerts = settings.get("alert_thresholds", {})
        for key, value in loaded_alerts.items():
            if key in ALERT_THRESHOLDS:
                ALERT_THRESHOLDS[key] = value

        loaded_removal = settings.get("removal_threshold", {})
        for key, value in loaded_removal.items():
            if key in REMOVAL_THRESHOLD:
                REMOVAL_THRESHOLD[key] = value

        print(f"[SETTINGS] Mode: {'Mock' if self.use_mock else 'Live'}, Theme: {self.current_theme}, Removal MCap: ${REMOVAL_THRESHOLD['min_market_cap']:,.0f}")

    def save_settings(self):
        """Save current settings to file"""
        settings = {
            "helius_api_key": self.helius_api_key,
            "use_mock": self.use_mock,
            "theme": self.current_theme,
            "alert_thresholds": ALERT_THRESHOLDS.copy(),
            "removal_threshold": REMOVAL_THRESHOLD.copy(),
        }
        save_settings_to_file(settings)

    def get_theme_colors(self) -> dict:
        """Get current theme colors"""
        return THEMES.get(self.current_theme, THEMES[DEFAULT_THEME])

    def apply_theme(self, theme_name: str):
        """Apply a new theme to the entire UI"""
        if theme_name not in THEMES:
            return

        self.current_theme = theme_name
        theme = self.get_theme_colors()
        self.colors = theme

        # Update root window
        self.root.configure(bg=theme["bg_dark"])

        # Update styles
        self.setup_styles()

        # Update main frame and all children recursively
        self._update_widget_colors(self.root, theme)

        # Save settings
        self.save_settings()
        self.add_alert(f"🎨 Theme changed to: {theme_name}")

    def _update_widget_colors(self, widget, theme):
        """Recursively update widget colors"""
        bg_dark = theme["bg_dark"]
        bg_card = theme["bg_card"]
        fg_primary = theme["fg_primary"]
        fg_secondary = theme["fg_secondary"]
        accent_blue = theme["accent_blue"]
        accent_green = theme["accent_green"]

        try:
            widget_class = widget.winfo_class()

            if widget_class == 'Frame':
                widget.configure(bg=bg_dark)
            elif widget_class == 'Label':
                # Check if it's a stat label or regular label
                current_fg = str(widget.cget('fg'))
                if current_fg in ['#58a6ff', '#3fb950', accent_blue, accent_green] or 'stat' in str(widget).lower():
                    widget.configure(bg=bg_card, fg=accent_blue)
                elif current_fg == fg_secondary or current_fg == '#8b949e':
                    widget.configure(bg=bg_card if 'card' in str(widget.master).lower() else bg_dark, fg=fg_secondary)
                else:
                    widget.configure(bg=bg_dark, fg=fg_primary)
            elif widget_class == 'Text':
                widget.configure(bg=bg_card, fg=fg_primary)
            elif widget_class == 'Button':
                # Keep button colors based on their function
                pass
        except tk.TclError:
            pass

        # Recursively update children
        for child in widget.winfo_children():
            self._update_widget_colors(child, theme)

    def setup_styles(self):
        """Configure ttk styles based on current theme"""
        style = ttk.Style()
        style.theme_use('clam')

        # Get colors from current theme
        theme = self.get_theme_colors()
        bg_dark = theme["bg_dark"]
        bg_card = theme["bg_card"]
        bg_hover = theme["bg_hover"]
        fg_primary = theme["fg_primary"]
        fg_secondary = theme["fg_secondary"]
        accent_green = theme["accent_green"]
        accent_red = theme["accent_red"]
        accent_blue = theme["accent_blue"]
        accent_yellow = theme["accent_yellow"]

        # Store colors for use in other methods
        self.colors = theme
        
        # Treeview
        style.configure("Treeview",
                       background=bg_card,
                       foreground=fg_primary,
                       fieldbackground=bg_card,
                       borderwidth=0,
                       font=('Consolas', 10))
        style.configure("Treeview.Heading",
                       background=bg_dark,
                       foreground=fg_secondary,
                       font=('Segoe UI', 10, 'bold'))
        style.map("Treeview",
                 background=[('selected', bg_hover)])
        
        # Buttons
        style.configure("Start.TButton",
                       background=accent_green,
                       foreground=bg_dark,
                       font=('Segoe UI', 10, 'bold'),
                       padding=(20, 10))
        style.configure("Stop.TButton",
                       background=accent_red,
                       foreground=fg_primary,
                       font=('Segoe UI', 10, 'bold'),
                       padding=(20, 10))
        style.configure("TButton",
                       background=bg_hover,
                       foreground=fg_primary,
                       font=('Segoe UI', 10),
                       padding=(15, 8))
        
        # Labels
        style.configure("Title.TLabel",
                       background=bg_dark,
                       foreground=fg_primary,
                       font=('Segoe UI', 24, 'bold'))
        style.configure("Subtitle.TLabel",
                       background=bg_dark,
                       foreground=fg_secondary,
                       font=('Segoe UI', 11))
        style.configure("Card.TLabel",
                       background=bg_card,
                       foreground=fg_primary,
                       font=('Segoe UI', 11))
        style.configure("Stat.TLabel",
                       background=bg_card,
                       foreground=accent_blue,
                       font=('Consolas', 18, 'bold'))
        style.configure("StatLabel.TLabel",
                       background=bg_card,
                       foreground=fg_secondary,
                       font=('Segoe UI', 9))
        
        # Frames
        style.configure("Card.TFrame",
                       background=bg_card)
        style.configure("Dark.TFrame",
                       background=bg_dark)
        
        # Entry
        style.configure("TEntry",
                       fieldbackground=bg_hover,
                       foreground=fg_primary,
                       insertcolor=fg_primary)
        
        # Notebook
        style.configure("TNotebook",
                       background=bg_dark,
                       borderwidth=0)
        style.configure("TNotebook.Tab",
                       background=bg_card,
                       foreground=fg_secondary,
                       padding=(20, 10),
                       font=('Segoe UI', 10))
        style.map("TNotebook.Tab",
                 background=[('selected', bg_hover)],
                 foreground=[('selected', fg_primary)])
                 
    def build_ui(self):
        """Build the main UI"""
        # Use colors from current theme
        bg_dark = self.colors["bg_dark"]
        bg_card = self.colors["bg_card"]
        fg_primary = self.colors["fg_primary"]
        fg_secondary = self.colors["fg_secondary"]

        # Configure root window background
        self.root.configure(bg=bg_dark)
        
        # Main container
        main_frame = ttk.Frame(self.root, style="Dark.TFrame")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Header
        header_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        header_frame.pack(fill=tk.X, pady=(0, 20))
        
        title_label = ttk.Label(header_frame, text="🚀 Pump.fun Monitor",
                               style="Title.TLabel")
        title_label.pack(side=tk.LEFT)
        
        # Control buttons
        btn_frame = ttk.Frame(header_frame, style="Dark.TFrame")
        btn_frame.pack(side=tk.RIGHT)
        
        self.start_btn = tk.Button(btn_frame, text="▶ Start Monitoring",
                                   bg="#3fb950", fg="#0d1117",
                                   font=('Segoe UI', 10, 'bold'),
                                   relief=tk.FLAT, padx=20, pady=8,
                                   cursor="hand2",
                                   command=self.toggle_monitoring)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        settings_btn = tk.Button(btn_frame, text="⚙ Settings",
                                bg="#21262d", fg="#f0f6fc",
                                font=('Segoe UI', 10),
                                relief=tk.FLAT, padx=15, pady=8,
                                cursor="hand2",
                                command=self.open_settings)
        settings_btn.pack(side=tk.LEFT, padx=5)
        
        # Stats cards
        stats_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        stats_frame.pack(fill=tk.X, pady=(0, 20))
        
        self.stats = {}
        stat_configs = [
            ("tracking", "Tracking", "0"),
            ("alerts", "Alerts", "0"),
            ("volume", "Total Vol (5m)", "$0"),
            ("avg_mcap", "Avg MCap", "$0"),
        ]
        
        for i, (key, label, default) in enumerate(stat_configs):
            card = tk.Frame(stats_frame, bg=bg_card, padx=20, pady=15)
            card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0 if i == 0 else 10, 0))
            
            value_label = tk.Label(card, text=default, bg=bg_card, fg="#58a6ff",
                                  font=('Consolas', 20, 'bold'))
            value_label.pack(anchor=tk.W)
            
            name_label = tk.Label(card, text=label, bg=bg_card, fg=fg_secondary,
                                 font=('Segoe UI', 9))
            name_label.pack(anchor=tk.W)
            
            self.stats[key] = value_label
        
        # Main content area with notebook
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True)
        
        # Tokens tab
        tokens_frame = ttk.Frame(notebook, style="Card.TFrame")
        notebook.add(tokens_frame, text="  📊 Live Tokens  ")
        
        # Token table
        columns = ("symbol", "name", "age", "mcap", "vol5m", "holders", "ratio", "progress")
        self.tree = ttk.Treeview(tokens_frame, columns=columns, show="headings",
                                 selectmode="browse", height=15)
        
        # Configure columns
        col_configs = [
            ("symbol", "Symbol", 80),
            ("name", "Name", 120),
            ("age", "Age", 70),
            ("mcap", "Market Cap", 100),
            ("vol5m", "Vol (5m)", 90),
            ("holders", "Holders", 70),
            ("ratio", "Buy/Sell", 80),
            ("progress", "Progress", 80),
        ]
        
        for col_id, heading, width in col_configs:
            self.tree.heading(col_id, text=heading)
            self.tree.column(col_id, width=width, anchor=tk.CENTER)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(tokens_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Bind double-click to open in browser
        self.tree.bind("<Double-1>", self.open_token_page)
        
        # Alerts tab
        alerts_frame = ttk.Frame(notebook, style="Card.TFrame")
        notebook.add(alerts_frame, text="  🔔 Alerts  ")
        
        self.alerts_text = tk.Text(alerts_frame, bg=bg_card, fg=fg_primary,
                                   font=('Consolas', 10), relief=tk.FLAT,
                                   padx=15, pady=15)
        self.alerts_text.pack(fill=tk.BOTH, expand=True)
        self.alerts_text.insert(tk.END, "Alerts will appear here when tokens meet your criteria...\n")
        self.alerts_text.config(state=tk.DISABLED)

        # Presets tab
        presets_frame = ttk.Frame(notebook, style="Card.TFrame")
        notebook.add(presets_frame, text="  ⚡ Presets  ")

        # Create presets content
        self.build_presets_tab(presets_frame, bg_card, fg_primary, fg_secondary)

        # Status bar
        status_frame = tk.Frame(main_frame, bg=bg_dark)
        status_frame.pack(fill=tk.X, pady=(15, 0))

        self.status_label = tk.Label(status_frame, text="● Idle", bg=bg_dark,
                                     fg=fg_secondary, font=('Segoe UI', 9))
        self.status_label.pack(side=tk.LEFT)

        mode_text = "Mode: Mock Data (for testing)" if self.use_mock else "Mode: LIVE (Helius WebSocket)"
        mode_color = fg_secondary if self.use_mock else "#3fb950"
        self.mode_label = tk.Label(status_frame, text=mode_text,
                                   bg=bg_dark, fg=mode_color, font=('Segoe UI', 9))
        self.mode_label.pack(side=tk.RIGHT)
        
    def toggle_monitoring(self):
        """Start/stop monitoring"""
        if not self.monitoring:
            self.start_monitoring()
        else:
            self.stop_monitoring()
    
    def start_monitoring(self):
        """Start the monitoring process"""
        # Validate API key for live mode
        if not self.use_mock and not self.helius_api_key:
            messagebox.showerror(
                "API Key Required",
                "Please set your Helius API key in Settings before using live mode."
            )
            return

        self.monitoring = True
        self.start_btn.config(text="⏹ Stop", bg="#f85149")

        if self.use_mock:
            self.status_label.config(text="● Monitoring (Mock)...", fg="#d29922")
        else:
            self.status_label.config(text="● Monitoring (LIVE)...", fg="#3fb950")
            self.add_alert("🔌 Connecting to Helius WebSocket...")

        # Start fetcher with correct mode
        self.fetcher.helius_api_key = self.helius_api_key
        self.fetcher.start_monitoring(self.on_token_update, use_mock=self.use_mock)

        # Start UI update loop
        self.update_ui()
        
    def stop_monitoring(self):
        """Stop the monitoring process"""
        self.monitoring = False
        self.fetcher.stop_monitoring()
        self.start_btn.config(text="▶ Start Monitoring", bg="#3fb950")
        self.status_label.config(text="● Stopped", fg="#8b949e")
        
    def on_token_update(self, action: str, token: Token):
        """Handle token updates from the fetcher (called from background thread)"""
        # Schedule UI update on main thread
        self.root.after(0, lambda: self._process_token_update(action, token))
        
    def _process_token_update(self, action: str, token: Token):
        """Process token update on main thread"""
        if action == "new":
            self.tokens[token.address] = token
            self.add_alert(f"🆕 New token: {token.symbol} ({token.name}) - MCap: ${token.market_cap:,.0f}")
        elif action == "update":
            self.tokens[token.address] = token
            # Check for alerts
            if token.meets_alert_criteria(ALERT_THRESHOLDS):
                self.add_alert(f"🔥 ALERT: {token.symbol} - MCap: ${token.market_cap:,.0f}, "
                             f"Vol: ${token.volume_5m:,.0f}, Holders: {token.holders}")
        elif action == "remove":
            if token.address in self.tokens:
                del self.tokens[token.address]
    
    def update_ui(self):
        """Update the UI with current data"""
        if not self.monitoring:
            return
            
        # Update tree
        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Sort by market cap
        sorted_tokens = sorted(self.tokens.values(), key=lambda t: t.market_cap, reverse=True)
        
        for token in sorted_tokens:
            age_str = f"{token.age_minutes:.0f}m"
            mcap_str = f"${token.market_cap:,.0f}"
            vol_str = f"${token.volume_5m:,.0f}"
            ratio_str = f"{token.buy_sell_ratio:.1f}x"
            progress_str = f"{token.bonding_progress:.1f}%"
            
            # Color tag based on performance
            tag = ""
            if token.buy_sell_ratio > 2:
                tag = "hot"
            elif token.buy_sell_ratio < 0.8:
                tag = "cold"
            
            self.tree.insert("", tk.END, values=(
                token.symbol, token.name, age_str, mcap_str,
                vol_str, token.holders, ratio_str, progress_str
            ), tags=(tag,))
        
        # Configure tags
        self.tree.tag_configure("hot", foreground="#3fb950")
        self.tree.tag_configure("cold", foreground="#f85149")
        
        # Update stats
        total_tokens = len(self.tokens)
        total_volume = sum(t.volume_5m for t in self.tokens.values())
        avg_mcap = sum(t.market_cap for t in self.tokens.values()) / max(total_tokens, 1)
        alert_count = len([t for t in self.tokens.values() if t.meets_alert_criteria(ALERT_THRESHOLDS)])
        
        self.stats["tracking"].config(text=str(total_tokens))
        self.stats["alerts"].config(text=str(alert_count))
        self.stats["volume"].config(text=f"${total_volume:,.0f}")
        self.stats["avg_mcap"].config(text=f"${avg_mcap:,.0f}")
        
        # Schedule next update
        self.root.after(1000, self.update_ui)
        
    def add_alert(self, message: str):
        """Add an alert message"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        alert_text = f"[{timestamp}] {message}\n"
        
        self.alerts_text.config(state=tk.NORMAL)
        self.alerts_text.insert(tk.END, alert_text)
        self.alerts_text.see(tk.END)
        self.alerts_text.config(state=tk.DISABLED)
        
    def build_presets_tab(self, parent, bg_card, fg_primary, fg_secondary):
        """Build the presets tab content"""
        theme = self.get_theme_colors()
        bg_dark = theme["bg_dark"]
        accent_green = theme["accent_green"]
        accent_red = theme["accent_red"]

        # Create scrollable canvas
        canvas = tk.Canvas(parent, bg=bg_dark, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=bg_dark)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        # Enable mousewheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        canvas.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        scrollbar.pack(side="right", fill="y")

        # Header
        header = tk.Label(scrollable_frame, text="Optimal Presets",
                         bg=bg_dark, fg=fg_primary,
                         font=('Segoe UI', 16, 'bold'))
        header.pack(pady=(10, 5), anchor=tk.W, padx=10)

        subtitle = tk.Label(scrollable_frame,
                           text="Research-backed configurations for different trading strategies",
                           bg=bg_dark, fg=fg_secondary,
                           font=('Segoe UI', 10))
        subtitle.pack(pady=(0, 15), anchor=tk.W, padx=10)

        # Risk level colors
        risk_colors = {
            "Extreme": "#ff4444",
            "Very High": "#ff6b6b",
            "High": "#ffa94d",
            "Medium-High": "#ffd43b",
            "Medium": "#69db7c",
            "Medium-Low": "#38d9a9",
            "Low": "#20c997",
        }

        # Create preset cards
        for preset_name, preset_data in PRESETS.items():
            # Card frame
            card = tk.Frame(scrollable_frame, bg=bg_card, relief=tk.FLAT)
            card.pack(fill=tk.X, padx=10, pady=8)

            # Inner padding frame
            inner = tk.Frame(card, bg=bg_card)
            inner.pack(fill=tk.X, padx=15, pady=12)

            # Header row with name and risk badge
            header_row = tk.Frame(inner, bg=bg_card)
            header_row.pack(fill=tk.X)

            name_label = tk.Label(header_row, text=preset_name,
                                 bg=bg_card, fg=fg_primary,
                                 font=('Segoe UI', 12, 'bold'))
            name_label.pack(side=tk.LEFT)

            # Risk level badge
            risk_level = preset_data.get("risk_level", "Medium")
            risk_color = risk_colors.get(risk_level, fg_secondary)
            risk_badge = tk.Label(header_row, text=f" {risk_level} ",
                                 bg=risk_color, fg=bg_dark,
                                 font=('Segoe UI', 9, 'bold'))
            risk_badge.pack(side=tk.LEFT, padx=(10, 0))

            # Load button
            load_btn = tk.Button(header_row, text="Load Preset",
                                bg=accent_green, fg=bg_dark,
                                font=('Segoe UI', 9, 'bold'),
                                relief=tk.FLAT, padx=12, pady=3,
                                cursor="hand2",
                                command=lambda p=preset_name: self.load_preset(p))
            load_btn.pack(side=tk.RIGHT)

            # Description
            desc_label = tk.Label(inner, text=preset_data.get("description", ""),
                                 bg=bg_card, fg=fg_secondary,
                                 font=('Segoe UI', 10), wraplength=500,
                                 justify=tk.LEFT)
            desc_label.pack(fill=tk.X, pady=(8, 5), anchor=tk.W)

            # Strategy
            strategy = preset_data.get("strategy", "")
            if strategy:
                strategy_label = tk.Label(inner, text=f"Strategy: {strategy}",
                                         bg=bg_card, fg=accent_green,
                                         font=('Segoe UI', 9, 'italic'), wraplength=500,
                                         justify=tk.LEFT)
                strategy_label.pack(fill=tk.X, pady=(0, 8), anchor=tk.W)

            # Settings grid
            settings_frame = tk.Frame(inner, bg=bg_card)
            settings_frame.pack(fill=tk.X, pady=(5, 0))

            alert_thresholds = preset_data.get("alert_thresholds", {})
            removal_threshold = preset_data.get("removal_threshold", {})

            # Create settings display
            settings_text = []
            if "min_market_cap" in alert_thresholds:
                settings_text.append(f"MCap: ${alert_thresholds['min_market_cap']:,}-${alert_thresholds.get('max_market_cap', 0):,}")
            if "min_holders" in alert_thresholds:
                settings_text.append(f"Holders: {alert_thresholds['min_holders']}+")
            if "min_volume_5m" in alert_thresholds:
                settings_text.append(f"Vol: ${alert_thresholds['min_volume_5m']:,}+")
            if "buy_sell_ratio" in alert_thresholds:
                settings_text.append(f"B/S: {alert_thresholds['buy_sell_ratio']}+")
            if "min_market_cap" in removal_threshold:
                settings_text.append(f"Remove below: ${removal_threshold['min_market_cap']:,}")

            settings_str = "  |  ".join(settings_text)
            settings_label = tk.Label(settings_frame, text=settings_str,
                                     bg=bg_card, fg=fg_secondary,
                                     font=('Consolas', 9))
            settings_label.pack(anchor=tk.W)

        # Footer note
        footer = tk.Label(scrollable_frame,
                         text="Note: These presets are based on pump.fun market analysis. Always do your own research.",
                         bg=bg_dark, fg=fg_secondary,
                         font=('Segoe UI', 9, 'italic'))
        footer.pack(pady=(15, 10), anchor=tk.W, padx=10)

    def load_preset(self, preset_name):
        """Load a preset configuration"""
        if preset_name not in PRESETS:
            return

        preset = PRESETS[preset_name]

        # Update alert thresholds
        alert_thresholds = preset.get("alert_thresholds", {})
        for key, value in alert_thresholds.items():
            if key in ALERT_THRESHOLDS:
                ALERT_THRESHOLDS[key] = value

        # Update removal threshold
        removal_threshold = preset.get("removal_threshold", {})
        for key, value in removal_threshold.items():
            if key in REMOVAL_THRESHOLD:
                REMOVAL_THRESHOLD[key] = value

        # Save to file
        self.save_settings()

        # Notify user
        self.add_alert(f"Loaded preset: {preset_name} (Risk: {preset.get('risk_level', 'Unknown')})")
        self.add_alert(f"  MCap range: ${ALERT_THRESHOLDS['min_market_cap']:,}-${ALERT_THRESHOLDS['max_market_cap']:,}")
        self.add_alert(f"  Remove below: ${REMOVAL_THRESHOLD['min_market_cap']:,}")

    def open_token_page(self, event):
        """Open token page in browser on double-click"""
        selection = self.tree.selection()
        if selection:
            item = self.tree.item(selection[0])
            symbol = item['values'][0]
            # Find token by symbol
            for token in self.tokens.values():
                if token.symbol == symbol:
                    url = f"https://pump.fun/{token.address}"
                    webbrowser.open(url)
                    break
    
    def open_settings(self):
        """Open settings dialog"""
        # Use current theme colors
        theme = self.get_theme_colors()
        bg_dark = theme["bg_dark"]
        bg_card = theme["bg_card"]
        fg_primary = theme["fg_primary"]
        fg_secondary = theme["fg_secondary"]
        accent_green = theme["accent_green"]

        settings_window = tk.Toplevel(self.root)
        settings_window.title("Settings")
        settings_window.geometry("500x800")
        settings_window.configure(bg=bg_dark)
        settings_window.transient(self.root)
        settings_window.grab_set()

        # Create scrollable canvas
        canvas = tk.Canvas(settings_window, bg=bg_dark, highlightthickness=0)
        scrollbar = ttk.Scrollbar(settings_window, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=bg_dark)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        # Enable mousewheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        canvas.pack(side="left", fill="both", expand=True, padx=20)
        scrollbar.pack(side="right", fill="y")

        # ---- Theme Selection Section ----
        theme_title = tk.Label(scrollable_frame, text="Theme",
                              bg=bg_dark, fg=fg_primary,
                              font=('Segoe UI', 14, 'bold'))
        theme_title.pack(pady=(20, 15), anchor=tk.W)

        theme_frame = tk.Frame(scrollable_frame, bg=bg_dark)
        theme_frame.pack(fill=tk.X, pady=10)

        theme_lbl = tk.Label(theme_frame, text="Select Theme", bg=bg_dark, fg=fg_secondary,
                            font=('Segoe UI', 10))
        theme_lbl.pack(anchor=tk.W)

        # Theme dropdown
        self.theme_var = tk.StringVar(value=self.current_theme)

        # Create themed listbox for theme selection
        theme_list_frame = tk.Frame(theme_frame, bg=bg_card)
        theme_list_frame.pack(fill=tk.X, pady=(5, 0))

        theme_listbox = tk.Listbox(theme_list_frame, bg=bg_card, fg=fg_primary,
                                   font=('Segoe UI', 10), relief=tk.FLAT,
                                   selectbackground=theme["bg_hover"],
                                   selectforeground=fg_primary,
                                   height=8, exportselection=False)

        theme_scrollbar = ttk.Scrollbar(theme_list_frame, orient="vertical", command=theme_listbox.yview)
        theme_listbox.configure(yscrollcommand=theme_scrollbar.set)

        # Group themes by category
        dark_themes = [t for t in THEMES.keys() if t.startswith("Dark") or t in ["Midnight", "Dracula", "Nord", "Monokai", "Gruvbox Dark", "Solarized Dark", "Ocean", "Cyberpunk", "Matrix", "Hacker", "Sunset", "Coffee", "Mint", "Rose", "Slate", "High Contrast"]]
        light_themes = [t for t in THEMES.keys() if t.startswith("Light") or t in ["Cream", "Paper", "Gruvbox Light"]]

        theme_listbox.insert(tk.END, "── Dark Themes ──")
        for t in sorted(dark_themes):
            theme_listbox.insert(tk.END, f"  {t}")

        theme_listbox.insert(tk.END, "")
        theme_listbox.insert(tk.END, "── Light Themes ──")
        for t in sorted(light_themes):
            theme_listbox.insert(tk.END, f"  {t}")

        # Select current theme
        for i in range(theme_listbox.size()):
            item = theme_listbox.get(i).strip()
            if item == self.current_theme:
                theme_listbox.selection_set(i)
                theme_listbox.see(i)
                break

        theme_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        theme_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Preview button
        def preview_theme():
            selection = theme_listbox.curselection()
            if selection:
                selected = theme_listbox.get(selection[0]).strip()
                if selected and not selected.startswith("──") and selected in THEMES:
                    self.apply_theme(selected)
                    self.theme_var.set(selected)
                    # Close settings dialog and reopen with new theme colors
                    settings_window.destroy()
                    canvas.unbind_all("<MouseWheel>")
                    # Reopen settings with new theme
                    self.root.after(100, self.open_settings)

        preview_btn = tk.Button(theme_frame, text="Apply Theme",
                               bg=accent_green, fg=bg_dark,
                               font=('Segoe UI', 10, 'bold'),
                               relief=tk.FLAT, padx=15, pady=5,
                               cursor="hand2", command=preview_theme)
        preview_btn.pack(pady=(10, 0), anchor=tk.W)

        # Separator
        sep0 = tk.Frame(scrollable_frame, bg=bg_card, height=1)
        sep0.pack(fill=tk.X, pady=20)

        # ---- Connection Settings Section ----
        conn_title = tk.Label(scrollable_frame, text="Connection Settings",
                              bg=bg_dark, fg=fg_primary,
                              font=('Segoe UI', 14, 'bold'))
        conn_title.pack(pady=(0, 15), anchor=tk.W)

        # Data mode toggle
        mode_frame = tk.Frame(scrollable_frame, bg=bg_dark)
        mode_frame.pack(fill=tk.X, pady=10)

        mode_lbl = tk.Label(mode_frame, text="Data Mode", bg=bg_dark, fg=fg_secondary,
                           font=('Segoe UI', 10))
        mode_lbl.pack(anchor=tk.W)

        self.mode_var = tk.StringVar(value="mock" if self.use_mock else "live")

        mode_btn_frame = tk.Frame(mode_frame, bg=bg_dark)
        mode_btn_frame.pack(fill=tk.X, pady=(5, 0))

        mock_rb = tk.Radiobutton(mode_btn_frame, text="Mock Data (Testing)",
                                  variable=self.mode_var, value="mock",
                                  bg=bg_dark, fg=fg_primary, selectcolor=bg_card,
                                  activebackground=bg_dark, activeforeground=fg_primary,
                                  font=('Segoe UI', 10))
        mock_rb.pack(anchor=tk.W)

        live_rb = tk.Radiobutton(mode_btn_frame, text="Live Data (Helius WebSocket)",
                                  variable=self.mode_var, value="live",
                                  bg=bg_dark, fg=accent_green, selectcolor=bg_card,
                                  activebackground=bg_dark, activeforeground=accent_green,
                                  font=('Segoe UI', 10))
        live_rb.pack(anchor=tk.W)

        # Helius API Key
        api_frame = tk.Frame(scrollable_frame, bg=bg_dark)
        api_frame.pack(fill=tk.X, pady=15)

        api_lbl = tk.Label(api_frame, text="Helius API Key", bg=bg_dark, fg=fg_secondary,
                          font=('Segoe UI', 10))
        api_lbl.pack(anchor=tk.W)

        self.api_key_var = tk.StringVar(value=self.helius_api_key)
        api_entry = tk.Entry(api_frame, textvariable=self.api_key_var, bg=bg_card,
                            fg=fg_primary, font=('Consolas', 10), relief=tk.FLAT,
                            insertbackground=fg_primary, show="*")
        api_entry.pack(fill=tk.X, pady=(5, 0), ipady=8)

        api_hint = tk.Label(api_frame, text="Get a free key at helius.dev",
                           bg=bg_dark, fg=fg_secondary, font=('Segoe UI', 9))
        api_hint.pack(anchor=tk.W, pady=(5, 0))

        # Separator
        sep = tk.Frame(scrollable_frame, bg=bg_card, height=1)
        sep.pack(fill=tk.X, pady=20)

        # ---- Alert Thresholds Section ----
        alert_title = tk.Label(scrollable_frame, text="Alert Thresholds",
                              bg=bg_dark, fg=fg_primary,
                              font=('Segoe UI', 14, 'bold'))
        alert_title.pack(pady=(0, 15), anchor=tk.W)

        self.setting_vars = {}
        settings_config = [
            ("min_market_cap", "Min Market Cap ($) for Alerts", ALERT_THRESHOLDS["min_market_cap"]),
            ("max_market_cap", "Max Market Cap ($)", ALERT_THRESHOLDS["max_market_cap"]),
            ("min_holders", "Min Holders", ALERT_THRESHOLDS["min_holders"]),
            ("min_volume_5m", "Min 5m Volume ($)", ALERT_THRESHOLDS["min_volume_5m"]),
            ("buy_sell_ratio", "Min Buy/Sell Ratio", ALERT_THRESHOLDS["buy_sell_ratio"]),
        ]

        # Separator before removal settings
        sep2 = tk.Frame(scrollable_frame, bg=bg_card, height=1)
        sep2.pack(fill=tk.X, pady=15)

        removal_title = tk.Label(scrollable_frame, text="Token Removal Settings",
                                bg=bg_dark, fg=fg_primary,
                                font=('Segoe UI', 14, 'bold'))
        removal_title.pack(pady=(0, 15), anchor=tk.W)

        # Removal threshold setting
        removal_frame = tk.Frame(scrollable_frame, bg=bg_dark)
        removal_frame.pack(fill=tk.X, pady=8)

        removal_lbl = tk.Label(removal_frame, text="Remove tokens below MCap ($)",
                              bg=bg_dark, fg=fg_secondary, font=('Segoe UI', 10))
        removal_lbl.pack(anchor=tk.W)

        self.removal_mcap_var = tk.StringVar(value=str(REMOVAL_THRESHOLD.get("min_market_cap", 1000)))
        removal_entry = tk.Entry(removal_frame, textvariable=self.removal_mcap_var, bg=bg_card,
                                fg=fg_primary, font=('Consolas', 11), relief=tk.FLAT,
                                insertbackground=fg_primary)
        removal_entry.pack(fill=tk.X, pady=(5, 0), ipady=8)

        removal_hint = tk.Label(removal_frame, text="Tokens with market cap below this will be removed from tracking",
                               bg=bg_dark, fg=fg_secondary, font=('Segoe UI', 9))
        removal_hint.pack(anchor=tk.W, pady=(5, 0))

        # Separator before alert thresholds
        sep3 = tk.Frame(scrollable_frame, bg=bg_card, height=1)
        sep3.pack(fill=tk.X, pady=15)

        for key, label, default in settings_config:
            frame = tk.Frame(scrollable_frame, bg=bg_dark)
            frame.pack(fill=tk.X, pady=8)

            lbl = tk.Label(frame, text=label, bg=bg_dark, fg=fg_secondary,
                          font=('Segoe UI', 10))
            lbl.pack(anchor=tk.W)

            var = tk.StringVar(value=str(default))
            self.setting_vars[key] = var

            entry = tk.Entry(frame, textvariable=var, bg=bg_card, fg=fg_primary,
                            font=('Consolas', 11), relief=tk.FLAT,
                            insertbackground=fg_primary)
            entry.pack(fill=tk.X, pady=(5, 0), ipady=8)

        # Save button
        def save_settings():
            # Save connection settings
            self.use_mock = (self.mode_var.get() == "mock")
            self.helius_api_key = self.api_key_var.get().strip()

            # Update mode label
            if self.use_mock:
                self.mode_label.config(text="Mode: Mock Data (for testing)", fg=fg_secondary)
            else:
                self.mode_label.config(text="Mode: LIVE (Helius WebSocket)", fg=accent_green)

            # Save removal threshold
            try:
                REMOVAL_THRESHOLD["min_market_cap"] = float(self.removal_mcap_var.get())
            except ValueError:
                pass

            # Save alert thresholds
            for key, var in self.setting_vars.items():
                try:
                    ALERT_THRESHOLDS[key] = float(var.get())
                except ValueError:
                    pass

            # Save to file
            self.save_settings()

            settings_window.destroy()
            self.add_alert(f"⚙ Settings saved - Removing tokens below ${REMOVAL_THRESHOLD['min_market_cap']:,.0f}")

            if not self.use_mock and not self.helius_api_key:
                self.add_alert("⚠ Warning: Live mode requires a Helius API key")

        save_btn = tk.Button(scrollable_frame, text="Save Settings",
                            bg=accent_green, fg=bg_dark,
                            font=('Segoe UI', 10, 'bold'),
                            relief=tk.FLAT, padx=20, pady=10,
                            cursor="hand2", command=save_settings)
        save_btn.pack(pady=25)
        
    def on_close(self):
        """Handle window close"""
        self.stop_monitoring()
        self.root.destroy()
        
    def run(self):
        """Start the application"""
        self.root.mainloop()


# ============================================================================
# Entry Point
# ============================================================================

if __name__ == "__main__":
    print("=" * 50)
    print("  Pump.fun Token Monitor")
    print("=" * 50)
    print()

    # Check dependencies
    if not SOLANA_AVAILABLE:
        print("Note: Solana libraries not installed (optional)")
        print("  Install: pip install solana solders --break-system-packages")
        print()

    if not WEBSOCKETS_AVAILABLE:
        print("Warning: websockets not installed (required for live data)")
        print("  Install: pip install websockets --break-system-packages")
        print()

    if HELIUS_API_KEY:
        print("Helius API key configured")
    else:
        print("No Helius API key set - configure in Settings for live data")
        print("  Get a free key at: https://helius.dev")
    print()

    print("Starting GUI...")
    print("  - Use Settings to configure mock/live mode")
    print("  - Live mode requires Helius API key")
    print()

    app = PumpFunMonitorApp()
    app.run()
