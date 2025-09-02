from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QComboBox, QLabel,
    QLineEdit, QPushButton, QTextEdit, QStackedLayout,
    QInputDialog, QApplication
)
from PySide6.QtCore import (
    QEventLoop, QTimer
)
import paramiko
from paramiko.ssh_exception import AuthenticationException, SSHException
import os
import tempfile

from ssh_helpers import get_ssh_params, SSHThread
from remote_browser import RemoteFileBrowser
from remote_dialog import RemoteFileDialog



# ----------------------------- HPC Client -----------------------------
class HPCClient(QWidget):                           # QWidget = Parent Class
    # ============ Initialisation ============
    def __init__(self):
        """INITIALISE CLIENT AND SET UP WINDOW"""
        super().__init__()                          # Initialise as QWidget  
        self.ssh_client = None
        self.sftp = None                      
        self.hpc_host = ""
        self.hpc_user = ""
        self.main_window = None
        
        # Stacked layout
        self.stack = QStackedLayout(self)

        # Connection page
        self.connection_page = QWidget()
        self._make_connection_page()
        self.stack.addWidget(self.connection_page)

        # Browser pafe
        self.browser_page = None


    def _make_connection_page(self):
        layout = QVBoxLayout(self.connection_page)                      # Vertical layout

        # Alias dropdown
        alias_layout = QVBoxLayout()
        alias_layout.setSpacing(2)
        alias_label = QLabel("Select SSH Alias / Host:")
        alias_label.setMaximumHeight(20)
        alias_layout.addWidget(alias_label)

        self.alias_dropdown = QComboBox()
        self.alias_dropdown.setMaximumHeight(25)
        alias_layout.addWidget(self.alias_dropdown)

        layout.addLayout(alias_layout)

        self.alias_dropdown.setToolTip("Select host")           
        self.alias_dropdown.addItem("")                         # Empty by default
        ssh_config_path = os.path.expanduser("~/.ssh/config")   # .ssh config path
        self.aliases = []
        if os.path.exists(ssh_config_path):
            with open(ssh_config_path) as f:
                cfg = paramiko.config.SSHConfig()               
                cfg.parse(f)                                    # Loads aliases from config w/ paramiko
                self.aliases = [h for h in cfg.get_hostnames() if '*' not in h]
            for host in self.aliases:
                self.alias_dropdown.addItem(host)               # Adds aliases to dropdown
        self.alias_dropdown.addItem("Manual Host")              # Manual host option

        # Manual host fields
        self.manual_container = QWidget()                       # Container holds manual host optopms
        manual_layout = QVBoxLayout()
        self.manual_host_input = QLineEdit()
        self.manual_host_input.setPlaceholderText("Hostname (e.g., login.hpc.cam.ac.uk)")
        manual_layout.addWidget(self.manual_host_input)         # HPC hostname
        self.manual_user_input = QLineEdit()
        self.manual_user_input.setPlaceholderText("Username")
        manual_layout.addWidget(self.manual_user_input)         # HPC Username
        self.manual_container.setLayout(manual_layout)
        self.manual_container.setVisible(False)                 # Manual container starts invisible
        layout.addWidget(self.manual_container)
        # Updates visibility when changed
        self.alias_dropdown.currentTextChanged.connect(self.update_manual_fields)

        # Password/Passphrase
        self.pass_input = QLineEdit()
        self.pass_input.setPlaceholderText("Password or Key Passphrase")
        self.pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.pass_input)           # HPC Password

        # Status box
        self.status_box = QTextEdit()
        self.status_box.setReadOnly(True)
        self.status_box.setMaximumHeight(100)
        layout.addWidget(self.status_box)

        # Connect Button
        connect_btn = QPushButton("Connect")
        connect_btn.clicked.connect(self.connect_hpc)
        layout.addWidget(connect_btn)               # HPC Connection Button (connect_hpc)

        self.setLayout(layout)                      # Attaches layout to window
        self.local_last_download = None             # Path to last downloaded file


    # ============ Connection Functions ============
    def update_manual_fields(self, text):
        """Update visibility of manual host container"""
        self.manual_container.setVisible(text == "Manual Host")

    def connect_hpc(self):
        """CONNECT TO HPC"""
        alias = self.alias_dropdown.currentText().strip()
        password = self.pass_input.text().strip() or None

        self.ssh_client = paramiko.SSHClient()  # Uses Paramiko to Connect
        self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            if alias and alias != "Manual Host":
                print(f"Alias connection: {alias}")
                # Connect via SSH config alias
                params = get_ssh_params(alias)
                try:
                    print("Trying SSH Connection...")
                    self._connect_simple(params, password)
                    print("Connected.")
                    self.status_box.setPlainText(f"✅ Connected via alias '{alias}'")
                    self.main_window._log(f"✅ Connected via alias '{alias}'")
                    self._enter_browser()
                    return
                except (AuthenticationException, SSHException):
                    self.status_box.setPlainText("⚠️ Normal auth failed, trying 2FA...")
                    self.main_window._log("⚠️ Normal auth failed, trying 2FA...")
                    QApplication.processEvents()
                    self._connect_with_2fa(params, password)
                    return
            
            elif alias == "Manual Host":
                # Connect manually
                host = self.manual_host_input.text().strip()
                user = self.manual_user_input.text().strip()
                if not host or not user:
                    self.status_box.setPlainText("❌ Enter hostname and username for manual host")
                    self.main_window._log("❌ Enter hostname and username for manual host")
                    return
                
                params = {"hostname": host, "port": 22, "username": user, "key_filename": None}
                try:
                    self._connect_simple(params, password)
                    self.status_box.setPlainText(f"✅ Connected to manual host {host}")
                    self.main_window._log(f"✅ Connected to manual host {host}")
                    self._enter_browser()
                    return
                
                except (AuthenticationException, SSHException):
                    self.status_box.setPlainText("⚠️ Normal auth failed, trying 2FA...")
                    self.main_window._log("⚠️ Normal auth failed, trying 2FA...")
                    self._connect_with_2fa(params, password)
                    return
                

            else:
                self.status_box.setPlainText("❌ Select an alias or manual host")
                self.main_window._log("❌ Select an alias or manual host")

        except Exception as e:
            print("Exception caught!")
            print("Type:", type(e))        # Shows the exact exception class
            print("Args:", e.args)         # Shows the arguments/messages
            self.status_box.setPlainText(f"❌ Connection failed: {e}")
            self.main_window._log(f"❌ Connection failed: {e}")

    # SIMPLE CONNECT
    def _connect_simple(self, params, password):
        """Normal SSH Connect""" 
        self.ssh_client.connect(
            hostname=params['hostname'],
            port=params['port'],
            username=params['username'],
            key_filename=params['key_filename'],
            passphrase=password
        )
        self.sftp = self.ssh_client.open_sftp()
        self.hpc_user = params['username']
        self.hpc_host = params['hostname']

    # 2FA CONNECT
    def _connect_with_2fa(self, params, password):
        """Interactive 2FA connect using Transport"""

        # Clear old SSH client
        if self.ssh_client:
            self.ssh_client.close()
            self.ssh_client = None
        if self.sftp:
            self.sftp.close()
            self.sftp = None

        self.ssh_thread = SSHThread(params, password)
        self.ssh_thread.log_signal.connect(lambda msg: self.main_window._log(msg))
        self.ssh_thread.otp_signal.connect(self._ask_otp_signal)
        self.ssh_thread.finished_signal.connect(self._ssh_finished)
        self.ssh_thread.start()

    def _ask_otp_signal(self, prompt, echo):
        """Show Dialog in main thread"""
        code, ok = QInputDialog.getText(
            self,
            "Two-Factor Authentication",
            prompt,
            QLineEdit.Normal if echo else QLineEdit.Password
        )
        if not ok:
            code = ""

        self.ssh_thread.otp_result = code

    def _ssh_finished(self, success, message):
        if success:
            self.ssh_client = self.ssh_thread.ssh_client
            self.sftp = self.ssh_thread.sftp
            self.hpc_user = self.ssh_thread.params['username']
            self.hpc_host = self.ssh_thread.params['hostname']
            self.status_box.setPlainText(f"✅ {message}")
            self.main_window._log(f"✅ {message}")
            self._enter_browser()
        else:
            self.status_box.setPlainText(f"❌ Connection failed: {message}")
            self.main_window._log(f"❌ Connection failed: {message}")


    def _enter_browser(self):
        if self.browser_page:
            self.stack.removeWidget(self.browser_page)

        def log_to_main_window(message):
            if self.main_window:
                self.main_window._log(message)

        def open_file_in_main(path, base):
            if self.main_window:
                self.main_window._make_image_tab(path, base)

        self.browser_page = RemoteFileBrowser(
            self.sftp,
            start_path=".",
            disconnect_callback=self.disconnect_hpc,
            ssh_client=self.ssh_client,
            hpc_user=self.hpc_user,
            log_callback=log_to_main_window,
            file_open_callback=open_file_in_main,
            main_window=self.main_window
        )
        self.stack.addWidget(self.browser_page)
        self.stack.setCurrentWidget(self.browser_page)

        if hasattr(self.browser_page, 'local_last_download'):
            self.local_last_download = self.browser_page.local_last_download

    
    def disconnect_hpc(self):
        if self.sftp:
            self.sftp.close()
            self.sftp = None
        if self.ssh_client:
            self.ssh_client.close()
            self.ssh_client = None
        self.hpc_user = ""
        self.hpc_host = ""
        self.stack.setCurrentWidget(self.connection_page)
        self.status_box.setPlainText("Disconnected from HPC")