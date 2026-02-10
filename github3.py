import customtkinter as ctk
import sqlite3
from tkinter import messagebox, ttk
import matplotlib.pyplot as plt
from datetime import datetime
import hashlib
import re
import os

# ============================================
# DELETE OLD DATABASE (FRESH START)
# ============================================
DB_NAME = "civicvoice.db"

# Remove old database file
if os.path.exists(DB_NAME):
    os.remove(DB_NAME)
    print(f"✅ Deleted old {DB_NAME}")

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

# ============================================
# AUTHENTICATION SERVICE
# ============================================
class AuthenticationService:
    """Handles user authentication"""
    
    def __init__(self, db_manager):
        self.db = db_manager
        self.current_user = None
    
    def register(self, name, email, password, role):
        """Register new user"""
        try:
            if not name or len(name) < 2:
                return False, "Name must be at least 2 characters"
            
            if not SecurityManager.validate_email(email):
                return False, "Invalid email format"
            
            is_valid, msg = SecurityManager.validate_password(password)
            if not is_valid:
                return False, msg
            
            conn = self.db.get_connection()
            cur = conn.cursor()
            
            hashed_password = SecurityManager.hash_password(password)
            
            # Verify table structure
            cur.execute("PRAGMA table_info(users)")
            columns = [col[1] for col in cur.fetchall()]
            print(f"✅ Users table columns: {columns}")
            
            cur.execute(
                "INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, ?)",
                (name, email, hashed_password, role)
            )
            
            conn.commit()
            conn.close()
            print(f"✅ User registered: {email} ({role})")
            return True, "Registration successful!"
            
        except sqlite3.IntegrityError as e:
            print(f"❌ Integrity error: {e}")
            return False, "Email already exists"
        except Exception as e:
            print(f"❌ Registration error: {e}")
            return False, f"Error: {str(e)}"
    
    def login(self, email, password):
        """Authenticate user"""
        try:
            if not SecurityManager.validate_email(email):
                return False, None, "Invalid email format"
            
            conn = self.db.get_connection()
            cur = conn.cursor()
            
            cur.execute(
                "SELECT name, password, role FROM users WHERE email=?",
                (email,)
            )
            user = cur.fetchone()
            conn.close()
            
            if user and SecurityManager.verify_password(password, user['password']):
                self.current_user = {
                    'email': email,
                    'name': user['name'],
                    'role': user['role']
                }
                print(f"✅ User logged in: {email} ({user['role']})")
                return True, user['role'], "Login successful!"
            else:
                return False, None, "Invalid email or password"
                
        except Exception as e:
            print(f"❌ Login error: {e}")
            return False, None, f"Error: {str(e)}"

