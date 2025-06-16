import pandas as pd
from dash import Dash, dcc, html, Input, Output, State, callback_context, ALL
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from geopy.exc import GeocoderTimedOut
import logging
import re
import json
from datetime import datetime, timedelta
from fuzzywuzzy import process
import openpyxl
from io import BytesIO
import requests

# Setup logging to console for Render
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize geolocator
geolocator = Nominatim(user_agent="sugar_procurement_chatbot")

# In-memory coordinate cache (no file system on Render free tier)
coord_cache = {}

# City coordinates
city_coords = {
    'Anand': (22.5645, 72.9281), 'Kolkata': (22.5726, 88.3639), 'Mumbai': (19.0760, 72.8777),
    'New Delhi': (28.6139, 77.2090), 'Hyderabad': (17.3850, 78.4867), 'Chennai': (13.0827, 80.2707),
    'Patna': (25.5941, 85.1376), 'Jaipur': (26.9124, 75.7873), 'Bangalore': (12.9716, 77.5946),
    'Ahmedabad': (23.0225, 72.5714), 'Pune': (18.5204, 73.8567), 'Guwahati': (26.1445, 91.7362),
    'Indore': (22.7196, 75.8577), 'Nagpur': (21.1458, 79.0882), 'Coimbatore': (11.0168, 76.9558),
    'Kanpur': (26.76, 80.3), 'Visakhapatnam': (17.7865, 83.21185), 'Bhopal': (62.2599, 77.4126),
    'Amravati': (20.64, 77.752), 'Gorakhpur': (26.7606, 83.3732), 'Navi Mumbai': (19, 73),
    'Navsari': (20.9467, 72.9230), 'Didwana': (27.4, 74.5667), 'Surendranagar': (22.7201, 71.6495),
    'Rohtak': (28.8955, 76.6066), 'Jati': (20.1597, 85.7071), 'Nawa City': (25.0195, 75.0023),
    'Bishalgarh': (23.6766, 91.2757), 'Barauni': (25.4715, 85.9756), 'Gaya': (24.7914, 85),
    'Jind': (29.3211, 76.3058), 'Gurgaon': (28.4595, 77.0266), 'Begusarai': (25.4167, 86.1294),
    'Hisar': (29.1492, 75.7217), 'Noida': (28.5355, 77.3910), 'Pipariya': (22.7629, 78.3520),
    'Shahjahanpur': (27.8793, 79.9120), 'Jamshedpur': (22.8046, 86.2029), 'Tirora': (21.4085, 79.9326),
    'Cuttack': (20.4650, 85.8793), 'Bhiwandi': (19.2967, 73.0631), 'Purnia': (25.7771, 87.4753),
    'Muzaffarpur': (26.1209, 85.3647), 'Raipur': (21.2514, 81.6296), 'Erode': (11.3410, 77.7172),
    'Meerut': (28.9845, 77.7064), 'Karnal': (29.6857, 76.9905), 'Ambala': (30.3782, 76.7767),
    'Shahabad': (30.1677, 76.8699), 'Parwanoo': (30.8387, 76.9630), 'Amritsar': (31.6340, 74.8723),
    'Satara': (17.6805, 74.0183), 'Kolhapur': (16.6950, 74.2317), 'Palakkad': (10.7867, 76.6548),
    'Kollam': (8.8932, 76.6141), 'Ernakulam': (9.9816, 76.2999),
    'Aligarh': (27.8974, 78.0880), 'Puducherry': (11.9416, 79.8083), 'Thane': (19.2183, 72.9781),
    'Ghaziabad': (28.6692, 77.4538), 'Saharanpur': (29.9640, 77.5452), 'Gandhidham': (23.0753, 70.1337),
    'Kaithal': (29.7954, 76.3996), 'Ahmednagar': (19.0948, 74.7480), 'Kukarmunda': (21.5167, 74.3167),
    'Bijnor': (29.3724, 78.1366), 'Shamli': (29.4496, 77.3127), 'Royapettah': (13.0550, 80.2639),
    'Secunderabad': (17.4399, 78.4983), 'Vadodara': (22.3072, 73.1812),
}

# Default coordinates
DEFAULT_COORDS = (20.5937, 78.9629)

# Get coordinates with fallback
def get_coordinates(city, coord_cache):
    city = city.title().replace('  ', ' ')
    if city in ['Delhi', 'New  Delhi']:
        city = 'New Delhi'
    elif city == 'Punaura':
        city = 'Purnia'
    elif city == 'Ambala Cantt':
        city = 'Ambala'
    elif city == 'Shahabad Markanda':
        city = 'Shahabad'
    
    if city in city_coords:
        return city_coords[city]
    if city in coord_cache and coord_cache[city] != [0, 0]:
        return tuple(coord_cache[city])
    
    try:
        location = geolocator.geocode(city + ", India", timeout=10)
        if location:
            coords = (location.latitude, location.longitude)
            coord_cache[city] = list(coords)
            logger.info(f"Geocoded {city} to {coords}")
            return coords
    except GeocoderTimedOut:
        logger.error(f"Geocoding timeout for {city}")
    
    logger.warning(f"Coordinates for {city} not found")
    return None

