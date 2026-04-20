"""
Nuvama VWAP Trading Strategy - AMO ORDERS

This version uses PlaceAMOTrade for After Market Orders (AMO).
Orders placed after market hours will be executed at market open next day.
Use nuvama_vwap_live.py for live market orders during trading hours.

AUTHENTICATION GUIDE:
====================
To generate a token (request ID) for Nuvama API:

1. URL to generate token:
   https://nuvamawealth.com/api-connect/login?api_key=YOUR_API_KEY

2. Steps:
   a) Replace YOUR_API_KEY with your actual API key
   b) Visit the URL in your browser
   c) You'll be redirected to a page with a request_id in the URL
   d) Copy the request_id from the redirect URL
   e) Use it with your API key and secret key in APIConnect()

3. Example:
   - Login URL: https://nuvamawealth.com/api-connect/login?api_key=ABC123XYZ
   - Redirect URL: https://nuvamawealth.com/api-connect/redirect?request_id=363932ced613ed37
   - Extract: request_id = "363932ced613ed37"

4. Use the helper function: get_request_id_from_url(api_key) to generate the URL

Documentation: https://www.nuvamawealth.com/library-documentation/#swagger-spec-for-our-equity-rest-project-uat-version
"""

import json
import datetime
import time
import sys
import pandas as pd
import requests
import webbrowser
from urllib.parse import urlparse, parse_qs
from APIConnect.APIConnect import APIConnect
from constants.exchange import ExchangeEnum
from constants.order_type import OrderTypeEnum
from constants.duration import DurationEnum
from constants.action import ActionEnum
from constants.product_code import ProductCodeENum
from constants.chart_exchange import ChartExchangeEnum
from constants.asset_type import AssetTypeEnum
from constants.eod_Interval import EODIntervalEnum

# Define lot sizes for different instruments
LOT_SIZES = {
    "TRENT25MARFUT": 100,  # Lot size for TRENT futures
    # Add more instruments and their respective lot sizes
}

def generate_token_url(api_key):
    """
    Generate the login URL to get the request ID (token).
    
    Args:
        api_key (str): Your Nuvama API key
        
    Returns:
        str: The login URL to visit
    """
    url = f"https://nuvamawealth.com/api-connect/login?api_key={api_key}"
    return url

def get_request_id_from_url(api_key, open_browser=True):
    """
    Generate token/request ID for Nuvama API authentication.
    
    Steps:
    1. Visit the login URL with your API key
    2. You'll be redirected to a page with a request ID in the URL
    3. Extract the request ID from the redirect URL
    4. Use this request ID with your API key and secret key to authenticate
    
    Args:
        api_key (str): Your Nuvama API key
        open_browser (bool): If True, opens the URL in browser automatically
        
    Returns:
        str: The login URL (you need to extract request_id from redirect URL manually)
    """
    login_url = generate_token_url(api_key)
    
    print("=" * 70)
    print("NUVAMA API TOKEN GENERATION")
    print("=" * 70)
    print(f"\nStep 1: Visit this URL in your browser:")
    print(f"\n{login_url}\n")
    print("Step 2: After visiting, you'll be redirected to a page.")
    print("Step 3: Check the redirect URL - it will contain a 'request_id' parameter.")
    print("Step 4: Copy that request_id and use it in APIConnect initialization.")
    print("\nExample redirect URL format:")
    print("https://nuvamawealth.com/api-connect/redirect?request_id=YOUR_REQUEST_ID_HERE")
    print("\n" + "=" * 70)
    
    if open_browser:
        try:
            webbrowser.open(login_url)
            print("\n✓ Browser opened with login URL")
        except Exception as e:
            print(f"\n⚠ Could not open browser automatically: {e}")
            print("Please copy and paste the URL above into your browser.")
    
    return login_url

def authenticate_nuvama(api_key, secret_key, request_id, download_contract=True, config_file=None):
    """
    Authenticate with Nuvama API using API key, secret key, and request ID.
    
    Args:
        api_key (str): Your Nuvama API key (also called vendor ID)
        secret_key (str): Your Nuvama API secret password
        request_id (str): Request ID obtained from login URL redirect
        download_contract (bool): Whether to download contract master file
        config_file (str): Path to configuration file (optional)
        
    Returns:
        APIConnect: Authenticated API connection object
    """
    print(f"\nAuthenticating with Nuvama API...")
    print(f"API Key: {api_key[:10]}...")
    
    try:
        if config_file:
            api_connect = APIConnect(api_key, secret_key, request_id, download_contract, config_file)
        else:
            api_connect = APIConnect(api_key, secret_key, request_id, download_contract)
        
        print("✓ Authentication successful!")
        return api_connect
    except Exception as e:
        print(f"✗ Authentication failed: {e}")
        raise

