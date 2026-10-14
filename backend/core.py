import os, sys, ctypes, json, time, threading, subprocess, socket, struct, queue, zipfile, shutil, webbrowser, logging, urllib.request
from flask import Flask, jsonify, request, send_from_directory, Response

# --- 1. WBUDOWANE AUTO-UAC WEWNĄTRZ PLIKU .EXE I SKRYPTU ---
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False

if not is_admin():
    if getattr(sys, 'frozen', False):
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, "", None, 1)
    else:
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{os.path.abspath(__file__)}"', None, 1)
    sys.exit(0)

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

if getattr(sys, 'frozen', False):
    BUNDLE_DIR = sys._MEIPASS
    WORK_DIR = os.path.dirname(sys.executable)
else:
    BUNDLE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    WORK_DIR = BUNDLE_DIR

PUBLIC_DIR = os.path.join(BUNDLE_DIR, "public")
BUNDLE_CFG_DIR = os.path.join(BUNDLE_DIR, "config")
CONFIG_DIR = os.path.join(WORK_DIR, "config")
IMAGES_DIR = os.path.join(WORK_DIR, "images")
BACKUPS_DIR = os.path.join(WORK_DIR, "backups")
CONFIG_PATH = os.path.join(CONFIG_DIR, "settings.json")
PROFILES_PATH = os.path.join(CONFIG_DIR, "hardware_profiles.json")
USBIP_EXE = r"C:\Program Files\USBip\usbip.exe"

for d in [CONFIG_DIR, IMAGES_DIR, BACKUPS_DIR]:
    os.makedirs(d, exist_ok=True)

# Jeśli uruchamiamy z czystego .EXE, kopiujemy domyślne pliki konfiguracyjne z wnętrza EXE
for cfg_name in ["settings.json", "hardware_profiles.json"]:
    dst_cfg = os.path.join(CONFIG_DIR, cfg_name)
    src_cfg = os.path.join(BUNDLE_CFG_DIR, cfg_name)
    if not os.path.exists(dst_cfg) and os.path.exists(src_cfg):
        shutil.copy2(src_cfg, dst_cfg)

