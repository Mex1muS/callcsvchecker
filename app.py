import os
import pandas as pd
import json
from flask import Flask, request, jsonify, render_template
from datetime import datetime

# --- FLASK SETUP ---
app = Flask(__name__)

# --- CONFIGURATION (Paths for your data files) ---
CSV_WEB_LOG = 'web_log.csv'
CSV_SCAM_LIST_SOURCE = 'call_scam.csv'    
CSV_OFFICIAL_LIST_SOURCE = 'call_official.csv'

# --- GLOBAL DATA AND LIST LOADING ---
# OFFICIAL_NUMBERS ถูกเปลี่ยนเป็น Dictionary เพื่อเก็บข้อมูลหน่วยงาน
OFFICIAL_NUMBERS_DETAILS = {} 
BLACKLIST_NUMBERS = set()

def load_data_and_model():
    """Loads CSV numbers and their details into memory."""
    global OFFICIAL_NUMBERS_DETAILS, BLACKLIST_NUMBERS

    print("--- Starting List Load (CSV Only) ---")
    
    # 1. Load Official List (จาก official_list.csv)
    try:
        if os.path.exists(CSV_OFFICIAL_LIST_SOURCE):
            # โหลดทุกคอลัมน์ (phone, result, feedback/หน่วยงาน)
            # Assumption: Headers are missing/not used, so we use index 0 and 2
            df_official = pd.read_csv(CSV_OFFICIAL_LIST_SOURCE, header=None, encoding='utf-8')
            # สร้าง Dictionary {phone: feedback/หน่วยงาน}
            # ใช้คอลัมน์ 0 เป็นเบอร์ และ คอลัมน์ 2 เป็นหน่วยงาน (จาก snippet: 021234567,official,กสทช.)
            OFFICIAL_NUMBERS_DETAILS = {
                str(row[0]).strip(): str(row[2]).strip()
                for index, row in df_official.iterrows()
            }
            print(f"Loaded {len(OFFICIAL_NUMBERS_DETAILS)} official numbers with details.")
        else:
            print(f"Warning: {CSV_OFFICIAL_LIST_SOURCE} not found. Skipping official list.")
    except Exception as e:
        print(f"Error loading official list: {e}")

    # 2. Load Blacklist (จาก call_final.csv)
    try:
        if os.path.exists(CSV_SCAM_LIST_SOURCE):
            df_scam = pd.read_csv(CSV_SCAM_LIST_SOURCE, encoding='utf-8')
            # Blacklist logic: Filter for entries marked as 'scam'
            blacklist = df_scam[df_scam['result'].astype(str).str.lower().str.contains('scam') & df_scam['phone'].notna()]
            BLACKLIST_NUMBERS = set(blacklist['phone'].astype(str).str.strip())
            print(f"Loaded {len(BLACKLIST_NUMBERS)} blacklist numbers from {CSV_SCAM_LIST_SOURCE}.")
        else:
            print(f"Warning: {CSV_SCAM_LIST_SOURCE} not found. Starting with empty blacklist.")
    except Exception as e:
        print(f"Error loading scammer list: {e}")

    # 3. Ensure the web log file exists with headers
    if not os.path.exists(CSV_WEB_LOG):
        print(f"Creating new log file: {CSV_WEB_LOG}")
        pd.DataFrame(columns=['datetime', 'phone', 'msg', 'result', 'feedback']).to_csv(CSV_WEB_LOG, index=False, encoding='utf-8')

    print("--- List Load Complete ---")

# --- CORE LOGIC FUNCTIONS ---

def log_call(phone, msg, result):
    """Appends the call check result to the new web log file (web_log.csv)."""
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg_log = msg if msg else 'list check only' # เปลี่ยนเป็น 'list check only'
        # เขียนลงไฟล์ web_log.csv
        new_entry = {'datetime': now, 'phone': phone, 'msg': msg_log, 'result': result, 'feedback': 'web_check_list_only'}
        
        df_new = pd.DataFrame([new_entry])
        df_new.to_csv(CSV_WEB_LOG, mode='a', header=False, index=False, encoding='utf-8')
    except Exception as e:
        print(f"Error writing to log file ({CSV_WEB_LOG}): {e}")

# --- FLASK ROUTES ---

# Route สำหรับหน้าหลัก (Search)
@app.route('/')
def index():
    """Renders the main search HTML page."""
    return render_template('index.html')

# Route สำหรับหน้า Log
@app.route('/log')
def view_log_page():
    """Renders the dedicated log viewing HTML page."""
    return render_template('log.html')


# API Endpoint สำหรับดึง Log ทั้งหมด (สำหรับหน้า /log)
@app.route('/api/logs/all')
def get_call_log():
    """Reads and returns the entire call log from web_log.csv for the log page."""
    try:
        if not os.path.exists(CSV_WEB_LOG):
            return jsonify({"error": "Web log file not found."}), 404
            
        df_log = pd.read_csv(CSV_WEB_LOG, encoding='utf-8')
        
        # เลือกคอลัมน์ที่ต้องการแสดง และจัดเรียงจากใหม่ไปเก่า
        log_data = df_log[['datetime', 'phone', 'msg', 'result']].sort_values(
            by='datetime', ascending=False
        ).to_dict('records')
        
        return jsonify(log_data)
    except Exception as e:
        print(f"Error reading call log: {e}")
        return jsonify({"error": "Failed to read log data"}), 500

# API Endpoint สำหรับการตรวจสอบ (Check)
@app.route('/api/check', methods=['POST'])
def check_scam():
    """API Endpoint to check a number using CSV lists only."""
    data = request.get_json()
    phone = data.get('phone', '').strip()
    message = data.get('message', '').strip()

    final_result = {"result": "❓ กรุณาใส่เบอร์โทรศัพท์", "color": "#666666"}
    
    if not phone:
        return jsonify(final_result)

    # 1. Check Phone Number against Official List (Priority 1)
    if phone in OFFICIAL_NUMBERS_DETAILS:
        agency = OFFICIAL_NUMBERS_DETAILS[phone]
        final_result = {
            "result": f"🟢✅ หมายเลขหน่วยงาน: {agency}", 
            "color": "#2ECC71"
        }
    # 2. Check Phone Number against Blacklist (Priority 2)
    elif phone in BLACKLIST_NUMBERS:
        final_result = {
            "result": "🔴🚨 หมายเลขมิจฉาชีพ", 
            "color": "#E74C3C"
        }
    # 3. Not Found
    else:
        final_result = {
            "result": "💛⭐ หมายเลขไม่พบในระบบ (ถือว่าปลอดภัยเบื้องต้น)", 
            "color": "#FFC300"
        }

    # Log the result
    log_call(phone, message, final_result['result'])
    
    # Return the result
    return jsonify(final_result)

if __name__ == '__main__':
    with app.app_context():
        load_data_and_model()
        
    app.run(debug=True)