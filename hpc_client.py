from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QComboBox, QLabel,
    QLineEdit, QPushButton, QTextEdit, QStackedLayout
)
import paramiko
import os
import tempfile

from ssh_helpers import get_ssh_params
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
                # Connect via SSH config alias
                params = get_ssh_params(alias)
                self.ssh_client.connect(
                    hostname=params['hostname'],
                    port=params['port'],
                    username=params['username'],
                    key_filename=params['key_filename'],
                    passphrase=password
                )
                self.hpc_user = params["username"] or ""
                self.hpc_host = params["hostname"]
                self.status_box.setPlainText(f"✅ Connected via alias '{alias}'")
                # Enter file browser
                self.sftp = self.ssh_client.open_sftp()
                self._enter_browser()
            elif alias == "Manual Host":
                # Connect manually
                host = self.manual_host_input.text().strip()
                user = self.manual_user_input.text().strip()
                if not host or not user:
                    self.status_box.setPlainText("❌ Enter hostname and username for manual host")
                    return
                self.ssh_client.connect(
                    hostname=host,
                    username=user,
                    password=password
                )
                self.hpc_user = user
                self.hpc_host = host
                self.status_box_box.setPlainText(f"✅ Connected to manual host {host}")
                # Enter file browser
                self.sftp = self.ssh_client.open_sftp()
                self._enter_browser()
            else:
                self.status_box.setPlainText("❌ Select an alias or manual host")
        
        except Exception as e:
            self.status_box.setPlainText(f"❌ Connection failed: {e}")
    

    def _enter_browser(self):
        if self.browser_page:
            self.stack.removeWidget(self.browser_page)

        def log_to_main_window(message):
            if self.main_window:
                self.main_window._log(message)


        self.browser_page = RemoteFileBrowser(
            self.sftp,
            start_path=".",
            disconnect_callback=self.disconnect_hpc,
            ssh_client=self.ssh_client,
            hpc_user=self.hpc_user,
            log_callback=log_to_main_window
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