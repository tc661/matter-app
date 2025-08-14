import sys              # Interact with command line
import os               # Interact with files, paths
import paramiko         # Network with ssh
import tempfile         # For temporary files
import subprocess       # Utilise multiple processes
# ============ GUI packages from PySide6 ============
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QPushButton, 
                               QLineEdit, QLabel, QTextEdit, QFileDialog, QComboBox,
                               QListWidget, QDialog)
from PySide6.QtCore import Qt
# ===================================================
from ase.io import read # For viewing atomic structures
import pyvista as pv    # For 3D visualisation
from stat import S_ISDIR, S_ISLNK
import shutil




# === HPC CLIENT APP ===
class HPCClient(QWidget):                           # QWidget = Parent Class
    def __init__(self):
        """INITIALISE CLIENT AND SET UP WINDOW"""
        super().__init__()                          # Initialise as QWidget
        self.setWindowTitle("HPC → VASP Frontend")  
        self.ssh_client = None                      
        self.hpc_host = ""
        self.hpc_user = ""
        
        layout = QVBoxLayout()                      # Vertical layout

        # Alias from ~/.ssh/config
        self.alias_dropdown = QComboBox()
        self.alias_dropdown.setToolTip("Select host")
        self.alias_dropdown.addItem("")

        # Load aliases from ~/.ssh/config
        ssh_config_path = os.path.expanduser("~/.ssh/config")
        self.aliases = []
        if os.path.exists(ssh_config_path):
            with open(ssh_config_path) as f:
                cfg = paramiko.config.SSHConfig()
                cfg.parse(f)
                self.aliases = [h for h in cfg.get_hostnames() if '*' not in h]
            for host in self.aliases:
                self.alias_dropdown.addItem(host)

        # Manual host option
        self.alias_dropdown.addItem("Manual Host")

        layout.addWidget(QLabel("Select SSH Alias / Host:"))
        layout.addWidget(self.alias_dropdown)

        #Manual host container
        self.manual_container = QWidget()
        manual_layout = QVBoxLayout()

        self.manual_host_input = QLineEdit()
        self.manual_host_input.setPlaceholderText("Hostname (e.g., login.hpc.cam.ac.uk)")
        manual_layout.addWidget(self.manual_host_input)

        self.manual_user_input = QLineEdit()
        self.manual_user_input.setPlaceholderText("Username")
        manual_layout.addWidget(self.manual_user_input)           # HPC Username


        self.manual_container.setLayout(manual_layout)
        layout.addWidget(self.manual_container)
        self.manual_container.setVisible(False)

        # Password
        self.pass_input = QLineEdit()
        self.pass_input.setPlaceholderText("Password or Key Passphrase")
        self.pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.pass_input)           # HPC Password

        # Single Connect Button
        connect_btn = QPushButton("Connect")
        connect_btn.clicked.connect(self.connect_hpc)
        layout.addWidget(connect_btn)               # HPC Connection Button (connect_hpc)

        # Connects dropdown change to show/hide manual inputs
        self.alias_dropdown.currentTextChanged.connect(self.update_manual_fields)

        # Job listing
        self.jobs_box = QTextEdit()
        self.jobs_box.setReadOnly(True)             
        layout.addWidget(self.jobs_box)             # Read-Only Jobs Window

        list_jobs_btn = QPushButton("List My Jobs")
        list_jobs_btn.clicked.connect(self.list_jobs)
        layout.addWidget(list_jobs_btn)             # List Jobs Button (list_jobs)

        # Download POSCAR + view
        get_poscar_btn = QPushButton("Download POSCAR and View")
        get_poscar_btn.clicked.connect(self.get_and_view_poscar)
        layout.addWidget(get_poscar_btn)            # POSCAR View Button (get_and_view_poscar)

        self.setLayout(layout)                      # Attaches layout to window
        self.local_poscar_path = None


    # CONNECTION FUNCTIONS
    def update_manual_fields(self, text):
        if text == "Manual Host":
            self.manual_container.setVisible(True)
        else:
            self.manual_container.setVisible(False)


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
    

    # LISTING JOBS FUNCTION
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
    

    # POSCAR FUNCTION
    def get_and_view_poscar(self):
        """DOWNLOADS AND VIEWS REMOTE POSCAR"""
        if not self.ssh_client:                     # Can't view POSCAR if not connected
            self.jobs_box.setPlainText("❌ Not connected to HPC.")
            return
        
        sftp = self.ssh_client.open_sftp()
        dialog = RemoteFileDialog(sftp, start_path=".")
        if dialog.exec():
            remote_path = dialog.selected_file
            local_tmp = os.path.join(tempfile.gettempdir(), "POSCAR")
            sftp.get(remote_path, local_tmp)        # Downloads POSCAR from HPC to local temp file by SFTP
            self.local_poscar_path = local_tmp      
            self.jobs_box.setPlainText(f"✅ POSCAR downloaded from {remote_path} to {local_tmp}")

        # View in PyVista
        try:
            atoms = read(self.local_poscar_path)     # Gets atom data from POSCAR file using ASE.io read()
            plotter = pv.Plotter()                  # Plotter from PyVista
            for atom in atoms:                      
                sphere = pv.Sphere(radius=0.3, center=atom.position)
                plotter.add_mesh(sphere, color='white')
            plotter.show()                          # Plots basic visualisation of structure
        except Exception as e:
            self.jobs_box.setPlainText(f"Error visualizing POSCAR: {e}")

        # Auto-open in VESTA if installed
        vesta_path = shutil.which("vesta")

        if vesta_path:
            subprocess.Popen(["vesta", self.local_poscar_path])
        else:
            self.jobs_box.append("VESTA not found in PATH. Please set it manually.")