# Calculate distance
def calculate_distance(loc1, loc2):
    try:
        return round(geodesic(loc1, loc2).kilometers, 2)
    except Exception as e:
        logger.error(f"Distance calculation failed: {e}")
        return float('inf')

# Load trade data from Google Drive
def load_data(file_url='https://drive.google.com/uc?export=download&id=1ypdDlE7oo2ovoB0osNqVM4ARsXCryPwi'):
    logger.info(f"Loading data from {file_url}")
    print(f"Loading data from {file_url}...")
    try:
        response = requests.get(file_url)
        response.raise_for_status()  # Raise error for bad status
        df = pd.read_excel(BytesIO(response.content), engine='openpyxl')
        
        logger.info(f"Excel Columns: {df.columns.tolist()}")
        print(f"Excel Columns: {df.columns.tolist()}")
        required_columns = [
            'Rank', 'Auction Id', 'Auction Ord No.', 'Auction Date', 'Market Code', 'Location',
            'Initiator', 'CMID', 'Bidder Name', 'Bidder City', 'Bidder State', 'Lowest Price',
            'Quantity', 'Product', 'Product Description', 'Auction Description', 'Order Status',
            'Bid Count', 'Rejection Reason', 'Product Name'
        ]
        
        df.columns = [col.strip().title() for col in df.columns]
        required_columns_normalized = [col.title() for col in required_columns]
        
        missing_columns = [col for col in required_columns_normalized if col not in df.columns]
        if missing_columns:
            error = f"Missing columns in Excel: {missing_columns}. Available: {df.columns.tolist()}"
            logger.error(error)
            raise ValueError(error)
        
        df.columns = [required_columns[required_columns_normalized.index(col)] for col in df.columns]
        
        df['Auction Date'] = pd.to_datetime(df['Auction Date'], errors='coerce')
        df['Product Name'] = df['Product Name'].astype(str).str.strip().replace('nan', 'Unknown')
        logger.info(f"Raw Product Names: {sorted(df['Product Name'].unique())}")
        print(f"Raw Product Names: {sorted(df['Product Name'].unique())}")
        df['Location'] = df['Location'].astype(str).str.strip().str.title()
        df['Bidder Name'] = df['Bidder Name'].astype(str).str.strip()
        df['Initiator'] = df['Initiator'].astype(str).str.strip().str.title()
        df['Bidder City'] = df['Bidder City'].astype(str).str.strip().str.title().replace({
            'New  Delhi': 'New Delhi', ' Delhi': 'New Delhi',
            'Punaura': 'Purnia', 'Muzzarpur': 'Muzaffarpur', 'Bhiwadi': 'Bhiwandi',
            'Shahabad Markanda': 'Shahabad', 'Ambala Cantt': 'Ambala'
        })
        df['Bidder State'] = df['Bidder State'].astype(str).str.strip().str.title().replace('nan', 'Unknown')
        df['Lowest Price'] = pd.to_numeric(df['Lowest Price'], errors='coerce')
        df['Quantity'] = pd.to_numeric(df['Quantity'], errors='coerce')
        df['Rank'] = pd.to_numeric(df['Rank'], errors='coerce')
        df['Rejection Reason'] = df['Rejection Reason'].astype(str).str.strip()
        df['Auction Ord No.'] = df['Auction Ord No.'].astype(str).str.strip()
        
        logger.info(f"Rank nulls: {df['Rank'].isna().sum()}, Non-numeric Rank sample: {df[df['Rank'].isna()][['Bidder Name', 'Rank']].head().to_dict('records')}")
        logger.info(f"Auction Ord No. nulls: {df['Auction Ord No.'].isna().sum()}, Sample: {df['Auction Ord No.'].head().tolist()}")
        logger.info(f"Rank value counts: {df['Rank'].value_counts(dropna=False).to_dict()}")
        
        df['Normalized Product'] = df['Product Name'].str.encode('ascii', 'ignore').str.decode('ascii').str.strip().str.upper().str.replace(r'\s+', '', regex=True).replace({
            'M30': 'M-30', 'M31': 'M-31', 'S30': 'S-30', 'S31': 'S-31', 'L30': 'L-30', 'L31': 'L-31',
            'M 30': 'M-30', 'M 31': 'M-31', 'S 30': 'S-30', 'S 31': 'S-31', 'L 30': 'L-30', 'L 31': 'L-31',
            'M-30': 'M-30', 'M-31': 'M-31', 'S-30': 'S-30', 'S-31': 'S-31', 'L-30': 'L-30', 'L-31': 'L-31',
            'M30SUGAR': 'M-30', 'S30SUGAR': 'S-30', 'M-30SUGAR': 'M-30', 'S-30SUGAR': 'S-30',
            'S1-30': 'S-30', 'M-30/31': 'M-30', 'M30/31': 'M-30',
            'PHARMA GRADE': 'PHARMA GRADE', 'PHARMAGRADE': 'PHARMA GRADE',
            'DOUBLE REFINED SUGAR': 'DOUBLE REFINED SUGAR', 'DOUBLEREFINEDSUGAR': 'DOUBLE REFINED SUGAR',
            'BRANDED SUGAR': 'BRANDED SUGAR', 'BRANDEDSUGAR': 'BRANDED SUGAR',
            'DEXTROSE MONOHYDRATE': 'DEXTROSE MONOHYDRATE', 'DEXTROSEMONOHYDRATE': 'DEXTROSE MONOHYDRATE',
            'G100': 'G-100', 'G60': 'G-60', 'G 100': 'G-100', 'G 60': 'G-60'
        }).str.replace(r'\(.*\)', '', regex=True).replace('UNKNOWN', 'Unknown')
        
        logger.info(f"Normalized Products: {sorted(df['Normalized Product'].unique())}")
        print(f"Normalized Products: {sorted(df['Normalized Product'].unique())}")
        print(f"M-30 Rows (Normalized): {len(df[df['Normalized Product'] == 'M-30'])}")
        print(f"S-30 Rows (Normalized): {len(df[df['Normalized Product'] == 'S-30'])}")
        logger.info(f"M-30 Rows (Normalized): {len(df[df['Normalized Product'] == 'M-30'])}")
        logger.info(f"S-30 Rows (Normalized): {len(df[df['Normalized Product'] == 'S-30'])}")
        if not df[df['Normalized Product'].isin(['M-30', 'S-30'])].empty:
            counts = df[df['Normalized Product'].isin(['M-30', 'S-30'])]['Normalized Product'].value_counts().to_dict()
            print(f"M-30/S-30 counts: {counts}")
            logger.info(f"M-30/S-30 counts: {counts}")
        else:
            print("No M-30/S-30 in normalized data")
            logger.warning("No M-30/S-30 in normalized data")
        
        if df['Bidder City'].isna().any():
            logger.warning(f"Filling {df['Bidder City'].isna().sum()} null Bidder City values with 'Unknown'")
            df['Bidder City'] = df['Bidder City'].fillna('Unknown')
        
        if df['Auction Date'].isna().any():
            logger.warning(f"Dropping {df['Auction Date'].isna().sum()} rows with invalid Auction Date")
            df = df.dropna(subset=['Auction Date'])
        
        if df['Auction Ord No.'].isna().any():
            logger.warning(f"Filling {df['Auction Ord No.'].isna().sum()} null Auction Ord No. with 'Unknown'")
            df['Auction Ord No.'] = df['Auction Ord No.'].fillna('Unknown')
        
        if df.empty:
            error = "DataFrame empty after cleaning"
            logger.error(error)
            raise ValueError(error)
        
        logger.info(f"Loaded {len(df)} rows")
        print(f"Loaded {len(df)} rows")
        return df
    except Exception as e:
        logger.error(f"Error loading data: {e}")
        print(f"Error loading data: {e}")
        raise