def check_market_hours():
    """
    Check if current time is within market hours (9:15 AM to 3:30 PM IST).
    
    Returns:
        bool: True if market is open, False otherwise
    """
    current_time = datetime.datetime.now().time()
    market_open = datetime.time(9, 15)
    market_close = datetime.time(15, 30)
    
    is_open = market_open <= current_time <= market_close
    
    if not is_open:
        print(f"⚠️  Market is currently CLOSED")
        print(f"   Current time: {current_time.strftime('%H:%M:%S')}")
        print(f"   Market hours: 09:15 - 15:30 IST")
        print(f"   Use nuvama_vwap.py for AMO orders outside market hours")
    else:
        print(f"✅ Market is OPEN")
        print(f"   Current time: {current_time.strftime('%H:%M:%S')}")
    
    return is_open

def get_lot_size(instrument):
    """Fetch lot size for the given instrument."""
    return LOT_SIZES.get(instrument, 1)  # Default to 1 if not found

def get_tick_size_from_price(price):
    """
    Determine tick size based on price range (NSE Equity standard).
    This is a fallback method if API doesn't provide tick size.
    
    Args:
        price (float): Stock price
        
    Returns:
        float: Tick size
    """
    if price < 25:
        return 0.05
    elif price < 100:
        return 0.10
    elif price < 500:
        return 0.25
    elif price < 1000:
        return 0.50
    else:
        return 1.00

def get_tick_size_from_symbol(api_connect, symbol):
    """
    Get tick size based on price. For NSE equity, tick size is determined by price range.
    This follows NSE standard tick size rules.
    
    Args:
        api_connect: APIConnect instance (not used but kept for API compatibility)
        symbol (str): Symbol in format "TOKEN_EXCHANGE" (e.g., "18143_NSE")
        
    Returns:
        float: Tick size (None to trigger price-based calculation)
    """
    # We'll use price-based calculation which is standard for NSE equity
    return None  # Will use price-based calculation in round_to_tick_size

def round_to_tick_size(price, tick_size):
    """
    Round price to nearest valid tick size.
    
    Args:
        price (float): Original price
        tick_size (float): Tick size (e.g., 0.05, 0.10, 0.25, 0.50, 1.00)
        
    Returns:
        float: Price rounded to nearest tick size
    """
    if tick_size is None or tick_size <= 0:
        # Fallback: determine tick size from price
        tick_size = get_tick_size_from_price(price)
    
    # Round to nearest tick size
    rounded_price = round(price / tick_size) * tick_size
    
    # Ensure we don't round to 0 or negative
    if rounded_price <= 0:
        rounded_price = tick_size
    
    return round(rounded_price, 2)

def calculate_vwap(df):
    """
    Calculates the Volume Weighted Average Price (VWAP) for a DataFrame.
    The VWAP calculation resets for each new trading day.
    """
    df['Date'] = pd.to_datetime(df['Date'])
    df['Typical Price'] = (df['High'] + df['Low'] + df['Close']) / 3
    df['TPV'] = df['Typical Price'] * df['Volume']
    
    # Reset VWAP calculations for each trading day
    df['Cumulative TPV'] = df.groupby(df['Date'].dt.date)['TPV'].cumsum()
    df['Cumulative Volume'] = df.groupby(df['Date'].dt.date)['Volume'].cumsum()
    df['VWAP'] = df['Cumulative TPV'] / df['Cumulative Volume']
    
    return df