# === REMOTE FILE BROWSER ===
class RemoteFileDialog(QDialog):
    """Remote file browser via SFTP"""
    def __init__(self, sftp, start_path="."):
        super().__init__()
        self.sftp = sftp
        self.current_path = start_path
        self.selected_file = None

        self.setWindowTitle("Remote File Browser")
        self.resize(600, 400)
        layout = QVBoxLayout()

        self.path_label = QLabel(self.current_path)
        layout.addWidget(self.path_label)

        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self.navigate_or_select)
        layout.addWidget(self.list_widget)

        button_layout = QVBoxLayout()

        self.back_btn = QPushButton(".. (Up)")
        self.back_btn.clicked.connect(self.go_up)
        button_layout.addWidget(self.back_btn)

        select_btn = QPushButton("Select")
        select_btn.clicked.connect(self.navigate_or_select)
        button_layout.addWidget(select_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)
        self.setLayout(layout)
        self.refresh_list()

    def normalise_remote_path(self, path):
        if path == ".":
            return self.sftp.getcwd() or "."
        return path.replace('\\', '/')
    
    def join_remote_path(self, base, name):
        base = self.normalise_remote_path(base)
        if base.endswith('/'):
            return base + name
        else:
            return base + '/' + name

    def refresh_list(self):
        self.list_widget.clear()
        self.current_path = self.normalise_remote_path(self.current_path)

        try:
            items = []
            for f in self.sftp.listdir_attr(self.current_path):
                name = f.filename

                if name.startswith("."): # Skips hidden
                    continue

                full_path = self.join_remote_path(self.current_path, name)

                is_dir = False
                is_symlink = False

                if S_ISDIR(f.st_mode):
                    is_dir = True
                elif S_ISLNK(f.st_mode):
                    is_symlink = True
                    try:
                        target_stat = self.sftp.stat(full_path)
                        is_dir = S_ISDIR(target_stat.st_mode)

                    except Exception as e1:
                        try:
                            target_path = self.sftp.readlink(full_path)
                            if not target_path.startswith("/"):
                                current_dir = self.current_path.rstrip("/")
                                target_path = current_dir + "/" + target_path
                            
                            target_stat = self.sftp.stat(target_path)
                            is_dir = S_ISDIR(target_stat.st_mode)
                        except Exception as e2:
                            is_dir=False

                display_name = name
                if is_symlink and is_dir:
                    display_name += " -> (dir)"
                elif is_symlink:
                    display_name += " -> (file)"
                elif is_dir:
                    display_name += "/"  # mark directories

                items.append((display_name, name, is_dir, is_symlink, full_path))

            # SORT FILES/DIRECTORIES      
            items.sort(key=lambda x: (not x[2], x[1].lower()))

            for display_name, _, _, _, _ in items:
                self.list_widget.addItem(display_name)
            
            self.path_label.setText(f"Path: {self.current_path}")  # Window title
        
        except Exception as e:
            self.list_widget.addItem(f"Error reading directory: {e}")
    
    def navigate_or_select(self, item):
        if not item:
            return
        
        display_name = item.text()

        original_name = display_name
        if " -> " in display_name:
            original_name = display_name.split(" -> ")[0]
        elif display_name.endswith("/"):
            original_name = display_name[:-1]
        
        full_path = self.join_remote_path(self.current_path, original_name)

        try:
            stat_result = self.sftp.stat(full_path)
            if S_ISDIR(stat_result.st_mode):
                self.current_path = full_path
                self.refresh_list()
                return
        except Exception as e:
            # If stat fails, might be a broken symlink
            if " -> " in display_name:
                self.list_widget.addItem(f"Cannot access: {e}")
                return
            
        self.selected_file = full_path
        self.accept()

    def go_up(self):
        if self.current_path != "/":
            self.current_path = os.path.dirname(self.current_path)
            self.refresh_list()