# Parse prompt
def parse_prompt(prompt, known_locations, known_products):
    print(f"Input prompt: '{prompt}'")
    logger.info(f"Input prompt: '{prompt}'")
    prompt_clean = prompt.strip()
    print(f"Cleaned prompt: '{prompt_clean}'")
    try:
        match = re.match(r'^(.+?)\s*for\s*(.+)$', prompt_clean, re.IGNORECASE)
        if match:
            product_input = match.group(1).strip()
            location_input = match.group(2).title().strip()
            print(f"Parsed product: '{product_input}', location: '{location_input}'")
            logger.info(f"Parsed product: '{product_input}', location: '{location_input}'")
            
            if product_input.lower() == 'any sugar':
                product = 'Any Sugar'
            else:
                product_match = process.extractOne(product_input.upper(), known_products, score_cutoff=80)
                if product_match:
                    product = product_match[0]
                    logger.info(f"Matched product '{product_input}' to '{product}' (score: {product_match[1]})")
                    print(f"Matched product '{product_input}' to '{product}'")
                else:
                    logger.warning(f"Product '{product_input}' not recognized")
                    print(f"Product '{product_input}' not recognized")
                    return None, location_input, False
            
            location_match = process.extractOne(location_input, known_locations + list(city_coords.keys()), score_cutoff=80)
            if location_match:
                location = location_match[0]
                logger.info(f"Matched '{location_input}' to '{location}' (score: {location_match[1]})")
                print(f"Matched '{location_input}' to '{location}'")
                return product, location, False
            else:
                logger.warning(f"Location '{location_input}' not recognized")
                print(f"Location '{location_input}' not recognized")
                return product, location_input, True
        
        logger.error("Invalid prompt format")
        print("Invalid prompt format")
        return None, None, False
    except Exception as e:
        logger.error(f"Error parsing prompt: {e}")
        print(f"Error parsing prompt: {e}")
        return None, None, False

