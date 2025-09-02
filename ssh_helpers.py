import os
import subprocess
import paramiko
from PySide6.QtCore import QThread, Signal, QCoreApplication
from stat import S_ISDIR 

# ----------------------------- Existing SSH helpers -----------------------------
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


class SSHThread(QThread):
    log_signal = Signal(str)
    otp_signal = Signal(str, bool)

    finished_signal = Signal(bool, str)

    def __init__(self, params, password):
        super().__init__()
        self.params = params
        self.password = password
        self.transport = None
        self.ssh_client = None
        self.sftp = None
        self.otp_result = None

    def run(self):
        try:
            self.log_signal.emit("Creating Transport")
            self.transport = paramiko.Transport((self.params['hostname'], self.params['port']))
            self.transport.start_client(timeout=30)


            # Public key auth
            if self.params['key_filename']:
                try:
                    pkey = paramiko.RSAKey.from_private_key_file(self.params['key_filename'], self.password)
                    self.transport.auth_publickey(self.params['username'], pkey)
                    self.log_signal.emit("Publickey step passed")
                except Exception as e:
                    self.log_signal.emit(f"Publickey failed: {e}")

            # Interactive 2FA
            def handler(title, instructions, prompts):
                answers = []
                for prompt, echo in prompts:
                    if "Password" in prompt:
                        answers.append(self.password or "")
                        self.log_signal.emit("Entering password")
                    else:
                        # Ask OTP via main thread
                        self.otp_result = None
                        self.otp_signal.emit(prompt, echo)  # This triggers main thread to show dialog
                        while self.otp_result is None:
                            QCoreApplication.processEvents()
                            self.msleep(50)  # wait until OTP is set by main thread
                        answers.append(self.otp_result)
                return answers

            self.transport.auth_interactive(self.params['username'], handler)
            if not self.transport.is_authenticated():
                raise Exception("2FA authentication failed")

            # Attach SSHClient
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client._transport = self.transport
            self.sftp = self.ssh_client.open_sftp()

            self.finished_signal.emit(True, "Connected")
        except Exception as e:
            self.finished_signal.emit(False, str(e))

def remote_walk(sftp, path):
    """
    Recursively walk a remote directory over SFTP.

    Yields: (dirpath, dirnames, filenames)
    """
    dirs, files = [], []
    for f in sftp.listdir_attr(path):
        if f.filename.startswith("."):
            continue
        full_path = path.rstrip("/") + "/" + f.filename
        if S_ISDIR(f.st_mode):
            dirs.append(f.filename)
        else:
            files.append(f.filename)
    yield path, dirs, files
    for d in dirs:
        new_path = path.rstrip("/") + "/" + d
        yield from remote_walk(sftp, new_path)

