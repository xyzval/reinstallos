# Reinstall OS - by xyzval

Script dan Telegram Bot untuk reinstall VPS ke **Windows** atau **Linux** secara otomatis.

---

## ⚡ Install 1-Klik (Recommended)

Cukup jalankan **1 command** ini di VPS/server yang akan menjalankan bot:

```bash
bash <(curl -sL https://raw.githubusercontent.com/xyzval/reinstallos/main/install.sh)
```

**Itu saja!** Bot langsung aktif 24/7, auto-restart jika crash. 🚀

> **Catatan:** Jalankan sebagai root. Jika belum root, gunakan:
> ```bash
> sudo bash <(curl -sL https://raw.githubusercontent.com/xyzval/reinstallos/main/install.sh)
> ```

### Apa yang dilakukan installer:
- ✅ Install semua dependencies otomatis (Python, pip, git, dll)
- ✅ Download bot dari GitHub ke `/opt/reinstallos`
- ✅ Buat virtual environment Python
- ✅ Minta Bot Token (dari @BotFather)
- ✅ Minta Telegram User ID (opsional, untuk keamanan)
- ✅ Setup service systemd (bot jalan 24/7 non-stop)
- ✅ Auto-restart jika bot crash (delay 5 detik)
- ✅ Auto-start saat VPS/server reboot
- ✅ Langsung aktif setelah install

---

## 📖 Cara Penggunaan Lengkap

### Step 1: Siapkan Bot Telegram

Sebelum install, kamu perlu membuat bot di Telegram:

1. Buka Telegram, cari **@BotFather**
2. Kirim `/newbot`
3. Masukkan nama bot (contoh: `ReinstallOS Bot`)
4. Masukkan username bot (contoh: `reinstallos_bot`)
5. **Simpan token** yang diberikan (format: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

> 💡 **Tips:** Untuk mendapatkan Telegram User ID kamu, chat ke **@userinfobot** dan kirim `/start`

### Step 2: Siapkan VPS/Server untuk Menjalankan Bot

Kamu butuh 1 VPS/server kecil yang akan menjalankan bot 24/7.
Bisa pakai VPS murah (RAM 512MB cukup) atau server yang sudah ada.

**Syarat minimal:**
- OS: Ubuntu/Debian/CentOS/AlmaLinux/Rocky/Fedora
- RAM: 512 MB+
- Python 3.8+ (akan di-install otomatis)
- Koneksi internet (akses ke Telegram API)

### Step 3: Install Bot (1 Klik!)

Login ke VPS via SSH, lalu jalankan:

```bash
bash <(curl -sL https://raw.githubusercontent.com/xyzval/reinstallos/main/install.sh)
```

Installer akan bertanya:
```
1. Bot Token: [paste token dari BotFather]
2. Telegram User ID: [isi user ID kamu, atau kosongkan]
```

Setelah itu bot langsung jalan! ✅

### Step 4: Gunakan Bot di Telegram

1. Buka Telegram → cari bot kamu
2. Kirim `/start`
3. Klik **➕ Tambah VPS Baru**
4. Kirim detail VPS target dengan format:
   ```
   ip:port@user:password
   ```
   Contoh:
   ```
   104.207.77.243:22@root:MyPassword123
   ```
5. Bot akan menyimpan VPS dan menampilkan menu aksi

### Step 5: Reinstall OS

1. Pilih VPS dari daftar
2. Klik **🔄 REINSTALL OS**
3. Pilih kategori: **WINDOWS** atau **LINUX**
4. Pilih versi OS yang diinginkan
5. Pilih bahasa (untuk Windows)
6. Klik **✅ YA, INSTALL!** untuk konfirmasi
7. Tunggu 15-30 menit ☕
8. Bot akan kasih notifikasi saat selesai + info login

### Step 6: Login ke VPS Setelah Reinstall

**Windows:**
```
Host: IP_VPS:3389 (via Remote Desktop/RDP)
User: Administrator
Pass: Teddysun.com
```

**Linux:**
```
Host: ssh root@IP_VPS
Pass: Bolehtuh1
```

---

## 🎯 Fitur Lengkap

| Fitur | Keterangan |
|---|---|
| Multi-VPS | Simpan banyak VPS sekaligus |
| Reinstall OS | Windows & Linux, pilih dari menu |
| SSH Command | Kirim command langsung dari Telegram |
| VPS Info | Lihat RAM, CPU, Disk, Uptime |
| Reboot/Shutdown | Kontrol VPS dari Telegram |
| Status Check | Ping cek online/offline |
| Auto-fix Password | Otomatis fix root password setelah install Linux |
| Loading UI | Progress bar real-time saat install |
| Keamanan | Password auto-dihapus dari chat |

---

## 🤖 Perintah Bot

| Perintah | Fungsi | Contoh |
|---|---|---|
| `/start` | Buka menu VPS | `/start` |
| `/info` | Info sistem VPS aktif | `/info` |
| `/ssh CMD` | Jalankan command SSH | `/ssh uptime` |
| `/reboot` | Reboot VPS aktif | `/reboot` |
| `/shutdown` | Shutdown VPS aktif | `/shutdown` |
| `/status` | Cek VPS online/offline | `/status` |
| `/help` | Tampilkan bantuan | `/help` |

### Contoh Penggunaan SSH:
```
/ssh uptime          → Cek berapa lama VPS nyala
/ssh df -h           → Cek penggunaan disk
/ssh free -m         → Cek RAM
/ssh whoami          → Cek user aktif
/ssh cat /etc/os-release  → Cek versi OS
```

---

## 📦 Metode Install Lainnya

### Metode 2: Setup Manual (tanpa installer)

1. Buat bot di Telegram via [@BotFather](https://t.me/BotFather), dapatkan token
2. Clone repo ini:
   ```bash
   git clone https://github.com/xyzval/reinstallos.git
   cd reinstallos
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Buat file `.env`:
   ```bash
   cp .env.example .env
   nano .env
   ```
   Isi `BOT_TOKEN` dengan token dari BotFather.

5. Jalankan bot:
   ```bash
   python3 bot.py
   ```

### Metode 3: Reinstall OS Langsung (tanpa bot)

Jalankan langsung di VPS yang mau di-reinstall:

```bash
wget -O reinstall.sh https://raw.githubusercontent.com/xyzval/reinstallos/main/reinstall.sh && chmod +x reinstall.sh && bash reinstall.sh
```

Pilih nomor OS dari menu, selesai!

---

## 🖥️ OS yang Tersedia

### Windows

| OS | Login Default |
|---|---|
| Windows 10 | Administrator / Teddysun.com |
| Windows 11 | Administrator / Teddysun.com |
| Windows Server 2012 R2 | Administrator / Teddysun.com |
| Windows Server 2016 | Administrator / Teddysun.com |
| Windows Server 2019 | Administrator / Teddysun.com |
| Windows Server 2022 | Administrator / Teddysun.com |

**Login via RDP port 3389**

### Linux

| OS | Login Default |
|---|---|
| Debian 9, 10, 11, 12 | root / Bolehtuh1 |
| Ubuntu 20.04, 22.04 | root / Bolehtuh1 |
| CentOS 9 Stream | root / Bolehtuh1 |
| AlmaLinux 9 | root / Bolehtuh1 |

**Login via SSH port 22**

---

## ⚙️ Persyaratan

### VPS Target (yang mau di-reinstall)
| Syarat | Keterangan |
|---|---|
| Virtualisasi | KVM, XEN, Hyper-V (BUKAN OpenVZ/LXC) |
| RAM minimal | 512 MB (Server), 1 GB (Windows 10/11) |
| Disk minimal | 25 GB (Windows), 5 GB (Linux) |
| Akses SSH | Harus bisa SSH ke VPS |

### Server Bot (tempat bot jalan 24/7)
| Syarat | Keterangan |
|---|---|
| OS | Ubuntu/Debian/CentOS/RHEL/Rocky/Alma/Fedora |
| RAM | 512 MB+ (cukup ringan) |
| Python | 3.8+ (auto-install oleh installer) |
| Network | Akses ke Telegram API dan VPS target |

---

## 🔧 Manajemen Bot

Setelah install, gunakan perintah ini untuk mengelola bot:

```bash
# Cek status bot (running/stopped)
systemctl status reinstall-bot

# Restart bot
systemctl restart reinstall-bot

# Stop bot
systemctl stop reinstall-bot

# Start bot
systemctl start reinstall-bot

# Lihat log real-time
journalctl -u reinstall-bot -f

# Lihat 50 baris log terakhir
journalctl -u reinstall-bot -n 50

# Update bot ke versi terbaru
cd /opt/reinstallos && git pull && systemctl restart reinstall-bot

# Edit konfigurasi (ganti token/user ID)
nano /opt/reinstallos/.env
systemctl restart reinstall-bot

# Uninstall bot
systemctl stop reinstall-bot
systemctl disable reinstall-bot
rm /etc/systemd/system/reinstall-bot.service
rm -rf /opt/reinstallos
systemctl daemon-reload
```

---

## 🔒 Keamanan

- Set `ALLOWED_USERS` di `.env` agar hanya kamu yang bisa pakai bot
- Password VPS otomatis dihapus dari chat setelah dikirim
- Jangan share bot token ke siapapun
- File `.env` hanya bisa dibaca oleh root (permission 600)
- Gunakan VPS terpisah untuk menjalankan bot (jangan di VPS yang sama yang mau di-reinstall)

---

## ❓ FAQ / Troubleshooting

### Bot tidak jalan setelah install?
```bash
journalctl -u reinstall-bot -n 30
```
Cek log untuk melihat error. Biasanya token salah.

### Bagaimana ganti Bot Token?
```bash
nano /opt/reinstallos/.env
# Edit BOT_TOKEN=token_baru_kamu
systemctl restart reinstall-bot
```

### Bot tiba-tiba mati?
Bot auto-restart dalam 5 detik jika crash. Cek status:
```bash
systemctl status reinstall-bot
```

### Install gagal di tengah jalan?
Jalankan ulang installer:
```bash
bash <(curl -sL https://raw.githubusercontent.com/xyzval/reinstallos/main/install.sh)
```
Installer akan update yang sudah ada.

### VPS tidak online setelah reinstall?
- Tunggu 30 menit (Windows butuh lebih lama)
- Cek VNC console di panel VPS provider
- Pastikan VPS mendukung KVM (bukan OpenVZ)

### Bagaimana update bot?
```bash
cd /opt/reinstallos && git pull && systemctl restart reinstall-bot
```

---

## 📋 Deploy Manual (Systemd)

> **Catatan:** Jika sudah menggunakan install 1-klik di atas, bagian ini tidak perlu.

### Jalankan sebagai service (systemd):

```bash
sudo nano /etc/systemd/system/reinstall-bot.service
```

Isi:
```ini
[Unit]
Description=Reinstall OS Telegram Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=/root/reinstallos
ExecStart=/usr/bin/python3 /root/reinstallos/bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Aktifkan:
```bash
sudo systemctl daemon-reload
sudo systemctl enable reinstall-bot
sudo systemctl start reinstall-bot
```

Cek status:
```bash
sudo systemctl status reinstall-bot
```

---

## 🙏 Credits

Script ini menggunakan:
- [leitbogioro/Tools](https://github.com/leitbogioro/Tools) - InstallNET.sh
- [bin456789/reinstall](https://github.com/bin456789/reinstall) - reinstall.sh

## License

MIT License