# Process requirement
def process_requirement(df, product, location, custom_coords=None):
    if df.empty:
        logger.error("No data available")
        print("No data available")
        return {"error": "No data available"}
    
    try:
        if custom_coords:
            loc_coords = custom_coords
            logger.info(f"Using custom coordinates for {location}: {loc_coords}")
            print(f"Using custom coordinates for {location}: {loc_coords}")
        else:
            loc_coords = get_coordinates(location, coord_cache)
            if loc_coords is None:
                logger.error(f"Cannot geocode location '{location}'")
                print(f"Cannot geocode location: {location}")
                return {"error": f"Cannot geocode '{location}'. Please provide coordinates."}
    
        print(f"Total rows before filtering: {len(df)}")
        logger.info(f"Total rows before filtering: {len(df)}")
        if product == "Any Sugar":
            bidders = df.copy()
            print(f"Selected all {len(bidders)} rows for '{product}'")
            logger.info(f"Selected all {len(bidders)} rows for '{product}'")
        else:
            product_clean = product.upper().strip()
            print(f"Filtering for product: '{product_clean}'")
            logger.info(f"Filtering for product: '{product_clean}'")
            print(f"Available Normalized Products: {sorted(df['Normalized Product'].unique())}")
            logger.info(f"Available Normalized Products: {sorted(df['Normalized Product'].unique())}")
            bidders = df[df['Normalized Product'] == product_clean].copy()
            print(f"Filtered {len(bidders)} rows for product: '{product}'")
            logger.info(f"Filtered {len(bidders)} rows for product: '{product}'")
            if bidders.empty:
                logger.warning(f"No rows found for '{product}'. Checking similar products.")
                print(f"No rows found for '{product}'. Checking similar products.")
                available_products = df['Normalized Product'].unique().tolist()
                suggestions = process.extract(product_clean, available_products, limit=3)
                suggestions = [s[0] for s in suggestions if s[1] >= 80]
                print(f"Suggestions: {suggestions}")
                logger.info(f"Suggestions: {suggestions}")
        
        if bidders.empty and product != "Any Sugar":
            available_products = sorted(df['Normalized Product'].unique())
            logger.warning(f"No bidders found for '{product}'. Available products: {available_products}")
            print(f"No bidders found for '{product}'. Available products: {available_products}")
            suggestions = process.extract(product, available_products, limit=3)
            suggestions = [s[0] for s in suggestions if s[1] >= 80]
            return {"error": f"No bidders found for {product}. Try: {', '.join(suggestions or available_products)}"}
        
        current_date = pd.to_datetime('2025-06-16')  # Updated to current date
        six_months_ago = current_date - timedelta(days=180)
        
        all_products = df.groupby(['Bidder Name', 'Bidder City', 'Bidder State'])['Normalized Product'].apply(lambda x: sorted(set(x))).reset_index(name='All Products')
        logger.info(f"Computed all products for {len(all_products)} unique bidders")
        print(f"Computed all products for {len(all_products)} unique bidders")
        
        bidder_agg = bidders.groupby(['Bidder Name', 'Bidder City', 'Bidder State']).agg({
            'Auction Ord No.': lambda x: len(set(x)),
            'Rank': lambda x: sum(x == 1),
            'Auction Date': [
                lambda x: len(x),
                lambda x: max(x),
                lambda x: any(x >= six_months_ago),
                lambda x: sorted(x, reverse=True)[:5]
            ],
            'Lowest Price': 'mean',
            'Initiator': lambda x: sorted(set(x)),
            'Product Name': lambda x: sorted(set(x)),
            'Normalized Product': 'first',
            'Location': 'first'
        }).reset_index()
        
        total_auctions = df.groupby(['Bidder Name', 'Bidder City', 'Bidder State'])['Auction Ord No.'].apply(lambda x: len(set(x))).reset_index(name='Total Auctions Full')
        
        bidder_agg.columns = [
            'Bidder Name', 'Bidder City', 'Bidder State',
            'Total Auctions', 'Wins',
            'Bid Count', 'Last Active Date', 'Recent Participation', 'Last 5 Auctions',
            'Lowest Price', 'Initiators', 'Products Participated', 'Product', 'Location'
        ]
        
        bidder_agg = bidder_agg.merge(total_auctions, on=['Bidder Name', 'Bidder City', 'Bidder State'], how='left')
        bidder_agg['Total Auctions'] = bidder_agg['Total Auctions Full'].fillna(bidder_agg['Total Auctions'])
        bidder_agg = bidder_agg.drop(columns=['Total Auctions Full'])
        
        bidder_agg = bidder_agg.merge(all_products, on=['Bidder Name', 'Bidder City', 'Bidder State'], how='left')
        
        def compute_other_products(row, selected_product):
            all_prods = row['All Products'] if isinstance(row['All Products'], list) else []
            if selected_product == "Any Sugar":
                return ', '.join(all_prods) if all_prods else 'None'
            return ', '.join([p for p in all_prods if p != selected_product.upper()]) if all_prods else 'None'
        
        bidder_agg['Other Products'] = bidder_agg.apply(lambda row: compute_other_products(row, product), axis=1)
        
        def is_active(row):
            recent_any = row['Recent Participation']
            last_5 = row['Last 5 Auctions']
            recent_last_5 = any(date >= six_months_ago for date in last_5) if last_5 else False
            is_active_status = recent_any or recent_last_5
            logger.info(f"Bidder {row['Bidder Name']}: Recent Any={recent_any}, Recent Last 5={recent_last_5}, Active={is_active_status}")
            return 'Yes' if is_active_status else 'No'
        
        bidder_agg['Active'] = bidder_agg.apply(is_active, axis=1)
        bidder_agg['Last Active Date'] = bidder_agg['Last Active Date'].dt.strftime('%Y-%m-%d')
        bidder_agg['Win Rate (%)'] = bidder_agg.apply(
            lambda row: f"{(row['Wins'] / row['Total Auctions'] * 100) if row['Total Auctions'] > 0 else 0:.2f} ({int(row['Wins'])}/{int(row['Total Auctions'])})",
            axis=1
        )
        bidder_agg['Distance (km)'] = bidder_agg['Bidder City'].apply(
            lambda city: calculate_distance(loc_coords, get_coordinates(city, coord_cache) or DEFAULT_COORDS)
        )
        bidder_agg['Avg Bid Price'] = bidder_agg['Lowest Price'].round(2)
        bidder_agg['Remarks'] = bidder_agg.apply(
            lambda row: f"Initiators: {', '.join(row['Initiators'])}; Products: {', '.join(row['Products Participated'])}",
            axis=1
        )
        
        result = bidder_agg[[
            'Bidder Name', 'Bidder City', 'Bidder State', 'Win Rate (%)',
            'Distance (km)', 'Avg Bid Price', 'Remarks', 'Last Active Date', 'Active', 'Other Products'
        ]].to_dict(orient='records')
        
        logger.info(f"Aggregated {len(result)} unique bidders for {product} in {location}")
        print(f"Aggregated {len(result)} unique bidders for {product} in {location}")
        return {"bidders": result}
    except Exception as e:
        logger.error(f"Error aggregating bidders for {product} in {location}: {e}")
        print(f"Error aggregating bidders: {e}")
        return {"error": f"Error processing data: {str(e)}"}