# ============================================
# COMPLAINT SERVICE
# ============================================
class ComplaintService:
    """Handles complaint operations"""
    
    def __init__(self, db_manager):
        self.db = db_manager
    
    def create_complaint(self, user_email, title, description, category, priority="Normal"):
        """Create new complaint"""
        try:
            if not title or len(title) < 5:
                return False, "Title must be at least 5 characters"
            
            if not description or len(description) < 10:
                return False, "Description must be at least 10 characters"
            
            conn = self.db.get_connection()
            cur = conn.cursor()
            
            cur.execute(
                """INSERT INTO complaints (user_email, title, description, category, status, priority)
                   VALUES (?, ?, ?, ?, 'Pending', ?)""",
                (user_email, title, description, category, priority)
            )
            
            conn.commit()
            complaint_id = cur.lastrowid
            conn.close()
            print(f"✅ Complaint created: #{complaint_id}")
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
                """SELECT id, title, status, priority, category, created_at 
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
                """SELECT id, user_email, title, status, priority, category, created_at 
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
# LOGIN WINDOW
# ============================================
class LoginWindow(ctk.CTk):
    """Main login/registration window"""
    
    def __init__(self):
        super().__init__()
        
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        self.title("🔔 CivicVoice - Community Complaint System")
        self.geometry("550x750")
        self.resizable(False, False)
        
        # Initialize services
        self.db_manager = DatabaseManager()
        self.auth_service = AuthenticationService(self.db_manager)
        self.complaint_service = ComplaintService(self.db_manager)
        self.analytics_service = AnalyticsService(self.db_manager)
        
        self.create_ui()
        print("✅ Login window initialized\n")
    
    def create_ui(self):
        """Create UI"""
        
        # Main container
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(fill="both", expand=True, padx=0, pady=0)
        
        # Header
        header = ctk.CTkFrame(main_frame, fg_color="#1E90FF")
        header.pack(fill="x", padx=0, pady=0)
        
        title = ctk.CTkLabel(
            header,
            text="🔔 CIVICVOICE",
            font=("Arial", 28, "bold"),
            text_color="white"
        )
        title.pack(pady=15)
        
        subtitle = ctk.CTkLabel(
            header,
            text="Community Complaint Management System",
            font=("Arial", 12),
            text_color="lightgray"
        )
        subtitle.pack(pady=(0, 15))
        
        # Notebook/Tabs
        self.notebook = ctk.CTkTabview(main_frame)
        self.notebook.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Login Tab
        login_tab = self.notebook.add("Login")
        self.create_login_tab(login_tab)
        
        # Register Tab
        register_tab = self.notebook.add("Register")
        self.create_register_tab(register_tab)
    
    def create_login_tab(self, tab):
        """Create login tab"""
        
        frame = ctk.CTkFrame(tab)
        frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Title
        title = ctk.CTkLabel(
            frame,
            text="Login to your account",
            font=("Arial", 18, "bold")
        )
        title.pack(pady=20)
        
        # Email
        email_label = ctk.CTkLabel(frame, text="📧 Email", font=("Arial", 12))
        email_label.pack(anchor="w", pady=(10, 5))
        self.login_email = ctk.CTkEntry(
            frame,
            placeholder_text="Enter your email",
            height=40,
            font=("Arial", 12)
        )
        self.login_email.pack(fill="x", pady=5)
        
        # Password
        pass_label = ctk.CTkLabel(frame, text="🔐 Password", font=("Arial", 12))
        pass_label.pack(anchor="w", pady=(15, 5))
        self.login_pass = ctk.CTkEntry(
            frame,
            placeholder_text="Enter your password",
            show="*",
            height=40,
            font=("Arial", 12)
        )
        self.login_pass.pack(fill="x", pady=5)
        
        # Login Button
        login_btn = ctk.CTkButton(
            frame,
            text="LOGIN",
            command=self.handle_login,
            font=("Arial", 14, "bold"),
            height=45,
            fg_color="#1E90FF"
        )
        login_btn.pack(fill="x", pady=30)
        
        # Demo info
        demo_label = ctk.CTkLabel(
            frame,
            text="Register first to create an account!",
            font=("Arial", 10),
            text_color="gray"
        )
        demo_label.pack(pady=10)
    
    def create_register_tab(self, tab):
        """Create register tab"""
        
        frame = ctk.CTkFrame(tab)
        frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Title
        title = ctk.CTkLabel(
            frame,
            text="Create new account",
            font=("Arial", 18, "bold")
        )
        title.pack(pady=20)
        
        # Name
        name_label = ctk.CTkLabel(frame, text="👤 Full Name", font=("Arial", 12))
        name_label.pack(anchor="w", pady=(10, 5))
        self.reg_name = ctk.CTkEntry(
            frame,
            placeholder_text="Enter your full name",
            height=40,
            font=("Arial", 12)
        )
        self.reg_name.pack(fill="x", pady=5)
        
        # Email
        email_label = ctk.CTkLabel(frame, text="📧 Email", font=("Arial", 12))
        email_label.pack(anchor="w", pady=(10, 5))
        self.reg_email = ctk.CTkEntry(
            frame,
            placeholder_text="Enter your email",
            height=40,
            font=("Arial", 12)
        )
        self.reg_email.pack(fill="x", pady=5)
        
        # Password
        pass_label = ctk.CTkLabel(frame, text="🔐 Password", font=("Arial", 12))
        pass_label.pack(anchor="w", pady=(10, 5))
        self.reg_pass = ctk.CTkEntry(
            frame,
            placeholder_text="Min 6 characters",
            show="*",
            height=40,
            font=("Arial", 12)
        )
        self.reg_pass.pack(fill="x", pady=5)
        
        # Role
        role_label = ctk.CTkLabel(frame, text="👥 Role", font=("Arial", 12))
        role_label.pack(anchor="w", pady=(10, 5))
        self.reg_role = ctk.CTkComboBox(
            frame,
            values=["user", "admin"],
            state="readonly",
            height=40,
            font=("Arial", 12)
        )
        self.reg_role.set("user")
        self.reg_role.pack(fill="x", pady=5)
        
        # Register Button
        reg_btn = ctk.CTkButton(
            frame,
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
            messagebox.showerror("Error", "Please fill all fields")
            return
        
        success, role, message = self.auth_service.login(email, password)
        
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
        password = self.reg_pass.get()
        role = self.reg_role.get()
        
        if not all([name, email, password]):
            messagebox.showerror("Error", "Please fill all fields")
            return
        
        success, message = self.auth_service.register(name, email, password, role)
        
        if success:
            messagebox.showinfo("✅ Success", message)
            self.reg_name.delete(0, ctk.END)
            self.reg_email.delete(0, ctk.END)
            self.reg_pass.delete(0, ctk.END)
            self.notebook.set("Login")
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
        
        self.title(f"User Dashboard - {self.user_name}")
        self.geometry("900x700")
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
            text=f"👋 Welcome, {self.user_name}!",
            font=("Arial", 20, "bold"),
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
        
        frame = ctk.CTkFrame(tab)
        frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Title
        title_label = ctk.CTkLabel(frame, text="Title", font=("Arial", 12, "bold"))
        title_label.pack(anchor="w", pady=(10, 5))
        self.complaint_title = ctk.CTkEntry(
            frame,
            placeholder_text="Enter complaint title",
            height=40,
            font=("Arial", 12)
        )
        self.complaint_title.pack(fill="x", pady=5)
        
        # Description
        desc_label = ctk.CTkLabel(frame, text="Description", font=("Arial", 12, "bold"))
        desc_label.pack(anchor="w", pady=(10, 5))
        self.complaint_desc = ctk.CTkTextbox(frame, height=150, font=("Arial", 12))
        self.complaint_desc.pack(fill="both", expand=True, pady=5)
        
        # Category
        cat_label = ctk.CTkLabel(frame, text="Category", font=("Arial", 12, "bold"))
        cat_label.pack(anchor="w", pady=(10, 5))
        self.complaint_category = ctk.CTkComboBox(
            frame,
            values=["Infrastructure", "Water", "Electricity", "Roads", "Sanitation", "Public Safety", "Other"],
            state="readonly",
            height=40,
            font=("Arial", 12)
        )
        self.complaint_category.set("Infrastructure")
        self.complaint_category.pack(fill="x", pady=5)
        
        # Priority
        pri_label = ctk.CTkLabel(frame, text="Priority", font=("Arial", 12, "bold"))
        pri_label.pack(anchor="w", pady=(10, 5))
        self.complaint_priority = ctk.CTkComboBox(
            frame,
            values=["Low", "Normal", "High", "Critical"],
            state="readonly",
            height=40,
            font=("Arial", 12)
        )
        self.complaint_priority.set("Normal")
        self.complaint_priority.pack(fill="x", pady=5)
        
        # Submit button
        submit_btn = ctk.CTkButton(
            frame,
            text="SUBMIT COMPLAINT",
            command=self.submit_complaint,
            font=("Arial", 14, "bold"),
            height=45,
            fg_color="#32CD32"
        )
        submit_btn.pack(fill="x", pady=20)
    
    def submit_complaint(self):
        """Submit complaint"""
        title = self.complaint_title.get().strip()
        description = self.complaint_desc.get("1.0", ctk.END).strip()
        category = self.complaint_category.get()
        priority = self.complaint_priority.get()
        
        success, message = self.complaint_service.create_complaint(
            self.user_email, title, description, category, priority
        )
        
        if success:
            messagebox.showinfo("✅ Success", message)
            self.complaint_title.delete(0, ctk.END)
            self.complaint_desc.delete("1.0", ctk.END)
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
        
        # Treeview frame
        tree_frame = ctk.CTkFrame(tab)
        tree_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        # Treeview
        self.complaints_tree = ttk.Treeview(
            tree_frame,
            columns=("ID", "Title", "Status", "Priority", "Category", "Created"),
            height=20
        )
        
        self.complaints_tree.column("#0", width=0, stretch=False)
        self.complaints_tree.column("ID", width=40, anchor="center")
        self.complaints_tree.column("Title", width=250, anchor="w")
        self.complaints_tree.column("Status", width=100, anchor="center")
        self.complaints_tree.column("Priority", width=80, anchor="center")
        self.complaints_tree.column("Category", width=120, anchor="w")
        self.complaints_tree.column("Created", width=120, anchor="center")
        
        self.complaints_tree.heading("#0", text="")
        self.complaints_tree.heading("ID", text="ID")
        self.complaints_tree.heading("Title", text="Title")
        self.complaints_tree.heading("Status", text="Status")
        self.complaints_tree.heading("Priority", text="Priority")
        self.complaints_tree.heading("Category", text="Category")
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
            self.complaints_tree.insert(
                "",
                "end",
                values=(
                    complaint[0],
                    complaint[1][:40],
                    complaint[2],
                    complaint[3],
                    complaint[4],
                    complaint[5][:10]
                )
            )

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
        self.geometry("1200x800")
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
            columns=("ID", "User", "Title", "Status", "Priority", "Category", "Created"),
            height=20
        )
        
        self.all_complaints_tree.column("#0", width=0, stretch=False)
        self.all_complaints_tree.column("ID", width=40, anchor="center")
        self.all_complaints_tree.column("User", width=150, anchor="w")
        self.all_complaints_tree.column("Title", width=250, anchor="w")
        self.all_complaints_tree.column("Status", width=100, anchor="center")
        self.all_complaints_tree.column("Priority", width=80, anchor="center")
        self.all_complaints_tree.column("Category", width=120, anchor="w")
        self.all_complaints_tree.column("Created", width=120, anchor="center")
        
        self.all_complaints_tree.heading("#0", text="")
        self.all_complaints_tree.heading("ID", text="ID")
        self.all_complaints_tree.heading("User", text="User Email")
        self.all_complaints_tree.heading("Title", text="Title")
        self.all_complaints_tree.heading("Status", text="Status")
        self.all_complaints_tree.heading("Priority", text="Priority")
        self.all_complaints_tree.heading("Category", text="Category")
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
            self.all_complaints_tree.insert(
                "",
                "end",
                values=(
                    complaint[0],
                    complaint[1],
                    complaint[2][:40],
                    complaint[3],
                    complaint[4],
                    complaint[5],
                    complaint[6][:10]
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
            details_window.geometry("600x500")
            
            # Create scrollable frame
            scrollable_frame = ctk.CTkScrollableFrame(details_window)
            scrollable_frame.pack(fill="both", expand=True, padx=20, pady=20)
            
            details_text = f"""
ID: {complaint[0]}
User Email: {complaint[1]}
Title: {complaint[2]}
Category: {complaint[4]}
Priority: {complaint[6]}
Status: {complaint[5]}
Created: {complaint[7]}

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
    print("\n" + "="*60)
    print("🚀 Starting CivicVoice Application")
    print("="*60 + "\n")
    
    app = LoginWindow()
    app.mainloop()