def place_limit_order(api_connect, symbol, quantity, target_price, ins, tick_size=None):
    """Places an AMO (After Market Order) limit buy order with error handling and tick size validation."""
    try:
        # Round price to tick size before placing order
        if tick_size is None:
            tick_size = get_tick_size_from_symbol(api_connect, symbol)
        
        rounded_price = round_to_tick_size(target_price, tick_size)
        
        print(f"\n📤 Placing AMO LIMIT BUY order:")
        print(f"   Symbol: {symbol} | Instrument: {ins}")
        print(f"   Quantity: {quantity}")
        print(f"   Original Price: ₹{target_price}")
        print(f"   Tick Size: {tick_size if tick_size else get_tick_size_from_price(target_price)}")
        print(f"   Rounded Price: ₹{rounded_price}")
        
        # Using PlaceAMOTrade for AMO orders (executes at market open next day)
        respon = api_connect.PlaceAMOTrade(
            Trading_Symbol=ins, 
            Exchange=ExchangeEnum.NSE, 
            Action=ActionEnum.BUY, 
            Duration=DurationEnum.DAY, 
            Order_Type=OrderTypeEnum.LIMIT, 
            Quantity=quantity, 
            Streaming_Symbol=symbol, 
            Limit_Price=str(rounded_price), 
            Disclosed_Quantity="0", 
            TriggerPrice="0", 
            ProductCode=ProductCodeENum.NRML
        )
        
        # Parse and display response
        if isinstance(respon, str):
            respon_dict = json.loads(respon)
        else:
            respon_dict = respon
            
        print(f"✅ Order Response: {json.dumps(respon_dict, indent=2)}")
        return respon
        
    except Exception as e:
        print(f"❌ Error placing limit order: {e}")
        print(f"   Symbol: {symbol}, Price: ₹{target_price}, Quantity: {quantity}")
        return None

def place_sell_order(api_connect, symbol, quantity, ins, limit_price="0"):
    """Places an AMO (After Market Order) sell order with error handling."""
    try:
        print(f"\n📤 Placing AMO MARKET SELL order:")
        print(f"   Symbol: {symbol} | Instrument: {ins}")
        print(f"   Quantity: {quantity}")
        
        # Using PlaceAMOTrade for AMO orders (executes at market open next day)
        respon = api_connect.PlaceAMOTrade(
            Trading_Symbol=ins, 
            Exchange=ExchangeEnum.NSE, 
            Action=ActionEnum.SELL, 
            Duration=DurationEnum.DAY, 
            Order_Type=OrderTypeEnum.MARKET, 
            Quantity=quantity, 
            Streaming_Symbol=symbol, 
            Limit_Price=limit_price, 
            Disclosed_Quantity="0", 
            TriggerPrice="0", 
            ProductCode=ProductCodeENum.CNC
        )
        
        # Parse and display response
        if isinstance(respon, str):
            respon_dict = json.loads(respon)
        else:
            respon_dict = respon
            
        print(f"✅ Sell Order Response: {json.dumps(respon_dict, indent=2)}")
        return respon
        
    except Exception as e:
        print(f"❌ Error placing sell order: {e}")
        return None

def check_session_expired(response_data):
    """
    Check if the API response indicates session expiration.
    
    Args:
        response_data (dict or str): API response data
        
    Returns:
        bool: True if session expired, False otherwise
    """
    if isinstance(response_data, str):
        try:
            response_data = json.loads(response_data)
        except:
            return False
    
    # Check for session expiration error
    if isinstance(response_data, dict):
        error = response_data.get('error', {})
        if isinstance(error, dict):
            err_msg = error.get('errMsg', '').lower()
            err_cd = error.get('errCd', '')
            if 'session expired' in err_msg or err_cd == 'EGN0011':
                return True
        # Also check for direct error message
        if 'Session Expired' in str(response_data):
            return True
    
    return False

def prompt_quantity_for_symbol(symbol_display, default_qty=5):
    """
    Ask user for quantity per order for the given symbol.
    Returns an integer quantity; defaults to default_qty if user presses Enter.
    """
    while True:
        user_input = input(f"Enter quantity per AMO order for {symbol_display} (default {default_qty}): ").strip()
        if user_input == "":
            return default_qty
        if user_input.isdigit() and int(user_input) > 0:
            return int(user_input)
        print("⚠️  Please enter a positive whole number or press Enter to use the default.")


