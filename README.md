# Reinstall OS - by xyzval

Script dan Telegram Bot untuk reinstall VPS ke **Windows** atau **Linux** secara otomatis.

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
- ✅ Install semua dependencies otomatis
- ✅ Download bot dari GitHub
- ✅ Minta Bot Token (dari @BotFather)
- ✅ Setup service systemd (bot jalan 24/7)
- ✅ Auto-restart jika bot crash
- ✅ Langsung aktif setelah install

---

## Fitur

- Telegram Bot: kirim detail VPS, pilih OS, otomatis install
- Script manual: jalankan langsung di VPS
- Windows 10, 11, Server 2012-2022
- Linux: Debian, Ubuntu, CentOS, AlmaLinux, Rocky, Fedora, Alpine
- ISO dicari otomatis (tidak perlu cari link sendiri)
- Menu interaktif bahasa Indonesia
- Multi-VPS management (simpan banyak VPS)
- Auto-fix Linux password setelah install

---

## Cara Pakai

### Metode 1: Install 1-Klik (Otomatis 24/7)

```bash
bash <(curl -sL https://raw.githubusercontent.com/xyzval/reinstallos/main/install.sh)
```

Ikuti instruksi di layar → Bot langsung jalan!

### Metode 2: Setup Manual

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

### Cara Pakai Bot

1. Buka bot di Telegram
2. Ketik `/start`
3. Masukkan detail VPS: `ip:port@user:password`
4. Pilih kategori: **Windows** atau **Linux**
5. Pilih OS yang diinginkan
6. Pilih bahasa (untuk Windows)
7. Konfirmasi → Bot akan otomatis install!
8. Tunggu 15-30 menit, lalu login via RDP/SSH

### Perintah Bot

| Perintah | Fungsi |
|---|---|
| `/start` | Menu VPS (tambah/pilih VPS) |
| `/info` | Info sistem VPS |
| `/ssh CMD` | Jalankan command SSH |
| `/reboot` | Reboot VPS |
| `/shutdown` | Shutdown VPS |
| `/status` | Cek online/offline |
| `/help` | Tampilkan bantuan |

---

### Metode 3: Jalankan Langsung di VPS (Manual)

```bash
wget -O reinstall.sh https://raw.githubusercontent.com/xyzval/reinstallos/main/reinstall.sh && chmod +x reinstall.sh && bash reinstall.sh
```

Pilih nomor OS dari menu, selesai!

---

## OS yang Tersedia

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
| Debian 11, 12 | root / password123 |
| Ubuntu 20.04, 22.04, 24.04 | root / password123 |
| CentOS 9 Stream | root / password123 |
| AlmaLinux 9 | root / password123 |
| RockyLinux 9 | root / password123 |
| Fedora 43 | root / password123 |
| Alpine 3.22 | root / password123 |

**Login via SSH port 22**

---

## Persyaratan

### VPS
| Syarat | Keterangan |
|---|---|
| Virtualisasi | KVM, XEN, Hyper-V (BUKAN OpenVZ/LXC) |
| RAM minimal | 512 MB (Server), 1 GB (Windows 10/11) |
| Disk minimal | 25 GB (Windows), 5 GB (Linux) |

### Bot (server tempat bot jalan)
| Syarat | Keterangan |
|---|---|
| Python | 3.8+ |
| Dependencies | python-telegram-bot, paramiko, python-dotenv |
| Network | Akses ke Telegram API dan VPS target |

---

## Deploy Bot di VPS/Server (Manual)

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

## Manajemen Bot

Setelah install, gunakan perintah ini untuk mengelola bot:

```bash
# Cek status bot
systemctl status reinstall-bot

# Restart bot
systemctl restart reinstall-bot

# Stop bot
systemctl stop reinstall-bot

# Lihat log real-time
journalctl -u reinstall-bot -f

# Update bot ke versi terbaru
cd /opt/reinstallos && git pull && systemctl restart reinstall-bot
```

---

## Keamanan

- Set `ALLOWED_USERS` di `.env` agar hanya kamu yang bisa pakai bot
- Password VPS otomatis dihapus dari chat setelah dikirim
- Jangan share bot token ke siapapun

---

## Credits

Script ini menggunakan:
- [leitbogioro/Tools](https://github.com/leitbogioro/Tools) - InstallNET.sh
- [bin456789/reinstall](https://github.com/bin456789/reinstall) - reinstall.sh

## License

MIT License