# Create bidder table
def create_bidder_table(bidders):
    if not bidders:
        return html.P("No bidders found. Check product or location.", className="text-red-600")
    
    columns = [
        'Bidder Name', 'Bidder City', 'Bidder State', 'Win Rate (%)',
        'Distance (km)', 'Avg Bid Price', 'Remarks', 'Last Active Date', 'Active', 'Other Products'
    ]
    
    return html.Table([
        html.Thead(
            html.Tr([
                html.Th(col, className="border border-gray-300 p-2 bg-gray-100 font-semibold text-gray-700")
                for col in columns
            ])
        ),
        html.Tbody([
            html.Tr([
                html.Td(
                    f"{bidder[col]:.2f}" if col in ['Distance (km)', 'Avg Bid Price'] else bidder[col],
                    className="border border-gray-200 p-2" if i % 2 == 0 else "border bg-gray-50 p-2"
                )
                for col in columns
            ], className="hover:bg-gray-100")
            for i, bidder in enumerate(bidders)
        ])
    ], className="w-full border-collapse shadow-md rounded-lg")

# Dash app
app = Dash(__name__, external_stylesheets=['https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css'])
server = app.server  # For Render/gunicorn

# Load data
try:
    df = load_data()
    known_locations = df['Location'].unique().tolist() if not df.empty else []
    known_products = sorted(df['Normalized Product'].unique().tolist())
    products = ['Any Sugar'] + known_products
except Exception as e:
    df = pd.DataFrame()
    known_locations = []
    known_products = []
    products = ['Any Sugar']
    logger.error(f"Failed to load data: {e}")
    print(f"Failed to load data: {e}")