# --- 2. WBUDOWANY AUTO-INSTALATOR STEROWNIKA USBIP-WIN2 PRZY STARCIE EXE ---
if not os.path.exists(USBIP_EXE):
    print("🔍 [WIKMAZ Auto-Driver] Pobieranie i cicha instalacja podpisanego sterownika usbip-win2...")
    tmp_installer = os.path.join(WORK_DIR, "usbip_setup_temp.exe")
    try:
        req = urllib.request.Request("https://api.github.com/repos/vadimgrn/usbip-win2/releases/latest", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            rel_data = json.loads(resp.read().decode())
            dl_url = next(a["browser_download_url"] for a in rel_data.get("assets", []) if a["name"].endswith("x64.exe"))
        with urllib.request.urlopen(urllib.request.Request(dl_url, headers={"User-Agent": "Mozilla/5.0"})) as r, open(tmp_installer, "wb") as f:
            f.write(r.read())
        subprocess.run([tmp_installer, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], check=False)
        if os.path.exists(tmp_installer):
            os.remove(tmp_installer)
    except Exception as e:
        print(f"⚠️ Informacja instalatora: {e}")

app = Flask(__name__, static_folder=PUBLIC_DIR)
event_queue = queue.Queue(maxsize=250)

shadow_stores = {"1": {}, "2": {}, "3": {}, "4": {}}
ram_stores = {"1": None, "2": None, "3": None, "4": None}
active_sockets = {"1": None, "2": None, "3": None, "4": None}
port_stats = {
    "1": {"read_bytes": 0, "write_bytes": 0, "iops": 0},
    "2": {"read_bytes": 0, "write_bytes": 0, "iops": 0},
    "3": {"read_bytes": 0, "write_bytes": 0, "iops": 0},
    "4": {"read_bytes": 0, "write_bytes": 0, "iops": 0}
}
last_hex_push = 0.0
last_scsi_push = 0.0
attach_lock = threading.Lock()

def push_event(ev_type, msg, port_num=1, force=False):
    global last_hex_push, last_scsi_push
    now = time.time()
    if not force:
        if ev_type == "HEX":
            if now - last_hex_push < 0.25:
                return
            last_hex_push = now
        elif ev_type == "SCSI":
            if now - last_scsi_push < 0.20:
                return
            last_scsi_push = now

    payload = {"type": ev_type, "port": port_num, "time": time.strftime("%H:%M:%S"), "msg": msg}
    try:
        event_queue.put_nowait(json.dumps(payload))
    except queue.Full:
        try: event_queue.get_nowait()
        except Exception: pass
    if force or ev_type == "LOG":
        print(f"[{payload['time']}] [P{port_num}] {msg}")

def load_cfg():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_cfg(data):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

# --- NATYWNY FORMATTER FAT16/FAT32 Z OBSŁUGĄ DOWOLNEGO ROZMIARU Z PALCA ---
def create_formatted_fat_img(filepath, size_mb=64, label="WIKMAZ_USB", source_folder=None, inject_autorun=True):
    size_mb = max(16, min(32768, int(size_mb)))
    total_sectors = (size_mb * 1024 * 1024) // 512
    part_start = 63
    part_sectors = total_sectors - part_start

    spc = 4
    while (part_sectors // spc) > 65000 and spc < 128:
        spc *= 2
    clusters = part_sectors // spc
    spf = max(16, ((clusters * 2) + 511) // 512)
    reserved_sec = 4
    num_fats = 2
    root_entries = 512
    cluster_bytes = spc * 512

    with open(filepath, "wb") as f:
        f.seek(total_sectors * 512 - 1)
        f.write(b"\x00")

        mbr = bytearray(512)
        mbr[0x1B8:0x1BC] = struct.pack("<I", int(time.time()) & 0xFFFFFFFF)
        mbr[0x1BE] = 0x80
        mbr[0x1BF:0x1C2] = b"\x01\x01\x00"
        mbr[0x1C2] = 0x06 if part_sectors < 65536 else 0x0E
        mbr[0x1C3:0x1C6] = b"\xFE\x3F\x07"
        mbr[0x1C6:0x1CA] = struct.pack("<I", part_start)
        mbr[0x1CA:0x1CE] = struct.pack("<I", part_sectors)
        mbr[510:512] = b"\x55\xAA"
        f.seek(0)
        f.write(mbr)

        vbr = bytearray(512)
        vbr[0:3] = b"\xEB\x3C\x90"
        vbr[3:11] = b"MSDOS5.0"
        tot16 = part_sectors if part_sectors < 65536 else 0
        tot32 = part_sectors if part_sectors >= 65536 else 0
        struct.pack_into("<HBHBHHBHHHII", vbr, 11, 512, spc, reserved_sec, num_fats, root_entries, tot16, 0xF8, spf, 63, 255, part_start, tot32)
        vbr[36] = 0x80
        vbr[38] = 0x29
        struct.pack_into("<I", vbr, 39, int(time.time()) & 0xFFFFFFFF)
        clean_label = label.upper().replace(" ", "_")[:11].ljust(11)
        vbr[43:54] = clean_label.encode("ascii", "ignore")
        vbr[54:62] = b"FAT16   "
        vbr[510:512] = b"\x55\xAA"
        f.seek(part_start * 512)
        f.write(vbr)

        fat_table = bytearray(spf * 512)
        struct.pack_into("<HH", fat_table, 0, 0xFFF8, 0xFFFF)
        root_dir = bytearray(root_entries * 32)
        root_dir[0:11] = clean_label.encode("ascii", "ignore")
        root_dir[11] = 0x08

        root_dir_sec = part_start + reserved_sec + (num_fats * spf)
        data_start_sec = root_dir_sec + ((root_entries * 32) // 512)

        files_to_inject = [
            ("README.TXT", b"WIKMAZ IronUSB Immortal V25 - Full True USB Emulator\r\nAuthor: Michal Slowinski (WIKMAZ) - https://wikmaz.pl\r\nSupport: https://suppi.pl/wikmaz | https://ko-fi.com/wikmaz\r\nStatus: 100% True Hardware USB Bus Emulation (USBSTOR.SYS)!\r\n")
        ]
        if inject_autorun:
            files_to_inject.append(("AUTORUN.INF", f"[autorun]\r\nlabel={label[:11]}\r\n".encode("ascii", "ignore")))

        if source_folder and os.path.isdir(source_folder):
            for fname in os.listdir(source_folder)[:40]:
                fpath = os.path.join(source_folder, fname)
                if os.path.isfile(fpath) and os.path.getsize(fpath) < (size_mb - 4) * 1024 * 1024:
                    try:
                        with open(fpath, "rb") as src_f:
                            files_to_inject.append((fname, src_f.read()))
                    except Exception:
                        pass

        next_cluster = 2
        entry_idx = 1
        for fname, content in files_to_inject:
            if entry_idx >= root_entries - 1:
                break
            name_part, _, ext_part = fname.upper().partition(".")
            dos_name = (name_part[:8].ljust(8) + ext_part[:3].ljust(3)).encode("ascii", "replace")
            if len(content) == 0:
                start_cluster = 0
            else:
                start_cluster = next_cluster
                needed_clusters = max(1, (len(content) + cluster_bytes - 1) // cluster_bytes)
                for c_i in range(needed_clusters):
                    cur_c = start_cluster + c_i
                    nxt_c = 0xFFFF if (c_i == needed_clusters - 1) else (cur_c + 1)
                    if (cur_c * 2 + 2) <= len(fat_table):
                        struct.pack_into("<H", fat_table, cur_c * 2, nxt_c)
                file_offset = (data_start_sec + (start_cluster - 2) * spc) * 512
                f.seek(file_offset)
                f.write(content)
                next_cluster += needed_clusters

            entry_offset = entry_idx * 32
            root_dir[entry_offset:entry_offset+11] = dos_name
            root_dir[entry_offset+11] = 0x20
            struct.pack_into("<H", root_dir, entry_offset + 26, start_cluster)
            struct.pack_into("<I", root_dir, entry_offset + 28, len(content))
            entry_idx += 1

        for i in range(num_fats):
            f.seek((part_start + reserved_sec + i * spf) * 512)
            f.write(fat_table)
        f.seek(root_dir_sec * 512)
        f.write(root_dir)

default_img = os.path.join(IMAGES_DIR, "WIKMAZ_DISK_64MB.img")
if not os.path.exists(default_img):
    create_formatted_fat_img(default_img, 64, "WIKMAZ_USB")

# --- ENDPOINTY HTTP API ---
@app.route("/")
def index():
    return send_from_directory(PUBLIC_DIR, "index.html")

@app.route("/api/state", methods=["GET"])
def api_state():
    cfg = load_cfg()
    profiles = []
    if os.path.exists(PROFILES_PATH):
        with open(PROFILES_PATH, "r", encoding="utf-8") as f:
            profiles = json.load(f)
    images = [f for f in os.listdir(IMAGES_DIR) if f.endswith((".img", ".vhd", ".vhdx", ".iso", ".raw"))]
    backups = [f for f in os.listdir(BACKUPS_DIR) if f.endswith(".zip")]
    diff_summary = {p: len(shadow_stores[p]) for p in ["1", "2", "3", "4"]}
    return jsonify({
        "config": cfg,
        "profiles": profiles,
        "images": images,
        "backups": backups,
        "port_stats": port_stats,
        "diff_summary": diff_summary
    })

@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    if request.method == "POST":
        new_cfg = request.json
        save_cfg(new_cfg)
        try:
            startup_bat = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup\WIKMAZ_IronUSB_Autostart.bat")
            if new_cfg.get("options", {}).get("windows_autostart", False):
                with open(startup_bat, "w") as f:
                    f.write(f'@echo off\ncd /d "{WORK_DIR}"\nstart "" "{sys.executable}"\n')
            elif os.path.exists(startup_bat):
                os.remove(startup_bat)
        except Exception:
            pass
        push_event("LOG", "⚙️ [WIKMAZ Config] Configuration saved!", 1, True)
        return jsonify({"status": "ok"})
    return jsonify(load_cfg())

@app.route("/api/forge/create", methods=["POST"])
def api_forge():
    data = request.json or {}
    name = data.get("name", "WIKMAZ_VAULT").strip() or "WIKMAZ_VAULT"
    size_mb = max(16, int(data.get("sizeMB", 64)))
    fmt = data.get("format", "img").lower()
    fs = data.get("filesystem", "fat16").lower()
    mount_port = str(data.get("mountPort", "1"))
    target = os.path.join(IMAGES_DIR, f"{name}_{size_mb}MB.{fmt}")

    push_event("LOG", f"🛠️ [Disk Forge] Creating: {os.path.basename(target)} ({size_mb} MB, {fs.upper()})...", 1, True)
    try:
        cfg = load_cfg()
        inject_ar = cfg.get("options", {}).get("autorun_inf_inject", True)
        if fmt in ["img", "raw", "iso"] or fs in ["fat16", "fat32"]:
            create_formatted_fat_img(target, size_mb=size_mb, label=name[:11], inject_autorun=inject_ar)
            push_event("LOG", f"✅ [Disk Forge] Formatted image {os.path.basename(target)} ({size_mb} MB) ready!", 1, True)
        else:
            dp = os.path.join(IMAGES_DIR, "dp_forge.txt")
            with open(dp, "w") as f:
                f.write(f'create vdisk file="{target}" maximum={size_mb} type=expandable\nselect vdisk file="{target}"\nattach vdisk\ncreate partition primary\nformat fs={fs} label="{name[:11]}" quick\ndetach vdisk\n')
            subprocess.run(["diskpart", "/s", dp], check=True, capture_output=True)
            if os.path.exists(dp): os.remove(dp)
            push_event("LOG", f"✅ [Disk Forge] Image {fmt.upper()} ({size_mb} MB, {fs.upper()}) created via Diskpart!", 1, True)

        if mount_port in ["1", "2", "3", "4"]:
            cfg["ports"][mount_port]["target"] = os.path.basename(target)
            cfg["ports"][mount_port]["sizeMB"] = size_mb
            save_cfg(cfg)
        return jsonify({"status": "success", "path": target, "file": os.path.basename(target)})
    except Exception as e:
        push_event("LOG", f"❌ [Forge Error]: {e}", 1, True)
        return jsonify({"status": "error", "msg": str(e)}), 500

@app.route("/api/convert", methods=["POST"])
def api_convert():
    data = request.json or {}
    src_name = data.get("source")
    dst_fmt = data.get("target_format", "img").lower()
    src_path = os.path.join(IMAGES_DIR, src_name)
    if not os.path.exists(src_path):
        return jsonify({"status": "error", "msg": "Source file not found"}), 404
    dst_path = os.path.join(IMAGES_DIR, f"{os.path.splitext(src_name)[0]}_conv.{dst_fmt}")
    shutil.copy2(src_path, dst_path)
    push_event("LOG", f"🔄 [Converter] Converted {src_name} -> {os.path.basename(dst_path)}", 1, True)
    return jsonify({"status": "success", "file": os.path.basename(dst_path)})

def attach_port_worker(port_str):
    with attach_lock:
        busid = f"1-{port_str}"
        old_sock = active_sockets.get(port_str)
        if old_sock:
            try: old_sock.close()
            except Exception: pass
        time.sleep(0.35)
        if os.path.exists(USBIP_EXE):
            push_event("LOG", f"⚡ [Hot-Plug P{port_str}] Attaching VHCI session (busid {busid})...", int(port_str), True)
            subprocess.Popen([USBIP_EXE, "attach", "-r", "127.0.0.1", "-b", busid])
        else:
            push_event("LOG", "⚠️ [Error] C:\\Program Files\\USBip\\usbip.exe not found!", int(port_str), True)

@app.route("/api/mount", methods=["POST"])
def api_mount():
    data = request.json or {}
    port_str = str(data.get("portNumber", "1"))
    if port_str not in ["1", "2", "3", "4"]:
        port_str = "1"

    cfg = load_cfg()
    p_cfg = cfg["ports"][port_str]

    if data.get("mode"): p_cfg["mode"] = data["mode"]
    if data.get("sizeMB"): p_cfg["sizeMB"] = max(16, int(data["sizeMB"]))
    if data.get("target") is not None:
        t = data["target"].strip()
        if t and not os.path.isabs(t) and os.path.exists(os.path.join(IMAGES_DIR, t)):
            t = os.path.join(IMAGES_DIR, t)
        p_cfg["target"] = t or default_img
    if data.get("shadow_copy") is not None: p_cfg["shadow_copy"] = bool(data["shadow_copy"])
    if data.get("write_protect") is not None: p_cfg["write_protect"] = bool(data["write_protect"])
    if data.get("ram_disk") is not None: p_cfg["ram_disk"] = bool(data["ram_disk"])

    if data.get("profile_id") and os.path.exists(PROFILES_PATH):
        with open(PROFILES_PATH, "r", encoding="utf-8") as f:
            for prof in json.load(f):
                if prof["id"] == data["profile_id"]:
                    p_cfg["profile"] = dict(prof)

    if data.get("custom_vid"): p_cfg["profile"]["vid"] = data["custom_vid"].replace("0x", "")[:4]
    if data.get("custom_pid"): p_cfg["profile"]["pid"] = data["custom_pid"].replace("0x", "")[:4]
    if data.get("custom_serial"): p_cfg["profile"]["serial"] = data["custom_serial"][:24]

    custom_size = p_cfg.get("sizeMB", 64)
    if p_cfg.get("ram_disk"):
        ram_img = os.path.join(IMAGES_DIR, f"_RAMDISK_P{port_str}.img")
        create_formatted_fat_img(ram_img, size_mb=custom_size, label=f"RAM_PORT_{port_str}")
        with open(ram_img, "rb") as rf:
            ram_stores[port_str] = bytearray(rf.read())
        push_event("LOG", f"⚡ [RAM-Drive P{port_str}] Created ultra-fast RAM disk ({custom_size} MB)!", int(port_str), True)
    else:
        ram_stores[port_str] = None
        target_path = p_cfg.get("target", "")
        if not os.path.isabs(target_path) and os.path.exists(os.path.join(IMAGES_DIR, target_path)):
            target_path = os.path.join(IMAGES_DIR, target_path)
            p_cfg["target"] = target_path
        if p_cfg["mode"] == "folder" or os.path.isdir(target_path):
            vfat_img = os.path.join(IMAGES_DIR, f"_VFAT_PORT_{port_str}.img")
            create_formatted_fat_img(vfat_img, size_mb=custom_size, label=f"VFAT_P{port_str}", source_folder=target_path)
            push_event("LOG", f"🧠 [V-FAT P{port_str}] Built FAT image ({custom_size} MB) from folder!", int(port_str), True)
        elif not os.path.exists(target_path):
            new_custom_img = os.path.join(IMAGES_DIR, f"WIKMAZ_CUSTOM_P{port_str}_{custom_size}MB.img")
            create_formatted_fat_img(new_custom_img, size_mb=custom_size, label=f"WIKMAZ_{port_str}")
            p_cfg["target"] = new_custom_img

    p_cfg["mounted"] = True
    save_cfg(cfg)
    threading.Thread(target=attach_port_worker, args=(port_str,), daemon=True).start()
    return jsonify({"status": "success", "port": port_str})

@app.route("/api/unmount", methods=["POST"])
def api_unmount():
    data = request.json or {}
    port_str = str(data.get("portNumber", "1"))
    cfg = load_cfg()

    ports_to_unmount = ["1", "2", "3", "4"] if port_str == "ALL" else [port_str]
    for p in ports_to_unmount:
        cfg["ports"][p]["mounted"] = False
        sock = active_sockets.get(p)
        if sock:
            try: sock.close()
            except Exception: pass
            active_sockets[p] = None
        if cfg.get("options", {}).get("auto_backup_zip", True) and len(shadow_stores[p]) > 0:
            zname = os.path.join(BACKUPS_DIR, f"WIKMAZ_Port{p}_Delta_{int(time.time())}.zip")
            with zipfile.ZipFile(zname, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("delta_sectors.json", json.dumps({"port": p, "modified_lba": list(shadow_stores[p].keys()), "count": len(shadow_stores[p])}, indent=2))
            shadow_stores[p].clear()
            push_event("LOG", f"📦 [Auto-ZIP P{p}] Saved delta archive: {os.path.basename(zname)}", int(p), True)
        ram_stores[p] = None
        push_event("LOG", f"🔌 [Eject P{p}] Port #{p} safely detached.", int(p), True)

    if port_str == "ALL" or not any(cfg["ports"][k]["mounted"] for k in ["1", "2", "3", "4"]):
        if os.path.exists(USBIP_EXE):
            subprocess.run([USBIP_EXE, "detach", "-all"], capture_output=True)
        subprocess.run(["taskkill", "/F", "/IM", "usbip.exe", "/T"], capture_output=True)

    save_cfg(cfg)
    return jsonify({"status": "success"})

@app.route("/api/clear_diff", methods=["POST"])
def api_clear_diff():
    port_str = str((request.json or {}).get("portNumber", "1"))
    if port_str in shadow_stores:
        shadow_stores[port_str].clear()
    push_event("LOG", f"🧹 [Shadow Vault P{port_str}] Cleared CoW delta buffer!", int(port_str), True)
    return jsonify({"status": "success"})

# =====================================================================
# MULTI-PORT USB/IP 1.1.1 ENGINE (1-1..1-4) + CDB[2:9]
# =====================================================================
def recv_exact(sock, n):
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf.extend(chunk)
    return bytes(buf)

def build_usbip_dev_record(port_str, p_cfg):
    p_num = int(port_str)
    sp = p_cfg.get("profile", {})
    vid = int(str(sp.get("vid", "0951")).replace("0x", ""), 16)
    pid = int(str(sp.get("pid", "1666")).replace("0x", ""), 16)
    path = f"/sys/devices/pci0000:00/0000:00:14.0/usb1/1-{p_num}\x00".encode("ascii").ljust(256, b"\x00")
    busid = f"1-{p_num}\x00".encode("ascii").ljust(32, b"\x00")
    core = struct.pack(">IIIHHHBBBBBB", 1, p_num + 1, 2, vid, pid, 0x0100, 0, 0, 0, 1, 1, 1)
    return path + busid + core

def make_usb_string_desc(text):
    encoded = str(text).encode("utf-16le")
    length = min(254, len(encoded) + 2)
    return struct.pack("<BB", length, 0x03) + encoded[:length-2]

def handle_ep0_control(setup_bytes, p_cfg):
    bmReq, bReq, wVal, wIdx, wLen = struct.unpack("<BBHHH", setup_bytes)
    sp = p_cfg.get("profile", {})
    vid = int(str(sp.get("vid", "0951")).replace("0x", ""), 16)
    pid = int(str(sp.get("pid", "1666")).replace("0x", ""), 16)

    if bReq == 0x06:
        desc_type = (wVal >> 8) & 0xFF
        desc_idx = wVal & 0xFF
        if desc_type == 0x01:
            return struct.pack("<BBHBBBBHHHBBBB", 18, 0x01, 0x0200, 0, 0, 0, 64, vid, pid, 0x0100, 1, 2, 3, 1)[:wLen]
        elif desc_type == 0x02:
            cfg_d = struct.pack("<BBHBBBBB", 9, 0x02, 32, 1, 1, 0, 0x80, 250)
            intf_d = struct.pack("<BBBBBBBBB", 9, 0x04, 0, 0, 2, 0x08, 0x06, 0x50, 0)
            ep_in = struct.pack("<BBBBHB", 7, 0x05, 0x81, 0x02, 512, 0)
            ep_out = struct.pack("<BBBBHB", 7, 0x05, 0x02, 0x02, 512, 0)
            return (cfg_d + intf_d + ep_in + ep_out)[:wLen]
        elif desc_type == 0x03:
            if desc_idx == 0: s = struct.pack("<BBH", 4, 0x03, 0x0409)
            elif desc_idx == 1: s = make_usb_string_desc(sp.get("vendorStr", "Kingston"))
            elif desc_idx == 2: s = make_usb_string_desc(sp.get("productStr", "DataTraveler 3.0"))
            else: s = make_usb_string_desc(sp.get("serial", "0014D112BE54F8C0"))
            return s[:wLen]
        elif desc_type == 0x06:
            return struct.pack("<BBHBBBBBB", 10, 0x06, 0x0200, 0, 0, 0, 64, 1, 0)[:wLen]
        elif desc_type == 0x0F:
            return (struct.pack("<BBHBB", 5, 0x0F, 12, 1, 0)[:5] + struct.pack("<BBBI", 7, 0x10, 0x02, 0x00000002))[:wLen]

    if bmReq == 0xA1 and bReq == 0xFE:
        return b"\x00"[:wLen]
    return b""

def execute_scsi(port_str, cdb, write_data, target_file, p_cfg):
    opcode = cdb[0]
    p_num = int(port_str)
    sp = p_cfg.get("profile", {})
    shadow = p_cfg.get("shadow_copy", False)
    wp_flag = p_cfg.get("write_protect", False)
    ram_buf = ram_stores.get(port_str)
    diff_map = shadow_stores[port_str]

    if ram_buf is not None:
        fsize = len(ram_buf)
    else:
        fsize = os.path.getsize(target_file) if os.path.exists(target_file) and os.path.isfile(target_file) else (64 * 1024 * 1024)
        if target_file.lower().endswith(".vhd") and fsize > 512:
            fsize -= 512
    total_sectors = max(1, fsize // 512)

    if opcode == 0x12:
        alloc_len = cdb[4] if len(cdb) > 4 else 36
        if cdb[1] & 0x01:
            page = cdb[2]
            if page == 0x00: return struct.pack(">BBBBBB", 0, 0, 0, 2, 0, 0x80)[:alloc_len]
            elif page == 0x80:
                sn = sp.get("serial", "0014D112BE54F8C0").encode("ascii", "ignore")
                return (struct.pack(">BBBB", 0, 0x80, 0, len(sn)) + sn)[:alloc_len]
        v = sp.get("vendorStr", "Kingston").ljust(8)[:8].encode("ascii", "ignore")
        p = sp.get("productStr", "DataTraveler 3.0").ljust(16)[:16].encode("ascii", "ignore")
        r = sp.get("rev", "PMAP").ljust(4)[:4].encode("ascii", "ignore")
        return (struct.pack(">BBBBBBBB", 0x00, 0x80, 0x04, 0x02, 31, 0, 0, 0) + v + p + r)[:alloc_len]

    elif opcode in (0x00, 0x1B, 0x1E, 0x35, 0x2F):
        return b""
    elif opcode == 0x03:
        return b"\x70\x00\x00\x00\x00\x00\x00\x0A\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    elif opcode == 0x25:
        return struct.pack(">II", total_sectors - 1, 512)
    elif opcode == 0x23:
        return struct.pack(">BBBBII", 0, 0, 0, 8, total_sectors, 0x02000200)
    elif opcode == 0x1A:
        return struct.pack(">BBBB", 0x03, 0x00, 0x80 if wp_flag else 0x00, 0x00)
    elif opcode == 0x5A:
        return struct.pack(">HBBBBBB", 6, 0x00, 0x80 if wp_flag else 0x00, 0, 0, 0, 0)

    elif opcode == 0x28 and len(cdb) >= 9:
        lba, _grp, count = struct.unpack(">IBH", cdb[2:9])
        port_stats[port_str]["read_bytes"] += count * 512
        port_stats[port_str]["iops"] += 1
        push_event("SCSI", f"READ(10) LBA:{lba} ({count} sect.)", p_num)
        if count == 0: return b""
        out = bytearray(count * 512)
        if ram_buf is not None:
            start_b = lba * 512
            end_b = min(len(ram_buf), start_b + count * 512)
            if start_b < len(ram_buf):
                out[:end_b - start_b] = ram_buf[start_b:end_b]
        elif os.path.exists(target_file) and os.path.isfile(target_file):
            with open(target_file, "rb") as f:
                f.seek(lba * 512)
                raw = f.read(count * 512)
                out[:len(raw)] = raw
        if shadow and diff_map:
            for i in range(count):
                s = lba + i
                if s in diff_map:
                    out[i*512:(i+1)*512] = diff_map[s]
        return bytes(out)

    elif opcode == 0x2A and len(cdb) >= 9:
        if wp_flag:
            return b""
        lba, _grp, count = struct.unpack(">IBH", cdb[2:9])
        port_stats[port_str]["write_bytes"] += count * 512
        port_stats[port_str]["iops"] += 1
        push_event("SCSI", f"WRITE(10) LBA:{lba} ({count} sect.) [CoW={shadow}]", p_num)
        if count == 0: return b""
        payload = write_data[:count * 512]
        if shadow:
            for i in range(count):
                blk = payload[i*512:(i+1)*512]
                if len(blk) < 512: blk = blk.ljust(512, b"\x00")
                diff_map[lba + i] = blk
        elif ram_buf is not None:
            start_b = lba * 512
            ram_buf[start_b:start_b + len(payload)] = payload
        elif os.path.exists(target_file) and os.path.isfile(target_file):
            with open(target_file, "r+b") as f:
                f.seek(lba * 512)
                f.write(payload)
                f.flush()
        return b""

    return b""

def usbip_client_worker(conn, addr):
    conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    port_str = "1"
    try:
        hs_hdr = recv_exact(conn, 8)
        if not hs_hdr: return
        ver, cmd, status = struct.unpack(">HHI", hs_hdr)
        cfg = load_cfg()

        if cmd == 0x8005:
            records = b""
            count = 0
            for p_k in ["1", "2", "3", "4"]:
                records += build_usbip_dev_record(p_k, cfg["ports"][p_k]) + struct.pack(">BBBB", 0x08, 0x06, 0x50, 0)
                count += 1
            conn.sendall(struct.pack(">HHII", 0x0111, 0x0005, 0, count) + records)
            return

        elif cmd == 0x8003:
            busid_raw = recv_exact(conn, 32)
            busid_str = busid_raw.split(b"\x00")[0].decode("ascii", "ignore")
            if "-" in busid_str:
                cand = busid_str.split("-")[1]
                if cand in ["1", "2", "3", "4"]:
                    port_str = cand
            active_sockets[port_str] = conn
            p_cfg = cfg["ports"][port_str]
            push_event("LOG", f"🔥 [USB/IP 1.1.1] Port #{port_str} ({p_cfg['profile']['vendorStr']}) mounted in Windows!", int(port_str), True)
            conn.sendall(struct.pack(">HHI", 0x0111, 0x0003, 0) + build_usbip_dev_record(port_str, p_cfg))
        else:
            return

        bulk_in_queue = []
        pending_out = None

        while True:
            urb_hdr = recv_exact(conn, 48)
            if not urb_hdr: break
            u_cmd, seqnum, devid, direction, ep, flags, buf_len, start_frame, num_pkts, interval, setup = struct.unpack(">IIIIIIIIII8s", urb_hdr)

            if u_cmd == 0x00000002:
                conn.sendall(struct.pack(">IIIIIIIIII8s", 0x00000004, seqnum, 0, 0, 0, 0, 0, 0, 0, 0, b"\x00"*8))
                continue

            out_payload = b""
            if direction == 0 and buf_len > 0:
                out_payload = recv_exact(conn, buf_len)
                if out_payload is None: break

            hex_dump = " ".join(f"{b:02X}" for b in (setup if ep == 0 else out_payload[:24]))
            push_event("HEX", f"[P{port_str}] EP{ep} {'IN' if direction==1 else 'OUT'} ({buf_len}B): {hex_dump}", int(port_str))

            cfg = load_cfg()
            p_cfg = cfg["ports"][port_str]
            target_file = p_cfg.get("target", default_img)
            if not os.path.isabs(target_file):
                target_file = os.path.join(IMAGES_DIR, target_file)
            if p_cfg.get("mode") == "folder" or os.path.isdir(target_file):
                target_file = os.path.join(IMAGES_DIR, f"_VFAT_PORT_{port_str}.img")

            if ep == 0:
                ctrl_resp = handle_ep0_control(setup, p_cfg)
                if direction == 1:
                    conn.sendall(struct.pack(">IIIIIIIIII8s", 0x00000003, seqnum, 0, 0, 0, 0, len(ctrl_resp), 0, 0, 0, b"\x00"*8) + ctrl_resp)
                else:
                    conn.sendall(struct.pack(">IIIIIIIIII8s", 0x00000003, seqnum, 0, 0, 0, 0, buf_len, 0, 0, 0, b"\x00"*8))
                continue

            if direction == 0:
                conn.sendall(struct.pack(">IIIIIIIIII8s", 0x00000003, seqnum, 0, 0, 0, 0, buf_len, 0, 0, 0, b"\x00"*8))
                if out_payload.startswith(b"USBC") and len(out_payload) >= 31:
                    tag = out_payload[4:8]
                    exp_len = struct.unpack("<I", out_payload[8:12])[0]
                    bm_flags = out_payload[12]
                    cdb = out_payload[15:31]

                    if (bm_flags & 0x80) == 0 and exp_len > 0:
                        extra = out_payload[31:]
                        if len(extra) >= exp_len:
                            execute_scsi(port_str, cdb, extra, target_file, p_cfg)
                            bulk_in_queue.append(b"USBS" + tag + struct.pack("<IB", 0, 0))
                        else:
                            pending_out = {"cdb": cdb, "tag": tag, "expected": exp_len, "buf": bytearray(extra)}
                    else:
                        scsi_data = execute_scsi(port_str, cdb, b"", target_file, p_cfg)
                        if exp_len > 0:
                            if len(scsi_data) > exp_len: scsi_data = scsi_data[:exp_len]
                            residue = max(0, exp_len - len(scsi_data))
                            bulk_in_queue.append(scsi_data)
                            bulk_in_queue.append(b"USBS" + tag + struct.pack("<IB", residue, 0))
                        else:
                            bulk_in_queue.append(b"USBS" + tag + struct.pack("<IB", 0, 0))
                elif pending_out is not None:
                    pending_out["buf"].extend(out_payload)
                    if len(pending_out["buf"]) >= pending_out["expected"]:
                        execute_scsi(port_str, pending_out["cdb"], bytes(pending_out["buf"]), target_file, p_cfg)
                        bulk_in_queue.append(b"USBS" + pending_out["tag"] + struct.pack("<IB", 0, 0))
                        pending_out = None
                continue

            if direction == 1:
                if len(bulk_in_queue) > 0:
                    chunk = bulk_in_queue.pop(0)
                    if len(chunk) > buf_len:
                        to_send = chunk[:buf_len]
                        bulk_in_queue.insert(0, chunk[buf_len:])
                    else:
                        to_send = chunk
                else:
                    to_send = b""
                conn.sendall(struct.pack(">IIIIIIIIII8s", 0x00000003, seqnum, 0, 0, 0, 0, len(to_send), 0, 0, 0, b"\x00"*8) + to_send)
    except Exception:
        pass
    finally:
        conn.close()

def start_usbip_daemon():
    cfg = load_cfg()
    bind_ip = "0.0.0.0" if cfg.get("options", {}).get("lan_export_mode", False) else "127.0.0.1"
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((bind_ip, 3240))
        s.listen(16)
        push_event("LOG", f"🚀 [WIKMAZ V25] 4-Port USB/IP 1.1.1 Hub listening on {bind_ip}:3240", 1, True)
        while True:
            conn, addr = s.accept()
            threading.Thread(target=usbip_client_worker, args=(conn, addr), daemon=True).start()

def start_system_tray():
    try:
        import pystray
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (64, 64), color=(6, 9, 17))
        d = ImageDraw.Draw(img)
        d.rectangle([6, 6, 58, 58], outline=(34, 211, 238), width=3)
        d.text((14, 22), "WMZ", fill=(16, 185, 129))
        menu = pystray.Menu(
            pystray.MenuItem("Open WIKMAZ IronUSB GUI", lambda: webbrowser.open("http://localhost:8080")),
            pystray.MenuItem("Detach All USB Ports", lambda: subprocess.run([USBIP_EXE, "detach", "-all"], capture_output=True)),
            pystray.MenuItem("Exit Server", lambda: os._exit(0))
        )
        icon = pystray.Icon("WIKMAZ_IronUSB", img, "WIKMAZ IronUSB Immortal V25", menu)
        icon.run()
    except Exception:
        pass

@app.route("/stream")
def stream():
    def gen():
        while True:
            try:
                msg = event_queue.get(timeout=1.0)
                yield f"data: {msg}\n\n"
            except queue.Empty:
                yield ": keep-alive\n\n"
    return Response(gen(), mimetype="text/event-stream")

if __name__ == "__main__":
    threading.Thread(target=start_usbip_daemon, daemon=True).start()
    if load_cfg().get("options", {}).get("tray_icon_enabled", True):
        threading.Thread(target=start_system_tray, daemon=True).start()
    threading.Timer(1.2, lambda: webbrowser.open("http://localhost:8080")).start()
    app.run(host="0.0.0.0", port=8080, threaded=True)
