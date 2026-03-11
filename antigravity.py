# ============================================
# CIVICVOICE - Civic Issue Reporting System
# Complete Application with All Features
# ============================================

import customtkinter as ctk  # type: ignore
import sqlite3
from tkinter import messagebox, ttk, filedialog
import matplotlib.pyplot as plt  # type: ignore
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg  # type: ignore
from datetime import datetime, timedelta
import hashlib
import re
import os
from PIL import Image, ImageTk  # type: ignore
from typing import Optional
import shutil
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('civicvoice.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ============================================
# CONFIGURATION
# ============================================
class Config:
    """Application configuration"""
    # Resolve all paths relative to this script's directory
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DB_NAME = os.path.join(BASE_DIR, "civicvoice.db")
    ADMIN_PASSWORD = "Admin@2026!"
    SESSION_TIMEOUT = 30
    MAX_LOGIN_ATTEMPTS = 5
    LOCKOUT_MINUTES = 15
    UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
    MAX_FILE_SIZE = 5242880  # 5MB
    ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "bmp"}
    CATEGORIES = ["Roads", "Waste Management", "Water Leakage", "Streetlight", "Other"]
    STATUSES = ["Pending", "In Progress", "Resolved"]
    PRIORITIES = ["Low", "Normal", "High", "Critical"]

    @staticmethod
    def init():
        """Create required directories"""
        if not os.path.exists(Config.UPLOAD_DIR):
            os.makedirs(Config.UPLOAD_DIR)

# ============================================
# SECURITY MANAGER
# ============================================
class SecurityManager:
    """Password hashing and input validation"""

    @staticmethod
    def hash_password(password):
        """Hash password using SHA-256 encryption"""
        return hashlib.sha256(password.encode()).hexdigest()

    @staticmethod
    def verify_password(password, hashed):
        """Verify password against stored hash"""
        return SecurityManager.hash_password(password) == hashed

    @staticmethod
    def validate_email(email):
        """Validate email format using regex"""
        return re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email) is not None

    @staticmethod
    def validate_password(password):
        """Enforce strong password requirements"""
        if len(password) < 8:
            return False, "Password must be at least 8 characters"
        if not re.search(r'[A-Z]', password):
            return False, "Must contain at least 1 uppercase letter"
        if not re.search(r'[a-z]', password):
            return False, "Must contain at least 1 lowercase letter"
        if not re.search(r'[0-9]', password):
            return False, "Must contain at least 1 digit"
        if not re.search(r'[!@#$%^&*()_+\-=\[\]{};:\'",.<>?/\\|`~]', password):
            return False, "Must contain at least 1 special character"
        return True, "Password is strong"

    @staticmethod
    def validate_phone(phone):
        """Validate phone number format"""
        cleaned = re.sub(r'[^\d+]', '', phone)
        if re.match(r'^\+?[1-9]\d{9,14}$', cleaned):
            return True, cleaned
        return False, "Invalid phone number"