app.layout = html.Div(className="min-h-screen bg-gray-100 flex items-center justify-center p-4", children=[
    html.Div(className="bg-white p-6 rounded-lg shadow-lg w-full max-w-4xl", children=[
        html.H1("Sugar Procurement Chatbot", className="text-2xl font-bold mb-4 text-center text-blue-600"),
        html.Div([
            html.Button("ℹ Products", id="products-btn", className="text-blue-500 font-medium p-2 bg-gray-100 rounded hover:bg-gray-200"),
            html.Div([
                html.Div([
                    html.H3("Available Products", className="text-lg font-semibold mb-2 text-gray-800"),
                    html.Ul([
                        html.Li([
                            html.Span(
                                product,
                                id={'type': 'product-id', 'index': product},
                                className="cursor-pointer text-blue-500 hover:underline",
                                **{'data-product': product}
                            ),
                            html.Button(
                                "Copy",
                                id={'type': 'copy-btn', 'index': product},
                                className="ml-2 px-2 py-1 text-sm bg-gray-200 rounded hover:bg-gray-300",
                                **{'data-product': product}
                            )
                        ], className="mb-2")
                        for product in products
                    ], className="list-none"),
                    html.Button("Close", id="close-modal-btn", className="mt-4 w-full p-2 bg-blue-500 text-white rounded hover:bg-blue-600")
                ], className="bg-white p-4 rounded-lg shadow")
            ], id="product-modal", className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center hidden")
        ], className="mb-4"),
        html.Label("Enter Requirement:", className="block text-sm font-medium text-gray-700 mb-1"),
        dcc.Input(
            id='recommendation-input',
            type='text',
            placeholder='e.g., S-30 for Anand or Any Sugar for Anand',
            className="w-full p-2 mb-2 border border-gray-300 rounded focus:ring-blue-500"
        ),
        html.Label("Sort By:", className="block text-sm font-medium text-gray-700 mb-1"),
        dcc.Dropdown(
            id='sort-dropdown',
            options=[
                {'label': 'Win Rate', 'value': 'Win Rate (%)'},
                {'label': 'Distance', 'value': 'Distance (km)'},
                {'label': 'Price', 'value': 'Avg Bid Price'}
            ],
            value='Distance (km)',
            className="w-full p-2 mb-3 border rounded"
        ),
        html.Button("Submit", id="submit-btn", n_clicks=0, className="w-full p-2 bg-blue-500 text-white rounded hover:bg-blue-600 mb-2"),
        html.Button("Download Excel", id="download-btn", n_clicks=0, className="w-full p-2 bg-green-500 text-white rounded hover:bg-green-600 hidden"),
        dcc.Download(id="download-excel"),
        dcc.Loading(
            id='loading',
            type="circle",
            children=html.Div(id='output', className="mt-4")
        ),
        html.Div([
            dcc.ConfirmDialog(
                id='modal',
                message="",
                displayed=False
            ),
            dcc.Store(id='dcc-data'),
            html.Div([
                html.Div([
                    html.H3("Unknown Location", className="text-lg font-semibold mb-2 text-gray-700"),
                    html.P([
                        "Location not recognized. Please enter coordinates. ",
                        html.A("Find coordinates", href="https://www.gps-coordinates.net/", target="_blank", className="text-blue-500 underline")
                    ], className="mb-2"),
                    html.Label("Latitude:", className="block text-sm font-medium text-gray-700 mb-1"),
                    dcc.Input(
                        id='latitude-input',
                        type='number',
                        placeholder='e.g., 22.5726',
                        className="w-full p-2 mb-2 border rounded"
                    ),
                    html.Label("Longitude:", className="block text-sm font-medium text-gray-700 mb-1"),
                    dcc.Input(
                        id='longitude-input',
                        type='number',
                        placeholder='e.g., 88.3639',
                        className="w-full p-2 mb-2 border rounded"
                    ),
                    html.Button("Submit Coordinates", id="submit-coordinates-btn", n_clicks=0,
                                className="w-full p-2 bg-blue-500 text-white rounded hover:bg-blue-600")
                ], className="bg-white p-4 rounded-lg shadow")
            ], id="modal-content", className="fixed inset-0 bg-black bg-opacity-50 hidden flex items-center justify-center")
        ])
    ])
])

# Toggle product modal
@app.callback(
    Output("product-modal", "className"),
    [Input("products-btn", "n_clicks"), Input("close-modal-btn", "n_clicks")],
    [State("product-modal", "className")],
    prevent_initial_call=True
)
def toggle_product_modal(info_clicks, close_clicks, current_class):
    ctx = callback_context
    if not ctx.triggered:
        return "fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center hidden"
    
    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0]
    base_class = "fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center"
    return base_class if triggered_id == 'products-btn' else f"{base_class} hidden"

