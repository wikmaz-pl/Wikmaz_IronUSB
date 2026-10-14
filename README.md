# 🚀 WIKMAZ IronUSB Immortal (v25.0 Gold)
**Full True Hardware-Level USB Flash Drive Emulator for Windows 10 / 11 (x64)**

[![Official Website](https://img.shields.io/badge/WEBSITE-wikmaz.pl-22d3ee?style=for-the-badge)](https://wikmaz.pl)
[![Support on Ko-fi](https://img.shields.io/badge/KO--FI-ko--fi.com%2Fwikmaz-10b981?style=for-the-badge)](https://ko-fi.com/wikmaz)
[![Support on Suppi](https://img.shields.io/badge/SUPPI.PL-suppi.pl%2Fwikmaz-f59e0b?style=for-the-badge)](https://suppi.pl/wikmaz)
[![Platform](https://img.shields.io/badge/OS-Windows_10_%2F_11_x64-0284c7?style=for-the-badge)](#)

---

## 🇬🇧 ENGLISH DOCUMENTATION – Overview & Architecture

### Why WIKMAZ IronUSB Immortal Changes the Game
Standard virtual drive tools (*ImDisk*, *OSFMount*, *Daemon Tools*, or native Windows *VHD/VHDX Mount*) attach images as `BusType = Virtual (0x0E)` or `BusType = SCSI (0x01)`. Any software that verifies physical USB hardware via `IOCTL_STORAGE_QUERY_PROPERTY` immediately rejects them.

**WIKMAZ IronUSB Immortal** emulates a real hardware USB device at the Windows kernel level using a WHLK-signed Virtual Host Controller (`usbip-win2`), **USB/IP 1.1.1**, **Endpoint 0 (`GET_DESCRIPTOR`)**, and **3-Phase SCSI Bulk-Only Transport (`08/06/50`)**.

Windows loads its native **`USBSTOR.SYS`** driver and recognizes `.IMG`, `.VHD`, `.VHDX`, `.ISO` files and local folders (`Live V-FAT`) as **100% Authentic Physical USB Flash Drives (`BusType = 0x07`, `RemovableMedia = TRUE`)**!

### ✨ Key Features
- **🔌 4 Independent Virtual USB Ports (`1-1` to `1-4`):** Hot-plug up to 4 virtual USB flash drives simultaneously.
- **🎭 Hardware Identity Spoofing (`VID / PID / Serial`):** Clone real controllers (*Kingston*, *SanDisk*, *Samsung*, *Corsair*, *Transcend*, *PNY*) or set custom hex IDs.
- **📁 Folder-to-USB Emulation (`Live V-FAT Injector`):** Point to any folder on your disk and mount its files directly as a formatted USB stick.
- **🛠️ Disk Forge & Custom Size Input:** Type any custom size in MB from your keyboard or click presets (`32 MB` – `8 GB`) to forge pre-formatted `MBR + FAT16/FAT32/NTFS` drives.
- **🔄 Universal Format Converter:** Convert between `.IMG`, `.VHD`, `.VHDX`, and `.ISO` on the fly.
- **🛡️ Copy-on-Write Sandbox (`Shadow Copy`) & Auto-ZIP:** Redirect writes to RAM so the original image is never modified, and auto-pack modified sectors into `.ZIP` on eject.
- **🎛️ 100% Optional Modules:** Hardware Write-Protect (`WP`), Ultra RAM-Disk Mode, LAN/Proxmox Export (`0.0.0.0:3240`), System Tray Icon, and Windows Autostart.

### 📊 Feature Comparison Matrix
| Feature | WIKMAZ IronUSB Immortal | ImDisk Toolkit | Windows VHD Mount | Hardware IODD |
| :--- | :---: | :---: | :---: | :---: |
| **Reported as `BusType = USB (0x07)`** | **YES (100% True USB)** | No (`Virtual`) | No (`Virtual/SCSI`) | Yes |
| **Loads Native `USBSTOR.SYS` Driver** | **YES** | No | No | Yes |
| **Hardware `VID / PID / Serial` Spoofing** | **YES (Live)** | No | No | No |
| **Local Folder as USB Pendrive (`V-FAT`)** | **YES** | No | No | No |
| **Copy-on-Write Sandbox + Auto-ZIP** | **YES** | No | No | No |
| **4 Simultaneous Hot-Plug Ports** | **YES (`1-1`..`1-4`)** | Drive Letters Only | Drive Letters Only | 1 Only |

### 🚀 Quick Start (Step-by-Step)
1. **Download & Run:** Download `WIKMAZ_IronUSB_Immortal.exe` from the **Releases** tab (or run `START_WIKMAZ_IRONUSB.bat`). It automatically requests Admin rights, verifies the signed USB driver, and opens `http://localhost:8080`.
2. **Mount a USB Drive:** Click **`⚡ Quick Mount`** in the top-right corner, select a Port (`#1`–`#4`), enter any size in MB, choose a hardware brand (e.g., *Kingston*), and click **`🔌 INITIALIZE USB HOT-PLUG`**.
3. **Done!** Your new physical USB flash drive immediately appears in Windows Explorer!

---

## 🇵🇱 POLSKA DOKUMENTACJA – Opis, Architektura i Instrukcja

### Dlaczego WIKMAZ IronUSB Immortal to absolutny przełom?
Zwykłe programy (*ImDisk*, *Daemon Tools* czy systemowe montowanie *VHD/VHDX*) tworzą dyski wirtualne o fladze `BusType = Virtual (0x0E)`. Programy wymagające fizycznego pendrive'a sprawdzają w jądrze Windowsa zapytanie `IOCTL_STORAGE_QUERY_PROPERTY` i natychmiast wykrywają oszustwo.

**WIKMAZ IronUSB Immortal** emuluje prawdziwy kontroler sprzętowy (**VHCI `usbip-win2` + protokół `USB/IP 1.1.1` + deskryptory `Endpoint 0` + 3-fazowy `SCSI BOT`**). System Windows ładuje natywny sterownik **`USBSTOR.SYS`** i widzi zamontowany plik (`.IMG, .VHD, .VHDX, .ISO`) lub folder z dysku (`V-FAT`) jako **100% fizyczny pendrive podłączony do gniazda USB (`BusType = 0x07`, `RMB = 1`)**!

### 👶 Instrukcja Obsługi „Po Ludzku” (Krok po Kroku)
1. **Uruchomienie:** Odpal plik **`WIKMAZ_IronUSB_Immortal.exe`** (z zakładki **Releases**) lub **`START_WIKMAZ_IRONUSB.bat`**. Program sam podniesie uprawnienia Administratora, sprawdzi podpisany sterownik USB i otworzy Centrum Dowodzenia na `http://localhost:8080`.
2. **Zmiana Języka:** W prawym górnym rogu kliknij **`🇵🇱 PL`**, aby przełączyć cały interfejs na język polski.
3. **Podłączenie Pendrive'a:** Kliknij **`⚡ Szybkie Montowanie`**, wybierz Port (`#1`–`#4`), wskaż plik obrazu lub folder z dysku, wpisz z palca dowolny rozmiar w MB i kliknij **`🔌 ZAINICJUJ HOT-PLUG USB`**.
4. **Gotowe!** Po 2 sekundach w oknie „Ten komputer” pojawi się nowy pendrive USB!

---

## ❤️ Support the Author / Wsparcie Autora (WIKMAZ)
Created and engineered by **Michał Słowiński (WIKMAZ)**:
- 🌐 **Official Website / Strona Autora:** [https://wikmaz.pl](https://wikmaz.pl)
- ☕ **Wsparcie w PLN (Suppi.pl):** [https://suppi.pl/wikmaz](https://suppi.pl/wikmaz)
- ❤️ **Support on Ko-fi:** [https://ko-fi.com/wikmaz](https://ko-fi.com/wikmaz)

---

### 🔍 Search Tags / Słowa Kluczowe SEO
`usb-emulator` `virtual-usb-windows` `vhd-to-usb` `vhdx-to-usb` `img-to-usb` `iso-to-usb` `virtual-pendrive` `usb-mass-storage-emulator` `usbip-windows` `hardware-spoofing` `vid-pid-spoofing` `virtual-flash-drive` `scsi-bot-emulator` `usbstor-emulator` `folder-to-usb` `vfat-emulator` `shadow-copy-usb` `windows-10-usb-emulator` `windows-11-usb-emulator` `wikmaz` `ironusb`