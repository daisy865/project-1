from flask import Flask, request, jsonify, render_template, redirect, url_for
import mysql.connector
from flask_cors import CORS
from dotenv import load_dotenv
import os
from werkzeug.utils import secure_filename
import base64
import time

load_dotenv()

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

# MySQL Configuration
db_config = {
    'host': os.getenv('MYSQL_HOST', 'localhost'),
    'user': os.getenv('MYSQL_USER', 'root'),
    'password': os.getenv('MYSQL_PASSWORD', ''),
    'database': os.getenv('MYSQL_DATABASE', 'reportme')
}

# Configure upload folder
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Create uploads directory if it doesn't exist
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def init_db():
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id INT AUTO_INCREMENT PRIMARY KEY,
                project_name VARCHAR(255),
                location VARCHAR(255),
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS report_images (
                id INT AUTO_INCREMENT PRIMARY KEY,
                report_id INT,
                image_path VARCHAR(255),
                FOREIGN KEY (report_id) REFERENCES reports(id)
            )
        """)
        conn.commit()
    except mysql.connector.Error as err:
        print(f"Error: {err}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

@app.route('/')
def root():
    return redirect('/report-vandalized-projects')

@app.route('/report-vandalized-projects')
def index():
    return app.send_static_file('index.html')

@app.route('/admin')
def admin():
    return render_template('admin.html')

@app.route('/report-vandalized-projects/submit', methods=['POST'])
def submit():
    try:
        project_name = request.form.get('Project Name')
        location = request.form.get('Location')
        description = request.form.get('Description')
        
        if not all([project_name, location, description]):
            return jsonify({"error": "Missing required fields"}), 400
        
        # Handle image upload
        image_paths = []
        if 'images[]' in request.files:
            files = request.files.getlist('images[]')
            for file in files:
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(filepath)
                    image_paths.append(filepath)

        # Handle base64 image from camera
        if 'camera_image' in request.form:
            try:
                image_data = request.form['camera_image'].split(',')[1]  # Remove data:image/jpeg;base64,
                binary_data = base64.b64decode(image_data)
                filename = f'camera_photo_{int(time.time())}.jpg'
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                with open(filepath, 'wb') as f:
                    f.write(binary_data)
                image_paths.append(filepath)
            except Exception as e:
                print(f"Error saving camera image: {e}")

        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
        # Insert report data
        sql = """INSERT INTO reports (project_name, location, description)
                 VALUES (%s, %s, %s)"""
        cursor.execute(sql, (project_name, location, description))
        report_id = cursor.lastrowid
        
        # If we want to store image paths in database, we can add them to a separate table
        if image_paths:
            image_sql = """INSERT INTO report_images (report_id, image_path) VALUES (%s, %s)"""
            for path in image_paths:
                cursor.execute(image_sql, (report_id, path))
        
        conn.commit()
        return jsonify({"message": "Data submitted successfully"}), 200
        
    except mysql.connector.Error as err:
        print(f"MySQL Error: {err}")
        return jsonify({"error": f"Database error occurred: {str(err)}"}), 500
    except Exception as e:
        print(f"General Error: {e}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

@app.route('/report-vandalized-projects/get_reports')
def get_reports():
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)
        
        # Get latest 10 reports with their images
        cursor.execute("""
            SELECT 
                r.id,
                r.project_name,
                r.location,
                r.description,
                r.created_at,
                GROUP_CONCAT(ri.image_path) as image_paths
            FROM reports r
            LEFT JOIN report_images ri ON r.id = ri.report_id
            GROUP BY r.id
            ORDER BY r.created_at DESC
            LIMIT 10
        """)
        
        reports = cursor.fetchall()
        
        # Process the reports to include image paths and format dates
        for report in reports:
            # Format the datetime for display
            if report['created_at']:
                report['created_at'] = report['created_at'].strftime('%Y-%m-%d %H:%M:%S')
            
            # Process image paths
            if report['image_paths']:
                report['images'] = report['image_paths'].split(',')
            else:
                report['images'] = []
            del report['image_paths']
        
        return jsonify(reports)
        
    except mysql.connector.Error as err:
        print(f"MySQL Error: {err}")
        return jsonify({"error": "Database error occurred"}), 500
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

@app.route('/api/reports')
def get_reports_api():
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)
        
        # Get reports with their images
        cursor.execute("""
            SELECT r.*, GROUP_CONCAT(ri.image_path) as images
            FROM reports r
            LEFT JOIN report_images ri ON r.id = ri.report_id
            GROUP BY r.id
            ORDER BY r.created_at DESC
        """)
        
        reports = cursor.fetchall()
        
        # Process the reports to convert image paths to list
        for report in reports:
            if report['images']:
                report['images'] = report['images'].split(',')
            else:
                report['images'] = []
                
            # Convert datetime objects to string for JSON serialization
            report['created_at'] = report['created_at'].isoformat()
        
        return jsonify(reports)
        
    except mysql.connector.Error as err:
        print(f"Database error: {err}")
        return jsonify({"error": "Database error"}), 500
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

if __name__ == '__main__':
    init_db()
    app.run(host='127.0.0.1', port=5000, debug=True)