# Insert product into input
@app.callback(
    Output('recommendation-input', 'value'),
    [Input({'type': 'product-id', 'index': ALL}, 'n_clicks')],
    [State({'type': 'product-id', 'index': ALL}, 'data-product'),
     State('recommendation-input', 'value')],
    prevent_initial_call=True
)
def insert_product(clicks, products, current_value):
    ctx = callback_context
    if not ctx.triggered or not any(clicks):
        return current_value
    
    triggered_id = json.loads(ctx.triggered[0]['prop_id'].split('.')[0])
    product = triggered_id['index']
    
    if current_value and 'for' in current_value.lower():
        parts = current_value.split('for', 1)
        return f"{product} for {parts[1].strip()}"
    return f"{product} for "

# Copy to clipboard
app.clientside_callback(
    """
    function(n_clicks, product) {
        if (n_clicks) {
            navigator.clipboard.writeText(product).then(() => {
                alert('Copied: ' + product);
            }).catch(err => {
                alert('Failed to copy');
            });
        }
        return null;
    }
    """,
    Output({'type': 'copy-btn', 'index': ALL}, 'data-product'),
    Input({'type': 'copy-btn', 'index': ALL}, 'n_clicks'),
    State({'type': 'copy-btn', 'index': ALL}, 'data-product')
)

