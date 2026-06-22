import subprocess
import sys
import os
import os as os_module

# ── Auto-install missing packages on startup ─────────────────────────────────
def auto_install_deps():
    apt_packages = [
        "tmate", "qemu-system-x86", "qemu-utils", "cloud-image-utils",
        "wget", "curl", "sshpass", "screen", "netcat-openbsd"
    ]
    pip_packages = ["discord.py", "python-dotenv"]
    print("🔍 Checking dependencies...")
    for pkg in apt_packages:
        result = subprocess.run(["bash", "-c", f"dpkg -l {pkg} 2>/dev/null | grep -q '^ii'"], capture_output=True)
        if result.returncode != 0:
            print(f"📦 Installing {pkg}...")
            subprocess.run(["bash", "-c", f"DEBIAN_FRONTEND=noninteractive apt-get install -y {pkg} -qq 2>/dev/null"], capture_output=True)
    for pkg in pip_packages:
        import_name = pkg.replace(".py","").replace("-","_").replace("python_dotenv","dotenv").replace("discord_py","discord")
        try:
            __import__(import_name)
        except ImportError:
            print(f"📦 Installing {pkg}...")
            subprocess.run([sys.executable, "-m", "pip", "install", pkg, "--break-system-packages", "-q"], capture_output=True)
    print("✅ All dependencies ready!")

auto_install_deps()

import discord
from discord import app_commands
import asyncio
import re
import glob
import datetime
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
YOUR_USER_ID = int(os.getenv("DISCORD_USER_ID"))
VM_DIR = os.path.expanduser("~/vms")

OS_OPTIONS = {
    "ubuntu22":   ("ubuntu",     "jammy",    "https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img",        "ubuntu22", "ubuntu", "ubuntu"),
    "ubuntu24":   ("ubuntu",     "noble",    "https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img",         "ubuntu24", "ubuntu", "ubuntu"),
    "debian11":   ("debian",     "bullseye", "https://cloud.debian.org/images/cloud/bullseye/latest/debian-11-generic-amd64.qcow2",   "debian11", "debian", "debian"),
    "debian12":   ("debian",     "bookworm", "https://cloud.debian.org/images/cloud/bookworm/latest/debian-12-generic-amd64.qcow2",   "debian12", "debian", "debian"),
    "fedora40":   ("fedora",     "40",       "https://download.fedoraproject.org/pub/fedora/linux/releases/40/Cloud/x86_64/images/Fedora-Cloud-Base-40-1.14.x86_64.qcow2", "fedora40", "fedora", "fedora"),
    "centos9":    ("centos",     "stream9",  "https://cloud.centos.org/centos/9-stream/x86_64/images/CentOS-Stream-GenericCloud-9-latest.x86_64.qcow2", "centos9", "centos", "centos"),
    "almalinux9": ("almalinux",  "9",        "https://repo.almalinux.org/almalinux/9/cloud/x86_64/images/AlmaLinux-9-GenericCloud-latest.x86_64.qcow2", "almalinux9", "alma", "alma"),
    "rocky9":     ("rockylinux", "9",        "https://download.rockylinux.org/pub/rocky/9/images/x86_64/Rocky-9-GenericCloud.latest.x86_64.qcow2", "rocky9", "rocky", "rocky"),
}

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

SSH_SCRIPT = """
unset TMUX
if ! command -v tmate &> /dev/null; then
  apt-get update -qq && apt-get install -y tmate -qq
fi
pkill -f tmate 2>/dev/null || true
sleep 1
rm -f /tmp/tmate.sock
tmate -S /tmp/tmate.sock new-session -d
tmate -S /tmp/tmate.sock wait tmate-ready
TMATE_LINK=$(tmate -S /tmp/tmate.sock display -p '#{tmate_ssh}')
echo "${TMATE_LINK/ssh /ssh -o ServerAliveInterval=60 }"
"""

DEL_SSH_SCRIPT = """
pkill -f tmate 2>/dev/null || true
rm -f /tmp/tmate.sock
echo "done"
"""

VPS_INFO_SCRIPT = """
echo "HOSTNAME=$(hostname)"
echo "OS=$(cat /etc/os-release | grep PRETTY_NAME | cut -d= -f2 | tr -d '\"')"
echo "KERNEL=$(uname -r)"
echo "CPU=$(lscpu | grep 'Model name' | cut -d: -f2 | xargs)"
echo "CPU_CORES=$(nproc)"
echo "RAM_TOTAL=$(free -m | awk '/Mem:/{print $2}')"
echo "RAM_USED=$(free -m | awk '/Mem:/{print $3}')"
echo "RAM_FREE=$(free -m | awk '/Mem:/{print $4}')"
echo "DISK_TOTAL=$(df -h / | awk 'NR==2{print $2}')"
echo "DISK_USED=$(df -h / | awk 'NR==2{print $3}')"
echo "DISK_FREE=$(df -h / | awk 'NR==2{print $4}')"
echo "DISK_PERCENT=$(df -h / | awk 'NR==2{print $5}')"
echo "PUBLIC_IP=$(curl -s ifconfig.me)"
echo "UPTIME=$(uptime -p)"
echo "LOAD=$(uptime | awk -F'load average:' '{print $2}' | xargs)"
echo "PING=$(ping -c 1 8.8.8.8 | tail -1 | awk -F'/' '{print $5}' 2>/dev/null || echo 'N/A')"
"""

PING_SCRIPT = """
echo "GOOGLE=$(ping -c 2 8.8.8.8 | tail -1 | awk -F'/' '{print $5}' 2>/dev/null || echo 'N/A')"
echo "CLOUDFLARE=$(ping -c 2 1.1.1.1 | tail -1 | awk -F'/' '{print $5}' 2>/dev/null || echo 'N/A')"
echo "GITHUB=$(ping -c 2 github.com | tail -1 | awk -F'/' '{print $5}' 2>/dev/null || echo 'N/A')"
"""

DATACENTER_SCRIPT = """
IP=$(curl -s ifconfig.me)
INFO=$(curl -s ipinfo.io/$IP)
echo "IP=$IP"
echo "CITY=$(echo $INFO | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('city','N/A'))")"
echo "REGION=$(echo $INFO | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('region','N/A'))")"
echo "COUNTRY=$(echo $INFO | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('country','N/A'))")"
echo "ORG=$(echo $INFO | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('org','N/A'))")"
echo "TIMEZONE=$(echo $INFO | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('timezone','N/A'))")"
echo "LOC=$(echo $INFO | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('loc','N/A'))")"
"""

DEL_XRDP_SCRIPT = """
systemctl stop xrdp 2>/dev/null
systemctl disable xrdp 2>/dev/null
apt-get remove --purge -y xrdp xfce4 xfce4-goodies dbus-x11 firefox-esr 2>/dev/null
apt-get autoremove -y 2>/dev/null
rm -f ~/.xsession
pkill -f "tcp@a.pinggy.io" 2>/dev/null
echo "done"
"""

# ── Detect host OS ───────────────────────────────────────────────────────────
def get_host_os():
    result = subprocess.run(["bash", "-c", "cat /etc/os-release | grep PRETTY_NAME | cut -d= -f2 | tr -d '\"'"], capture_output=True, text=True)
    os_str = result.stdout.strip().lower()
    if "ubuntu 22" in os_str: return "ubuntu22"
    elif "ubuntu 24" in os_str: return "ubuntu24"
    elif "ubuntu" in os_str: return "ubuntu"
    elif "debian" in os_str:
        ver = subprocess.run(["bash", "-c", "cat /etc/debian_version | cut -d. -f1"], capture_output=True, text=True).stdout.strip()
        return f"debian{ver}"
    return "unknown"

HOST_OS = get_host_os()

def get_xrdp_install_script():
    """Returns the correct XRDP install script based on host OS"""
    base = """
apt-get update -y
DEBIAN_FRONTEND=noninteractive apt-get upgrade -y
DEBIAN_FRONTEND=noninteractive apt-get install -y xfce4 xfce4-goodies xrdp dbus-x11
"""
    ubuntu22_extra = """
DEBIAN_FRONTEND=noninteractive apt-get install -y dbus-user-session xorg
echo "xfce4-session" > ~/.xsession
chmod +x ~/.xsession
chown $(whoami):$(whoami) ~/.xsession
adduser xrdp ssl-cert 2>/dev/null || usermod -aG ssl-cert xrdp 2>/dev/null || true
sed -i 's/^Exec=firefox-esr.*/Exec=firefox-esr --no-sandbox --disable-seccomp/' /usr/share/applications/firefox-esr.desktop 2>/dev/null || true
"""
    debian12_extra = """
DEBIAN_FRONTEND=noninteractive apt-get install -y dbus-user-session xorg
echo "xfce4-session" > ~/.xsession
chmod +x ~/.xsession
chown $(whoami):$(whoami) ~/.xsession
adduser xrdp ssl-cert 2>/dev/null || usermod -aG ssl-cert xrdp 2>/dev/null || true
mkdir -p /run/dbus
dbus-daemon --system --fork 2>/dev/null || true
echo "allowed_users=anybody" >> /etc/X11/Xwrapper.config 2>/dev/null || true
echo "xfce4-session" > /etc/xrdp/startwm.sh 2>/dev/null || true
chmod +x /etc/xrdp/startwm.sh 2>/dev/null || true
sed -i 's/^Exec=firefox-esr.*/Exec=firefox-esr --no-sandbox --disable-seccomp/' /usr/share/applications/firefox-esr.desktop 2>/dev/null || true
"""
    debian11_extra = """
echo "xfce4-session" > ~/.xsession
chmod +x ~/.xsession
chown $(whoami):$(whoami) ~/.xsession
adduser xrdp ssl-cert 2>/dev/null || usermod -aG ssl-cert xrdp 2>/dev/null || true
sed -i 's/^Exec=firefox-esr.*/Exec=firefox-esr --no-sandbox --disable-seccomp/' /usr/share/applications/firefox-esr.desktop 2>/dev/null || true
"""
    end = """
systemctl enable xrdp 2>/dev/null || true
systemctl enable xrdp-sesman 2>/dev/null || true
systemctl restart xrdp 2>/dev/null || true
/etc/init.d/xrdp restart 2>/dev/null || true
echo "XRDP_INSTALL_DONE"
"""
    if "ubuntu22" in HOST_OS or "ubuntu24" in HOST_OS or "ubuntu" in HOST_OS:
        return base + ubuntu22_extra + end
    elif "debian12" in HOST_OS:
        return base + debian12_extra + end
    else:
        return base + debian11_extra + end

# ── VM helpers ───────────────────────────────────────────────────────────────
def get_vm_list():
    os.makedirs(VM_DIR, exist_ok=True)
    confs = glob.glob(os.path.join(VM_DIR, "*.conf"))
    return sorted([os.path.basename(c).replace(".conf","") for c in confs])

def load_vm_config(vm_name):
    conf = os.path.join(VM_DIR, f"{vm_name}.conf")
    if not os.path.exists(conf): return None
    info = {}
    with open(conf) as f:
        for line in f:
            line = line.strip().strip("\r")
            if "=" in line:
                k, _, v = line.partition("=")
                info[k.strip()] = v.strip().strip('"')
    return info

