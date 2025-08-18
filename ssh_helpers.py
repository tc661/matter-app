import os
import subprocess

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