@app.callback(
    [
        Output('output', 'children'),
        Output('modal', 'message'),
        Output('modal', 'displayed'),
        Output('modal-content', 'className'),
        Output('dcc-data', 'data'),
        Output('download-btn', 'className'),
        Output('download-excel', 'data')
    ],
    [
        Input('submit-btn', 'n_clicks'),
        Input('submit-coordinates-btn', 'n_clicks'),
        Input('sort-dropdown', 'value'),
        Input('download-btn', 'n_clicks')
    ],
    [
        State('recommendation-input', 'value'),
        State('latitude-input', 'value'),
        State('longitude-input', 'value'),
        State('dcc-data', 'data')
    ],
    prevent_initial_call=True
)
def update_output(submit_n_clicks, coords_n_clicks, sort_by, download_n_clicks, requirement, latitude, longitude, stored_data):
    ctx = callback_context
    if not ctx.triggered:
        return [
            "",
            "",
            False,
            "modal-content hidden",
            None,
            "download-btn hidden",
            None
        ]
    
    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0]
    logger.info(f"Callback triggered by {triggered_id}. Submit: {submit_n_clicks}, Coords: {coords_n_clicks}, Download: {download_n_clicks}, Sort: {sort_by}, Input: '{requirement}'")
    print(f"Callback triggered by {triggered_id}. Submit: {submit_n_clicks}, Coords: {coords_n_clicks}, Download: {download_n_clicks}, Sort: {sort_by}, Input: '{requirement}'")
    
    if df.empty:
        logger.error("No data available")
        return [
            html.P("Error: No data loaded from Google Drive", className="text-red-600"),
            "",
            False,
            "modal-content hidden",
            None,
            "download-btn hidden",
            None
        ]

    def sort_bidders(bidders, sort_by):
        if not bidders:
            return []
        try:
            bidders_df = pd.DataFrame(bidders)
            if sort_by == 'Win Rate (%)':
                bidders_df['Win Rate Sort'] = bidders_df['Win Rate (%)'].apply(lambda x: float(x.split()[0]))
                bidders_df = bidders_df.sort_values('Win Rate Sort', ascending=False)
            elif sort_by in bidders_df.columns:
                bidders_df = bidders_df.sort_values(sort_by, ascending=True)
            return bidders_df.drop(columns=['Win Rate Sort'] if 'Win Rate Sort' in bidders_df.columns else []).to_dict('records')
        except Exception as e:
            logger.error(f"Sort bidders error: {e}")
            return []

    def generate_excel(bidders):
        if not bidders:
            return None
        try:
            df_excel = pd.DataFrame(bidders)
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_excel.to_excel(writer, index=False, sheet_name='Bidders')
            output.seek(0)
            return dcc.send_bytes(output.getvalue(), f"bidders_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
        except Exception as e:
            logger.error(f"Excel generation error: {e}")
            return None

    try:
        if triggered_id == 'download-btn':
            if stored_data and 'bidders' in stored_data:
                bidders = sort_bidders(stored_data['bidders'], sort_by)
                return [
                    create_bidder_table(bidders),
                    "",
                    False,
                    "modal-content hidden",
                    stored_data,
                    "download-btn w-full p-2 bg-green-500 text-white rounded hover:bg-green-600",
                    generate_excel(bidders)
                ]
            return [
                html.P("No data to download", className="text-red-600"),
                "No data to download",
                True,
                "modal-content hidden",
                stored_data,
                "download-btn hidden",
                None
            ]

        elif triggered_id in ['submit-btn', 'submit-coordinates-btn']:
            if triggered_id == 'submit-btn':
                if not requirement:
                    logger.warning(f"Empty requirement")
                    return [
                        html.P("Error: Please enter a requirement", className="text-red-600"),
                        "",
                        False,
                        "modal-content hidden",
                        None,
                        "download-btn hidden",
                        None
                    ]
                
                product, location, is_unknown = parse_prompt(requirement, known_locations, known_products)
                print(f"Parsed: product={product}, location={location}, is_unknown={is_unknown}")
                logger.info(f"Parsed: product={product}, location={location}, is_unknown={is_unknown}")
                if not product or not location:
                    logger.error("Invalid product or location")
                    return [
                        html.P("Error: Invalid input format. Use: 'S-30 for Anand' or 'Any Sugar for Anand'", className="text-red-600"),
                        "",
                        False,
                        "modal-content hidden",
                        None,
                        "download-btn hidden",
                        None
                    ]
                
                if is_unknown:
                    logger.warning(f"Unknown location: {location}")
                    return [
                        html.P(f"Error: Location '{location}' not recognized", className="text-red-600"),
                        f"Location '{location}' not recognized. Please provide coordinates.",
                        True,
                        "modal-content flex items-center justify-center",
                        {'product': product, 'location': location, 'bidders': []},
                        "download-btn hidden",
                        None
                    ]
                
                result = process_requirement(df, product, location)
            
            elif triggered_id == 'submit-coordinates-btn':
                if latitude is None or longitude is None:
                    logger.warning("Missing coordinates")
                    return [
                        html.P("Error: Please enter coordinates", className="text-red-600"),
                        "Error: Please enter valid coordinates",
                        True,
                        "modal-content flex items-center justify-center",
                        stored_data,
                        "download-btn hidden",
                        None
                    ]
                
                try:
                    lat, lon = float(latitude), float(longitude)
                    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                        raise ValueError("Invalid coordinates")
                except ValueError as e:
                    logger.error(f"Invalid coordinates: {e}")
                    return [
                        html.P("Error: Invalid coordinates", className="text-red-600"),
                        "Error: Invalid coordinates. Latitude: -90 to 90, longitude: -180 to 180",
                        True,
                        "modal-content flex items-center justify-center",
                        stored_data,
                        "download-btn hidden",
                        None
                    ]
                
                if not stored_data or 'product' not in stored_data or 'location' not in stored_data:
                    logger.error("Missing stored data")
                    return [
                        html.P("Error retrieving location data", className="text-red-600"),
                        "Error retrieving location data",
                        True,
                        "modal-content flex items-center justify-center",
                        stored_data,
                        "download-btn hidden",
                        None
                    ]
                
                product = stored_data['product']
                location = stored_data['location']
                result = process_requirement(df, product, location, custom_coords=(lat, lon))
            
            if "error" in result:
                logger.error(f"Processing error: {result['error']}")
                return [
                    html.P(f"Error: {result['error']}", className="text-red-600"),
                    "",
                    False,
                    "modal-content hidden",
                    None,
                    "download-btn hidden",
                    None
                ]
            
            bidders = result["bidders"]
            if not bidders:
                available_products = sorted(df['Normalized Product'].unique())
                logger.warning(f"No bidders found for {product} in {location}. Available: {available_products}")
                return [
                    html.P(f"No bidders found for {product} in {location}. Try: {', '.join(available_products)}", className="text-red-600"),
                    "",
                    False,
                    "modal-content hidden",
                    None,
                    "download-btn hidden",
                    None
                ]
            
            bidders = sort_bidders(bidders, sort_by)
            stored_data = {'product': product, 'location': location, 'bidders': bidders}
            return [
                create_bidder_table(bidders),
                "",
                False,
                "modal-content hidden",
                stored_data,
                "download-btn w-full p-2 bg-green-500 text-white rounded hover:bg-green-600",
                None
            ]

        elif triggered_id == 'sort-dropdown':
            if not stored_data or 'bidders' not in stored_data:
                logger.warning("No bidders to sort")
                return [
                    html.P("Error: No bidders to sort", className="text-red-600"),
                    "",
                    False,
                    "modal-content hidden",
                    stored_data,
                    "download-btn hidden",
                    None
                ]
            
            bidders = sort_bidders(stored_data['bidders'], sort_by)
            stored_data['bidders'] = bidders
            return [
                create_bidder_table(bidders),
                "",
                False,
                "modal-content hidden",
                stored_data,
                "download-btn w-full p-2 bg-green-500 text-white rounded hover:bg-green-600",
                None
            ]
    except Exception as e:
        error_msg = f"Callback error: {str(e)}"
        logger.error(error_msg)
        print(error_msg)
        return [
            html.P(f"Error: {error_msg}", className="text-red-600"),
            "",
            False,
            "modal-content hidden",
            None,
            "download-btn hidden",
            None
        ]

if __name__ == '__main__':
    print("Starting Dash app...")
    logger.info("Starting Dash app")
    app.run_server(host='0.0.0.0', port=8050)