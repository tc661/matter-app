from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QListWidget, QPushButton
)
from stat import S_ISDIR, S_ISLNK
import os

# ----------------------------- Remote File Dialog -----------------------------------------------
class RemoteFileDialog(QDialog):
    """Remote file browser via SFTP"""
    def __init__(self, sftp, start_path=".", filters=None):
        super().__init__()
        self.sftp = sftp
        self.current_path = start_path
        self.selected_file = None
        self.filters = filters

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