# ============================================
# DATABASE MANAGER
# ============================================
class DatabaseManager:
    """Manages SQLite database operations"""

    def __init__(self, db_name=Config.DB_NAME):
        self.db_name = db_name
        self.create_tables()

    def get_connection(self):
        """Get database connection with row factory"""
        conn = sqlite3.connect(self.db_name, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def create_tables(self):
        """Create all required database tables and handle schema migrations"""
        conn = self.get_connection()
        cur = conn.cursor()

        # Users table - stores registered users
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            phone TEXT,
            role TEXT NOT NULL CHECK(role IN ('user','admin')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

        # Complaints table - stores all civic complaints
        cur.execute("""
        CREATE TABLE IF NOT EXISTS complaints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            category TEXT NOT NULL,
            location TEXT,
            phone TEXT,
            image_path TEXT,
            status TEXT NOT NULL DEFAULT 'Pending'
                CHECK(status IN ('Pending','In Progress','Resolved')),
            priority TEXT DEFAULT 'Normal',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_email) REFERENCES users(email)
        )""")

        # Migration: Add missing 'phone' column to 'users' if it doesn't exist
        try:
            cur.execute("ALTER TABLE users ADD COLUMN phone TEXT")
            logger.info("Migrated: Added 'phone' column to users table")
        except sqlite3.OperationalError:
            # Column already exists, ignore
            pass

        # Migration: Add missing 'phone' column to 'complaints' if it doesn't exist
        try:
            cur.execute("ALTER TABLE complaints ADD COLUMN phone TEXT")
            logger.info("Migrated: Added 'phone' column to complaints table")
        except sqlite3.OperationalError:
            # Column already exists, ignore
            pass

        # Migration: Add missing 'location' column to 'complaints' if it doesn't exist
        try:
            cur.execute("ALTER TABLE complaints ADD COLUMN location TEXT")
            logger.info("Migrated: Added 'location' column to complaints table")
        except sqlite3.OperationalError:
            # Column already exists, ignore
            pass

        # Login attempts table - for rate limiting
        cur.execute("""
        CREATE TABLE IF NOT EXISTS login_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            attempt_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            success BOOLEAN DEFAULT 0
        )""")

        # Create indexes for performance
        cur.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_complaints_email ON complaints(user_email)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_complaints_status ON complaints(status)")

        conn.commit()
        conn.close()
        logger.info("Database initialized/migrated successfully")

# ============================================
# FILE MANAGER
# ============================================
class FileManager:
    """Manages image file uploads with validation"""

    @staticmethod
    def validate_image(path):
        """Validate image file type and size"""
        if not os.path.exists(path):
            return False, "File not found"
        if os.path.getsize(path) > Config.MAX_FILE_SIZE:
            return False, "File exceeds 5MB limit"
        ext = path.split('.')[-1].lower()
        if ext not in Config.ALLOWED_EXTENSIONS:
            return False, f"Only {', '.join(Config.ALLOWED_EXTENSIONS)} files allowed"
        return True, "Valid"

    @staticmethod
    def save_image(path, complaint_id):
        """Save uploaded image with unique timestamp filename"""
        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            fname = f"complaint_{complaint_id}_{ts}_{os.path.basename(path)}"
            dest = os.path.join(Config.UPLOAD_DIR, fname)
            shutil.copy2(path, dest)
            logger.info(f"Image saved: {dest}")
            return dest
        except Exception as e:
            logger.error(f"Error saving image: {e}")
            return None

# ============================================
# AUTHENTICATION SERVICE
# ============================================
class AuthService:
    """Handles user registration and login with security features"""

    def __init__(self, db):
        self.db = db
        self.current_user: Optional[dict] = None

    def register(self, name, email, password, phone, role, admin_pass=None):
        """Register a new user with validation and password encryption"""
        # Validate all inputs
        if not name or len(name) < 2:
            return False, "Name must be at least 2 characters"
        if not SecurityManager.validate_email(email):
            return False, "Invalid email format"
        ok, cleaned = SecurityManager.validate_phone(phone)
        if not ok:
            return False, cleaned
        ok, msg = SecurityManager.validate_password(password)
        if not ok:
            return False, msg

        # Admin registration requires admin password
        if role == "admin":
            conn = self.db.get_connection()
            count = conn.execute(
                "SELECT COUNT(*) FROM users WHERE role='admin'"
            ).fetchone()[0]
            conn.close()
            if count > 0 and admin_pass != Config.ADMIN_PASSWORD:
                return False, "Incorrect admin password!"

        try:
            conn = self.db.get_connection()
            hashed = SecurityManager.hash_password(password)
            conn.execute(
                "INSERT INTO users (name,email,password,phone,role) VALUES (?,?,?,?,?)",
                (name, email, hashed, cleaned, role)
            )
            conn.commit()
            conn.close()
            logger.info(f"User registered: {email} ({role})")
            return True, f"{role.upper()} account created successfully!"
        except sqlite3.IntegrityError:
            return False, "Email already exists"
        except Exception as e:
            return False, str(e)

    def login(self, email, password):
        """Authenticate user with rate limiting and account lockout"""
        if not SecurityManager.validate_email(email):
            return False, None, "Invalid email format"

        conn = self.db.get_connection()

        # Check if account is locked (too many failed attempts)
        threshold = datetime.now() - timedelta(minutes=Config.LOCKOUT_MINUTES)
        fails = conn.execute(
            "SELECT COUNT(*) FROM login_attempts WHERE email=? AND success=0 AND attempt_time>?",
            (email, threshold)
        ).fetchone()[0]

        if fails >= Config.MAX_LOGIN_ATTEMPTS:
            conn.close()
            return False, None, f"Account locked. Try again in {Config.LOCKOUT_MINUTES} min."

        # Verify credentials
        user = conn.execute(
            "SELECT name,password,role,phone FROM users WHERE email=?",
            (email,)
        ).fetchone()

        if user and SecurityManager.verify_password(password, user['password']):
            # Successful login - clear failed attempts
            conn.execute("INSERT INTO login_attempts (email,success) VALUES (?,1)", (email,))
            conn.execute("DELETE FROM login_attempts WHERE email=? AND success=0", (email,))
            conn.commit()
            conn.close()
            self.current_user = {
                'email': email, 'name': user['name'],
                'role': user['role'], 'phone': user['phone']
            }
            logger.info(f"User logged in: {email} ({user['role']})")
            return True, user['role'], "Login successful!"
        else:
            # Failed login - record attempt
            conn.execute("INSERT INTO login_attempts (email,success) VALUES (?,0)", (email,))
            conn.commit()
            conn.close()
            return False, None, f"Invalid credentials ({fails+1}/{Config.MAX_LOGIN_ATTEMPTS})"

    def logout(self):
        """Log user out"""
        if self.current_user:
            logger.info(f"User logged out: {self.current_user['email']}")  # type: ignore
        self.current_user = None

# ============================================
# COMPLAINT SERVICE
# ============================================
class ComplaintService:
    """Handles all complaint CRUD operations"""

    def __init__(self, db):
        self.db = db

    def create(self, email, title, desc, category, location, phone,
               image_path=None, priority="Normal"):
        """Create a new complaint with optional image upload"""
        if not title or len(title) < 5:
            return False, "Title must be at least 5 characters"
        if not desc or len(desc) < 10:
            return False, "Description must be at least 10 characters"
        try:
            conn = self.db.get_connection()
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO complaints
                   (user_email,title,description,category,location,phone,status,priority)
                   VALUES (?,?,?,?,?,?,'Pending',?)""",
                (email, title, desc, category, location, phone, priority)
            )
            conn.commit()
            cid = cur.lastrowid

            # Handle image upload
            if image_path:
                ok, msg = FileManager.validate_image(image_path)
                if not ok:
                    conn.close()
                    return False, f"Image error: {msg}"
                saved = FileManager.save_image(image_path, cid)
                if saved:
                    cur.execute("UPDATE complaints SET image_path=? WHERE id=?", (saved, cid))
                    conn.commit()
            conn.close()
            logger.info(f"Complaint #{cid} created by {email}")
            return True, f"Complaint #{cid} submitted successfully!"
        except Exception as e:
            logger.error(f"Error creating complaint: {e}")
            return False, str(e)

    def get_user_complaints(self, email, status_filter=None, category_filter=None):
        """Get complaints for a specific user with optional filters"""
        conn = self.db.get_connection()
        q = "SELECT * FROM complaints WHERE user_email=?"
        params = [email]
        if status_filter and status_filter != "All":
            q += " AND status=?"
            params.append(status_filter)
        if category_filter and category_filter != "All":
            q += " AND category=?"
            params.append(category_filter)
        q += " ORDER BY created_at DESC"
        rows = conn.execute(q, params).fetchall()
        conn.close()
        return rows

    def get_all_complaints(self, status_filter=None, category_filter=None, search=None):
        """Get all complaints with optional filters and search (admin)"""
        conn = self.db.get_connection()
        q = "SELECT * FROM complaints WHERE 1=1"
        params = []
        if status_filter and status_filter != "All":
            q += " AND status=?"
            params.append(status_filter)
        if category_filter and category_filter != "All":
            q += " AND category=?"
            params.append(category_filter)
        if search:
            q += " AND (title LIKE ? OR description LIKE ? OR user_email LIKE ?)"
            s = f"%{search}%"
            params.extend([s, s, s])
        q += " ORDER BY created_at DESC"
        rows = conn.execute(q, params).fetchall()
        conn.close()
        return rows

    def update_status(self, cid, status):
        """Update complaint status (admin action)"""
        conn = self.db.get_connection()
        conn.execute("UPDATE complaints SET status=? WHERE id=?", (status, cid))
        conn.commit()
        conn.close()
        logger.info(f"Complaint #{cid} status updated to {status}")
        return True, "Status updated successfully!"

    def get_details(self, cid):
        """Get full details of a specific complaint"""
        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM complaints WHERE id=?", (cid,)).fetchone()
        conn.close()
        return row

# ============================================
# ANALYTICS SERVICE
# ============================================
class AnalyticsService:
    """Provides complaint statistics for charts"""

    def __init__(self, db):
        self.db = db

    def get_stats(self):
        """Get aggregated complaint statistics"""
        conn = self.db.get_connection()
        status = dict(conn.execute(
            "SELECT status, COUNT(*) FROM complaints GROUP BY status"
        ).fetchall())
        category = dict(conn.execute(
            "SELECT category, COUNT(*) FROM complaints GROUP BY category"
        ).fetchall())
        priority = dict(conn.execute(
            "SELECT priority, COUNT(*) FROM complaints GROUP BY priority"
        ).fetchall())
        total = conn.execute("SELECT COUNT(*) FROM complaints").fetchone()[0]
        conn.close()
        return {
            'status': status, 'category': category,
            'priority': priority, 'total': total
        }

# ============================================
# LOGIN WINDOW (Main Application Window)
# ============================================
class LoginWindow(ctk.CTk):
    """
    Main application window with login and registration forms.
    Acts as the entry point for the CivicVoice application.
    """

    def __init__(self):
        super().__init__()

        # Set dark theme
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("CivicVoice - Civic Issue Reporting System")
        self.geometry("600x750")
        self.resizable(False, False)

        # Initialize application
        Config.init()
        self.db = DatabaseManager()
        self.auth = AuthService(self.db)
        self.complaints = ComplaintService(self.db)
        self.analytics = AnalyticsService(self.db)
        self.build_ui()

    def build_ui(self):
        """Build the main login/register UI"""
        # Header bar with app title
        header = ctk.CTkFrame(self, fg_color="#1565C0", height=80)
        header.pack(fill="x")
        header.pack_propagate(False)
        ctk.CTkLabel(
            header, text="🔔 CIVICVOICE",
            font=("Arial", 28, "bold"), text_color="white"
        ).pack(pady=8)
        ctk.CTkLabel(
            header, text="Civic Issue Reporting System",
            font=("Arial", 12), text_color="#BBDEFB"
        ).pack()

        # Toggle buttons for Login / Register
        tog = ctk.CTkFrame(self, fg_color="transparent")
        tog.pack(fill="x", padx=20, pady=(15, 5))
        self.btn_login = ctk.CTkButton(
            tog, text="🔐 LOGIN", command=self.show_login,
            font=("Arial", 12, "bold"), fg_color="#1565C0", width=150, height=38
        )
        self.btn_login.pack(side="left", padx=5)
        self.btn_reg = ctk.CTkButton(
            tog, text="✍️ REGISTER", command=self.show_register,
            font=("Arial", 12, "bold"), fg_color="#444", width=150, height=38
        )
        self.btn_reg.pack(side="left", padx=5)

        # Content frame for forms
        self.content = ctk.CTkFrame(self)
        self.content.pack(fill="both", expand=True, padx=20, pady=15)
        self.show_login()

    def clear_content(self):
        """Clear all widgets from content frame"""
        for w in self.content.winfo_children():
            w.destroy()

    def show_login(self):
        """Display login form"""
        self.clear_content()
        self.btn_login.configure(fg_color="#1565C0")
        self.btn_reg.configure(fg_color="#444")

        ctk.CTkLabel(
            self.content, text="Login to your account",
            font=("Arial", 18, "bold")
        ).pack(pady=20)

        ctk.CTkLabel(self.content, text="📧 Email", font=("Arial", 12)).pack(anchor="w", pady=(10, 3))
        self.l_email = ctk.CTkEntry(self.content, placeholder_text="Enter email", height=40)
        self.l_email.pack(fill="x", pady=3)

        ctk.CTkLabel(self.content, text="🔐 Password", font=("Arial", 12)).pack(anchor="w", pady=(10, 3))
        self.l_pass = ctk.CTkEntry(self.content, placeholder_text="Enter password", show="*", height=40)
        self.l_pass.pack(fill="x", pady=3)

        ctk.CTkButton(
            self.content, text="LOGIN", command=self.do_login,
            font=("Arial", 14, "bold"), height=45, fg_color="#1565C0"
        ).pack(fill="x", pady=25)

        ctk.CTkLabel(
            self.content, text="Don't have an account? Click REGISTER above!",
            font=("Arial", 10), text_color="gray"
        ).pack()

    def show_register(self):
        """Display registration form"""
        self.clear_content()
        self.btn_login.configure(fg_color="#444")
        self.btn_reg.configure(fg_color="#1565C0")

        sf = ctk.CTkScrollableFrame(self.content)
        sf.pack(fill="both", expand=True)

        ctk.CTkLabel(sf, text="Create new account", font=("Arial", 18, "bold")).pack(pady=15)

        # Name field
        ctk.CTkLabel(sf, text="👤 Full Name", font=("Arial", 12)).pack(anchor="w", pady=(8, 2))
        self.r_name = ctk.CTkEntry(sf, placeholder_text="Enter full name", height=38)
        self.r_name.pack(fill="x", pady=2)

        # Email field
        ctk.CTkLabel(sf, text="📧 Email", font=("Arial", 12)).pack(anchor="w", pady=(8, 2))
        self.r_email = ctk.CTkEntry(sf, placeholder_text="Enter email", height=38)
        self.r_email.pack(fill="x", pady=2)

        # Phone field
        ctk.CTkLabel(sf, text="📱 Phone", font=("Arial", 12)).pack(anchor="w", pady=(8, 2))
        self.r_phone = ctk.CTkEntry(sf, placeholder_text="+91XXXXXXXXXX", height=38)
        self.r_phone.pack(fill="x", pady=2)

        # Password field with requirements info
        ctk.CTkLabel(sf, text="🔐 Password", font=("Arial", 12, "bold")).pack(anchor="w", pady=(8, 2))
        ctk.CTkLabel(
            sf, text="Min 8 chars: 1 upper, 1 lower, 1 digit, 1 special",
            font=("Arial", 9), text_color="orange"
        ).pack(anchor="w")
        self.r_pass = ctk.CTkEntry(sf, placeholder_text="Enter strong password", show="*", height=38)
        self.r_pass.pack(fill="x", pady=2)

        # Role selection
        ctk.CTkLabel(sf, text="👥 Role", font=("Arial", 12, "bold")).pack(anchor="w", pady=(8, 2))
        self.r_role = ctk.CTkComboBox(sf, values=["user", "admin"], state="readonly", height=38)
        self.r_role.set("user")
        self.r_role.pack(fill="x", pady=2)

        # Admin password field (shown only when admin role selected)
        self.admin_lbl = ctk.CTkLabel(sf, text="🔑 Admin Password", font=("Arial", 12))
        self.r_admin = ctk.CTkEntry(sf, placeholder_text="Enter admin password", show="*", height=38)

        def on_role(*args):
            if self.r_role.get() == "admin":
                self.admin_lbl.pack(anchor="w", pady=(8, 2))
                self.r_admin.pack(fill="x", pady=2)
            else:
                self.admin_lbl.pack_forget()
                self.r_admin.pack_forget()
        self.r_role.configure(command=on_role)

        # Register button
        ctk.CTkButton(
            sf, text="REGISTER", command=self.do_register,
            font=("Arial", 14, "bold"), height=45, fg_color="#2E7D32"
        ).pack(fill="x", pady=20)

    def do_login(self):
        """Handle login button click"""
        email = self.l_email.get().strip()
        pwd = self.l_pass.get()
        if not email or not pwd:
            messagebox.showerror("Error", "Please fill all fields")
            return
        ok, role, msg = self.auth.login(email, pwd)
        if ok:
            messagebox.showinfo("Success", msg)
            if role == "admin":
                AdminDashboard(self, self.auth, self.complaints, self.analytics)
            else:
                UserDashboard(self, self.auth, self.complaints)
        else:
            messagebox.showerror("Error", msg)

    def do_register(self):
        """Handle register button click"""
        name = self.r_name.get().strip()
        email = self.r_email.get().strip()
        phone = self.r_phone.get().strip()
        pwd = self.r_pass.get()
        role = self.r_role.get()
        admin_p = self.r_admin.get() if role == "admin" else None
        if not all([name, email, phone, pwd]):
            messagebox.showerror("Error", "Please fill all fields")
            return
        ok, msg = self.auth.register(name, email, pwd, phone, role, admin_p)
        if ok:
            messagebox.showinfo("Success", msg)
            self.show_login()
        else:
            messagebox.showerror("Error", msg)

# ============================================
# USER DASHBOARD
# ============================================
class UserDashboard(ctk.CTkToplevel):
    """
    User dashboard window for submitting and tracking complaints.
    Features: complaint submission with image upload, complaint list
    with filtering by status and category.
    """

    def __init__(self, parent, auth, complaints):
        super().__init__(parent)  # type: ignore
        self.auth = auth
        self.cs = complaints
        self.user = auth.current_user
        self.selected_image: Optional[str] = None
        self.title(f"CivicVoice - {self.user['name']}")
        self.geometry("1100x700")
        self.build_ui()

    def build_ui(self):
        """Build user dashboard UI"""
        # Header
        header = ctk.CTkFrame(self, fg_color="#1565C0", height=55)
        header.pack(fill="x")
        header.pack_propagate(False)
        ctk.CTkLabel(
            header, text=f"👋 Welcome, {self.user['name']}",
            font=("Arial", 16, "bold"), text_color="white"
        ).pack(side="left", padx=15)
        ctk.CTkButton(
            header, text="🔓 Logout", command=self.logout,
            fg_color="#C62828", width=80, height=30
        ).pack(side="right", padx=15, pady=12)

        # Tabview with Submit and View tabs
        self.tabs = ctk.CTkTabview(self)
        self.tabs.pack(fill="both", expand=True, padx=15, pady=10)
        self.build_submit_tab(self.tabs.add("📝 Submit Complaint"))
        self.build_view_tab(self.tabs.add("📋 My Complaints"))

    def build_submit_tab(self, tab):
        """Build the complaint submission form"""
        main = ctk.CTkFrame(tab)
        main.pack(fill="both", expand=True, padx=10, pady=10)

        # Left side - form fields
        left = ctk.CTkFrame(main)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))

        # Title field
        ctk.CTkLabel(left, text="📌 Title", font=("Arial", 12, "bold")).pack(anchor="w", pady=(8, 2))
        self.c_title = ctk.CTkEntry(left, placeholder_text="Complaint title", height=38)
        self.c_title.pack(fill="x", pady=2)

        # Location field
        ctk.CTkLabel(left, text="📍 Location", font=("Arial", 12, "bold")).pack(anchor="w", pady=(8, 2))
        self.c_loc = ctk.CTkEntry(left, placeholder_text="Location/Address", height=38)
        self.c_loc.pack(fill="x", pady=2)

        # Description field
        ctk.CTkLabel(left, text="📝 Description", font=("Arial", 12, "bold")).pack(anchor="w", pady=(8, 2))
        self.c_desc = ctk.CTkTextbox(left, height=100)
        self.c_desc.pack(fill="both", expand=True, pady=2)

        # Category dropdown
        ctk.CTkLabel(left, text="📂 Category", font=("Arial", 12, "bold")).pack(anchor="w", pady=(8, 2))
        self.c_cat = ctk.CTkComboBox(left, values=Config.CATEGORIES, state="readonly", height=38)
        self.c_cat.set(Config.CATEGORIES[0])
        self.c_cat.pack(fill="x", pady=2)

        # Priority dropdown
        ctk.CTkLabel(left, text="⚡ Priority", font=("Arial", 12, "bold")).pack(anchor="w", pady=(8, 2))
        self.c_pri = ctk.CTkComboBox(left, values=Config.PRIORITIES, state="readonly", height=38)
        self.c_pri.set("Normal")
        self.c_pri.pack(fill="x", pady=2)

        # Right side - image upload
        right = ctk.CTkFrame(main, width=280)
        right.pack(side="right", fill="both", padx=(8, 0))
        ctk.CTkLabel(right, text="📸 Upload Image", font=("Arial", 14, "bold")).pack(pady=8)

        self.img_lbl = ctk.CTkLabel(
            right, text="No image selected",
            width=240, height=220, fg_color="#2c2c2c", corner_radius=10
        )
        self.img_lbl.pack(pady=8, fill="both", expand=True)

        ctk.CTkButton(
            right, text="📁 Choose Image",
            command=self.pick_image, fg_color="#E65100", height=38
        ).pack(fill="x", pady=4)

        self.img_info = ctk.CTkLabel(
            right, text="Max 5MB | JPG, PNG, GIF, BMP",
            font=("Arial", 9), text_color="gray"
        )
        self.img_info.pack(pady=2)

        # Submit button
        ctk.CTkButton(
            tab, text="✅ SUBMIT COMPLAINT", command=self.submit,
            font=("Arial", 14, "bold"), height=48, fg_color="#2E7D32"
        ).pack(fill="x", padx=10, pady=8)

    def pick_image(self):
        """Open file dialog to select an image"""
        path = filedialog.askopenfilename(
            title="Select image",
            filetypes=[("Images", "*.jpg *.jpeg *.png *.gif *.bmp")]
        )
        if path:
            ok, msg = FileManager.validate_image(path)
            if not ok:
                messagebox.showerror("Error", msg)
                return
            self.selected_image = path
            try:
                img = Image.open(path)
                img.thumbnail((240, 220), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                self.img_lbl.configure(image=photo, text="")
                self.img_lbl.image = photo
                sz = os.path.getsize(path) / 1024
                self.img_info.configure(text=f"✅ {os.path.basename(path)} ({sz:.1f} KB)")
            except Exception as e:
                messagebox.showerror("Error", str(e))

    def submit(self):
        """Submit a new complaint"""
        title = self.c_title.get().strip()
        desc = self.c_desc.get("1.0", ctk.END).strip()
        cat = self.c_cat.get()
        loc = self.c_loc.get().strip()
        pri = self.c_pri.get()

        ok, msg = self.cs.create(
            self.user['email'], title, desc, cat, loc,
            self.user['phone'], self.selected_image, pri
        )
        if ok:
            messagebox.showinfo("Success", msg)
            # Clear form
            self.c_title.delete(0, ctk.END)
            self.c_desc.delete("1.0", ctk.END)
            self.c_loc.delete(0, ctk.END)
            self.selected_image = None
            self.img_lbl.configure(image="", text="No image selected")
            self.img_lbl.image = None
            self.img_info.configure(text="Max 5MB | JPG, PNG, GIF, BMP")
            self.refresh()
        else:
            messagebox.showerror("Error", msg)

    def build_view_tab(self, tab):
        """Build the complaints list view with filters"""
        # Toolbar with refresh, view image, and filters
        top = ctk.CTkFrame(tab)
        top.pack(fill="x", padx=10, pady=5)
        ctk.CTkButton(top, text="🔄 Refresh", command=self.refresh, width=90).pack(side="left", padx=3)
        ctk.CTkButton(top, text="👁 View Image", command=self.view_img, width=100).pack(side="left", padx=3)

        ctk.CTkLabel(top, text="Status:").pack(side="left", padx=(15, 3))
        self.f_status = ctk.CTkComboBox(
            top, values=["All"] + Config.STATUSES,
            state="readonly", width=120, command=lambda e: self.refresh()
        )
        self.f_status.set("All")
        self.f_status.pack(side="left", padx=3)

        ctk.CTkLabel(top, text="Category:").pack(side="left", padx=(10, 3))
        self.f_cat = ctk.CTkComboBox(
            top, values=["All"] + Config.CATEGORIES,
            state="readonly", width=140, command=lambda e: self.refresh()
        )
        self.f_cat.set("All")
        self.f_cat.pack(side="left", padx=3)

        # Treeview table
        tf = ctk.CTkFrame(tab)
        tf.pack(fill="both", expand=True, padx=10, pady=5)
        cols = ("ID", "Title", "Category", "Location", "Status", "Priority", "Image", "Date")
        self.tree = ttk.Treeview(tf, columns=cols, show="headings", height=18)
        widths = [40, 200, 100, 120, 90, 70, 50, 100]
        for c, w in zip(cols, widths):
            self.tree.heading(c, text=c)
            self.tree.column(c, width=w, anchor="center" if w < 120 else "w")
        sb = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.refresh()

    def refresh(self):
        """Refresh complaints list with current filters"""
        for i in self.tree.get_children():
            self.tree.delete(i)
        sf = self.f_status.get() if hasattr(self, 'f_status') else None
        cf = self.f_cat.get() if hasattr(self, 'f_cat') else None
        for r in self.cs.get_user_complaints(self.user['email'], sf, cf):
            img = "✅" if r['image_path'] else "❌"
            dt = str(r['created_at'])[0:10] if r['created_at'] else ""  # type: ignore
            self.tree.insert("", "end", values=(
                r['id'], r['title'][:35], r['category'],
                r['location'] or "", r['status'], r['priority'], img, dt
            ))

    def view_img(self):
        """View the image attached to selected complaint"""
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Warning", "Select a complaint first")
            return
        cid = self.tree.item(sel[0])['values'][0]
        c = self.cs.get_details(cid)
        if not c or not c['image_path'] or not os.path.exists(c['image_path']):
            messagebox.showinfo("Info", "No image available")
            return
        win = ctk.CTkToplevel(self)
        win.title(f"Complaint #{cid} Image")
        win.geometry("600x600")
        img = Image.open(c['image_path'])
        img.thumbnail((550, 550), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        lbl = ctk.CTkLabel(win, image=photo, text="")
        lbl.pack(fill="both", expand=True, padx=10, pady=10)
        lbl.image = photo

    def logout(self):
        """Logout and close dashboard"""
        self.auth.logout()
        messagebox.showinfo("Logged Out", "You have been logged out.")
        self.destroy()

# ============================================
# ADMIN DASHBOARD
# ============================================
class AdminDashboard(ctk.CTkToplevel):
    """
    Admin dashboard with full management capabilities.
    Features: view/manage all complaints, update statuses,
    view statistics charts (Matplotlib), and manage users.
    """

    def __init__(self, parent, auth, complaints, analytics):
        super().__init__(parent)  # type: ignore
        self.auth = auth
        self.cs = complaints
        self.analytics = analytics
        self.db = complaints.db
        self.admin = auth.current_user
        self.title(f"CivicVoice Admin - {self.admin['name']}")
        self.geometry("1200x750")
        self.build_ui()

    def build_ui(self):
        """Build admin dashboard UI"""
        # Header
        header = ctk.CTkFrame(self, fg_color="#0D47A1", height=55)
        header.pack(fill="x")
        header.pack_propagate(False)
        ctk.CTkLabel(
            header, text=f"⚙️ Admin Panel — {self.admin['name']}",
            font=("Arial", 16, "bold"), text_color="white"
        ).pack(side="left", padx=15)
        ctk.CTkButton(
            header, text="🔓 Logout", command=self.logout,
            fg_color="#C62828", width=80, height=30
        ).pack(side="right", padx=15, pady=12)

        # Admin tabs
        self.tabs = ctk.CTkTabview(self)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=8)
        self.build_complaints_tab(self.tabs.add("📋 All Complaints"))
        self.build_stats_tab(self.tabs.add("📊 Statistics"))
        self.build_users_tab(self.tabs.add("👥 Manage Users"))

    # --- ALL COMPLAINTS TAB ---
    def build_complaints_tab(self, tab):
        """Build the admin complaints management tab"""
        # Toolbar with filters and search
        top = ctk.CTkFrame(tab)
        top.pack(fill="x", padx=8, pady=5)
        ctk.CTkButton(top, text="🔄 Refresh", command=self.refresh_complaints, width=90).pack(side="left", padx=3)
        ctk.CTkButton(top, text="👁 Image", command=self.admin_view_img, width=80).pack(side="left", padx=3)

        ctk.CTkLabel(top, text="Status:").pack(side="left", padx=(12, 3))
        self.a_status = ctk.CTkComboBox(
            top, values=["All"] + Config.STATUSES,
            state="readonly", width=110, command=lambda e: self.refresh_complaints()
        )
        self.a_status.set("All")
        self.a_status.pack(side="left", padx=3)

        ctk.CTkLabel(top, text="Category:").pack(side="left", padx=(8, 3))
        self.a_cat = ctk.CTkComboBox(
            top, values=["All"] + Config.CATEGORIES,
            state="readonly", width=130, command=lambda e: self.refresh_complaints()
        )
        self.a_cat.set("All")
        self.a_cat.pack(side="left", padx=3)

        ctk.CTkLabel(top, text="Search:").pack(side="left", padx=(8, 3))
        self.a_search = ctk.CTkEntry(top, placeholder_text="Search...", width=150, height=30)
        self.a_search.pack(side="left", padx=3)
        ctk.CTkButton(top, text="🔍", command=self.refresh_complaints, width=35, height=30).pack(side="left", padx=2)

        # Status update bar
        upd = ctk.CTkFrame(tab)
        upd.pack(fill="x", padx=8, pady=3)
        ctk.CTkLabel(upd, text="Update Status:").pack(side="left", padx=3)
        self.new_status = ctk.CTkComboBox(upd, values=Config.STATUSES, state="readonly", width=120)
        self.new_status.set("Pending")
        self.new_status.pack(side="left", padx=3)
        ctk.CTkButton(
            upd, text="✅ Update", command=self.update_status,
            width=90, fg_color="#2E7D32"
        ).pack(side="left", padx=3)

        # Complaints treeview
        tf = ctk.CTkFrame(tab)
        tf.pack(fill="both", expand=True, padx=8, pady=5)
        cols = ("ID", "User", "Title", "Category", "Location", "Status", "Priority", "Image", "Date")
        self.a_tree = ttk.Treeview(tf, columns=cols, show="headings", height=20)
        widths = [35, 150, 180, 100, 110, 85, 65, 45, 90]
        for c, w in zip(cols, widths):
            self.a_tree.heading(c, text=c)
            self.a_tree.column(c, width=w)
        sb = ttk.Scrollbar(tf, orient="vertical", command=self.a_tree.yview)
        self.a_tree.configure(yscroll=sb.set)
        self.a_tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.refresh_complaints()

    def refresh_complaints(self):
        """Refresh admin complaints list with current filters"""
        for i in self.a_tree.get_children():
            self.a_tree.delete(i)
        sf = self.a_status.get()
        cf = self.a_cat.get()
        search = self.a_search.get().strip() if hasattr(self, 'a_search') else None
        for r in self.cs.get_all_complaints(sf, cf, search):
            img = "✅" if r['image_path'] else "❌"
            dt = str(r['created_at'])[0:10] if r['created_at'] else ""  # type: ignore
            self.a_tree.insert("", "end", values=(
                r['id'], r['user_email'], r['title'][:30],
                r['category'], r['location'] or "",
                r['status'], r['priority'], img, dt
            ))

    def update_status(self):
        """Update selected complaint's status"""
        sel = self.a_tree.selection()
        if not sel:
            messagebox.showwarning("Warning", "Select a complaint first")
            return
        cid = self.a_tree.item(sel[0])['values'][0]
        status = self.new_status.get()
        ok, msg = self.cs.update_status(cid, status)
        if ok:
            messagebox.showinfo("Success", msg)
            self.refresh_complaints()
        else:
            messagebox.showerror("Error", msg)

    def admin_view_img(self):
        """View image for selected complaint"""
        sel = self.a_tree.selection()
        if not sel:
            messagebox.showwarning("Warning", "Select a complaint first")
            return
        cid = self.a_tree.item(sel[0])['values'][0]
        c = self.cs.get_details(cid)
        if not c or not c['image_path'] or not os.path.exists(c['image_path']):
            messagebox.showinfo("Info", "No image available")
            return
        win = ctk.CTkToplevel(self)
        win.title(f"Complaint #{cid} Image")
        win.geometry("600x600")
        img = Image.open(c['image_path'])
        img.thumbnail((550, 550), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        lbl = ctk.CTkLabel(win, image=photo, text="")
        lbl.pack(fill="both", expand=True, padx=10, pady=10)
        lbl.image = photo

    # --- STATISTICS TAB ---
    def build_stats_tab(self, tab):
        """Build the statistics tab with Matplotlib charts"""
        ctk.CTkButton(
            tab, text="🔄 Refresh Charts",
            command=self.draw_charts, width=140
        ).pack(pady=8)
        self.chart_frame = ctk.CTkFrame(tab)
        self.chart_frame.pack(fill="both", expand=True, padx=8, pady=5)
        self.draw_charts()

    def draw_charts(self):
        """Draw Matplotlib charts showing complaint statistics"""
        for w in self.chart_frame.winfo_children():
            w.destroy()

        stats = self.analytics.get_stats()
        if not stats or stats.get('total', 0) == 0:
            ctk.CTkLabel(
                self.chart_frame, text="No complaints yet to display.",
                font=("Arial", 14)
            ).pack(pady=50)
            return

        # Create figure with 3 subplots
        fig, axes = plt.subplots(1, 3, figsize=(14, 4.5))
        fig.patch.set_facecolor('#1a1a2e')
        colors_status = ['#FF6B6B', '#4ECDC4', '#45B7D1']
        colors_cat = ['#E91E63', '#9C27B0', '#3F51B5', '#00BCD4', '#4CAF50']
        colors_pri = ['#FF9800', '#2196F3', '#F44336', '#4CAF50']

        # Chart 1: Complaints by Status (bar chart)
        s = stats.get('status', {})
        if s:
            axes[0].bar(s.keys(), s.values(), color=list(colors_status)[0:len(s)])  # type: ignore
            axes[0].set_title('By Status', color='white', fontsize=12, fontweight='bold')
        axes[0].set_facecolor('#16213e')
        axes[0].tick_params(colors='white')
        for spine in axes[0].spines.values():
            spine.set_color('#333')

        # Chart 2: Complaints by Category (pie chart)
        cat = stats.get('category', {})
        if cat:
            axes[1].pie(
                cat.values(), labels=cat.keys(), autopct='%1.1f%%',
                colors=list(colors_cat)[0:len(cat)],  # type: ignore
                textprops={'color': 'white', 'fontsize': 8}
            )
            axes[1].set_title('By Category', color='white', fontsize=12, fontweight='bold')
        axes[1].set_facecolor('#16213e')

        # Chart 3: Complaints by Priority (horizontal bar)
        p = stats.get('priority', {})
        if p:
            axes[2].barh(list(p.keys()), list(p.values()), color=list(colors_pri)[0:len(p)])  # type: ignore
            axes[2].set_title('By Priority', color='white', fontsize=12, fontweight='bold')
        axes[2].set_facecolor('#16213e')
        axes[2].tick_params(colors='white')
        for spine in axes[2].spines.values():
            spine.set_color('#333')

        fig.suptitle(
            f"Total Complaints: {stats['total']}",
            color='#4ECDC4', fontsize=14, fontweight='bold'
        )
        fig.tight_layout()

        # Embed Matplotlib chart into CTkinter window
        canvas = FigureCanvasTkAgg(fig, self.chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)

    # --- MANAGE USERS TAB ---
    def build_users_tab(self, tab):
        """Build the user management tab"""
        top = ctk.CTkFrame(tab)
        top.pack(fill="x", padx=8, pady=5)
        ctk.CTkButton(top, text="🔄 Refresh", command=self.refresh_users, width=90).pack(side="left", padx=3)
        ctk.CTkButton(
            top, text="🗑 Delete User", command=self.delete_user,
            width=110, fg_color="#C62828"
        ).pack(side="left", padx=3)

        tf = ctk.CTkFrame(tab)
        tf.pack(fill="both", expand=True, padx=8, pady=5)
        cols = ("ID", "Name", "Email", "Phone", "Role", "Joined")
        self.u_tree = ttk.Treeview(tf, columns=cols, show="headings", height=18)
        for c, w in zip(cols, [40, 150, 200, 120, 60, 100]):
            self.u_tree.heading(c, text=c)
            self.u_tree.column(c, width=w)
        sb = ttk.Scrollbar(tf, orient="vertical", command=self.u_tree.yview)
        self.u_tree.configure(yscroll=sb.set)
        self.u_tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.refresh_users()

    def refresh_users(self):
        """Refresh the users list"""
        for i in self.u_tree.get_children():
            self.u_tree.delete(i)
        conn = self.db.get_connection()
        for r in conn.execute(
            "SELECT id,name,email,phone,role,created_at FROM users ORDER BY id"
        ).fetchall():
            self.u_tree.insert("", "end", values=(
                r['id'], r['name'], r['email'],
                r['phone'] or "", r['role'],
                str(r['created_at'])[0:10]  # type: ignore
            ))
        conn.close()

    def delete_user(self):
        """Delete selected user (admin cannot delete self)"""
        sel = self.u_tree.selection()
        if not sel:
            messagebox.showwarning("Warning", "Select a user first")
            return
        vals = self.u_tree.item(sel[0])['values']
        email = vals[2]
        if email == self.admin['email']:
            messagebox.showerror("Error", "Cannot delete yourself!")
            return
        if not messagebox.askyesno("Confirm", f"Delete user {email}?"):
            return
        conn = self.db.get_connection()
        conn.execute("DELETE FROM users WHERE email=?", (email,))
        conn.commit()
        conn.close()
        messagebox.showinfo("Success", "User deleted!")
        self.refresh_users()

    def logout(self):
        """Logout admin and close dashboard"""
        self.auth.logout()
        messagebox.showinfo("Logged Out", "Admin logged out.")
        self.destroy()

# ============================================
# MAIN ENTRY POINT
# ============================================
if __name__ == "__main__":
    app = LoginWindow()
    app.mainloop()