def is_vm_running(vm_name):
    cfg = load_vm_config(vm_name)
    if not cfg: return False
    ssh_port = cfg.get("SSH_PORT","")
    if ssh_port:
        result = subprocess.run(["bash","-c",f"ss -tlnp 2>/dev/null | grep ':{ssh_port} '"], capture_output=True, text=True)
        return bool(result.stdout.strip())
    return False

def start_vm_background(vm_name):
    cfg = load_vm_config(vm_name)
    if not cfg: return False, "VM config not found"
    img_file  = cfg.get("IMG_FILE","")
    seed_file = cfg.get("SEED_FILE","")
    memory    = cfg.get("MEMORY","2048")
    cpus      = cfg.get("CPUS","2")
    ssh_port  = cfg.get("SSH_PORT","2222")
    if not os.path.exists(img_file): return False, f"Image not found: {img_file}"
    if not os.path.exists(seed_file): return False, f"Seed not found: {seed_file}"
    cmd = (
        f"nohup qemu-system-x86_64 -enable-kvm -m {memory} -smp {cpus} -cpu host "
        f"-drive file={img_file},format=qcow2,if=virtio "
        f"-drive file={seed_file},format=raw,if=virtio "
        f"-boot order=c -device virtio-net-pci,netdev=n0 "
        f"-netdev user,id=n0,hostfwd=tcp::{ssh_port}-:22 "
        f"-nographic -serial none -monitor none "
        f"-device virtio-balloon-pci "
        f"-object rng-random,filename=/dev/urandom,id=rng0 "
        f"-device virtio-rng-pci,rng=rng0 "
        f"> /tmp/vm_{vm_name}.log 2>&1 &"
    )
    subprocess.Popen(["bash","-c",cmd])
    return True, ""

def stop_vm_proc(vm_name):
    cfg = load_vm_config(vm_name)
    if not cfg: return False
    img = cfg.get("IMG_FILE","")
    subprocess.run(["bash","-c",f"pkill -f 'qemu.*{os_module.path.basename(img)}' 2>/dev/null"], capture_output=True)
    return True

def create_vm_files(vm_name, os_key, disk_size, memory, cpus, ssh_port, password):
    if os_key not in OS_OPTIONS: return False, f"Unknown OS: {os_key}"
    os_type, codename, img_url, hostname, username, default_pass = OS_OPTIONS[os_key]
    if not password: password = default_pass
    os.makedirs(VM_DIR, exist_ok=True)
    img_file  = os.path.join(VM_DIR, f"{vm_name}.img")
    seed_file = os.path.join(VM_DIR, f"{vm_name}-seed.iso")
    if not os.path.exists(img_file):
        r = subprocess.run(["bash","-c",f"wget -q '{img_url}' -O '{img_file}.tmp' && mv '{img_file}.tmp' '{img_file}'"], capture_output=True, text=True, timeout=600)
        if r.returncode != 0: return False, f"Download failed: {r.stderr[:500]}"
    subprocess.run(["bash","-c",f"qemu-img resize '{img_file}' {disk_size} 2>/dev/null"], capture_output=True, timeout=60)
    hash_result = subprocess.run(["bash","-c",f"openssl passwd -6 '{password}'"], capture_output=True, text=True)
    pw_hash = hash_result.stdout.strip()
    user_data = f"""#cloud-config
hostname: {hostname}
ssh_pwauth: true
disable_root: false
users:
  - name: {username}
    sudo: ALL=(ALL) NOPASSWD:ALL
    shell: /bin/bash
    password: {pw_hash}
chpasswd:
  list: |
    root:{password}
    {username}:{password}
  expire: false
"""
    meta_data = f"instance-id: iid-{vm_name}\nlocal-hostname: {hostname}\n"
    ud_path = f"/tmp/user-data-{vm_name}"
    md_path = f"/tmp/meta-data-{vm_name}"
    with open(ud_path,"w") as f: f.write(user_data)
    with open(md_path,"w") as f: f.write(meta_data)
    r = subprocess.run(["bash","-c",f"cloud-localds '{seed_file}' '{ud_path}' '{md_path}'"], capture_output=True, text=True, timeout=60)
    if r.returncode != 0: return False, f"cloud-localds failed: {r.stderr[:500]}"
    conf = os.path.join(VM_DIR, f"{vm_name}.conf")
    with open(conf,"w") as f:
        f.write(f'VM_NAME="{vm_name}"\n')
        f.write(f'OS_TYPE="{os_type}"\n')
        f.write(f'CODENAME="{codename}"\n')
        f.write(f'IMG_URL="{img_url}"\n')
        f.write(f'HOSTNAME="{hostname}"\n')
        f.write(f'USERNAME="{username}"\n')
        f.write(f'PASSWORD="{password}"\n')
        f.write(f'DISK_SIZE="{disk_size}"\n')
        f.write(f'MEMORY="{memory}"\n')
        f.write(f'CPUS="{cpus}"\n')
        f.write(f'SSH_PORT="{ssh_port}"\n')
        f.write(f'IMG_FILE="{img_file}"\n')
        f.write(f'SEED_FILE="{seed_file}"\n')
        f.write(f'CREATED="{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}"\n')
    return True, ""

pending_deletes = {}

