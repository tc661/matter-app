from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget
)

from stat import S_ISDIR, S_ISLNK
import os
import tempfile

# ----------------------------- Remote File Browser --------------------------------------------
class RemoteFileBrowser(QWidget):
    """Embedded remote file browser"""
    def __init__(self, sftp, start_path=".", filters=None, disconnect_callback=None, ssh_client=None, hpc_user="", log_callback=None):
        super().__init__()
        self.sftp = sftp
        self.ssh_client = ssh_client
        self.hpc_user = hpc_user
        self.current_path = start_path
        self.filters = filters
        self.disconnect_callback = disconnect_callback
        self.log_callback = log_callback
        self.local_last_download = None

        layout = QVBoxLayout()

        # Path Label
        header_layout = QHBoxLayout()
        self.path_label = QLabel(self.current_path)
        self.path_label.setWordWrap(True)
        self.path_label.setMinimumWidth(100)
        self.path_label.setMaximumWidth(300)
        header_layout.addWidget(self.path_label)

        # List jobs button
        list_jobs_btn = QPushButton("List My Jobs")
        list_jobs_btn.setMaximumWidth(100)
        list_jobs_btn.clicked.connect(self.list_jobs)
        layout.addWidget(list_jobs_btn)

        # Disconnect button
        disconnect_btn = QPushButton("Disconnect")
        disconnect_btn.setMaximumWidth(100)
        disconnect_btn.clicked.connect(self.handle_disconnect)
        header_layout.addWidget(disconnect_btn)

        layout.addLayout(header_layout)

        # File browser section
        browser_layout = QVBoxLayout()

        # File list
        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self.navigate_or_select)
        layout.addWidget(self.list_widget)

        # Nav Buttons
        nav_layout = QHBoxLayout()
        back_btn = QPushButton(".. (Up)")
        back_btn.setMaximumWidth(80)
        back_btn.clicked.connect(self.go_up)
        nav_layout.addWidget(back_btn)

        selected_file_btn = QPushButton("Download Selected File")
        selected_file_btn.setMaximumWidth(140)
        selected_file_btn.clicked.connect(self.download_selected_file)
        nav_layout.addWidget(selected_file_btn)

        browser_layout.addLayout(nav_layout)
        layout.addLayout(browser_layout)

        self.setLayout(layout)
        self.refresh_list()

    def handle_disconnect(self):
        if self.disconnect_callback:
            self.disconnect_callback()

    # ============ Jobs ============
    def list_jobs(self):
        """LIST JOBS WHEN CONNECTED"""
        if not self.ssh_client:                     # Can't list jobs when not on HPC
            self._log("Not connected to HPC.")
            return
        try:
            stdin, stdout, stderr = self.ssh_client.exec_command(f"qstat -u {self.hpc_user}")
            output = stdout.read().decode()         # Interprets results of qstat
            job_output = output if output else "No jobs running."
            self._log(f"=== Jobs for {self.hpc_user} ===\n{job_output}")
        except Exception as e:
            self._log(f"Error listing jobs: {e}")
    
    def _log(self, message):
        """Send message to main window via callback"""
        if self.log_callback:
            self.log_callback(message)

    # ============ File Management ==============
    def download_selected_file(self):
        """Downloads currently selected file"""
        current_item = self.list_widget.currentItem()
        if not current_item:
            self._log("No file selected.")
            return
        
        display_name = current_item.text()

        # Skip directories
        if display_name.endswith("/") or " -> (dir)" in display_name:
            self._log("Cannot download directories. Select a file.")
            return
        
        original_name = display_name.split(" -> ")[0].rstrip('/')
        full_path = self.join_remote_path(self.current_path, original_name)

        try:
            stat_result = self.sftp.stat(full_path)
            if S_ISDIR(stat_result.st_mode):
                self._log("Selected item is a directory. Select a file.")
                return

            base = os.path.basename(full_path)
            local_tmp = os.path.join(tempfile.gettempdir(), base or "remote_file")
            self.sftp.get(full_path, local_tmp)
            self.local_last_download = local_tmp
            self._log(f"File downloaded from {full_path} to {local_tmp}")

        except Exception as e:
            self._log(f"Error downloading file: {e}")

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
            for display_name, *_ in items:
                self.list_widget.addItem(display_name)
            
            self.path_label.setText(f"Path: {self.current_path}")  # Window title
        except Exception as e:
            self.list_widget.addItem(f"Error reading directory: {e}")


    def navigate_or_select(self, item):
        if not item:
            return
    
        display_name = item.text()
        original_name = display_name.split(" -> ")[0].rstrip('/')
        full_path = self.join_remote_path(self.current_path, original_name)

        try:
            stat_result = self.sftp.stat(full_path)
            if S_ISDIR(stat_result.st_mode):
                self.current_path = full_path
                self.refresh_list()
                return
        except Exception as e:
            self.list_widget.addItem(f"Cannot access: {e}")
            return
        
        self._log(f"Selected file: {full_path} (click 'Download Selected File' to download)")

    def go_up(self):
        if self.current_path != "/":
            self.current_path = os.path.dirname(self.current_path)
            self.refresh_list()
