import os
import uuid
import requests
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
from pymongo import MongoClient

app = Flask(__name__)
# Enable CORS for local testing and production
CORS(app)

# --- DIRECTORY SETUP ---
# Detects the folder where this file is located
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
# Moves up one level to the project root (WebCert/)
BASE_DIR = os.path.dirname(CURRENT_DIR)
# Path for uploaded receipts
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
# Path for HTML files
FRONTEND_FOLDER = os.path.join(BASE_DIR, 'frontend')

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- CONFIGURATION (Environment Variables) ---
# When hosting on Render, you set these in the 'Environment' tab
# For local, it will use the default values provided below
MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://boraffcremix_db_user:YOUR_PASSWORD@irracert.pt0grqz.mongodb.net/?appName=irracert")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8379666289:AAEiYiFzSf4rkkP6g_u_13vbrv0ILi9eh4o")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "5007619095")
GMAIL_USER = os.environ.get("GMAIL_USER", "irra11store@gmail.com")
GMAIL_APP_PASS = os.environ.get("GMAIL_APP_PASS", "scvo cdjt ucdw kvii")

# --- DATABASE CONNECTION ---
try:
    client = MongoClient(MONGO_URI)
    db = client['WebCertDB']
    orders_col = db['orders']
    # Test connection
    client.admin.command('ping')
    print("✅ Connected to MongoDB Atlas")
except Exception as e:
    print(f"❌ MongoDB Connection Error: {e}")

# --- HELPER FUNCTIONS ---
def send_gmail_logic(to_email, order_id, link):
    subject = f"Your iOS Certificate is Ready! - {order_id}"
    body = f"Hello,\n\nYour certificate has been issued.\n\nDownload Link: {link}\n\nThank you for choosing Irra Esign."
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = GMAIL_USER
    msg['To'] = to_email
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASS)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Email Error: {e}")
        return False

# --- FRONTEND ROUTES (Serving HTML) ---

@app.route('/')
def serve_index():
    return send_from_directory(FRONTEND_FOLDER, 'index.html')

@app.route('/admin-panel')
def serve_admin():
    # Simple security: You can add ?pw=yourpass to the URL if you want
    return send_from_directory(FRONTEND_FOLDER, 'admin.html')

@app.route('/uploads/<filename>')
def serve_receipt(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# --- API ROUTES ---

@app.route('/api/orders', methods=['GET'])
def get_orders():
    try:
        orders = list(orders_col.find())
        orders_dict = {}
        for o in orders:
            o['_id'] = str(o['_id'])
            orders_dict[o['order_id']] = o
        return jsonify(orders_dict)
    except:
        return jsonify({}), 500

@app.route('/verify-payment', methods=['POST'])
def verify_payment():
    try:
        email = request.form.get('email')
        udid = request.form.get('udid')
        file = request.files.get('receipt')

        if not file or not email or not udid:
            return jsonify({"success": False, "msg": "Missing data"}), 400

        order_id = str(uuid.uuid4())[:8].upper()
        filename = secure_filename(f"{order_id}_{file.filename}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        receipt_url = f"/uploads/{filename}"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Save to Mongo
        order_doc = {
            "order_id": order_id,
            "email": email,
            "udid": udid,
            "timestamp": timestamp,
            "status": "pending",
            "download_link": "",
            "receipt_url": receipt_url
        }
        orders_col.insert_one(order_doc)

        # Telegram Notification
        # window.location.origin replacement for Telegram
        base_url = request.host_url.rstrip('/') 
        receipt_link = f"{base_url}{receipt_url}"
        
        msg = (f"🔔 <b>NEW ORDER</b>\n\n"
               f"🆔 ID: {order_id}\n"
               f"📧 Email: {email}\n"
               f"📱 UDID: {udid}\n"
               f"🖼️ <a href='{receipt_link}'>View Receipt</a>")
        
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", 
                      json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"})

        return jsonify({"success": True, "order_id": order_id})
    except Exception as e:
        print(f"Verify Payment Error: {e}")
        return jsonify({"success": False}), 500

@app.route('/api/send-link', methods=['POST'])
def send_link():
    data = request.json
    oid = data.get('order_id')
    link = data.get('link')
    orders_col.update_one({"order_id": oid}, {"$set": {"download_link": link, "status": "completed"}})
    return jsonify({"success": True})

@app.route('/api/send-email', methods=['POST'])
def api_send_email():
    oid = request.json.get('order_id')
    order = orders_col.find_one({"order_id": oid})
    if order and order.get('download_link'):
        if send_gmail_logic(order['email'], oid, order['download_link']):
            return jsonify({"success": True})
    return jsonify({"success": False}), 500

# --- START SERVER ---
if __name__ == '__main__':
    # PORT is required for hosting on Render
    port = int(os.environ.get("PORT", 5000))
    print(f"\n🚀 IRRA ESIGN RUNNING ON PORT {port}")
    app.run(host='0.0.0.0', port=port, debug=True)