# === SSH Helper Functions ===
def get_ssh_params(alias):
    """Read ~/.ssh/config and return params for given alias."""
    ssh_config_path = os.path.expanduser("~/.ssh/config")               # Opens config from user profile
    ssh_params = {}                                                     # Empty dictionary for ssh params
    if os.path.exists(ssh_config_path):
        from paramiko.config import SSHConfig                           # Only loads SSHConfig package if config path found
        with open(ssh_config_path) as f:
            ssh_config = SSHConfig()
            ssh_config.parse(f)                                         # Parses .ssh/config into paramiko SSHConfig() object
            host_config = ssh_config.lookup(alias)                      # Checks host config params for an alias
            ssh_params['hostname'] = host_config.get('hostname', alias)
            ssh_params['username'] = host_config.get('user', None)
            ssh_params['port'] = int(host_config.get('port', 22))
            ssh_params['key_filename'] = host_config.get('identityfile', [None])[0]
    else:                                                               # No config file found
        ssh_params['hostname'] = alias                                  # Creates default hostname and port parameter
        ssh_params['username'] = None
        ssh_params['port'] = 22
        ssh_params['key_filename'] = None
    return ssh_params


def generate_ssh_key(key_path="~/.ssh/id_rsa"):
    """Generate SSH keypair if it doesn't exist."""
    key_path = os.path.expanduser(key_path)
    if not os.path.exists(key_path):                                    # runs ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa -N 
        subprocess.run(["ssh-keygen", "-t", "rsa", "-b", "4096", "-f", key_path, "-N", ""])
        return True                                                     # returns true if new keypair
    return False                                                        # returns false if keypair already exists


def add_key_to_server(alias="hpc"):
    """Copy SSH public key to remote server."""
    subprocess.run(["ssh-copy-id", alias])                             # adds keypair as authorised on server "hpc"



if __name__ == "__main__":
    print("Starting Application")
    app = QApplication(sys.argv)                    # Runs as an app
    print("QApplication initialized")
    window = HPCClient()                            # Opens / initialises GUI window
    print("Window Initialized")
    window.resize(500, 400)
    print("Window resized")
    window.show()                                   # Shows window
    print("Window shown")
    sys.exit(app.exec())                            # Starts app loop and exits upon exit
