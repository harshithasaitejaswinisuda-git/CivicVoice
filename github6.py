import customtkinter as ctk
import sqlite3
from tkinter import messagebox, ttk, filedialog
import matplotlib.pyplot as plt
from datetime import datetime
import hashlib
import re
import os
from PIL import Image, ImageTk
import shutil

# ============================================
# ADMIN PASSWORD - CHANGE THIS TO YOUR PASSWORD
# ============================================
ADMIN_PASSWORD = "admin@2026"  # Change this to your desired admin password

# ============================================
# DELETE OLD DATABASE (FRESH START)
# ============================================
DB_NAME = "civicvoice.db"

# Remove old database file
if os.path.exists(DB_NAME):
    os.remove(DB_NAME)
    print(f"✅ Deleted old {DB_NAME}")

# Create uploads directory
UPLOAD_DIR = "uploads"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)
    print(f"✅ Created {UPLOAD_DIR} directory")

# ============================================
# DATABASE SETUP
# ============================================
class DatabaseManager:
    """Manages all database operations"""
    
    def __init__(self, db_name=DB_NAME):
        self.db_name = db_name
        self.create_tables()
    
    def get_connection(self):
        """Get database connection"""
        conn = sqlite3.connect(self.db_name, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn
    
    def create_tables(self):
        """Create all required tables from scratch"""
        try:
            conn = self.get_connection()
            cur = conn.cursor()
            
            # Drop tables if they exist (FRESH START)
            cur.execute("DROP TABLE IF EXISTS complaint_notes")
            cur.execute("DROP TABLE IF EXISTS complaints")
            cur.execute("DROP TABLE IF EXISTS users")
            
            print("✅ Dropped old tables")
            
            # Create users table
            cur.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                phone_number TEXT,
                role TEXT NOT NULL CHECK(role IN ('user', 'admin')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            print("✅ Created users table")
            
            # Create complaints table
            cur.execute("""
            CREATE TABLE complaints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_email TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                category TEXT NOT NULL,
                phone_number TEXT,
                image_path TEXT,
                image_filename TEXT,
                status TEXT NOT NULL DEFAULT 'Pending' CHECK(status IN ('Pending', 'In Progress', 'Resolved', 'Rejected')),
                priority TEXT DEFAULT 'Normal' CHECK(priority IN ('Low', 'Normal', 'High', 'Critical')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_email) REFERENCES users(email)
            )
            """)
            print("✅ Created complaints table")
            
            # Create complaint_notes table
            cur.execute("""
            CREATE TABLE complaint_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                complaint_id INTEGER NOT NULL,
                admin_email TEXT,
                note TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(complaint_id) REFERENCES complaints(id)
            )
            """)
            print("✅ Created complaint_notes table")
            
            conn.commit()
            conn.close()
            print("✅ Database initialized successfully!\n")
            
        except Exception as e:
            print(f"❌ Database error: {e}")
            raise

# ============================================
# SECURITY MANAGER
# ============================================
class SecurityManager:
    """Handles password hashing and validation"""
    
    @staticmethod
    def hash_password(password):
        return hashlib.sha256(password.encode()).hexdigest()
    
    @staticmethod
    def verify_password(password, hashed):
        return SecurityManager.hash_password(password) == hashed
    
    @staticmethod
    def validate_email(email):
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
    
    @staticmethod
    def validate_password(password):
        if len(password) < 6:
            return False, "Password must be at least 6 characters"
        return True, "Valid password"
    
    @staticmethod
    def validate_phone(phone_number):
        """Validate phone number format"""
        cleaned = re.sub(r'[^\d+]', '', phone_number)
        if re.match(r'^\+?[1-9]\d{9,14}$', cleaned):
            return True, cleaned
        return False, "Invalid phone number format (use +1-234-567-8900 or similar)"

# ============================================
# FILE MANAGER
# ============================================
class FileManager:
    """Manages file uploads"""
    
    ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'bmp'}
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
    
    @staticmethod
    def validate_image(file_path):
        """Validate image file"""
        if not os.path.exists(file_path):
            return False, "File not found"
        
        if os.path.getsize(file_path) > FileManager.MAX_FILE_SIZE:
            return False, f"File size exceeds {FileManager.MAX_FILE_SIZE / 1024 / 1024}MB"
        
        ext = file_path.split('.')[-1].lower()
        if ext not in FileManager.ALLOWED_EXTENSIONS:
            return False, f"Only {', '.join(FileManager.ALLOWED_EXTENSIONS)} files allowed"
        
        return True, "Valid"
    
    @staticmethod
    def save_image(file_path, complaint_id):
        """Save image with timestamp"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"complaint_{complaint_id}_{timestamp}_{os.path.basename(file_path)}"
            destination = os.path.join(UPLOAD_DIR, filename)
            
            shutil.copy2(file_path, destination)
            print(f"✅ Image saved: {destination}")
            return filename, destination
            
        except Exception as e:
            print(f"❌ Error saving image: {e}")
            return None, None
    
    @staticmethod
    def delete_image(image_path):
        """Delete image file"""
        try:
            if image_path and os.path.exists(image_path):
                os.remove(image_path)
                print(f"✅ Deleted image: {image_path}")
                return True
        except Exception as e:
            print(f"❌ Error deleting image: {e}")
        return False

# ============================================
# AUTHENTICATION SERVICE
# ============================================
class AuthenticationService:
    """Handles user authentication"""
    
    def __init__(self, db_manager):
        self.db = db_manager
        self.current_user = None
    
    def check_admin_exists(self):
        """Check if any admin account exists"""
        try:
            conn = self.db.get_connection()
            cur = conn.cursor()
            
            cur.execute("SELECT COUNT(*) FROM users WHERE role='admin'")
            count = cur.fetchone()[0]
            conn.close()
            
            return count > 0
        except Exception as e:
            print(f"❌ Error checking admin: {e}")
            return False
    
    def register(self, name, email, password, phone_number, role, admin_password=None):
        """Register new user with admin password verification"""
        try:
            if not name or len(name) < 2:
                return False, "Name must be at least 2 characters"
            
            if not SecurityManager.validate_email(email):
                return False, "Invalid email format"
            
            is_valid_phone, cleaned_phone = SecurityManager.validate_phone(phone_number)
            if not is_valid_phone:
                return False, "Invalid phone number format"
            
            is_valid, msg = SecurityManager.validate_password(password)
            if not is_valid:
                return False, msg
            
            # ============ ADMIN VALIDATION ============
            if role == "admin":
                # If admin exists, require admin password
                if self.check_admin_exists():
                    if not admin_password:
                        return False, "Admin password required to create admin account"
                    
                    if admin_password != ADMIN_PASSWORD:
                        return False, "❌ Incorrect admin password! Access denied."
                    
                    print(f"✅ Admin password verified")
                else:
                    # First admin account creation
                    print(f"✅ Creating first admin account")
            # ==========================================
            
            conn = self.db.get_connection()
            cur = conn.cursor()
            
            hashed_password = SecurityManager.hash_password(password)
            
            cur.execute(
                "INSERT INTO users (name, email, password, phone_number, role) VALUES (?, ?, ?, ?, ?)",
                (name, email, hashed_password, cleaned_phone, role)
            )
            
            conn.commit()
            conn.close()
            print(f"✅ User registered: {email} ({role}) | Phone: {cleaned_phone}")
            return True, f"✅ {role.upper()} account created successfully!"
            
        except sqlite3.IntegrityError:
            return False, "❌ Email already exists"
        except Exception as e:
            print(f"❌ Registration error: {e}")
            return False, f"Error: {str(e)}"
    
    def login(self, email, password):
        """Authenticate user"""
        try:
            if not SecurityManager.validate_email(email):
                return False, None, None, "Invalid email format"
            
            conn = self.db.get_connection()
            cur = conn.cursor()
            
            cur.execute(
                "SELECT name, password, role, phone_number FROM users WHERE email=?",
                (email,)
            )
            user = cur.fetchone()
            conn.close()
            
            if user and SecurityManager.verify_password(password, user['password']):
                self.current_user = {
                    'email': email,
                    'name': user['name'],
                    'role': user['role'],
                    'phone_number': user['phone_number']
                }
                print(f"✅ User logged in: {email} ({user['role']})")
                return True, user['role'], user['phone_number'], "Login successful!"
            else:
                return False, None, None, "Invalid email or password"
                
        except Exception as e:
            print(f"❌ Login error: {e}")
            return False, None, None, f"Error: {str(e)}"

# ============================================
# COMPLAINT SERVICE
# ============================================
class ComplaintService:
    """Handles complaint operations"""
    
    def __init__(self, db_manager):
        self.db = db_manager
    
    def create_complaint(self, user_email, title, description, category, phone_number, 
                        image_path=None, priority="Normal"):
        """Create new complaint"""
        try:
            if not title or len(title) < 5:
                return False, "Title must be at least 5 characters"
            
            if not description or len(description) < 10:
                return False, "Description must be at least 10 characters"
            
            is_valid_phone, cleaned_phone = SecurityManager.validate_phone(phone_number)
            if not is_valid_phone:
                return False, "Invalid phone number"
            
            conn = self.db.get_connection()
            cur = conn.cursor()
            
            cur.execute(
                """INSERT INTO complaints (user_email, title, description, category, phone_number, status, priority)
                   VALUES (?, ?, ?, ?, ?, 'Pending', ?)""",
                (user_email, title, description, category, cleaned_phone, priority)
            )
            
            conn.commit()
            complaint_id = cur.lastrowid
            
            image_filename = None
            image_path_saved = None
            
            if image_path:
                is_valid, msg = FileManager.validate_image(image_path)
                if not is_valid:
                    return False, f"Image validation failed: {msg}"
                
                image_filename, image_path_saved = FileManager.save_image(image_path, complaint_id)
                
                if image_filename:
                    cur.execute(
                        "UPDATE complaints SET image_filename=?, image_path=? WHERE id=?",
                        (image_filename, image_path_saved, complaint_id)
                    )
                    conn.commit()
            
            conn.close()
            print(f"✅ Complaint created: #{complaint_id} | Phone: {cleaned_phone}")
            return True, "Complaint submitted successfully!"
            
        except Exception as e:
            print(f"❌ Error creating complaint: {e}")
            return False, f"Error: {str(e)}"
    
    def get_user_complaints(self, user_email):
        """Get user's complaints"""
        try:
            conn = self.db.get_connection()
            cur = conn.cursor()
            
            cur.execute(
                """SELECT id, title, status, priority, category, phone_number, image_filename, created_at 
                   FROM complaints WHERE user_email=? ORDER BY created_at DESC""",
                (user_email,)
            )
            
            complaints = cur.fetchall()
            conn.close()
            return complaints
            
        except Exception as e:
            print(f"❌ Error fetching complaints: {e}")
            return []
    
    def get_all_complaints(self):
        """Get all complaints (admin)"""
        try:
            conn = self.db.get_connection()
            cur = conn.cursor()
            
            cur.execute(
                """SELECT id, user_email, title, status, priority, category, phone_number, image_filename, created_at 
                   FROM complaints ORDER BY created_at DESC"""
            )
            
            complaints = cur.fetchall()
            conn.close()
            return complaints
            
        except Exception as e:
            print(f"❌ Error fetching complaints: {e}")
            return []
    
    def update_status(self, complaint_id, status):
        """Update complaint status"""
        try:
            conn = self.db.get_connection()
            cur = conn.cursor()
            
            cur.execute(
                "UPDATE complaints SET status=? WHERE id=?",
                (status, complaint_id)
            )
            
            conn.commit()
            conn.close()
            print(f"✅ Complaint #{complaint_id} updated to {status}")
            return True, "Status updated successfully!"
            
        except Exception as e:
            print(f"❌ Error updating status: {e}")
            return False, f"Error: {str(e)}"
    
    def get_complaint_details(self, complaint_id):
        """Get complaint details"""
        try:
            conn = self.db.get_connection()
            cur = conn.cursor()
            
            cur.execute("SELECT * FROM complaints WHERE id=?", (complaint_id,))
            complaint = cur.fetchone()
            
            conn.close()
            return complaint
            
        except Exception as e:
            print(f"❌ Error fetching complaint details: {e}")
            return None

# ============================================
# ANALYTICS SERVICE
# ============================================
class AnalyticsService:
    """Provides analytics"""
    
    def __init__(self, db_manager):
        self.db = db_manager
    
    def get_stats(self):
        """Get complaint statistics"""
        try:
            conn = self.db.get_connection()
            cur = conn.cursor()
            
            cur.execute("SELECT status, COUNT(*) FROM complaints GROUP BY status")
            status_stats = dict(cur.fetchall())
            
            cur.execute("SELECT priority, COUNT(*) FROM complaints GROUP BY priority")
            priority_stats = dict(cur.fetchall())
            
            cur.execute("SELECT category, COUNT(*) FROM complaints GROUP BY category")
            category_stats = dict(cur.fetchall())
            
            cur.execute("SELECT COUNT(*) FROM complaints")
            total = cur.fetchone()[0]
            
            conn.close()
            
            return {
                'status': status_stats,
                'priority': priority_stats,
                'category': category_stats,
                'total': total
            }
            
        except Exception as e:
            print(f"❌ Error getting stats: {e}")
            return {}

# ============================================
# LOGIN WINDOW - IMPROVED UI
# ============================================
class LoginWindow(ctk.CTk):
    """Main login/registration window"""
    
    def __init__(self):
        super().__init__()
        
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        self.title("🔔 CivicVoice - Community Complaint System")
        self.geometry("650x850")
        self.resizable(False, False)
        
        # Initialize services
        self.db_manager = DatabaseManager()
        self.auth_service = AuthenticationService(self.db_manager)
        self.complaint_service = ComplaintService(self.db_manager)
        self.analytics_service = AnalyticsService(self.db_manager)
        
        # Track current view
        self.current_view = "login"
        
        self.create_ui()
        print("✅ Login window initialized\n")
    
    def create_ui(self):
        """Create UI"""
        
        # Main container
        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.pack(fill="both", expand=True, padx=0, pady=0)
        
        # Header
        self.header = ctk.CTkFrame(self.main_frame, fg_color="#1E90FF", height=80)
        self.header.pack(fill="x", padx=0, pady=0)
        self.header.pack_propagate(False)
        
        title = ctk.CTkLabel(
            self.header,
            text="🔔 CIVICVOICE",
            font=("Arial", 28, "bold"),
            text_color="white"
        )
        title.pack(pady=10)
        
        subtitle = ctk.CTkLabel(
            self.header,
            text="Community Complaint Management System",
            font=("Arial", 12),
            text_color="lightgray"
        )
        subtitle.pack(pady=(0, 10))
        
        # Toggle button frame
        toggle_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        toggle_frame.pack(fill="x", padx=20, pady=(15, 10))
        
        self.login_btn = ctk.CTkButton(
            toggle_frame,
            text="🔐 LOGIN",
            command=self.show_login,
            font=("Arial", 12, "bold"),
            fg_color="#1E90FF",
            width=150,
            height=40
        )
        self.login_btn.pack(side="left", padx=5)
        
        self.register_btn = ctk.CTkButton(
            toggle_frame,
            text="✍️ REGISTER",
            command=self.show_register,
            font=("Arial", 12, "bold"),
            fg_color="#444444",
            width=150,
            height=40
        )
        self.register_btn.pack(side="left", padx=5)
        
        # Content frame
        self.content_frame = ctk.CTkFrame(self.main_frame)
        self.content_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Show login by default
        self.show_login()
    
    def show_login(self):
        """Show login view"""
        # Clear content
        for widget in self.content_frame.winfo_children():
            widget.destroy()
        
        self.current_view = "login"
        self.login_btn.configure(fg_color="#1E90FF")
        self.register_btn.configure(fg_color="#444444")
        
        # Title
        title = ctk.CTkLabel(
            self.content_frame,
            text="Login to your account",
            font=("Arial", 18, "bold")
        )
        title.pack(pady=20)
        
        # Email
        email_label = ctk.CTkLabel(self.content_frame, text="📧 Email", font=("Arial", 12))
        email_label.pack(anchor="w", pady=(10, 5))
        self.login_email = ctk.CTkEntry(
            self.content_frame,
            placeholder_text="Enter your email",
            height=40,
            font=("Arial", 12)
        )
        self.login_email.pack(fill="x", pady=5)
        
        # Password
        pass_label = ctk.CTkLabel(self.content_frame, text="🔐 Password", font=("Arial", 12))
        pass_label.pack(anchor="w", pady=(15, 5))
        self.login_pass = ctk.CTkEntry(
            self.content_frame,
            placeholder_text="Enter your password",
            show="*",
            height=40,
            font=("Arial", 12)
        )
        self.login_pass.pack(fill="x", pady=5)
        
        # Login Button
        login_btn = ctk.CTkButton(
            self.content_frame,
            text="LOGIN",
            command=self.handle_login,
            font=("Arial", 14, "bold"),
            height=45,
            fg_color="#1E90FF"
        )
        login_btn.pack(fill="x", pady=30)
        
        # Demo info
        demo_label = ctk.CTkLabel(
            self.content_frame,
            text="Don't have an account? Click REGISTER tab above!",
            font=("Arial", 10),
            text_color="gray"
        )
        demo_label.pack(pady=10)
    
    def show_register(self):
        """Show register view"""
        # Clear content
        for widget in self.content_frame.winfo_children():
            widget.destroy()
        
        self.current_view = "register"
        self.login_btn.configure(fg_color="#444444")
        self.register_btn.configure(fg_color="#1E90FF")
        
        # Create scrollable frame for register form
        scroll_frame = ctk.CTkScrollableFrame(self.content_frame)
        scroll_frame.pack(fill="both", expand=True, padx=0, pady=0)
        
        # Title
        title = ctk.CTkLabel(
            scroll_frame,
            text="Create new account",
            font=("Arial", 18, "bold")
        )
        title.pack(pady=20)
        
        # Name
        name_label = ctk.CTkLabel(scroll_frame, text="👤 Full Name", font=("Arial", 12))
        name_label.pack(anchor="w", pady=(10, 5))
        self.reg_name = ctk.CTkEntry(
            scroll_frame,
            placeholder_text="Enter your full name",
            height=40,
            font=("Arial", 12)
        )
        self.reg_name.pack(fill="x", pady=5)
        
        # Email
        email_label = ctk.CTkLabel(scroll_frame, text="📧 Email", font=("Arial", 12))
        email_label.pack(anchor="w", pady=(10, 5))
        self.reg_email = ctk.CTkEntry(
            scroll_frame,
            placeholder_text="Enter your email",
            height=40,
            font=("Arial", 12)
        )
        self.reg_email.pack(fill="x", pady=5)
        
        # Phone Number
        phone_label = ctk.CTkLabel(scroll_frame, text="📱 Phone Number", font=("Arial", 12))
        phone_label.pack(anchor="w", pady=(10, 5))
        self.reg_phone = ctk.CTkEntry(
            scroll_frame,
            placeholder_text="+1-234-567-8900",
            height=40,
            font=("Arial", 12)
        )
        self.reg_phone.pack(fill="x", pady=5)
        
        # Password
        pass_label = ctk.CTkLabel(scroll_frame, text="🔐 Password", font=("Arial", 12))
        pass_label.pack(anchor="w", pady=(10, 5))
        self.reg_pass = ctk.CTkEntry(
            scroll_frame,
            placeholder_text="Min 6 characters",
            show="*",
            height=40,
            font=("Arial", 12)
        )
        self.reg_pass.pack(fill="x", pady=5)
        
        # Role
        role_label = ctk.CTkLabel(scroll_frame, text="👥 Role", font=("Arial", 12, "bold"))
        role_label.pack(anchor="w", pady=(15, 5))
        
        self.reg_role = ctk.CTkComboBox(
            scroll_frame,
            values=["user", "admin"],
            state="readonly",
            height=40,
            font=("Arial", 12)
        )
        self.reg_role.set("user")
        self.reg_role.pack(fill="x", pady=5)
        
        role_info = ctk.CTkLabel(
            scroll_frame,
            text="⚠️ Select 'admin' only if you have the admin password",
            font=("Arial", 10),
            text_color="orange"
        )
        role_info.pack(anchor="w", pady=(0, 10))
        
        # Admin Password (hidden by default, shown only if admin role selected)
        self.admin_pass_label = ctk.CTkLabel(scroll_frame, text="🔑 Admin Password (if Admin role)", font=("Arial", 12))
        self.admin_pass_label.pack(anchor="w", pady=(10, 5))
        self.admin_pass_label.pack_forget()
        
        self.reg_admin_pass = ctk.CTkEntry(
            scroll_frame,
            placeholder_text="Enter admin password",
            show="*",
            height=40,
            font=("Arial", 12)
        )
        self.reg_admin_pass.pack(fill="x", pady=5)
        self.reg_admin_pass.pack_forget()
        
        # Show/hide admin password field based on role selection
        def update_admin_field(*args):
            if self.reg_role.get() == "admin":
                self.admin_pass_label.pack(anchor="w", pady=(10, 5))
                self.reg_admin_pass.pack(fill="x", pady=5)
            else:
                self.admin_pass_label.pack_forget()
                self.reg_admin_pass.pack_forget()
        
        self.reg_role.configure(command=update_admin_field)
        
        # Register Button
        reg_btn = ctk.CTkButton(
            scroll_frame,
            text="REGISTER",
            command=self.handle_register,
            font=("Arial", 14, "bold"),
            height=45,
            fg_color="#32CD32"
        )
        reg_btn.pack(fill="x", pady=30)
    
    def handle_login(self):
        """Handle login"""
        email = self.login_email.get().strip()
        password = self.login_pass.get()
        
        if not email or not password:
            messagebox.showerror("❌ Error", "Please fill all fields")
            return
        
        success, role, phone, message = self.auth_service.login(email, password)
        
        if success:
            messagebox.showinfo("✅ Success", message)
            if role == "admin":
                AdminDashboard(self, self.auth_service, self.complaint_service, self.analytics_service)
            else:
                UserDashboard(self, self.auth_service, self.complaint_service)
        else:
            messagebox.showerror("❌ Error", message)
    
    def handle_register(self):
        """Handle registration"""
        name = self.reg_name.get().strip()
        email = self.reg_email.get().strip()
        phone = self.reg_phone.get().strip()
        password = self.reg_pass.get()
        role = self.reg_role.get()
        admin_password = self.reg_admin_pass.get() if role == "admin" else None
        
        if not all([name, email, phone, password]):
            messagebox.showerror("❌ Error", "Please fill all fields")
            return
        
        success, message = self.auth_service.register(name, email, password, phone, role, admin_password)
        
        if success:
            messagebox.showinfo("✅ Success", message)
            self.show_login()
        else:
            messagebox.showerror("❌ Error", message)

# ============================================
# USER DASHBOARD
# ============================================
class UserDashboard(ctk.CTkToplevel):
    """User dashboard"""
    
    def __init__(self, parent, auth_service, complaint_service):
        super().__init__(parent)
        
        self.auth_service = auth_service
        self.complaint_service = complaint_service
        self.user_email = auth_service.current_user['email']
        self.user_name = auth_service.current_user['name']
        self.user_phone = auth_service.current_user['phone_number']
        self.selected_image = None
        
        self.title(f"User Dashboard - {self.user_name}")
        self.geometry("1100x750")
        self.resizable(True, True)
        
        self.create_ui()
        print("✅ User dashboard opened\n")
    
    def create_ui(self):
        """Create UI"""
        
        # Header
        header = ctk.CTkFrame(self, fg_color="#1E90FF")
        header.pack(fill="x", padx=0, pady=0)
        
        title = ctk.CTkLabel(
            header,
            text=f"👋 Welcome, {self.user_name}! | 📱 {self.user_phone}",
            font=("Arial", 18, "bold"),
            text_color="white"
        )
        title.pack(pady=15)
        
        # Notebook
        self.notebook = ctk.CTkTabview(self)
        self.notebook.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Submit tab
        submit_tab = self.notebook.add("📝 Submit Complaint")
        self.create_submit_tab(submit_tab)
        
        # View tab
        view_tab = self.notebook.add("📋 My Complaints")
        self.create_view_tab(view_tab)
    
    def create_submit_tab(self, tab):
        """Create submit complaint tab"""
        
        # Main container with two columns
        main_container = ctk.CTkFrame(tab)
        main_container.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Left column - Form
        left_frame = ctk.CTkFrame(main_container)
        left_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))
        
        # Title
        title_label = ctk.CTkLabel(left_frame, text="Title", font=("Arial", 12, "bold"))
        title_label.pack(anchor="w", pady=(10, 5))
        self.complaint_title = ctk.CTkEntry(
            left_frame,
            placeholder_text="Enter complaint title",
            height=40,
            font=("Arial", 12)
        )
        self.complaint_title.pack(fill="x", pady=5)
        
        # Description
        desc_label = ctk.CTkLabel(left_frame, text="Description", font=("Arial", 12, "bold"))
        desc_label.pack(anchor="w", pady=(10, 5))
        self.complaint_desc = ctk.CTkTextbox(left_frame, height=120, font=("Arial", 12))
        self.complaint_desc.pack(fill="both", expand=True, pady=5)
        
        # Category
        cat_label = ctk.CTkLabel(left_frame, text="Category", font=("Arial", 12, "bold"))
        cat_label.pack(anchor="w", pady=(10, 5))
        self.complaint_category = ctk.CTkComboBox(
            left_frame,
            values=["Infrastructure", "Water", "Electricity", "Roads", "Sanitation", "Public Safety", "Other"],
            state="readonly",
            height=40,
            font=("Arial", 12)
        )
        self.complaint_category.set("Infrastructure")
        self.complaint_category.pack(fill="x", pady=5)
        
        # Priority
        pri_label = ctk.CTkLabel(left_frame, text="Priority", font=("Arial", 12, "bold"))
        pri_label.pack(anchor="w", pady=(10, 5))
        self.complaint_priority = ctk.CTkComboBox(
            left_frame,
            values=["Low", "Normal", "High", "Critical"],
            state="readonly",
            height=40,
            font=("Arial", 12)
        )
        self.complaint_priority.set("Normal")
        self.complaint_priority.pack(fill="x", pady=5)
        
        # Right column - Image upload
        right_frame = ctk.CTkFrame(main_container)
        right_frame.pack(side="right", fill="both", expand=True, padx=(10, 0))
        
        image_title = ctk.CTkLabel(
            right_frame,
            text="📸 Upload Image",
            font=("Arial", 14, "bold")
        )
        image_title.pack(pady=10)
        
        # Image preview area
        self.image_preview_label = ctk.CTkLabel(
            right_frame,
            text="No image selected",
            font=("Arial", 11),
            text_color="gray",
            width=250,
            height=250,
            fg_color="#2c2c2c",
            corner_radius=10
        )
        self.image_preview_label.pack(pady=10, fill="both", expand=True)
        
        # Upload button
        upload_btn = ctk.CTkButton(
            right_frame,
            text="📁 Choose Image",
            command=self.select_image,
            height=40,
            font=("Arial", 12, "bold"),
            fg_color="#FF6347"
        )
        upload_btn.pack(fill="x", pady=5)
        
        # Image info label
        self.image_info_label = ctk.CTkLabel(
            right_frame,
            text="Max 5MB | JPG, PNG, GIF, BMP",
            font=("Arial", 10),
            text_color="gray"
        )
        self.image_info_label.pack(pady=5)
        
        # Bottom: Submit button
        bottom_frame = ctk.CTkFrame(tab)
        bottom_frame.pack(fill="x", padx=20, pady=10)
        
        submit_btn = ctk.CTkButton(
            bottom_frame,
            text="✅ SUBMIT COMPLAINT",
            command=self.submit_complaint,
            font=("Arial", 14, "bold"),
            height=50,
            fg_color="#32CD32"
        )
        submit_btn.pack(fill="x")
    
    def select_image(self):
        """Select image file"""
        file_path = filedialog.askopenfilename(
            title="Select complaint image",
            filetypes=[
                ("Images", "*.jpg *.jpeg *.png *.gif *.bmp"),
                ("All files", "*.*")
            ]
        )
        
        if file_path:
            # Validate
            is_valid, msg = FileManager.validate_image(file_path)
            if not is_valid:
                messagebox.showerror("❌ Invalid Image", msg)
                return
            
            self.selected_image = file_path
            
            # Show preview
            try:
                img = Image.open(file_path)
                img.thumbnail((250, 250), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                
                self.image_preview_label.configure(image=photo, text="")
                self.image_preview_label.image = photo
                
                # Show file info
                file_size = os.path.getsize(file_path) / 1024
                filename = os.path.basename(file_path)
                self.image_info_label.configure(
                    text=f"✅ {filename} ({file_size:.1f} KB)"
                )
                print(f"✅ Image selected: {file_path}")
                
            except Exception as e:
                messagebox.showerror("❌ Error", f"Could not load image: {e}")
                self.selected_image = None
    
    def submit_complaint(self):
        """Submit complaint"""
        title = self.complaint_title.get().strip()
        description = self.complaint_desc.get("1.0", ctk.END).strip()
        category = self.complaint_category.get()
        priority = self.complaint_priority.get()
        
        success, message = self.complaint_service.create_complaint(
            self.user_email, title, description, category, self.user_phone,
            image_path=self.selected_image,
            priority=priority
        )
        
        if success:
            messagebox.showinfo("✅ Success", message)
            self.complaint_title.delete(0, ctk.END)
            self.complaint_desc.delete("1.0", ctk.END)
            self.selected_image = None
            self.image_preview_label.configure(image="", text="No image selected")
            self.image_preview_label.image = None
            self.image_info_label.configure(text="Max 5MB | JPG, PNG, GIF, BMP")
            self.refresh_complaints()
        else:
            messagebox.showerror("❌ Error", message)
    
    def create_view_tab(self, tab):
        """Create view complaints tab"""
        
        # Button frame
        btn_frame = ctk.CTkFrame(tab)
        btn_frame.pack(fill="x", padx=20, pady=10)
        
        refresh_btn = ctk.CTkButton(
            btn_frame,
            text="🔄 Refresh",
            command=self.refresh_complaints,
            width=100
        )
        refresh_btn.pack(side="left", padx=5)
        
        view_btn = ctk.CTkButton(
            btn_frame,
            text="👁️ View Image",
            command=self.view_image,
            width=100
        )
        view_btn.pack(side="left", padx=5)
        
        # Treeview frame
        tree_frame = ctk.CTkFrame(tab)
        tree_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        # Treeview
        self.complaints_tree = ttk.Treeview(
            tree_frame,
            columns=("ID", "Title", "Status", "Priority", "Category", "Phone", "Image", "Created"),
            height=20
        )
        
        self.complaints_tree.column("#0", width=0, stretch=False)
        self.complaints_tree.column("ID", width=40, anchor="center")
        self.complaints_tree.column("Title", width=200, anchor="w")
        self.complaints_tree.column("Status", width=100, anchor="center")
        self.complaints_tree.column("Priority", width=80, anchor="center")
        self.complaints_tree.column("Category", width=100, anchor="w")
        self.complaints_tree.column("Phone", width=120, anchor="center")
        self.complaints_tree.column("Image", width=60, anchor="center")
        self.complaints_tree.column("Created", width=120, anchor="center")
        
        self.complaints_tree.heading("#0", text="")
        self.complaints_tree.heading("ID", text="ID")
        self.complaints_tree.heading("Title", text="Title")
        self.complaints_tree.heading("Status", text="Status")
        self.complaints_tree.heading("Priority", text="Priority")
        self.complaints_tree.heading("Category", text="Category")
        self.complaints_tree.heading("Phone", text="Phone")
        self.complaints_tree.heading("Image", text="📷")
        self.complaints_tree.heading("Created", text="Created")
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.complaints_tree.yview)
        self.complaints_tree.configure(yscroll=scrollbar.set)
        
        self.complaints_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        self.refresh_complaints()
    
    def refresh_complaints(self):
        """Refresh complaints list"""
        for item in self.complaints_tree.get_children():
            self.complaints_tree.delete(item)
        
        complaints = self.complaint_service.get_user_complaints(self.user_email)
        print(f"📋 Found {len(complaints)} complaints")
        
        for complaint in complaints:
            image_indicator = "✅" if complaint[6] else "❌"
            self.complaints_tree.insert(
                "",
                "end",
                values=(
                    complaint[0],
                    complaint[1][:40],
                    complaint[2],
                    complaint[3],
                    complaint[4],
                    complaint[5],
                    image_indicator,
                    complaint[7][:10]
                )
            )
    
    def view_image(self):
        """View selected complaint image"""
        selection = self.complaints_tree.selection()
        if not selection:
            messagebox.showwarning("⚠️ Warning", "Please select a complaint")
            return
        
        item = self.complaints_tree.item(selection[0])
        complaint_id = item['values'][0]
        
        complaint = self.complaint_service.get_complaint_details(complaint_id)
        
        if not complaint or not complaint[7]:
            messagebox.showinfo("ℹ️ Info", "No image attached to this complaint")
            return
        
        image_path = complaint[7]
        if not os.path.exists(image_path):
            messagebox.showerror("❌ Error", "Image file not found")
            return
        
        # Create image viewer window
        viewer = ctk.CTkToplevel(self)
        viewer.title(f"Complaint #{complaint_id} - Image")
        viewer.geometry("600x600")
        
        try:
            img = Image.open(image_path)
            img.thumbnail((550, 550), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            
            label = ctk.CTkLabel(viewer, image=photo, text="")
            label.pack(padx=20, pady=20, fill="both", expand=True)
            label.image = photo
            
            info_label = ctk.CTkLabel(
                viewer,
                text=f"File: {os.path.basename(image_path)}",
                font=("Arial", 10),
                text_color="gray"
            )
            info_label.pack(pady=10)
            
        except Exception as e:
            messagebox.showerror("❌ Error", f"Could not display image: {e}")

# ============================================
# ADMIN DASHBOARD
# ============================================
class AdminDashboard(ctk.CTkToplevel):
    """Admin dashboard"""
    
    def __init__(self, parent, auth_service, complaint_service, analytics_service):
        super().__init__(parent)
        
        self.auth_service = auth_service
        self.complaint_service = complaint_service
        self.analytics_service = analytics_service
        self.admin_email = auth_service.current_user['email']
        self.admin_name = auth_service.current_user['name']
        
        self.title(f"Admin Dashboard - {self.admin_name}")
        self.geometry("1400x900")
        self.resizable(True, True)
        
        self.create_ui()
        print("✅ Admin dashboard opened\n")
    
    def create_ui(self):
        """Create UI"""
        
        # Header
        header = ctk.CTkFrame(self, fg_color="#FF6347")
        header.pack(fill="x", padx=0, pady=0)
        
        title = ctk.CTkLabel(
            header,
            text=f"🛡️ Admin Dashboard - {self.admin_name}",
            font=("Arial", 20, "bold"),
            text_color="white"
        )
        title.pack(pady=15)
        
        # Notebook
        self.notebook = ctk.CTkTabview(self)
        self.notebook.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Manage tab
        manage_tab = self.notebook.add("📊 Manage Complaints")
        self.create_manage_tab(manage_tab)
        
        # Analytics tab
        analytics_tab = self.notebook.add("📈 Analytics")
        self.create_analytics_tab(analytics_tab)
    
    def create_manage_tab(self, tab):
        """Create manage complaints tab"""
        
        # Button frame
        btn_frame = ctk.CTkFrame(tab)
        btn_frame.pack(fill="x", padx=20, pady=10)
        
        refresh_btn = ctk.CTkButton(
            btn_frame,
            text="🔄 Refresh",
            command=self.refresh_all_complaints,
            width=100
        )
        refresh_btn.pack(side="left", padx=5)
        
        view_btn = ctk.CTkButton(
            btn_frame,
            text="👁️ View Details",
            command=self.view_details,
            width=100
        )
        view_btn.pack(side="left", padx=5)
        
        image_btn = ctk.CTkButton(
            btn_frame,
            text="📷 View Image",
            command=self.view_image,
            width=100
        )
        image_btn.pack(side="left", padx=5)
        
        update_btn = ctk.CTkButton(
            btn_frame,
            text="✏️ Change Status",
            command=self.change_status,
            width=100
        )
        update_btn.pack(side="left", padx=5)
        
        # Treeview frame
        tree_frame = ctk.CTkFrame(tab)
        tree_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        # Treeview
        self.all_complaints_tree = ttk.Treeview(
            tree_frame,
            columns=("ID", "User", "Phone", "Title", "Status", "Priority", "Category", "Image", "Created"),
            height=20
        )
        
        self.all_complaints_tree.column("#0", width=0, stretch=False)
        self.all_complaints_tree.column("ID", width=40, anchor="center")
        self.all_complaints_tree.column("User", width=130, anchor="w")
        self.all_complaints_tree.column("Phone", width=120, anchor="center")
        self.all_complaints_tree.column("Title", width=200, anchor="w")
        self.all_complaints_tree.column("Status", width=100, anchor="center")
        self.all_complaints_tree.column("Priority", width=80, anchor="center")
        self.all_complaints_tree.column("Category", width=100, anchor="w")
        self.all_complaints_tree.column("Image", width=60, anchor="center")
        self.all_complaints_tree.column("Created", width=120, anchor="center")
        
        self.all_complaints_tree.heading("#0", text="")
        self.all_complaints_tree.heading("ID", text="ID")
        self.all_complaints_tree.heading("User", text="User Email")
        self.all_complaints_tree.heading("Phone", text="Phone Number")
        self.all_complaints_tree.heading("Title", text="Title")
        self.all_complaints_tree.heading("Status", text="Status")
        self.all_complaints_tree.heading("Priority", text="Priority")
        self.all_complaints_tree.heading("Category", text="Category")
        self.all_complaints_tree.heading("Image", text="📷")
        self.all_complaints_tree.heading("Created", text="Created")
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.all_complaints_tree.yview)
        self.all_complaints_tree.configure(yscroll=scrollbar.set)
        
        self.all_complaints_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        self.refresh_all_complaints()
    
    def refresh_all_complaints(self):
        """Refresh all complaints"""
        for item in self.all_complaints_tree.get_children():
            self.all_complaints_tree.delete(item)
        
        complaints = self.complaint_service.get_all_complaints()
        print(f"📊 Found {len(complaints)} total complaints")
        
        for complaint in complaints:
            image_indicator = "✅" if complaint[7] else "❌"
            self.all_complaints_tree.insert(
                "",
                "end",
                values=(
                    complaint[0],
                    complaint[1],
                    complaint[6],
                    complaint[2][:40],
                    complaint[3],
                    complaint[4],
                    complaint[5],
                    image_indicator,
                    complaint[8][:10]
                )
            )
    
    def view_details(self):
        """View complaint details"""
        selection = self.all_complaints_tree.selection()
        if not selection:
            messagebox.showwarning("⚠️ Warning", "Please select a complaint")
            return
        
        item = self.all_complaints_tree.item(selection[0])
        complaint_id = item['values'][0]
        
        complaint = self.complaint_service.get_complaint_details(complaint_id)
        
        if complaint:
            details_window = ctk.CTkToplevel(self)
            details_window.title(f"Complaint #{complaint_id}")
            details_window.geometry("700x700")
            
            # Create scrollable frame
            scrollable_frame = ctk.CTkScrollableFrame(details_window)
            scrollable_frame.pack(fill="both", expand=True, padx=20, pady=20)
            
            details_text = f"""
ID: {complaint[0]}
User Email: {complaint[1]}
Phone Number: {complaint[5]}
Title: {complaint[2]}
Category: {complaint[4]}
Priority: {complaint[7]}
Status: {complaint[6]}
Created: {complaint[9]}
Image Attached: {'Yes' if complaint[8] else 'No'}

DESCRIPTION:
{complaint[3]}
"""
            
            label = ctk.CTkLabel(
                scrollable_frame,
                text=details_text,
                justify="left",
                font=("Arial", 11)
            )
            label.pack(fill="both", expand=True)
    
    def view_image(self):
        """View complaint image"""
        selection = self.all_complaints_tree.selection()
        if not selection:
            messagebox.showwarning("⚠️ Warning", "Please select a complaint")
            return
        
        item = self.all_complaints_tree.item(selection[0])
        complaint_id = item['values'][0]
        
        complaint = self.complaint_service.get_complaint_details(complaint_id)
        
        if not complaint or not complaint[8]:
            messagebox.showinfo("ℹ️ Info", "No image attached to this complaint")
            return
        
        image_path = complaint[8]
        if not os.path.exists(image_path):
            messagebox.showerror("❌ Error", "Image file not found")
            return
        
        # Create image viewer window
        viewer = ctk.CTkToplevel(self)
        viewer.title(f"Complaint #{complaint_id} - Image")
        viewer.geometry("700x700")
        
        try:
            img = Image.open(image_path)
            img.thumbnail((650, 650), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            
            label = ctk.CTkLabel(viewer, image=photo, text="")
            label.pack(padx=20, pady=20, fill="both", expand=True)
            label.image = photo
            
            info_label = ctk.CTkLabel(
                viewer,
                text=f"File: {os.path.basename(image_path)}",
                font=("Arial", 10),
                text_color="gray"
            )
            info_label.pack(pady=10)
            
        except Exception as e:
            messagebox.showerror("❌ Error", f"Could not display image: {e}")
    
    def change_status(self):
        """Change complaint status"""
        selection = self.all_complaints_tree.selection()
        if not selection:
            messagebox.showwarning("⚠️ Warning", "Please select a complaint")
            return
        
        item = self.all_complaints_tree.item(selection[0])
        complaint_id = item['values'][0]
        
        # Create dialog
        dialog = ctk.CTkToplevel(self)
        dialog.title("Change Status")
        dialog.geometry("400x250")
        
        frame = ctk.CTkFrame(dialog)
        frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        label = ctk.CTkLabel(frame, text="Select new status:", font=("Arial", 12))
        label.pack(pady=10)
        
        status_var = ctk.StringVar(value="Pending")
        status_combo = ctk.CTkComboBox(
            frame,
            values=["Pending", "In Progress", "Resolved", "Rejected"],
            variable=status_var,
            state="readonly",
            height=40,
            font=("Arial", 12)
        )
        status_combo.pack(fill="x", pady=10)
        
        def apply():
            new_status = status_var.get()
            success, msg = self.complaint_service.update_status(complaint_id, new_status)
            if success:
                messagebox.showinfo("✅ Success", msg)
                dialog.destroy()
                self.refresh_all_complaints()
            else:
                messagebox.showerror("❌ Error", msg)
        
        apply_btn = ctk.CTkButton(
            frame,
            text="APPLY CHANGES",
            command=apply,
            height=45,
            font=("Arial", 12)
        )
        apply_btn.pack(fill="x", pady=20)
    
    def create_analytics_tab(self, tab):
        """Create analytics tab"""
        
        frame = ctk.CTkFrame(tab)
        frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Title
        title = ctk.CTkLabel(
            frame,
            text="📊 Complaint Statistics",
            font=("Arial", 16, "bold")
        )
        title.pack(pady=20)
        
        # Stats label
        self.stats_label = ctk.CTkLabel(
            frame,
            text="Loading statistics...",
            justify="left",
            font=("Arial", 12)
        )
        self.stats_label.pack(anchor="nw", fill="both", expand=True, padx=20, pady=20)
        
        # Button
        chart_btn = ctk.CTkButton(
            frame,
            text="📈 Generate Charts",
            command=self.generate_charts,
            height=45,
            font=("Arial", 12)
        )
        chart_btn.pack(fill="x", pady=20)
        
        self.update_stats()
    
    def update_stats(self):
        """Update statistics"""
        stats = self.analytics_service.get_stats()
        
        status_text = "\n".join([f"  • {k}: {v}" for k, v in stats.get('status', {}).items()])
        priority_text = "\n".join([f"  • {k}: {v}" for k, v in stats.get('priority', {}).items()])
        category_text = "\n".join([f"  • {k}: {v}" for k, v in stats.get('category', {}).items()])
        
        text = f"""Total Complaints: {stats.get('total', 0)}

Status Distribution:
{status_text if status_text else "  No data"}

Priority Distribution:
{priority_text if priority_text else "  No data"}

Category Distribution:
{category_text if category_text else "  No data"}
"""
        
        self.stats_label.configure(text=text)
    
    def generate_charts(self):
        """Generate charts"""
        stats = self.analytics_service.get_stats()
        
        if not stats or stats.get('total', 0) == 0:
            messagebox.showinfo("ℹ️ Info", "No data available for charts")
            return
        
        fig, axes = plt.subplots(1, 3, figsize=(15, 5))
        fig.suptitle("CivicVoice Analytics", fontsize=14, fontweight='bold')
        
        # Status chart
        status = stats.get('status', {})
        if status:
            axes[0].bar(status.keys(), status.values(), color='steelblue')
            axes[0].set_title("By Status")
            axes[0].set_xlabel("Status")
            axes[0].set_ylabel("Count")
            axes[0].tick_params(axis='x', rotation=45)
        
        # Priority chart
        priority = stats.get('priority', {})
        if priority:
            axes[1].pie(priority.values(), labels=priority.keys(), autopct='%1.1f%%')
            axes[1].set_title("By Priority")
        
        # Category chart
        category = stats.get('category', {})
        if category:
            axes[2].barh(category.keys(), category.values(), color='coral')
            axes[2].set_title("By Category")
            axes[2].set_xlabel("Count")
        
        plt.tight_layout()
        plt.show()

# ============================================
# MAIN EXECUTION
# ============================================
if __name__ == "__main__":
    print("\n" + "="*70)
    print("🚀 Starting CivicVoice Application (Secure v3 - Admin Protected)")
    print("="*70)
    print("\n📌 ADMIN PASSWORD: admin@2026")
    print("   ⚠️  Change ADMIN_PASSWORD in the code to secure your system!")
    print("="*70 + "\n")
    
    app = LoginWindow()
    app.mainloop()