def wait_for_vm_ssh(vm_name, max_wait=180):
    cfg = load_vm_config(vm_name)
    if not cfg: return None
    ssh_port = cfg.get("SSH_PORT","2222")
    username = cfg.get("USERNAME","ubuntu")
    password = cfg.get("PASSWORD","")
    import time

    # Wait for actual SSH to accept connections (not just port open)
    for _ in range(max_wait // 5):
        check = subprocess.run(
            ["bash","-c",f"sshpass -p '{password}' ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 -o BatchMode=no -p {ssh_port} {username}@localhost echo connected 2>/dev/null"],
            capture_output=True, text=True
        )
        if "connected" in check.stdout:
            break
        time.sleep(5)
    else:
        return None

    time.sleep(2)

    # Write tmate script to temp file
    script_path = f"/tmp/vmssh_{vm_name}.sh"
    script_content = """#!/bin/bash
unset TMUX
command -v tmate &>/dev/null || (sudo apt-get update -qq && sudo apt-get install -y tmate -qq 2>/dev/null || true)
pkill -f tmate 2>/dev/null || true
sleep 2
rm -f /tmp/tmate.sock
tmate -S /tmp/tmate.sock new-session -d
tmate -S /tmp/tmate.sock wait tmate-ready
LINK=$(tmate -S /tmp/tmate.sock display -p "#{tmate_ssh}")
echo "${LINK/ssh /ssh -o ServerAliveInterval=60 }"
"""
    with open(script_path,"w") as f: f.write(script_content)
    os.chmod(script_path, 0o755)

    copy_cmd = f"sshpass -p '{password}' scp -o StrictHostKeyChecking=no -o ConnectTimeout=15 -P {ssh_port} {script_path} {username}@localhost:/tmp/vmssh.sh 2>/dev/null"
    subprocess.run(["bash","-c",copy_cmd], capture_output=True, timeout=30)

    run_cmd = f"sshpass -p '{password}' ssh -o StrictHostKeyChecking=no -o ConnectTimeout=15 -p {ssh_port} {username}@localhost bash /tmp/vmssh.sh 2>/dev/null"
    result = subprocess.run(["bash","-c",run_cmd], capture_output=True, text=True, timeout=90)
    link = result.stdout.strip()
    if link and "ssh" in link: return link
    return None

def delete_vm_files(vm_name):
    cfg = load_vm_config(vm_name)
    if cfg:
        ssh_port = cfg.get("SSH_PORT","")
        img = cfg.get("IMG_FILE","")
        subprocess.run(["bash","-c",f"pkill -f 'qemu.*{os_module.path.basename(img)}' 2>/dev/null"], capture_output=True)
        import time; time.sleep(2)
        if ssh_port:
            subprocess.run(["bash","-c",f"ssh-keygen -f /root/.ssh/known_hosts -R '[localhost]:{ssh_port}' 2>/dev/null"], capture_output=True)
        for key in ["IMG_FILE","SEED_FILE"]:
            f = cfg.get(key,"")
            if f and os.path.exists(f):
                try: os.remove(f)
                except: pass
    conf = os.path.join(VM_DIR, f"{vm_name}.conf")
    if os.path.exists(conf):
        try: os.remove(conf)
        except: pass
    subprocess.run(["bash","-c",f"rm -f /tmp/user-data-{vm_name} /tmp/meta-data-{vm_name} /tmp/vm_{vm_name}.log /tmp/vmssh_{vm_name}.sh 2>/dev/null"], capture_output=True)

def build_vminfo_embed(vm_name):
    cfg = load_vm_config(vm_name)
    if not cfg: return None
    running = is_vm_running(vm_name)
    status = "🟢 Running" if running else "🔴 Stopped"
    img_file = cfg.get("IMG_FILE","")
    disk_actual = "N/A"
    if img_file and os.path.exists(img_file):
        r = subprocess.run(["bash","-c",f"du -h '{img_file}' | cut -f1"], capture_output=True, text=True)
        disk_actual = r.stdout.strip() or "N/A"
    uptime_val = "VM not running"
    ping_val = "VM not running"
    if running:
        try:
            ssh_port = cfg.get("SSH_PORT","")
            password = cfg.get("PASSWORD","")
            username = cfg.get("USERNAME","")
            r = subprocess.run(["bash","-c",f"sshpass -p '{password}' ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 -p {ssh_port} {username}@localhost 'uptime -p' 2>/dev/null"], capture_output=True, text=True, timeout=10)
            uptime_val = r.stdout.strip() or "N/A"
            r2 = subprocess.run(["bash","-c",f"sshpass -p '{password}' ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 -p {ssh_port} {username}@localhost \"ping -c 1 8.8.8.8 | tail -1 | awk -F'/' '{{print $5}}'\" 2>/dev/null"], capture_output=True, text=True, timeout=15)
            ping_val = f"{r2.stdout.strip()} ms" if r2.stdout.strip() else "N/A"
        except: pass
    embed = discord.Embed(title=f"🖥️ VM Info — {vm_name}", description=f"Status: {status}", color=0x2ecc71 if running else 0xe74c3c)
    embed.add_field(name="🐧 OS", value=cfg.get("OS_TYPE","N/A"), inline=True)
    embed.add_field(name="📦 Codename", value=cfg.get("CODENAME","N/A"), inline=True)
    embed.add_field(name="🏠 Hostname", value=cfg.get("HOSTNAME","N/A"), inline=True)
    embed.add_field(name="🧠 RAM", value=f"{cfg.get('MEMORY','N/A')} MB", inline=True)
    embed.add_field(name="🧵 CPUs", value=cfg.get("CPUS","N/A"), inline=True)
    embed.add_field(name="🔌 SSH Port", value=cfg.get("SSH_PORT","N/A"), inline=True)
    embed.add_field(name="💾 Disk Size", value=cfg.get("DISK_SIZE","N/A"), inline=True)
    embed.add_field(name="📂 Disk Used", value=disk_actual, inline=True)
    embed.add_field(name="👤 Username", value=cfg.get("USERNAME","N/A"), inline=True)
    embed.add_field(name="⏱️ VM Uptime", value=uptime_val, inline=True)
    embed.add_field(name="🏓 VM Ping", value=ping_val, inline=True)
    embed.add_field(name="📅 Created", value=cfg.get("CREATED","N/A"), inline=False)
    embed.set_footer(text="Auto-deletes in 20 seconds")
    return embed

# ── General helpers ──────────────────────────────────────────────────────────
def run_script(script, timeout=300):
    result = subprocess.run(["bash","-c",script], capture_output=True, text=True, timeout=timeout)
    return result.stdout.strip(), result.stderr.strip()

def parse_info(output):
    info = {}
    for line in output.split("\n"):
        if "=" in line:
            key, _, value = line.partition("=")
            info[key.strip()] = value.strip()
    return info

def safe_int(value, default=0):
    try: return int(str(value).replace("MB","").replace("GB","").strip())
    except: return default

def is_ssh_active():
    result = subprocess.run(["bash","-c","tmate -S /tmp/tmate.sock display -p '#{tmate_ssh}' 2>/dev/null"], capture_output=True, text=True)
    return result.returncode == 0 and result.stdout.strip() != ""

def is_xrdp_installed():
    result = subprocess.run(["bash","-c","dpkg -l xrdp 2>/dev/null | grep -q '^ii'"], capture_output=True)
    return result.returncode == 0

def is_pinggy_running():
    result = subprocess.run(["bash","-c","pgrep -f 'tcp@a.pinggy.io'"], capture_output=True)
    return result.returncode == 0

def kill_pinggy():
    subprocess.run(["bash","-c","pkill -f 'tcp@a.pinggy.io' 2>/dev/null"], capture_output=True)

def start_pinggy_and_get_url():
    kill_pinggy()
    import time
    open("/tmp/pinggy.log","w").close()
    subprocess.Popen(["bash","-c","nohup ssh -o StrictHostKeyChecking=no -p 443 -R0:localhost:3389 tcp@a.pinggy.io > /tmp/pinggy.log 2>&1 &"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = None
    for _ in range(20):
        time.sleep(2)
        try:
            with open("/tmp/pinggy.log","r") as f: content = f.read()
            match = re.search(r'tcp://([\w\-\.]+:\d+)', content)
            if match: url = match.group(1); break
        except: pass
    return url

def make_progress_bar(percent):
    filled = percent // 10
    return f"`{'█' * filled + '░' * (10-filled)}` {percent}%"

def auth_check(message):
    return message.author.id == YOUR_USER_ID

def is_dm(message):
    return isinstance(message.channel, discord.DMChannel)

async def auto_delete(msg, user_msg, delay=20):
    if is_dm(user_msg): return
    await asyncio.sleep(delay)
    try: await msg.delete()
    except: pass
    try: await user_msg.delete()
    except: pass

async def install_xrdp_with_progress(msg):
    def make_embed(title, desc, percent, color=0x3498db):
        embed = discord.Embed(title=title, description=desc, color=color)
        embed.add_field(name="Progress", value=make_progress_bar(percent), inline=False)
        embed.set_footer(text=f"Running on {HOST_OS} • Please wait...")
        return embed

    loop = asyncio.get_event_loop()
    xrdp_script = get_xrdp_install_script()
    steps = xrdp_script.strip().split("\n")

    await msg.edit(content=None, embed=make_embed("⏳ Installing XRDP", f"**Step 1/5** — Updating packages...\n*Detected OS: `{HOST_OS}`*", 10))
    await loop.run_in_executor(None, lambda: run_script("apt-get update -y", timeout=120))

    await msg.edit(embed=make_embed("⏳ Installing XRDP", "**Step 2/5** — Upgrading system...", 25))
    await loop.run_in_executor(None, lambda: run_script("DEBIAN_FRONTEND=noninteractive apt-get upgrade -y", timeout=180))

    await msg.edit(embed=make_embed("⏳ Installing XRDP", "**Step 3/5** — Installing XFCE4, XRDP, Firefox...\n*(Slowest step)*", 50))
    stdout, stderr = await loop.run_in_executor(None, lambda: run_script(
        "DEBIAN_FRONTEND=noninteractive apt-get install -y xfce4 xfce4-goodies xrdp dbus-x11 dbus-user-session xorg", timeout=600))
    if "error" in stderr.lower() and "xrdp" not in stdout.lower():
        return False, stderr

    # Install Firefox separately — snap on Ubuntu, apt on Debian
    await msg.edit(embed=make_embed("⏳ Installing XRDP", "**Step 3.5/5** — Installing Firefox...", 60))
    await loop.run_in_executor(None, lambda: run_script("""
if [ "$(. /etc/os-release && echo $ID)" = "ubuntu" ] && command -v snap &>/dev/null; then
  snap install firefox 2>/dev/null || true
else
  DEBIAN_FRONTEND=noninteractive apt-get install -y firefox-esr 2>/dev/null || true
fi
""", timeout=180))

    await msg.edit(embed=make_embed("⏳ Installing XRDP", "**Step 4/5** — Configuring for your OS...", 75))
    await loop.run_in_executor(None, lambda: run_script(get_xrdp_install_script().split("systemctl enable")[0], timeout=60))

    await msg.edit(embed=make_embed("⏳ Installing XRDP", "**Step 5/5** — Starting XRDP service...", 90))
    await loop.run_in_executor(None, lambda: run_script("""
systemctl enable xrdp 2>/dev/null || true
systemctl enable xrdp-sesman 2>/dev/null || true
systemctl restart xrdp 2>/dev/null || true
/etc/init.d/xrdp restart 2>/dev/null || true
""", timeout=60))

    await msg.edit(embed=make_embed("✅ XRDP Installed!", f"Installation complete on `{HOST_OS}`! Starting tunnel...", 100, color=0x2ecc71))
    await asyncio.sleep(1)
    return True, ""

# ── VM name autocomplete ─────────────────────────────────────────────────────
async def vm_name_autocomplete(interaction: discord.Interaction, current: str):
    vms = get_vm_list()
    return [app_commands.Choice(name=vm, value=vm) for vm in vms if current.lower() in vm.lower()][:25]

@client.event
async def on_ready():
    await tree.sync()
    print(f"✅ Bot online as {client.user}")
    print(f"✅ Detected host OS: {HOST_OS}")
    print(f"✅ Slash commands synced!")

@client.event
async def on_message(message):
    if message.author == client.user: return
    if not auth_check(message):
        if not is_dm(message):
            if message.content.strip().startswith("!"):
                embed = discord.Embed(title="🚫 Unauthorised", description="You are not allowed to use this bot.", color=0xe74c3c)
                reply = await message.reply(embed=embed)
                asyncio.ensure_future(auto_delete(reply, message))
        return

    cmd = message.content.strip()

    # ─── !ssh ────────────────────────────────────────────────
    if cmd == "!ssh":
        msg = await message.reply("⏳ Setting up SSH session...")
        if is_ssh_active(): run_script(DEL_SSH_SCRIPT)
        stdout, stderr = run_script(SSH_SCRIPT)
        if stdout:
            embed = discord.Embed(title="🔐 SSH Session Ready", description="Paste in Termux!", color=0x2ecc71)
            embed.add_field(name="📡 SSH Command", value=f"```{stdout}```", inline=False)
            embed.add_field(name="💡 Tip", value="Anti-freeze enabled (`ServerAliveInterval=60`)", inline=False)
            embed.set_footer(text="Auto-deletes in 20 seconds • Use !delssh to kill")
            await msg.edit(content=None, embed=embed)
        else:
            embed = discord.Embed(title="❌ SSH Failed", description=f"```{stderr}```", color=0xe74c3c)
            await msg.edit(content=None, embed=embed)
        asyncio.ensure_future(auto_delete(msg, message))

    # ─── !delssh ─────────────────────────────────────────────
    elif cmd == "!delssh":
        if is_ssh_active():
            run_script(DEL_SSH_SCRIPT)
            embed = discord.Embed(title="🔴 SSH Killed", description="tmate session terminated.", color=0xe67e22)
        else:
            embed = discord.Embed(title="ℹ️ No Active Session", color=0x95a5a6)
        embed.set_footer(text="Auto-deletes in 20 seconds")
        reply = await message.reply(embed=embed)
        asyncio.ensure_future(auto_delete(reply, message))

    # ─── !vpsinfo ────────────────────────────────────────────
    elif cmd == "!vpsinfo":
        msg = await message.reply("📊 Fetching VPS info...")
        stdout, _ = run_script(VPS_INFO_SCRIPT)
        info = parse_info(stdout)
        ram_used = safe_int(info.get("RAM_USED",0))
        ram_total = safe_int(info.get("RAM_TOTAL",1)) or 1
        ram_percent = round((ram_used/ram_total)*100)
        ram_bar = ("█"*(ram_percent//10)).ljust(10,"░")
        disk_percent_num = safe_int(info.get("DISK_PERCENT","0").replace("%",""))
        disk_bar = ("█"*(disk_percent_num//10)).ljust(10,"░")
        embed = discord.Embed(title="🖥️ VPS Info", description=f"**{info.get('HOSTNAME','N/A')}**\n🐧 {info.get('OS','N/A')}", color=0x3498db)
        embed.add_field(name="🌐 Public IP", value=f"`{info.get('PUBLIC_IP','N/A')}`", inline=True)
        embed.add_field(name="⏱️ Uptime", value=info.get("UPTIME","N/A"), inline=True)
        embed.add_field(name="🔗 SSH", value="🟢 Active" if is_ssh_active() else "🔴 Inactive", inline=True)
        embed.add_field(name="⚙️ CPU", value=info.get("CPU","N/A"), inline=False)
        embed.add_field(name="🧵 Cores", value=info.get("CPU_CORES","N/A"), inline=True)
        embed.add_field(name="📈 Load", value=info.get("LOAD","N/A"), inline=True)
        embed.add_field(name="🏓 Ping", value=f"{info.get('PING','N/A')} ms", inline=True)
        embed.add_field(name=f"🧠 RAM — {ram_used}MB/{ram_total}MB ({ram_percent}%)", value=f"`{ram_bar}` {ram_percent}%", inline=False)
        embed.add_field(name=f"💾 Disk — {info.get('DISK_USED','N/A')}/{info.get('DISK_TOTAL','N/A')} ({info.get('DISK_PERCENT','N/A')})", value=f"`{disk_bar}` {info.get('DISK_PERCENT','N/A')}", inline=False)
        embed.add_field(name="🐧 Kernel", value=info.get("KERNEL","N/A"), inline=False)
        embed.add_field(name="🖥️ XRDP", value="🟢 Installed" if is_xrdp_installed() else "🔴 Not Installed", inline=True)
        embed.set_footer(text="Auto-deletes in 20 seconds")
        await msg.edit(content=None, embed=embed)
        asyncio.ensure_future(auto_delete(msg, message))

    # ─── !ping ───────────────────────────────────────────────
    elif cmd == "!ping":
        msg = await message.reply("🏓 Pinging...")
        stdout, _ = run_script(PING_SCRIPT)
        info = parse_info(stdout)
        bot_latency = round(client.latency*1000)
        def pe(val):
            try:
                p = float(val)
                return "🟢" if p<20 else "🟡" if p<60 else "🔴"
            except: return "⚪"
        g,c,gh = info.get("GOOGLE","N/A"),info.get("CLOUDFLARE","N/A"),info.get("GITHUB","N/A")
        embed = discord.Embed(title="🏓 Ping Results", color=0x1abc9c)
        embed.add_field(name="🤖 Bot Latency", value=f"`{bot_latency}ms`", inline=False)
        embed.add_field(name=f"{pe(g)} Google", value=f"`{g} ms`", inline=True)
        embed.add_field(name=f"{pe(c)} Cloudflare", value=f"`{c} ms`", inline=True)
        embed.add_field(name=f"{pe(gh)} GitHub", value=f"`{gh} ms`", inline=True)
        embed.set_footer(text="🟢<20ms 🟡<60ms 🔴60ms+ • Auto-deletes in 20 seconds")
        await msg.edit(content=None, embed=embed)
        asyncio.ensure_future(auto_delete(msg, message))

    # ─── !uptime ─────────────────────────────────────────────
    elif cmd == "!uptime":
        stdout, _ = run_script('echo "UPTIME=$(uptime -p)" && echo "LOAD=$(uptime | awk -F\'load average:\' \'{print $2}\' | xargs)"')
        info = parse_info(stdout)
        embed = discord.Embed(title="⏱️ VPS Uptime", color=0xf39c12)
        embed.add_field(name="🕐 Uptime", value=info.get("UPTIME","N/A"), inline=False)
        embed.add_field(name="📈 Load", value=info.get("LOAD","N/A"), inline=False)
        embed.set_footer(text="Auto-deletes in 20 seconds")
        reply = await message.reply(embed=embed)
        asyncio.ensure_future(auto_delete(reply, message))

    # ─── !ram ────────────────────────────────────────────────
    elif cmd == "!ram":
        stdout, _ = run_script("free -m")
        embed = discord.Embed(title="🧠 RAM Usage", color=0x9b59b6)
        embed.add_field(name="📊 Output", value=f"```{stdout}```", inline=False)
        embed.set_footer(text="Auto-deletes in 20 seconds")
        reply = await message.reply(embed=embed)
        asyncio.ensure_future(auto_delete(reply, message))

    # ─── !disk ───────────────────────────────────────────────
    elif cmd == "!disk":
        stdout, _ = run_script("df -h")
        embed = discord.Embed(title="💾 Disk Usage", color=0xe67e22)
        embed.add_field(name="📊 Output", value=f"```{stdout}```", inline=False)
        embed.set_footer(text="Auto-deletes in 20 seconds")
        reply = await message.reply(embed=embed)
        asyncio.ensure_future(auto_delete(reply, message))

    # ─── !datacenter ─────────────────────────────────────────
    elif cmd == "!datacenter":
        msg = await message.reply("🌍 Fetching location...")
        stdout, _ = run_script(DATACENTER_SCRIPT, timeout=30)
        info = parse_info(stdout)
        country_flags = {"US":"🇺🇸","GB":"🇬🇧","DE":"🇩🇪","FR":"🇫🇷","JP":"🇯🇵","SG":"🇸🇬","IN":"🇮🇳","AU":"🇦🇺","NL":"🇳🇱","CA":"🇨🇦","TW":"🇹🇼","HK":"🇭🇰","ID":"🇮🇩","MY":"🇲🇾","PH":"🇵🇭","TH":"🇹🇭","VN":"🇻🇳","RU":"🇷🇺","TR":"🇹🇷","PL":"🇵🇱","SE":"🇸🇪"}
        country = info.get("COUNTRY","N/A")
        flag = country_flags.get(country,"🌐")
        embed = discord.Embed(title=f"{flag} Datacenter Location", color=0x2ecc71)
        embed.add_field(name="🌐 IP", value=f"`{info.get('IP','N/A')}`", inline=False)
        embed.add_field(name="🏙️ City", value=info.get("CITY","N/A"), inline=True)
        embed.add_field(name="📍 Region", value=info.get("REGION","N/A"), inline=True)
        embed.add_field(name=f"{flag} Country", value=country, inline=True)
        embed.add_field(name="🏢 ISP", value=info.get("ORG","N/A"), inline=False)
        embed.add_field(name="🕐 Timezone", value=info.get("TIMEZONE","N/A"), inline=True)
        embed.add_field(name="📌 Coordinates", value=info.get("LOC","N/A"), inline=True)
        embed.set_footer(text="Auto-deletes in 20 seconds")
        await msg.edit(content=None, embed=embed)
        asyncio.ensure_future(auto_delete(msg, message))

    # ─── !vmlist ─────────────────────────────────────────────
    elif cmd == "!vmlist":
        vms = get_vm_list()
        if not vms:
            embed = discord.Embed(title="🖥️ Virtual Machines", description="No VMs found. Use `!vmcreate` to create one.", color=0x95a5a6)
        else:
            embed = discord.Embed(title="🖥️ Virtual Machines", color=0x3498db)
            for i, vm in enumerate(vms,1):
                cfg = load_vm_config(vm)
                running = is_vm_running(vm)
                status = "🟢 Running" if running else "🔴 Stopped"
                os_type = cfg.get("OS_TYPE","N/A") if cfg else "N/A"
                memory = cfg.get("MEMORY","N/A") if cfg else "N/A"
                cpus = cfg.get("CPUS","N/A") if cfg else "N/A"
                ssh_port = cfg.get("SSH_PORT","N/A") if cfg else "N/A"
                disk = cfg.get("DISK_SIZE","N/A") if cfg else "N/A"
                embed.add_field(name=f"{i}. {vm} — {status}", value=f"OS: `{os_type}` | RAM: `{memory}MB` | CPUs: `{cpus}` | Disk: `{disk}` | Port: `{ssh_port}`", inline=False)
            embed.set_footer(text="Auto-deletes in 20 seconds")
        reply = await message.reply(embed=embed)
        asyncio.ensure_future(auto_delete(reply, message))

    # ─── !vminfo ─────────────────────────────────────────────
    elif cmd.startswith("!vminfo"):
        parts = cmd.split()
        if len(parts) < 2:
            embed = discord.Embed(title="❌ Missing VM Name", description="**Usage:** `!vminfo <vmname>`", color=0xe74c3c)
            reply = await message.reply(embed=embed)
            asyncio.ensure_future(auto_delete(reply, message))
            return
        vm_name = parts[1]
        if not os.path.exists(os.path.join(VM_DIR, f"{vm_name}.conf")):
            embed = discord.Embed(title="❌ VM Not Found", description=f"No VM named `{vm_name}`.", color=0xe74c3c)
            reply = await message.reply(embed=embed)
            asyncio.ensure_future(auto_delete(reply, message))
            return
        msg = await message.reply("📊 Fetching VM info...")
        loop = asyncio.get_event_loop()
        embed = await loop.run_in_executor(None, lambda: build_vminfo_embed(vm_name))
        await msg.edit(content=None, embed=embed)
        asyncio.ensure_future(auto_delete(msg, message))

    # ─── !vmcreate ───────────────────────────────────────────
    elif cmd.startswith("!vmcreate"):
        parts = cmd.split()
        valid_os = ", ".join(OS_OPTIONS.keys())
        example = "📋 **Example:**\n`!vmcreate myvm ubuntu22 20G 2048 2 3000 mypassword`\n\n**Format:** `!vmcreate <name> <os> <disk> <ram_mb> <cpus> <ssh_port> <password>`"
        os_list = f"**Available OS:**\n`{valid_os}`"
        if len(parts) < 7:
            embed = discord.Embed(title="❌ Invalid Format", description=f"{example}\n\n{os_list}", color=0xe74c3c)
            reply = await message.reply(embed=embed)
            asyncio.ensure_future(auto_delete(reply, message))
            return
        _, vm_name, os_key, disk_size, memory, cpus, ssh_port = parts[0],parts[1],parts[2],parts[3],parts[4],parts[5],parts[6]
        password = parts[7] if len(parts) >= 8 else ""
        FORBIDDEN_PORTS = list(range(2222,2231)) + [22,80,443,3389,3306,5432,6379,8080,8443,27017,5900,21,23,25,53,110,143]
        errors = []
        if not re.match(r'^[a-zA-Z0-9_-]+$', vm_name): errors.append("VM name: letters, numbers, hyphens only")
        if os_key not in OS_OPTIONS: errors.append(f"Invalid OS. Choose from: `{valid_os}`")
        if not re.match(r'^\d+[GgMm]$', disk_size): errors.append("Disk size like `20G`")
        if not memory.isdigit(): errors.append("RAM must be number like `2048`")
        if not cpus.isdigit(): errors.append("CPUs must be number like `2`")
        if not ssh_port.isdigit() or not (1024 <= int(ssh_port) <= 65535): errors.append("Port must be 1024-65535")
        elif int(ssh_port) in FORBIDDEN_PORTS: errors.append(f"Port `{ssh_port}` is reserved. Try `3000`, `4000`, `5000`")
        elif ssh_port.isdigit():
            pc = subprocess.run(["bash","-c",f"ss -tlnp 2>/dev/null | grep ':{ssh_port} '"], capture_output=True, text=True)
            if pc.stdout.strip(): errors.append(f"Port `{ssh_port}` already in use")
        if os.path.exists(os.path.join(VM_DIR, f"{vm_name}.conf")): errors.append(f"VM `{vm_name}` already exists")
        if errors:
            embed = discord.Embed(title="❌ Invalid Input", description="\n".join(f"• {e}" for e in errors) + f"\n\n{example}\n\n{os_list}", color=0xe74c3c)
            reply = await message.reply(embed=embed)
            asyncio.ensure_future(auto_delete(reply, message))
            return
        msg = await message.reply(embed=discord.Embed(title="⏳ Creating VM...", description=f"Setting up **{vm_name}** with `{os_key}`\nDownloading OS image...", color=0x3498db))
        loop = asyncio.get_event_loop()
        ok, err = await loop.run_in_executor(None, lambda: create_vm_files(vm_name, os_key, disk_size, memory, cpus, ssh_port, password))
        if ok:
            cfg = load_vm_config(vm_name)
            username = cfg.get("USERNAME","N/A") if cfg else "N/A"
            final_pass = cfg.get("PASSWORD",password) if cfg else password
            embed = discord.Embed(title="✅ VM Created!", description=f"**{vm_name}** is ready!", color=0x2ecc71)
            embed.add_field(name="🖥️ OS", value=os_key, inline=True)
            embed.add_field(name="💾 Disk", value=disk_size, inline=True)
            embed.add_field(name="🧠 RAM", value=f"{memory}MB", inline=True)
            embed.add_field(name="🧵 CPUs", value=cpus, inline=True)
            embed.add_field(name="🔌 Port", value=ssh_port, inline=True)
            embed.add_field(name="👤 Username", value=username, inline=True)
            embed.add_field(name="🔑 Password", value=f"`{final_pass}`", inline=True)
            embed.add_field(name="▶️ Start", value=f"`!vmstart {vm_name}`", inline=False)
        else:
            embed = discord.Embed(title="❌ VM Creation Failed", description=f"```{err[:1000]}```", color=0xe74c3c)
        embed.set_footer(text="Auto-deletes in 20 seconds")
        await msg.edit(content=None, embed=embed)
        asyncio.ensure_future(auto_delete(msg, message))

    # ─── !vmstart ────────────────────────────────────────────
    elif cmd.startswith("!vmstart"):
        parts = cmd.split()
        if len(parts) < 2:
            embed = discord.Embed(title="❌ Missing VM Name", description="**Usage:** `!vmstart <vmname>`", color=0xe74c3c)
            reply = await message.reply(embed=embed)
            asyncio.ensure_future(auto_delete(reply, message))
            return
        vm_name = parts[1]
        if not os.path.exists(os.path.join(VM_DIR, f"{vm_name}.conf")):
            embed = discord.Embed(title="❌ VM Not Found", description=f"No VM named `{vm_name}`.", color=0xe74c3c)
            reply = await message.reply(embed=embed)
            asyncio.ensure_future(auto_delete(reply, message))
            return
        if is_vm_running(vm_name):
            embed = discord.Embed(title="ℹ️ Already Running", description=f"`{vm_name}` is already running.\nUse `!vmssh {vm_name}` to connect.", color=0x95a5a6)
            reply = await message.reply(embed=embed)
            asyncio.ensure_future(auto_delete(reply, message))
            return
        msg = await message.reply(embed=discord.Embed(title="▶️ Starting VM...", description=f"Booting **{vm_name}**...", color=0x3498db))
        loop = asyncio.get_event_loop()
        ok, err = await loop.run_in_executor(None, lambda: start_vm_background(vm_name))
        if ok:
            cfg = load_vm_config(vm_name)
            ssh_port = cfg.get("SSH_PORT","N/A") if cfg else "N/A"
            username = cfg.get("USERNAME","N/A") if cfg else "N/A"
            password = cfg.get("PASSWORD","") if cfg else ""
            embed = discord.Embed(title="✅ VM Started!", description=f"**{vm_name}** is booting...\nYou'll get a **🟢 Ready** notification when SSH is available.", color=0x3498db)
            embed.add_field(name="🔌 SSH Port", value=ssh_port, inline=True)
            embed.add_field(name="👤 Username", value=username, inline=True)
            embed.set_footer(text="Auto-deletes in 20 seconds")
            await msg.edit(content=None, embed=embed)
            asyncio.ensure_future(auto_delete(msg, message))

            async def wait_and_notify():
                port = ssh_port
                uname = username
                pw = password
                for _ in range(60):
                    await asyncio.sleep(5)
                    check = subprocess.run(
                        ["bash","-c",f"sshpass -p '{pw}' ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 -o BatchMode=no -p {port} {uname}@localhost echo connected 2>/dev/null"],
                        capture_output=True, text=True
                    )
                    if "connected" in check.stdout:
                        ready_embed = discord.Embed(title="🟢 VM is Ready!", description=f"**{vm_name}** has fully booted! SSH is accepting connections.", color=0x2ecc71)
                        ready_embed.add_field(name="🔑 Connect now", value=f"`!vmssh {vm_name}`", inline=False)
                        ready_embed.set_footer(text="Auto-deletes in 30 seconds")
                        try:
                            notify_msg = await message.channel.send(embed=ready_embed)
                            await asyncio.sleep(30)
                            try: await notify_msg.delete()
                            except: pass
                        except: pass
                        return
                try:
                    timeout_embed = discord.Embed(title="⚠️ VM Taking Long", description=f"**{vm_name}** is taking longer than expected.\nTry `!vmssh {vm_name}` manually in a few minutes.", color=0xfee75c)
                    timeout_msg = await message.channel.send(embed=timeout_embed)
                    await asyncio.sleep(20)
                    try: await timeout_msg.delete()
                    except: pass
                except: pass

            asyncio.ensure_future(wait_and_notify())
        else:
            embed = discord.Embed(title="❌ Failed to Start VM", description=f"```{err}```", color=0xe74c3c)
            embed.set_footer(text="Auto-deletes in 20 seconds")
            await msg.edit(content=None, embed=embed)
            asyncio.ensure_future(auto_delete(msg, message))

    # ─── !vmstop ─────────────────────────────────────────────
    elif cmd.startswith("!vmstop"):
        parts = cmd.split()
        if len(parts) < 2:
            embed = discord.Embed(title="❌ Missing VM Name", description="**Usage:** `!vmstop <vmname>`", color=0xe74c3c)
            reply = await message.reply(embed=embed)
            asyncio.ensure_future(auto_delete(reply, message))
            return
        vm_name = parts[1]
        if not is_vm_running(vm_name):
            embed = discord.Embed(title="ℹ️ Not Running", description=f"`{vm_name}` is not running.", color=0x95a5a6)
            reply = await message.reply(embed=embed)
            asyncio.ensure_future(auto_delete(reply, message))
            return
        stop_vm_proc(vm_name)
        embed = discord.Embed(title="⏹️ VM Stopped", description=f"**{vm_name}** stopped.", color=0xe67e22)
        embed.set_footer(text="Auto-deletes in 20 seconds")
        reply = await message.reply(embed=embed)
        asyncio.ensure_future(auto_delete(reply, message))

    # ─── !vmssh ──────────────────────────────────────────────
    elif cmd.startswith("!vmssh"):
        parts = cmd.split()
        if len(parts) < 2:
            embed = discord.Embed(title="❌ Missing VM Name", description="**Usage:** `!vmssh <vmname>`", color=0xe74c3c)
            reply = await message.reply(embed=embed)
            asyncio.ensure_future(auto_delete(reply, message))
            return
        vm_name = parts[1]
        if not os.path.exists(os.path.join(VM_DIR, f"{vm_name}.conf")):
            embed = discord.Embed(title="❌ VM Not Found", description=f"No VM named `{vm_name}`.", color=0xe74c3c)
            reply = await message.reply(embed=embed)
            asyncio.ensure_future(auto_delete(reply, message))
            return
        if not is_vm_running(vm_name):
            embed = discord.Embed(title="❌ VM Not Running", description=f"Use `!vmstart {vm_name}` first.", color=0xe74c3c)
            reply = await message.reply(embed=embed)
            asyncio.ensure_future(auto_delete(reply, message))
            return
        msg = await message.reply(embed=discord.Embed(title="⏳ Getting SSH Link...", description=f"Connecting to **{vm_name}**...", color=0x3498db))
        loop = asyncio.get_event_loop()
        link = await loop.run_in_executor(None, lambda: wait_for_vm_ssh(vm_name))
        if link:
            embed = discord.Embed(title="🔐 VM SSH Ready", description=f"SSH link for **{vm_name}** — paste in Termux!", color=0x2ecc71)
            embed.add_field(name="📡 SSH Command", value=f"```{link}```", inline=False)
            embed.add_field(name="💡 Tip", value="Anti-freeze enabled (`ServerAliveInterval=60`)", inline=False)
        else:
            cfg2 = load_vm_config(vm_name)
            port2 = cfg2.get("SSH_PORT","?") if cfg2 else "?"
            user2 = cfg2.get("USERNAME","?") if cfg2 else "?"
            sp = subprocess.run(["bash","-c","command -v sshpass"], capture_output=True)
            sshpass_ok = "✅ Installed" if sp.returncode==0 else "❌ Not installed"
            embed = discord.Embed(title="❌ SSH Failed", description=f"Could not connect to **{vm_name}**.", color=0xe74c3c)
            embed.add_field(name="🔍 Debug", value=f"Port: `{port2}` | User: `{user2}` | sshpass: {sshpass_ok}", inline=False)
            embed.add_field(name="💡 Fixes", value="• VM still booting — wait and retry\n• Run `!vmstart` to confirm running", inline=False)
        embed.set_footer(text="Auto-deletes in 20 seconds")
        await msg.edit(content=None, embed=embed)
        asyncio.ensure_future(auto_delete(msg, message))

    # ─── !vmdelete ───────────────────────────────────────────
    elif cmd.startswith("!vmdelete"):
        parts = cmd.split()
        if len(parts) < 2:
            embed = discord.Embed(title="❌ Missing VM Name", description="**Usage:** `!vmdelete <vmname>`", color=0xe74c3c)
            reply = await message.reply(embed=embed)
            asyncio.ensure_future(auto_delete(reply, message))
            return
        vm_name = parts[1]
        user_id = message.author.id
        if not os.path.exists(os.path.join(VM_DIR, f"{vm_name}.conf")):
            embed = discord.Embed(title="❌ VM Not Found", color=0xe74c3c)
            reply = await message.reply(embed=embed)
            asyncio.ensure_future(auto_delete(reply, message))
            return
        state = pending_deletes.get(user_id, {})
        if state.get("vm_name") != vm_name:
            pending_deletes[user_id] = {"vm_name": vm_name, "step": 1}
            embed = discord.Embed(title="⚠️ Confirm Delete — Step 1/2", description=f"Delete **{vm_name}**? This is **permanent**.\n\nType `!vmdelete {vm_name}` again to confirm.", color=0xfee75c)
            embed.set_footer(text="Expires in 30 seconds")
            reply = await message.reply(embed=embed)
            asyncio.ensure_future(auto_delete(reply, message, delay=30))
            async def cancel1(uid, vname):
                await asyncio.sleep(30)
                if pending_deletes.get(uid,{}).get("vm_name") == vname: pending_deletes.pop(uid,None)
            asyncio.ensure_future(cancel1(user_id, vm_name))
        elif state.get("step") == 1:
            pending_deletes[user_id] = {"vm_name": vm_name, "step": 2}
            embed = discord.Embed(title="🚨 Final Warning — Step 2/2", description=f"**LAST CHANCE.** Deleting **{vm_name}** is irreversible.\n\nType `!vmdelete {vm_name}` ONE MORE TIME.", color=0xe74c3c)
            embed.set_footer(text="Expires in 30 seconds")
            reply = await message.reply(embed=embed)
            asyncio.ensure_future(auto_delete(reply, message, delay=30))
            async def cancel2(uid, vname):
                await asyncio.sleep(30)
                if pending_deletes.get(uid,{}).get("vm_name") == vname: pending_deletes.pop(uid,None)
            asyncio.ensure_future(cancel2(user_id, vm_name))
        elif state.get("step") == 2:
            pending_deletes.pop(user_id, None)
            msg = await message.reply(embed=discord.Embed(title="🗑️ Deleting VM...", color=0xe67e22))
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: delete_vm_files(vm_name))
            embed = discord.Embed(title="✅ VM Deleted", description=f"**{vm_name}** permanently deleted.", color=0x2ecc71)
            embed.set_footer(text="Auto-deletes in 20 seconds")
            await msg.edit(content=None, embed=embed)
            asyncio.ensure_future(auto_delete(msg, message))

    # ─── !xrdp ───────────────────────────────────────────────
    elif cmd == "!xrdp":
        if not is_xrdp_installed():
            msg = await message.reply(embed=discord.Embed(title="⏳ Installing XRDP", description=f"Starting installation on `{HOST_OS}`...", color=0x3498db))
            success, err = await install_xrdp_with_progress(msg)
            if not success:
                embed = discord.Embed(title="❌ XRDP Install Failed", description=f"```{err[:1000]}```", color=0xe74c3c)
                await msg.edit(embed=embed)
                asyncio.ensure_future(auto_delete(msg, message))
                return
        else:
            msg = await message.reply(embed=discord.Embed(title="✅ XRDP Already Installed", description="Starting Pinggy tunnel...", color=0x2ecc71))
        if is_pinggy_running(): kill_pinggy(); await asyncio.sleep(2)
        await msg.edit(embed=discord.Embed(title="🔗 Starting Tunnel...", color=0x3498db))
        loop = asyncio.get_event_loop()
        url = await loop.run_in_executor(None, start_pinggy_and_get_url)
        if url:
            embed = discord.Embed(title="🖥️ Remote Desktop Ready", description="Open **RD Client** and connect!", color=0x2ecc71)
            embed.add_field(name="🔗 RD Client Address", value=f"```{url}```", inline=False)
            embed.add_field(name="👤 Username", value="`root` (or your VPS user)", inline=True)
            embed.add_field(name="🔑 Password", value="Your VPS root password", inline=True)
            embed.add_field(name="💡 Tip", value="No `tcp://` prefix needed", inline=False)
            embed.set_footer(text="Auto-deletes in 20 seconds • !startxrdp to restart • !delxrdp to remove")
        else:
            embed = discord.Embed(title="⚠️ URL Not Captured", description="Check `/tmp/pinggy.log`", color=0xfee75c)
            embed.add_field(name="Manual check", value="```cat /tmp/pinggy.log```", inline=False)
            embed.set_footer(text="Auto-deletes in 20 seconds")
        await msg.edit(content=None, embed=embed)
        asyncio.ensure_future(auto_delete(msg, message))

    # ─── !startxrdp ──────────────────────────────────────────
    elif cmd == "!startxrdp":
        if not is_xrdp_installed():
            embed = discord.Embed(title="❌ XRDP Not Installed", description="Run `!xrdp` first.", color=0xe74c3c)
            reply = await message.reply(embed=embed)
            asyncio.ensure_future(auto_delete(reply, message))
            return
        msg = await message.reply(embed=discord.Embed(title="🔗 Restarting Tunnel...", color=0x3498db))
        if is_pinggy_running(): kill_pinggy(); await asyncio.sleep(2)
        subprocess.run(["bash","-c","/etc/init.d/xrdp start 2>/dev/null"], capture_output=True)
        loop = asyncio.get_event_loop()
        url = await loop.run_in_executor(None, start_pinggy_and_get_url)
        if url:
            embed = discord.Embed(title="🔗 Tunnel Restarted", color=0x2ecc71)
            embed.add_field(name="🖥️ RD Client Address", value=f"```{url}```", inline=False)
        else:
            embed = discord.Embed(title="⚠️ URL Not Captured", description="Check `/tmp/pinggy.log`", color=0xfee75c)
        embed.set_footer(text="Auto-deletes in 20 seconds")
        await msg.edit(content=None, embed=embed)
        asyncio.ensure_future(auto_delete(msg, message))

    # ─── !stopxrdp ───────────────────────────────────────────
    elif cmd == "!stopxrdp":
        msg = await message.reply(embed=discord.Embed(title="⏹️ Stopping XRDP...", color=0xe67e22))
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: run_script('pkill -f "tcp@a.pinggy.io" 2>/dev/null; systemctl stop xrdp 2>/dev/null', timeout=30))
        embed = discord.Embed(title="⏹️ XRDP Stopped", description="Tunnel killed and XRDP stopped.\nRun `!xrdp` to start again.", color=0xe67e22)
        embed.set_footer(text="Auto-deletes in 20 seconds")
        await msg.edit(content=None, embed=embed)
        asyncio.ensure_future(auto_delete(msg, message))

    # ─── !xrdpfix ────────────────────────────────────────────
    elif cmd == "!xrdpfix":
        msg = await message.reply(embed=discord.Embed(title="🔧 Fixing XRDP...", color=0x3498db))
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: run_script('echo "xfce4-session" > ~/.xsession; chmod +x ~/.xsession; systemctl restart xrdp 2>/dev/null; /etc/init.d/xrdp restart 2>/dev/null', timeout=30))
        embed = discord.Embed(title="✅ XRDP Fixed", description="Run `!startxrdp` for fresh URL.", color=0x2ecc71)
        embed.set_footer(text="Auto-deletes in 20 seconds")
        await msg.edit(content=None, embed=embed)
        asyncio.ensure_future(auto_delete(msg, message))

    # ─── !delxrdp ────────────────────────────────────────────
    elif cmd == "!delxrdp":
        if not is_xrdp_installed() and not is_pinggy_running():
            embed = discord.Embed(title="ℹ️ Nothing to Remove", color=0x95a5a6)
            reply = await message.reply(embed=embed)
            asyncio.ensure_future(auto_delete(reply, message))
            return
        msg = await message.reply(embed=discord.Embed(title="🗑️ Removing XRDP...", color=0xe67e22))
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: run_script(DEL_XRDP_SCRIPT, timeout=120))
        embed = discord.Embed(title="🔴 XRDP Removed", description="XRDP, XFCE, Firefox and tunnel removed.", color=0xe67e22)
        embed.set_footer(text="Auto-deletes in 20 seconds")
        await msg.edit(content=None, embed=embed)
        asyncio.ensure_future(auto_delete(msg, message))

    # ─── !help ───────────────────────────────────────────────
    elif cmd == "!help":
        embed = discord.Embed(title="🤖 Bot Commands", description=f"Owner only 🔒 • DMs never deleted • Host OS: `{HOST_OS}`", color=0x9b59b6)
        embed.add_field(name="🔐 `!ssh`", value="Fresh SSH link", inline=False)
        embed.add_field(name="🔴 `!delssh`", value="Kill SSH session", inline=False)
        embed.add_field(name="🖥️ `!vpsinfo`", value="Full VPS stats", inline=False)
        embed.add_field(name="🏓 `!ping`", value="Ping servers + bot latency", inline=False)
        embed.add_field(name="⏱️ `!uptime`", value="VPS uptime", inline=False)
        embed.add_field(name="🧠 `!ram`", value="RAM usage", inline=False)
        embed.add_field(name="💾 `!disk`", value="Disk usage", inline=False)
        embed.add_field(name="🌍 `!datacenter`", value="Datacenter location", inline=False)
        embed.add_field(name="━━━━━━━━ VM Commands ━━━━━━━━", value="\u200b", inline=False)
        embed.add_field(name="📋 `!vmlist`", value="List all VMs", inline=False)
        embed.add_field(name="ℹ️ `!vminfo <name>`", value="Full VM details", inline=False)
        embed.add_field(name="➕ `!vmcreate <name> <os> <disk> <ram> <cpus> <port> [pass]`", value="Create VM\nOS: `ubuntu22, ubuntu24, debian11, debian12, fedora40, centos9, almalinux9, rocky9`", inline=False)
        embed.add_field(name="▶️ `!vmstart <name>`", value="Start VM (notifies when ready)", inline=False)
        embed.add_field(name="⏹️ `!vmstop <name>`", value="Stop VM", inline=False)
        embed.add_field(name="🔑 `!vmssh <name>`", value="Get SSH link for VM", inline=False)
        embed.add_field(name="🗑️ `!vmdelete <name>`", value="Delete VM (double confirm)", inline=False)
        embed.add_field(name="━━━━━━━━ XRDP Commands ━━━━━━━━", value="\u200b", inline=False)
        embed.add_field(name="🖥️ `!xrdp`", value="Install XRDP + tunnel (auto-detects OS)", inline=False)
        embed.add_field(name="🔗 `!startxrdp`", value="Restart tunnel only", inline=False)
        embed.add_field(name="⏹️ `!stopxrdp`", value="Stop XRDP + tunnel", inline=False)
        embed.add_field(name="🔧 `!xrdpfix`", value="Fix XRDP session", inline=False)
        embed.add_field(name="🗑️ `!delxrdp`", value="Remove XRDP completely", inline=False)
        embed.set_footer(text="Auto-deletes in 20 seconds • Also available as / commands")
        reply = await message.reply(embed=embed)
        asyncio.ensure_future(auto_delete(reply, message))


# ── Slash Commands ───────────────────────────────────────────────────────────
def slash_auth(interaction): return interaction.user.id == YOUR_USER_ID
async def slash_unauth(interaction):
    await interaction.response.send_message(embed=discord.Embed(title="🚫 Unauthorised", color=0xe74c3c), ephemeral=True)

@tree.command(name="ssh", description="Generate a fresh SSH session link")
async def slash_ssh(interaction: discord.Interaction):
    if not slash_auth(interaction): await slash_unauth(interaction); return
    await interaction.response.defer(ephemeral=True)
    if is_ssh_active(): run_script(DEL_SSH_SCRIPT)
    stdout, stderr = run_script(SSH_SCRIPT)
    if stdout:
        embed = discord.Embed(title="🔐 SSH Session Ready", color=0x2ecc71)
        embed.add_field(name="📡 SSH Command", value=f"```{stdout}```", inline=False)
        embed.set_footer(text="Only visible to you")
    else:
        embed = discord.Embed(title="❌ SSH Failed", description=f"```{stderr}```", color=0xe74c3c)
    await interaction.followup.send(embed=embed, ephemeral=True)

@tree.command(name="delssh", description="Kill the active SSH session")
async def slash_delssh(interaction: discord.Interaction):
    if not slash_auth(interaction): await slash_unauth(interaction); return
    await interaction.response.defer(ephemeral=True)
    if is_ssh_active():
        run_script(DEL_SSH_SCRIPT)
        embed = discord.Embed(title="🔴 SSH Killed", color=0xe67e22)
    else:
        embed = discord.Embed(title="ℹ️ No Active Session", color=0x95a5a6)
    await interaction.followup.send(embed=embed, ephemeral=True)

@tree.command(name="vpsinfo", description="Show full VPS stats")
async def slash_vpsinfo(interaction: discord.Interaction):
    if not slash_auth(interaction): await slash_unauth(interaction); return
    await interaction.response.defer(ephemeral=True)
    stdout, _ = run_script(VPS_INFO_SCRIPT)
    info = parse_info(stdout)
    ram_used = safe_int(info.get("RAM_USED",0))
    ram_total = safe_int(info.get("RAM_TOTAL",1)) or 1
    ram_percent = round((ram_used/ram_total)*100)
    ram_bar = ("█"*(ram_percent//10)).ljust(10,"░")
    disk_percent_num = safe_int(info.get("DISK_PERCENT","0").replace("%",""))
    disk_bar = ("█"*(disk_percent_num//10)).ljust(10,"░")
    embed = discord.Embed(title="🖥️ VPS Info", description=f"**{info.get('HOSTNAME','N/A')}**\n🐧 {info.get('OS','N/A')}", color=0x3498db)
    embed.add_field(name="🌐 IP", value=f"`{info.get('PUBLIC_IP','N/A')}`", inline=True)
    embed.add_field(name="⏱️ Uptime", value=info.get("UPTIME","N/A"), inline=True)
    embed.add_field(name="🔗 SSH", value="🟢 Active" if is_ssh_active() else "🔴 Inactive", inline=True)
    embed.add_field(name="⚙️ CPU", value=info.get("CPU","N/A"), inline=False)
    embed.add_field(name="🧵 Cores", value=info.get("CPU_CORES","N/A"), inline=True)
    embed.add_field(name="📈 Load", value=info.get("LOAD","N/A"), inline=True)
    embed.add_field(name="🏓 Ping", value=f"{info.get('PING','N/A')} ms", inline=True)
    embed.add_field(name=f"🧠 RAM {ram_percent}%", value=f"`{ram_bar}`", inline=False)
    embed.add_field(name=f"💾 Disk {info.get('DISK_PERCENT','N/A')}", value=f"`{disk_bar}`", inline=False)
    embed.add_field(name="🖥️ XRDP", value="🟢 Installed" if is_xrdp_installed() else "🔴 Not Installed", inline=True)
    await interaction.followup.send(embed=embed, ephemeral=True)

@tree.command(name="ping", description="Ping servers + bot latency")
async def slash_ping(interaction: discord.Interaction):
    if not slash_auth(interaction): await slash_unauth(interaction); return
    await interaction.response.defer(ephemeral=True)
    stdout, _ = run_script(PING_SCRIPT)
    info = parse_info(stdout)
    bot_latency = round(client.latency*1000)
    def pe(val):
        try:
            p=float(val); return "🟢" if p<20 else "🟡" if p<60 else "🔴"
        except: return "⚪"
    g,c,gh = info.get("GOOGLE","N/A"),info.get("CLOUDFLARE","N/A"),info.get("GITHUB","N/A")
    embed = discord.Embed(title="🏓 Ping Results", color=0x1abc9c)
    embed.add_field(name="🤖 Bot", value=f"`{bot_latency}ms`", inline=True)
    embed.add_field(name=f"{pe(g)} Google", value=f"`{g} ms`", inline=True)
    embed.add_field(name=f"{pe(c)} Cloudflare", value=f"`{c} ms`", inline=True)
    embed.add_field(name=f"{pe(gh)} GitHub", value=f"`{gh} ms`", inline=True)
    await interaction.followup.send(embed=embed, ephemeral=True)

@tree.command(name="uptime", description="VPS uptime and load")
async def slash_uptime(interaction: discord.Interaction):
    if not slash_auth(interaction): await slash_unauth(interaction); return
    await interaction.response.defer(ephemeral=True)
    stdout, _ = run_script('echo "UPTIME=$(uptime -p)" && echo "LOAD=$(uptime | awk -F\'load average:\' \'{print $2}\' | xargs)"')
    info = parse_info(stdout)
    embed = discord.Embed(title="⏱️ VPS Uptime", color=0xf39c12)
    embed.add_field(name="🕐 Uptime", value=info.get("UPTIME","N/A"), inline=False)
    embed.add_field(name="📈 Load", value=info.get("LOAD","N/A"), inline=False)
    await interaction.followup.send(embed=embed, ephemeral=True)

@tree.command(name="ram", description="Quick RAM usage")
async def slash_ram(interaction: discord.Interaction):
    if not slash_auth(interaction): await slash_unauth(interaction); return
    await interaction.response.defer(ephemeral=True)
    stdout, _ = run_script("free -m")
    embed = discord.Embed(title="🧠 RAM Usage", color=0x9b59b6)
    embed.add_field(name="📊 Output", value=f"```{stdout}```", inline=False)
    await interaction.followup.send(embed=embed, ephemeral=True)

@tree.command(name="disk", description="Disk usage breakdown")
async def slash_disk(interaction: discord.Interaction):
    if not slash_auth(interaction): await slash_unauth(interaction); return
    await interaction.response.defer(ephemeral=True)
    stdout, _ = run_script("df -h")
    embed = discord.Embed(title="💾 Disk Usage", color=0xe67e22)
    embed.add_field(name="📊 Output", value=f"```{stdout}```", inline=False)
    await interaction.followup.send(embed=embed, ephemeral=True)

@tree.command(name="datacenter", description="Show VPS datacenter location")
async def slash_datacenter(interaction: discord.Interaction):
    if not slash_auth(interaction): await slash_unauth(interaction); return
    await interaction.response.defer(ephemeral=True)
    stdout, _ = run_script(DATACENTER_SCRIPT, timeout=30)
    info = parse_info(stdout)
    country_flags = {"US":"🇺🇸","GB":"🇬🇧","DE":"🇩🇪","FR":"🇫🇷","JP":"🇯🇵","SG":"🇸🇬","IN":"🇮🇳","AU":"🇦🇺","NL":"🇳🇱","CA":"🇨🇦","TW":"🇹🇼","HK":"🇭🇰"}
    country = info.get("COUNTRY","N/A")
    flag = country_flags.get(country,"🌐")
    embed = discord.Embed(title=f"{flag} Datacenter Location", color=0x2ecc71)
    embed.add_field(name="🌐 IP", value=f"`{info.get('IP','N/A')}`", inline=False)
    embed.add_field(name="🏙️ City", value=info.get("CITY","N/A"), inline=True)
    embed.add_field(name="📍 Region", value=info.get("REGION","N/A"), inline=True)
    embed.add_field(name=f"{flag} Country", value=country, inline=True)
    embed.add_field(name="🏢 ISP", value=info.get("ORG","N/A"), inline=False)
    embed.add_field(name="🕐 Timezone", value=info.get("TIMEZONE","N/A"), inline=True)
    await interaction.followup.send(embed=embed, ephemeral=True)

@tree.command(name="vmlist", description="List all VMs with status")
async def slash_vmlist(interaction: discord.Interaction):
    if not slash_auth(interaction): await slash_unauth(interaction); return
    await interaction.response.defer(ephemeral=True)
    vms = get_vm_list()
    if not vms:
        embed = discord.Embed(title="🖥️ Virtual Machines", description="No VMs found.", color=0x95a5a6)
    else:
        embed = discord.Embed(title="🖥️ Virtual Machines", color=0x3498db)
        for i, vm in enumerate(vms,1):
            cfg = load_vm_config(vm)
            running = is_vm_running(vm)
            status = "🟢 Running" if running else "🔴 Stopped"
            os_type = cfg.get("OS_TYPE","N/A") if cfg else "N/A"
            memory = cfg.get("MEMORY","N/A") if cfg else "N/A"
            ssh_port = cfg.get("SSH_PORT","N/A") if cfg else "N/A"
            disk = cfg.get("DISK_SIZE","N/A") if cfg else "N/A"
            embed.add_field(name=f"{i}. {vm} — {status}", value=f"OS: `{os_type}` | RAM: `{memory}MB` | Disk: `{disk}` | Port: `{ssh_port}`", inline=False)
    await interaction.followup.send(embed=embed, ephemeral=True)

@tree.command(name="vminfo", description="Show full details of a VM")
@app_commands.describe(name="VM name")
@app_commands.autocomplete(name=vm_name_autocomplete)
async def slash_vminfo(interaction: discord.Interaction, name: str):
    if not slash_auth(interaction): await slash_unauth(interaction); return
    await interaction.response.defer(ephemeral=True)
    if not os_module.path.exists(os_module.path.join(VM_DIR, f"{name}.conf")):
        await interaction.followup.send(embed=discord.Embed(title="❌ VM Not Found", color=0xe74c3c), ephemeral=True); return
    loop = asyncio.get_event_loop()
    embed = await loop.run_in_executor(None, lambda: build_vminfo_embed(name))
    await interaction.followup.send(embed=embed, ephemeral=True)

@tree.command(name="vmcreate", description="Create a new VM")
@app_commands.describe(name="VM name", os="OS to install", disk="Disk size e.g. 20G", ram="RAM in MB e.g. 2048", cpus="CPUs e.g. 2", port="SSH port e.g. 3000", password="VM password (optional)")
@app_commands.choices(os=[
    app_commands.Choice(name="Ubuntu 22.04", value="ubuntu22"),
    app_commands.Choice(name="Ubuntu 24.04", value="ubuntu24"),
    app_commands.Choice(name="Debian 11", value="debian11"),
    app_commands.Choice(name="Debian 12", value="debian12"),
    app_commands.Choice(name="Fedora 40", value="fedora40"),
    app_commands.Choice(name="CentOS 9 Stream", value="centos9"),
    app_commands.Choice(name="AlmaLinux 9", value="almalinux9"),
    app_commands.Choice(name="Rocky Linux 9", value="rocky9"),
])
async def slash_vmcreate(interaction: discord.Interaction, name: str, os: str, disk: str, ram: str, cpus: str, port: str, password: str = ""):
    if not slash_auth(interaction): await slash_unauth(interaction); return
    await interaction.response.defer(ephemeral=True)
    FORBIDDEN_PORTS = list(range(2222,2231)) + [22,80,443,3389,3306,5432,6379,8080,8443,27017,5900,21,23,25,53,110,143]
    errors = []
    if not re.match(r"^[a-zA-Z0-9_-]+$", name): errors.append("VM name: letters, numbers, hyphens only")
    if not re.match(r"^\d+[GgMm]$", disk): errors.append("Disk: like `20G`")
    if not ram.isdigit(): errors.append("RAM: number like `2048`")
    if not cpus.isdigit(): errors.append("CPUs: number like `2`")
    if not port.isdigit() or not (1024 <= int(port) <= 65535): errors.append("Port: 1024-65535")
    elif int(port) in FORBIDDEN_PORTS: errors.append(f"Port `{port}` reserved. Try `3000`, `4000`, `5000`")
    if os_module.path.exists(os_module.path.join(VM_DIR, f"{name}.conf")): errors.append(f"VM `{name}` already exists")
    if errors:
        await interaction.followup.send(embed=discord.Embed(title="❌ Invalid Input", description="\n".join(f"• {e}" for e in errors), color=0xe74c3c), ephemeral=True); return
    await interaction.followup.send(embed=discord.Embed(title="⏳ Creating VM...", description=f"Setting up **{name}** with `{os}`...", color=0x3498db), ephemeral=True)
    loop = asyncio.get_event_loop()
    ok, err = await loop.run_in_executor(None, lambda: create_vm_files(name, os, disk, ram, cpus, port, password))
    if ok:
        cfg = load_vm_config(name)
        embed = discord.Embed(title="✅ VM Created!", description=f"**{name}** is ready!", color=0x2ecc71)
        embed.add_field(name="🖥️ OS", value=os, inline=True)
        embed.add_field(name="💾 Disk", value=disk, inline=True)
        embed.add_field(name="🧠 RAM", value=f"{ram}MB", inline=True)
        embed.add_field(name="🔌 Port", value=port, inline=True)
        embed.add_field(name="👤 User", value=cfg.get("USERNAME","N/A") if cfg else "N/A", inline=True)
        embed.add_field(name="🔑 Password", value=f"`{cfg.get('PASSWORD',password) if cfg else password}`", inline=True)
        embed.add_field(name="▶️ Start", value=f"Use `/vmstart` with name `{name}`", inline=False)
    else:
        embed = discord.Embed(title="❌ VM Creation Failed", description=f"```{err[:1000]}```", color=0xe74c3c)
    await interaction.edit_original_response(embed=embed)

@tree.command(name="vmstart", description="Start a VM")
@app_commands.describe(name="VM name to start")
@app_commands.autocomplete(name=vm_name_autocomplete)
async def slash_vmstart(interaction: discord.Interaction, name: str):
    if not slash_auth(interaction): await slash_unauth(interaction); return
    await interaction.response.defer(ephemeral=True)
    if not os_module.path.exists(os_module.path.join(VM_DIR, f"{name}.conf")):
        await interaction.followup.send(embed=discord.Embed(title="❌ VM Not Found", color=0xe74c3c), ephemeral=True); return
    if is_vm_running(name):
        await interaction.followup.send(embed=discord.Embed(title="ℹ️ Already Running", color=0x95a5a6), ephemeral=True); return
    loop = asyncio.get_event_loop()
    ok, err = await loop.run_in_executor(None, lambda: start_vm_background(name))
    if ok:
        cfg = load_vm_config(name)
        pw = cfg.get("PASSWORD","") if cfg else ""
        uname = cfg.get("USERNAME","ubuntu") if cfg else "ubuntu"
        port = cfg.get("SSH_PORT","2222") if cfg else "2222"
        embed = discord.Embed(title="✅ VM Started!", description=f"**{name}** is booting...\nYou'll get a notification when SSH is ready.", color=0x3498db)
        embed.add_field(name="🔌 Port", value=port, inline=True)

        async def slash_notify():
            for _ in range(60):
                await asyncio.sleep(5)
                check = subprocess.run(
                    ["bash","-c",f"sshpass -p '{pw}' ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 -o BatchMode=no -p {port} {uname}@localhost echo connected 2>/dev/null"],
                    capture_output=True, text=True
                )
                if "connected" in check.stdout:
                    try:
                        ready_embed = discord.Embed(title="🟢 VM is Ready!", description=f"**{name}** fully booted! SSH is available.", color=0x2ecc71)
                        ready_embed.add_field(name="🔑 Connect", value=f"Use `/vmssh` with name `{name}`", inline=False)
                        await interaction.followup.send(embed=ready_embed, ephemeral=True)
                    except: pass
                    return
        asyncio.ensure_future(slash_notify())
    else:
        embed = discord.Embed(title="❌ Failed", description=f"```{err}```", color=0xe74c3c)
    await interaction.followup.send(embed=embed, ephemeral=True)

@tree.command(name="vmstop", description="Stop a running VM")
@app_commands.describe(name="VM name to stop")
@app_commands.autocomplete(name=vm_name_autocomplete)
async def slash_vmstop(interaction: discord.Interaction, name: str):
    if not slash_auth(interaction): await slash_unauth(interaction); return
    await interaction.response.defer(ephemeral=True)
    if not is_vm_running(name):
        await interaction.followup.send(embed=discord.Embed(title="ℹ️ Not Running", color=0x95a5a6), ephemeral=True); return
    stop_vm_proc(name)
    await interaction.followup.send(embed=discord.Embed(title="⏹️ VM Stopped", description=f"**{name}** stopped.", color=0xe67e22), ephemeral=True)

@tree.command(name="vmssh", description="Get SSH link for a VM")
@app_commands.describe(name="VM name")
@app_commands.autocomplete(name=vm_name_autocomplete)
async def slash_vmssh(interaction: discord.Interaction, name: str):
    if not slash_auth(interaction): await slash_unauth(interaction); return
    await interaction.response.defer(ephemeral=True)
    if not os_module.path.exists(os_module.path.join(VM_DIR, f"{name}.conf")):
        await interaction.followup.send(embed=discord.Embed(title="❌ VM Not Found", color=0xe74c3c), ephemeral=True); return
    if not is_vm_running(name):
        await interaction.followup.send(embed=discord.Embed(title="❌ VM Not Running", description="Use `/vmstart` first.", color=0xe74c3c), ephemeral=True); return
    await interaction.edit_original_response(embed=discord.Embed(title="⏳ Getting SSH Link...", color=0x3498db))
    loop = asyncio.get_event_loop()
    link = await loop.run_in_executor(None, lambda: wait_for_vm_ssh(name))
    if link:
        embed = discord.Embed(title="🔐 VM SSH Ready", color=0x2ecc71)
        embed.add_field(name="📡 SSH Command", value=f"```{link}```", inline=False)
        embed.add_field(name="💡 Tip", value="Anti-freeze enabled", inline=False)
    else:
        embed = discord.Embed(title="❌ SSH Failed", description="VM may still be booting. Wait and retry.", color=0xe74c3c)
    await interaction.edit_original_response(embed=embed)

@tree.command(name="vmdelete", description="Delete a VM permanently (double confirmation)")
@app_commands.describe(name="VM name to delete")
@app_commands.autocomplete(name=vm_name_autocomplete)
async def slash_vmdelete(interaction: discord.Interaction, name: str):
    if not slash_auth(interaction): await slash_unauth(interaction); return
    await interaction.response.defer(ephemeral=True)
    if not os_module.path.exists(os_module.path.join(VM_DIR, f"{name}.conf")):
        await interaction.followup.send(embed=discord.Embed(title="❌ VM Not Found", color=0xe74c3c), ephemeral=True); return
    user_id = interaction.user.id
    state = pending_deletes.get(user_id, {})
    if state.get("vm_name") != name:
        pending_deletes[user_id] = {"vm_name": name, "step": 1}
        embed = discord.Embed(title="⚠️ Confirm Delete — Step 1/2", description=f"Delete **{name}**? Run `/vmdelete` again to confirm.", color=0xfee75c)
        await interaction.followup.send(embed=embed, ephemeral=True)
        async def cancel(uid, vname):
            await asyncio.sleep(60)
            if pending_deletes.get(uid,{}).get("vm_name") == vname: pending_deletes.pop(uid,None)
        asyncio.ensure_future(cancel(user_id, name))
    elif state.get("step") == 1:
        pending_deletes[user_id] = {"vm_name": name, "step": 2}
        embed = discord.Embed(title="🚨 Final Warning — Step 2/2", description=f"**LAST CHANCE.** Run `/vmdelete` one more time to permanently delete **{name}**.", color=0xe74c3c)
        await interaction.followup.send(embed=embed, ephemeral=True)
    elif state.get("step") == 2:
        pending_deletes.pop(user_id, None)
        await interaction.followup.send(embed=discord.Embed(title="🗑️ Deleting...", color=0xe67e22), ephemeral=True)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: delete_vm_files(name))
        await interaction.edit_original_response(embed=discord.Embed(title="✅ VM Deleted", description=f"**{name}** permanently deleted.", color=0x2ecc71))

@tree.command(name="xrdp", description="Install XRDP and start Pinggy tunnel")
async def slash_xrdp(interaction: discord.Interaction):
    if not slash_auth(interaction): await slash_unauth(interaction); return
    await interaction.response.send_message(embed=discord.Embed(title=f"⏳ Starting XRDP on `{HOST_OS}`...", color=0x3498db), ephemeral=True)
    if not is_xrdp_installed():
        await interaction.edit_original_response(embed=discord.Embed(title="⏳ Installing XRDP...", description=f"Detected `{HOST_OS}`. Takes 2-5 mins...", color=0x3498db))
        loop = asyncio.get_event_loop()
        ok, _ = await loop.run_in_executor(None, lambda: run_script(get_xrdp_install_script(), timeout=600))
        if "XRDP_INSTALL_DONE" not in ok:
            await interaction.edit_original_response(embed=discord.Embed(title="❌ Install Failed", color=0xe74c3c)); return
    if is_pinggy_running(): kill_pinggy(); await asyncio.sleep(2)
    loop = asyncio.get_event_loop()
    url = await loop.run_in_executor(None, start_pinggy_and_get_url)
    if url:
        embed = discord.Embed(title="🖥️ Remote Desktop Ready", color=0x2ecc71)
        embed.add_field(name="🔗 RD Client Address", value=f"```{url}```", inline=False)
    else:
        embed = discord.Embed(title="⚠️ URL Not Captured", description="Check `/tmp/pinggy.log`", color=0xfee75c)
    await interaction.edit_original_response(embed=embed)

@tree.command(name="startxrdp", description="Restart Pinggy tunnel for XRDP")
async def slash_startxrdp(interaction: discord.Interaction):
    if not slash_auth(interaction): await slash_unauth(interaction); return
    await interaction.response.send_message(embed=discord.Embed(title="🔗 Restarting Tunnel...", color=0x3498db), ephemeral=True)
    if is_pinggy_running(): kill_pinggy(); await asyncio.sleep(2)
    subprocess.run(["bash","-c","/etc/init.d/xrdp start 2>/dev/null"], capture_output=True)
    loop = asyncio.get_event_loop()
    url = await loop.run_in_executor(None, start_pinggy_and_get_url)
    if url:
        embed = discord.Embed(title="🔗 Tunnel Restarted", color=0x2ecc71)
        embed.add_field(name="🖥️ RD Client Address", value=f"```{url}```", inline=False)
    else:
        embed = discord.Embed(title="⚠️ URL Not Captured", description="Check `/tmp/pinggy.log`", color=0xfee75c)
    await interaction.edit_original_response(embed=embed)

@tree.command(name="stopxrdp", description="Stop XRDP and kill Pinggy tunnel")
async def slash_stopxrdp(interaction: discord.Interaction):
    if not slash_auth(interaction): await slash_unauth(interaction); return
    await interaction.response.defer(ephemeral=True)
    run_script('pkill -f "tcp@a.pinggy.io" 2>/dev/null; systemctl stop xrdp 2>/dev/null', timeout=30)
    await interaction.followup.send(embed=discord.Embed(title="⏹️ XRDP Stopped", color=0xe67e22), ephemeral=True)

@tree.command(name="xrdpfix", description="Fix XRDP session file")
async def slash_xrdpfix(interaction: discord.Interaction):
    if not slash_auth(interaction): await slash_unauth(interaction); return
    await interaction.response.defer(ephemeral=True)
    run_script('echo "xfce4-session" > ~/.xsession; chmod +x ~/.xsession; systemctl restart xrdp 2>/dev/null', timeout=30)
    await interaction.followup.send(embed=discord.Embed(title="✅ XRDP Fixed", description="Run `/startxrdp` for fresh URL.", color=0x2ecc71), ephemeral=True)

@tree.command(name="delxrdp", description="Remove XRDP completely")
async def slash_delxrdp(interaction: discord.Interaction):
    if not slash_auth(interaction): await slash_unauth(interaction); return
    await interaction.response.defer(ephemeral=True)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: run_script(DEL_XRDP_SCRIPT, timeout=120))
    await interaction.followup.send(embed=discord.Embed(title="🔴 XRDP Removed", color=0xe67e22), ephemeral=True)

client.run(TOKEN)
