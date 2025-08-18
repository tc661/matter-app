from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QComboBox, QLabel,
    QLineEdit, QPushButton, QTextEdit
)
import paramiko
import os
import tempfile

from ssh_helpers import get_ssh_params
from remote_dialog import RemoteFileDialog


# ----------------------------- HPC Client -----------------------------
class HPCClient(QWidget):                           # QWidget = Parent Class
    # ============ Initialisation ============
    def __init__(self):
        """INITIALISE CLIENT AND SET UP WINDOW"""
        super().__init__()                          # Initialise as QWidget
        self.setWindowTitle("HPC → VASP Frontend")  
        self.ssh_client = None                      
        self.hpc_host = ""
        self.hpc_user = ""
        
        layout = QVBoxLayout()                      # Vertical layout

        # Alias dropdown
        self.alias_dropdown = QComboBox()       
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

        layout.addWidget(QLabel("Select SSH Alias / Host:"))
        layout.addWidget(self.alias_dropdown)

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

        # Connect Button
        connect_btn = QPushButton("Connect")
        connect_btn.clicked.connect(self.connect_hpc)
        layout.addWidget(connect_btn)               # HPC Connection Button (connect_hpc)


        # Job listing
        self.jobs_box = QTextEdit()
        self.jobs_box.setReadOnly(True)             
        layout.addWidget(self.jobs_box)             # Read-Only Jobs Window

        list_jobs_btn = QPushButton("List My Jobs")
        list_jobs_btn.clicked.connect(self.list_jobs)
        layout.addWidget(list_jobs_btn)             # List Jobs Button (list_jobs)

        # Remote POSCAR
        get_poscar_btn = QPushButton("Pick Remote File...")
        get_poscar_btn.clicked.connect(self.pick_remote_file)
        layout.addWidget(get_poscar_btn)            # POSCAR View Button (get_and_view_poscar)

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
                self.jobs_box.setPlainText(f"✅ Connected via alias '{alias}'")
            elif alias == "Manual Host":
                # Connect manually
                host = self.manual_host_input.text().strip()
                user = self.manual_user_input.text().strip()
                if not host or not user:
                    self.jobs_box.setPlainText("❌ Enter hostname and username for manual host")
                    return
                self.ssh_client.connect(
                    hostname=host,
                    username=user,
                    password=password
                )
                self.hpc_user = user
                self.hpc_host = host
                self.jobs_box.setPlainText(f"✅ Connected to manual host {host}")
            else:
                self.jobs_box.setPlainText("❌ Select an alias or manual host")
        except Exception as e:
            self.jobs_box.setPlainText(f"❌ Connection failed: {e}")
    

    # ============ Jobs ============
    def list_jobs(self):
        """LIST JOBS WHEN CONNECTED"""
        if not self.ssh_client:                     # Can't list jobs when not on HPC
            self.jobs_box.setPlainText("Not connected.")
            return
        try:
            stdin, stdout, stderr = self.ssh_client.exec_command(f"qstat -u {self.hpc_user}")
            output = stdout.read().decode()         # Interprets results of qstat
            self.jobs_box.setPlainText(output if output else "No jobs running.")
        except Exception as e:
            self.jobs_box.setPlainText(f"Error listing jobs: {e}")
    

    # ============ File viewing ============
    def pick_remote_file(self):
        """Opens remote browser and downloads selected file to a temp path"""
        if not self.ssh_client:                     # Can't view POSCAR if not connected
            self.jobs_box.setPlainText("❌ Not connected to HPC.")
            return
        sftp = self.ssh_client.open_sftp()
        try:
            dialog = RemoteFileDialog(sftp, start_path=".")
            if dialog.exec():
                remote_path = dialog.selected_file
                base = os.path.basename(remote_path)
                local_tmp = os.path.join(tempfile.gettempdir(), base or "remote_file")
                sftp.get(remote_path, local_tmp)        # Downloads POSCAR from HPC to local temp file by SFTP
                self.local_last_download = local_tmp      
                self.jobs_box.setPlainText(f"✅ File downloaded from {remote_path} to {local_tmp}")
        finally:
            sftp.close()