def process_symbol(api_connect, symbol, instrument, amttobuy, display_name=None):
    """
    Fetches EOD chart data, calculates VWAP, and places AMO (After Market Order) limit orders
    at calculated prices. Orders will execute at market open next day.
    """
    name_to_show = display_name or symbol  # Define outside try block for exception handlers
    try:
        print(f"\n{'='*70}")
        print(f"📊 Processing Symbol: {name_to_show} ({symbol}) | Instrument: {instrument}")
        print(f"{'='*70}")
        
        # Fetch EOD chart data
        print(f"\n📥 Fetching EOD chart data...")
        sys.stdout.flush()
        
        try:
            response = api_connect.getEODChart(
                ChartExchangeEnum.NSE, 
                AssetTypeEnum.EQUITY, 
                symbol, 
                EODIntervalEnum.D1, 
                IncludeContinuousFutures=False
            )
        except KeyError as e:
            # This happens when API returns error response without 'data' key
            print(f"\n❌ API Error: The API returned an error response (likely 400 Bad Request)")
            print(f"   Error: {e}")
            print(f"   This usually means:")
            print(f"   1. Invalid symbol format: {symbol}")
            print(f"   2. Symbol not found or not available")
            print(f"   3. API endpoint issue")
            print(f"\n   Try checking:")
            print(f"   - Is the symbol format correct? (should be 'TOKEN_EXCHANGE' like '18143_NSE')")
            print(f"   - Does this symbol exist in your account?")
            print(f"   - Try generating a new request_id token")
            return
        except Exception as e:
            print(f"\n❌ Error calling getEODChart: {e}")
            print(f"   Error type: {type(e).__name__}")
            import traceback
            traceback.print_exc()
            return
        
        # Check if response is empty
        if not response or response.strip() == "":
            print(f"\n❌ Empty response from API")
            print(f"   This usually means:")
            print(f"   1. API returned an error (400/500) and library converted it to empty string")
            print(f"   2. Symbol '{symbol}' not found or not available for chart data")
            print(f"   3. Session expired or authentication issue")
            print(f"\n   Check apiconnect.log for the actual HTTP response")
            sys.stdout.flush()
            return
        
        # Parse JSON response
        try:
            data_dict = json.loads(response)
        except json.JSONDecodeError as e:
            print(f"\n❌ JSON Decode Error: {e}")
            print(f"   Response is not valid JSON")
            print(f"   Response was: {repr(response)}")
            sys.stdout.flush()
            return
        
        # Check for session expiration FIRST (like in original code)
        if check_session_expired(data_dict):
            print(f"\n❌ SESSION EXPIRED!")
            print(f"   The API token (request ID) has expired.")
            print(f"   Please generate a new token and update it in the code.")
            print(f"\n   To generate a new token:")
            print(f"   1. Run: get_request_id_from_url('YOUR_API_KEY', open_browser=True)")
            print(f"   2. Visit the URL in your browser")
            print(f"   3. Copy the request_id from the redirect URL")
            print(f"   4. Update REQUEST_ID in the code")
            raise Exception("Session Expired - Please generate a new request ID")
        
        # Check if data is available
        if not isinstance(data_dict, dict):
            print(f"\n❌ Response is not a dictionary")
            sys.stdout.flush()
            return
        
        # Use .get() to safely access 'data' key
        data_list = data_dict.get("data")
        
        if data_list is None:
            print(f"\n❌ 'data' key not found in response")
            print(f"   Available keys: {list(data_dict.keys())}")
            print(f"   Full response: {json.dumps(data_dict, indent=2)}")
            sys.stdout.flush()
            return
            
        if not data_list:
            print(f"\n❌ 'data' key exists but is empty")
            sys.stdout.flush()
            return
        
        df1 = pd.DataFrame(data_list, columns=["Date", "Open", "High", "Low", "Close", "Volume"])
        
        if len(df1) == 0:
            print(f"❌ Empty dataframe for {symbol}")
            return
        
        # Calculate VWAP
        df1 = calculate_vwap(df1)
        
        # Get latest values
        vwamp = df1['VWAP'].iloc[-1]
        vwamp_minus_1_percent = vwamp - (vwamp * 0.01)
        
        low_price = df1['Low'].iloc[-1]
        low_price_minus_1_percent = low_price - (low_price * 0.01)
        latestcloseprice = df1['Close'].iloc[-1]
        latestdate = df1['Date'].iloc[-1]

        # Get tick size for this symbol (once, to use for all orders)
        print(f"\n📏 Fetching tick size for {symbol}...")
        tick_size = get_tick_size_from_symbol(api_connect, symbol)
        if tick_size is None:
            # Use price-based calculation
            tick_size = get_tick_size_from_price(latestcloseprice)
            print(f"   Using calculated tick size: {tick_size} (based on price ₹{latestcloseprice})")

        print(f"\n📈 Calculated Values (before tick size rounding):")
        print(f"   Latest Date: {latestdate}")
        print(f"   Latest Close: ₹{round(latestcloseprice, 2)}")
        print(f"   VWAP: ₹{round(vwamp, 2)}")
        print(f"   VWAP - 1%: ₹{round(vwamp_minus_1_percent, 2)}")
        print(f"   Low Price: ₹{round(low_price, 2)}")
        print(f"   Low - 1%: ₹{round(low_price_minus_1_percent, 2)}")
        print(f"\n📋 Placing {amttobuy} quantity AMO orders at 4 price levels...")
        print(f"   ⚠️  Note: AMO orders will execute at market open next day")
        print(f"   Tick Size: {tick_size}")

        # Calculate prices and round to tick size
        raw_prices = [
            vwamp,
            vwamp_minus_1_percent,
            low_price,
            low_price_minus_1_percent
        ]
        
        # Round all prices to tick size
        order_prices = [round_to_tick_size(price, tick_size) for price in raw_prices]
        
        print(f"\n💰 Final Order Prices (after tick size rounding):")
        for i, (raw, rounded) in enumerate(zip(raw_prices, order_prices), 1):
            print(f"   Order {i}: ₹{raw:.2f} → ₹{rounded:.2f}")
        
        order_ids = []
        for price in order_prices:
            order_response = place_limit_order(api_connect, symbol, amttobuy, price, instrument, tick_size)
            # Extract order ID from response
            if order_response:
                try:
                    if isinstance(order_response, str):
                        resp_dict = json.loads(order_response)
                    else:
                        resp_dict = order_response
                    
                    if 'data' in resp_dict and 'oid' in resp_dict['data']:
                        order_ids.append(resp_dict['data']['oid'])
                        print(f"   ✓ Order ID: {resp_dict['data']['oid']}")
                except:
                    pass
            
            # Small delay between orders to avoid rate limiting
            time.sleep(0.5)
        
        # Verify orders in order book
        print(f"\n📋 Verifying orders in order book...")
        try:
            time.sleep(2)  # Wait a bit for orders to appear
            order_book = api_connect.OrderBook()
            order_book_dict = json.loads(order_book) if isinstance(order_book, str) else order_book
            
            if 'eq' in order_book_dict and 'data' in order_book_dict['eq']:
                orders = order_book_dict['eq']['data'].get('ord', [])
                print(f"   Found {len(orders)} order(s) in order book")
                
                # Filter orders for this symbol
                symbol_orders = [o for o in orders if o.get('sym') == symbol]
                print(f"   Orders for {symbol}: {len(symbol_orders)}")
                
                for order in symbol_orders:
                    status = order.get('sts', 'Unknown')
                    order_id = order.get('ordID', 'N/A')
                    price = order.get('prc', 'N/A')
                    qty = order.get('qty', 'N/A')
                    rej_reason = order.get('rejRsn', '')
                    
                    print(f"   Order ID: {order_id} | Status: {status} | Price: ₹{price} | Qty: {qty}")
                    if rej_reason:
                        print(f"      ⚠️  Rejection Reason: {rej_reason}")
            else:
                print(f"   ⚠️  Could not parse order book response")
        except Exception as e:
            print(f"   ⚠️  Error checking order book: {e}")
        
        print(f"\n✅ Completed processing {name_to_show}")
        print(f"{'='*70}\n")
        
    except json.JSONDecodeError as e:
        print(f"❌ Error parsing JSON response for {name_to_show}: {e}")
    except KeyError as e:
        print(f"❌ Missing key in response for {name_to_show}: {e}")
    except Exception as e:
        print(f"❌ Error processing {name_to_show}: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Initializes the API and processes the defined symbols for AMO (After Market Order) trading."""
    
    print("\n" + "="*70)
    print("🚀 NUVAMA VWAP TRADING STRATEGY - AMO ORDERS")
    print("="*70)
    print(f"⏰ Start Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70 + "\n")
    
    # Check if market is open - AMO orders are typically only accepted after market hours
    is_market_open = check_market_hours()
    if is_market_open:
        print("\n⚠️  WARNING: Market is currently OPEN!")
        print("   AMO orders are typically only accepted AFTER market hours.")
        print("   During market hours, use nuvama_vwap_live.py for live market orders.")
        print("   If you place AMO orders during market hours, they may be rejected.")
        response = input("\n   Do you want to continue with AMO orders anyway? (yes/no): ")
        if response.lower() != 'yes':
            print("   Exiting... Use nuvama_vwap_live.py for live market orders.")
            return
        print()
    else:
        print("ℹ️  Market is CLOSED - Perfect time for AMO orders!")
        print("   AMO orders will execute at market open next trading day\n")
    
    # ============================================
    # CONFIGURE YOUR CREDENTIALS HERE
    # ============================================
    API_KEY = "D0G4NYboa7D6fQ"              # Your Nuvama API Key (Vendor ID)
    SECRET_KEY = "g0ZM4h#3mjZ!5@Q8"         # Your Nuvama Secret Key (Password)
    REQUEST_ID = "646239d6117ac55f"         # Request ID from login URL redirect
    CLIENT_ID = "YOUR_CLIENT_ID_HERE"       # Your Client ID (if needed)
    
    # ============================================
    # TO GENERATE REQUEST ID (TOKEN):
    # ============================================
    # Uncomment the line below to generate token URL
    # get_request_id_from_url(API_KEY, open_browser=True)
    
    # ============================================
    # AUTHENTICATE AND USE API
    # ============================================
    try:
        print("🔐 Authenticating with Nuvama API...")
        # Option 1: Using the helper function
        # api_connect = authenticate_nuvama(API_KEY, SECRET_KEY, REQUEST_ID, True, "c:\\python-settings.ini")
        
        # Option 2: Direct initialization (current method)
        # Config file is optional - removed to avoid file not found error
        api_connect = APIConnect(API_KEY, SECRET_KEY, REQUEST_ID, True)
        
        # Monkey-patch to fix enum formatting bug in APIConnect library
        # The library uses .format() with enums which converts them incorrectly in Python 3.11
        # We'll patch the method to manually construct URL with enum values
        from urllib.parse import urljoin
        import json as json_lib
        from resources.chart_response_formatter import ChartResponseFormatter
        
        original_method = api_connect._APIConnect__getChartDataOfScrip
        def patched_get_chart(Exchange, AssetType, Streaming_Symbol, Interval, TillDate=None, IncludeContinuousFutures=False):
            # Get enum values as strings
            exc_val = Exchange.value if hasattr(Exchange, 'value') else str(Exchange)
            aTyp_val = AssetType.value if hasattr(AssetType, 'value') else str(AssetType)
            interval_val = Interval.value if hasattr(Interval, 'value') else str(Interval)
            
            # Manually construct URL with enum values (fixing the bug)
            base_url = api_connect._APIConnect__router.baseurlcontent
            url = urljoin(base_url, f"charts/v2/main/{interval_val}/{exc_val}/{aTyp_val}/{Streaming_Symbol}")
            
            # Prepare data (same as original)
            if AssetType not in [AssetTypeEnum.FUTCOM, AssetTypeEnum.FUTCUR, AssetTypeEnum.FUTIDX, AssetTypeEnum.FUTSTK]:
                IncludeContinuousFutures = False
            
            data = {'chTyp': "Interval", 'conti': IncludeContinuousFutures, 'ltt': TillDate}
            
            # Make the POST request
            reply = api_connect._APIConnect__http._PostMethod(url, json_lib.dumps(data))
            
            # Format response (same as original)
            if reply != "":
                reply = ChartResponseFormatter(reply).getOHCLResponse()
            return json_lib.dumps(reply)
        
        api_connect._APIConnect__getChartDataOfScrip = patched_get_chart
        
        print("✅ Authentication successful!\n")
        
        # Test connection by fetching holdings
        print("📊 Fetching account holdings...")
        holdingresponse = api_connect.Holdings()
        print("✅ Holdings fetched successfully\n")
        # Uncomment to see holdings: print(holdingresponse)
        
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        print("\n⚠️  Please check:")
        print("   1. Your API key, secret key, and request ID are correct")
        print("   2. Your request ID is not expired (generate a new one if needed)")
        print("   3. Your internet connection is working")
        print("   4. If config file error: Config file is optional and has been removed")
        return
    
    # ============================================
    # TRADING SYMBOLS CONFIGURATION
    # ============================================
    symbols = [
        {"symbol": "18143_NSE", "instrument": "INE758E01017", "name": "JIOFIN"},
        {"symbol": "2475_NSE", "instrument": "INE213A01029", "name": "ONGC"},
    ]
    
    print(f"📋 Processing {len(symbols)} symbol(s)...\n")
    
    # Process each symbol
    for idx, item in enumerate(symbols, 1):
        print(f"\n[{idx}/{len(symbols)}] Processing symbol...")
        try:
            display_name = item.get("name", item["symbol"])
            per_symbol_qty = prompt_quantity_for_symbol(display_name, default_qty=5)
            process_symbol(api_connect, item["symbol"], item["instrument"], per_symbol_qty, display_name=display_name)
        except Exception as e:
            print(f"❌ Failed to process {item['symbol']}: {e}")
            continue
    
    print("\n" + "="*70)
    print("✅ ALL SYMBOLS PROCESSED")
    print(f"⏰ End Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
