import os
import pandas as pd
from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy 
from sqlalchemy import func # สำหรับใช้ func.now() ในการบันทึกเวลาปัจจุบัน

# --- FLASK SETUP ---
app = Flask(__name__)

# --- DATABASE CONFIGURATION (PostgreSQL) ---

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///web_log.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- Define Log Model (แทนที่ web_log.csv) ---
class LogEntry(db.Model):
    __tablename__ = 'log_entries' # ชื่อตารางสำหรับ Log
    id = db.Column(db.Integer, primary_key=True)
    datetime = db.Column(db.DateTime, default=func.now()) # บันทึกเวลาปัจจุบันอัตโนมัติ
    phone = db.Column(db.String(50), nullable=False)
    msg = db.Column(db.String(255))
    result = db.Column(db.String(255), nullable=False)
    feedback = db.Column(db.String(255))


# --- CONFIGURATION (Paths for your data files) ---
# CSV_WEB_LOG ไม่จำเป็นต้องใช้แล้ว
APP_ROOT = os.path.dirname(os.path.abspath(__file__))

# การโหลด CSVs ข้อมูลหลัก
CSV_SCAM_LIST_SOURCE = os.path.join(APP_ROOT, 'call_scam.csv')
CSV_OFFICIAL_LIST_SOURCE = os.path.join(APP_ROOT, 'call_official.csv')

# --- GLOBAL DATA AND LIST LOADING ---
OFFICIAL_NUMBERS_DETAILS = {} 
BLACKLIST_NUMBERS = set()

def load_data_and_model():
    """Loads CSV numbers and their details into memory."""
    global OFFICIAL_NUMBERS_DETAILS, BLACKLIST_NUMBERS

    print("--- Starting List Load (CSV Only) ---")
    
    # 1. Load Official List
    try:
        # **Note:** บน Render/PA ไฟล์ทั้งหมดจะอยู่ใน Root Directory
        if os.path.exists(CSV_OFFICIAL_LIST_SOURCE):
            # สมมติว่าไฟล์ CSV มี header (phone, result, feedback)
            df_official = pd.read_csv(CSV_OFFICIAL_LIST_SOURCE, encoding='utf-8')
            OFFICIAL_NUMBERS_DETAILS = {
                str(row['phone']).strip(): str(row['feedback']).strip() 
                for index, row in df_official.iterrows()
            }
            print(f"Loaded {len(OFFICIAL_NUMBERS_DETAILS)} official numbers with details.")
        else:
            print(f"Warning: {CSV_OFFICIAL_LIST_SOURCE} not found. Skipping official list.")
    except Exception as e:
        print(f"Error loading official list: {e}")

    # 2. Load Blacklist
    try:
        if os.path.exists(CSV_SCAM_LIST_SOURCE):
            df_scam = pd.read_csv(CSV_SCAM_LIST_SOURCE, encoding='utf-8')
            blacklist = df_scam[df_scam['result'].astype(str).str.lower().str.contains('scam') & df_scam['phone'].notna()]
            BLACKLIST_NUMBERS = set(blacklist['phone'].astype(str).str.strip())
            print(f"Loaded {len(BLACKLIST_NUMBERS)} blacklist numbers from {CSV_SCAM_LIST_SOURCE}.")
        else:
            print(f"Warning: {CSV_SCAM_LIST_SOURCE} not found. Starting with empty blacklist.")
    except Exception as e:
        print(f"Error loading scammer list: {e}")

    # 3. Ensure the Log Table exists in the database
    # การสร้างตารางต้องทำภายใต้ application context
    try:
        with app.app_context():
            db.create_all()
            print("Log database table ensured (LogEntry).")
    except Exception as e:
        print(f"Warning: Could not connect to database or create tables: {e}")
        print("Running in list-only mode (Logging disabled due to DB error).")
    
    print("--- List Load Complete ---")

# --- CORE LOGIC FUNCTIONS ---

def log_call(phone, msg, result):
    """Saves the call check result to the PostgreSQL database."""
    try:
        msg_log = msg if msg else 'list check only'
        
        # สร้าง Object LogEntry ใหม่
        new_entry = LogEntry(
            phone=phone,
            msg=msg_log,
            result=result,
            feedback='web_check_list_only'
        )
        
        # บันทึกเข้าฐานข้อมูล
        db.session.add(new_entry)
        db.session.commit()
    except Exception as e:
        # หากเชื่อมต่อ DB ไม่ได้หรือเกิด error ให้ทำการ rollback และไม่ให้แอปฯ พัง
        db.session.rollback() 
        print(f"Error writing to database log: {e}")

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
    """Reads and returns the entire call log from the database."""
    try:
        # Query ข้อมูลจากฐานข้อมูล
        log_entries = LogEntry.query.order_by(LogEntry.datetime.desc()).all()
        
        log_data = []
        for entry in log_entries:
            log_data.append({
                'datetime': entry.datetime.strftime("%Y-%m-%d %H:%M:%S"),
                'phone': entry.phone,
                'msg': entry.msg,
                'result': entry.result
            })
        
        return jsonify(log_data)
    except Exception as e:
        print(f"Error reading call log from database: {e}")
        return jsonify({"error": "Failed to read log data from database"}), 500

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

    # Log the result (บันทึกข้อมูลลงฐานข้อมูล)
    log_call(phone, message, final_result['result'])
    
    # Return the result
    return jsonify(final_result)

# โหลดข้อมูล CSV และสร้างตาราง DB (จะรันเมื่อ Gunicorn/Render โหลดโมดูล)
load_data_and_model() 


if __name__ == '__main__':
    # เมื่อรันในเครื่องตัวเอง จะสร้างไฟล์ SQLite database ขึ้นมา
    app.run()
