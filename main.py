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
    market_cap: float = 0.0
    volume_5m: float = 0.0
    volume_1h: float = 0.0
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

    def fetch_bonding_curve_data(self, mint_address: str) -> dict:
        """Fetch bonding curve state for a pump.fun token"""
        curve_data = {
            "market_cap": 0.0,
            "bonding_progress": 0.0,
            "volume_5m": 0.0,
        }

        # For now, we'll use the pump.fun API if available
        # The bonding curve PDA can be derived and read from chain
        try:
            # Try pump.fun's public API
            api_url = f"https://frontend-api.pump.fun/coins/{mint_address}"
            response = requests.get(api_url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                curve_data["market_cap"] = float(data.get("usd_market_cap", 0))
                # Progress is based on bonding curve completion (target ~$69k for graduation)
                curve_data["bonding_progress"] = min(100, (curve_data["market_cap"] / 69000) * 100)
        except:
            pass

        return curve_data

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

        # Create token object
        token = Token(
            address=mint_address,
            name=metadata["name"],
            symbol=metadata["symbol"],
            created_at=time.time(),
            market_cap=curve_data["market_cap"],
            bonding_progress=curve_data["bonding_progress"],
            volume_5m=curve_data["volume_5m"],
            holders=1,
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

                token = Token(
                    address=mint,
                    name=metadata["name"],
                    symbol=metadata["symbol"],
                    created_at=time.time(),
                    market_cap=curve_data["market_cap"],
                    bonding_progress=curve_data["bonding_progress"],
                    volume_5m=curve_data["volume_5m"],
                    holders=1,
                    buys=1 if trade_type == "buy" else 0,
                    sells=1 if trade_type == "sell" else 0,
                )
                self.known_tokens[mint] = token
                self.update_queue.put(("new", token))
                print(f"[NEW] {token.symbol} ({token.name}) - MCap: ${token.market_cap:,.0f}", flush=True)

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

                    # Start listener and queue processor concurrently
                    listener_task = asyncio.create_task(self.helius_ws.listen())
                    processor_task = asyncio.create_task(
                        self._process_queue_async(callback)
                    )

                    await asyncio.gather(listener_task, processor_task)

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

        # Data mode settings
        self.use_mock = True  # Set to False for live data
        self.helius_api_key = HELIUS_API_KEY

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
        
    def setup_styles(self):
        """Configure ttk styles for dark theme"""
        style = ttk.Style()
        style.theme_use('clam')
        
        # Colors
        bg_dark = "#0d1117"
        bg_card = "#161b22"
        bg_hover = "#21262d"
        fg_primary = "#f0f6fc"
        fg_secondary = "#8b949e"
        accent_green = "#3fb950"
        accent_red = "#f85149"
        accent_blue = "#58a6ff"
        accent_yellow = "#d29922"
        
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
        bg_dark = "#0d1117"
        bg_card = "#161b22"
        fg_primary = "#f0f6fc"
        fg_secondary = "#8b949e"
        
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
        settings_window = tk.Toplevel(self.root)
        settings_window.title("Settings")
        settings_window.geometry("450x650")
        settings_window.configure(bg="#0d1117")
        settings_window.transient(self.root)
        settings_window.grab_set()

        bg_card = "#161b22"
        fg_primary = "#f0f6fc"
        fg_secondary = "#8b949e"

        # Create scrollable canvas
        canvas = tk.Canvas(settings_window, bg="#0d1117", highlightthickness=0)
        scrollbar = ttk.Scrollbar(settings_window, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg="#0d1117")

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True, padx=20)
        scrollbar.pack(side="right", fill="y")

        # ---- Connection Settings Section ----
        conn_title = tk.Label(scrollable_frame, text="Connection Settings",
                              bg="#0d1117", fg=fg_primary,
                              font=('Segoe UI', 14, 'bold'))
        conn_title.pack(pady=(20, 15), anchor=tk.W)

        # Data mode toggle
        mode_frame = tk.Frame(scrollable_frame, bg="#0d1117")
        mode_frame.pack(fill=tk.X, pady=10)

        mode_lbl = tk.Label(mode_frame, text="Data Mode", bg="#0d1117", fg=fg_secondary,
                           font=('Segoe UI', 10))
        mode_lbl.pack(anchor=tk.W)

        self.mode_var = tk.StringVar(value="mock" if self.use_mock else "live")

        mode_btn_frame = tk.Frame(mode_frame, bg="#0d1117")
        mode_btn_frame.pack(fill=tk.X, pady=(5, 0))

        mock_rb = tk.Radiobutton(mode_btn_frame, text="Mock Data (Testing)",
                                  variable=self.mode_var, value="mock",
                                  bg="#0d1117", fg=fg_primary, selectcolor=bg_card,
                                  activebackground="#0d1117", activeforeground=fg_primary,
                                  font=('Segoe UI', 10))
        mock_rb.pack(anchor=tk.W)

        live_rb = tk.Radiobutton(mode_btn_frame, text="Live Data (Helius WebSocket)",
                                  variable=self.mode_var, value="live",
                                  bg="#0d1117", fg="#3fb950", selectcolor=bg_card,
                                  activebackground="#0d1117", activeforeground="#3fb950",
                                  font=('Segoe UI', 10))
        live_rb.pack(anchor=tk.W)

        # Helius API Key
        api_frame = tk.Frame(scrollable_frame, bg="#0d1117")
        api_frame.pack(fill=tk.X, pady=15)

        api_lbl = tk.Label(api_frame, text="Helius API Key", bg="#0d1117", fg=fg_secondary,
                          font=('Segoe UI', 10))
        api_lbl.pack(anchor=tk.W)

        self.api_key_var = tk.StringVar(value=self.helius_api_key)
        api_entry = tk.Entry(api_frame, textvariable=self.api_key_var, bg=bg_card,
                            fg=fg_primary, font=('Consolas', 10), relief=tk.FLAT,
                            insertbackground=fg_primary, show="*")
        api_entry.pack(fill=tk.X, pady=(5, 0), ipady=8)

        api_hint = tk.Label(api_frame, text="Get a free key at helius.dev",
                           bg="#0d1117", fg=fg_secondary, font=('Segoe UI', 9))
        api_hint.pack(anchor=tk.W, pady=(5, 0))

        # Separator
        sep = tk.Frame(scrollable_frame, bg=bg_card, height=1)
        sep.pack(fill=tk.X, pady=20)

        # ---- Alert Thresholds Section ----
        alert_title = tk.Label(scrollable_frame, text="Alert Thresholds",
                              bg="#0d1117", fg=fg_primary,
                              font=('Segoe UI', 14, 'bold'))
        alert_title.pack(pady=(0, 15), anchor=tk.W)

        self.setting_vars = {}
        settings_config = [
            ("min_market_cap", "Min Market Cap ($)", ALERT_THRESHOLDS["min_market_cap"]),
            ("max_market_cap", "Max Market Cap ($)", ALERT_THRESHOLDS["max_market_cap"]),
            ("min_holders", "Min Holders", ALERT_THRESHOLDS["min_holders"]),
            ("min_volume_5m", "Min 5m Volume ($)", ALERT_THRESHOLDS["min_volume_5m"]),
            ("buy_sell_ratio", "Min Buy/Sell Ratio", ALERT_THRESHOLDS["buy_sell_ratio"]),
        ]

        for key, label, default in settings_config:
            frame = tk.Frame(scrollable_frame, bg="#0d1117")
            frame.pack(fill=tk.X, pady=8)

            lbl = tk.Label(frame, text=label, bg="#0d1117", fg=fg_secondary,
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
                self.mode_label.config(text="Mode: Mock Data (for testing)", fg="#8b949e")
            else:
                self.mode_label.config(text="Mode: LIVE (Helius WebSocket)", fg="#3fb950")

            # Save alert thresholds
            for key, var in self.setting_vars.items():
                try:
                    ALERT_THRESHOLDS[key] = float(var.get())
                except ValueError:
                    pass

            settings_window.destroy()
            self.add_alert("⚙ Settings updated")

            if not self.use_mock and not self.helius_api_key:
                self.add_alert("⚠ Warning: Live mode requires a Helius API key")

        save_btn = tk.Button(scrollable_frame, text="Save Settings",
                            bg="#3fb950", fg="#0d1117",
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
