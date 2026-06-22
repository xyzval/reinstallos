# Reinstall OS - by xyzval

Script untuk reinstall VPS ke **Windows** atau **Linux** dengan mudah dan cepat.

## Fitur

- Install Windows 10, 11, Server 2012-2022
- Install Linux (Debian, Ubuntu, CentOS, AlmaLinux, Rocky, Fedora, Alpine)
- Custom Windows ISO
- Custom DD Image
- Menu interaktif bahasa Indonesia
- Otomatis deteksi sistem & IP
- Otomatis konfigurasi network

## Persyaratan

| Syarat | Keterangan |
|---|---|
| Akses root | Wajib |
| Virtualisasi | KVM, XEN, Hyper-V (BUKAN OpenVZ/LXC) |
| RAM minimal | 512 MB (Server), 1 GB (Windows 10/11) |
| Disk minimal | 25 GB (Windows), 5 GB (Linux) |

## Cara Pakai

### 1. Download & Jalankan (1 perintah)

```bash
wget -O reinstall.sh https://raw.githubusercontent.com/xyzval/reinstallos/main/reinstall.sh && chmod +x reinstall.sh && bash reinstall.sh
```

### 2. Pilih OS dari Menu

Script akan menampilkan menu interaktif:

```
=== PILIH SISTEM OPERASI ===

[WINDOWS DESKTOP]
  1) Windows 10
  2) Windows 11

[WINDOWS SERVER]
  3) Windows Server 2012 R2
  4) Windows Server 2016
  5) Windows Server 2019
  6) Windows Server 2022

[LINUX]
  7) Debian 12
  8) Debian 11
  9) Ubuntu 24.04
 10) Ubuntu 22.04
 11) Ubuntu 20.04
 12) CentOS 9 Stream
 13) AlmaLinux 9
 14) RockyLinux 9
 15) Fedora 43
 16) Alpine 3.22

[LAINNYA]
 17) Custom Windows ISO
 18) Custom Linux DD Image
```

### 3. Tunggu Instalasi Selesai (15-30 menit)

## Login Setelah Install

### Windows (via RDP)

| Setting | Nilai |
|---|---|
| Host | IP VPS kamu |
| Port | 3389 |
| Username | `Administrator` |
| Password | `Teddysun.com` |

> Jika login gagal, coba: `.\Administrator`

### Linux (via SSH)

| Setting | Nilai |
|---|---|
| Host | IP VPS kamu |
| Port | 22 |
| Username | `root` |
| Password | Yang kamu set saat install |

## Install Langsung Tanpa Menu

### Windows 10 (English)

```bash
wget -O reinstall.sh https://raw.githubusercontent.com/xyzval/reinstallos/main/reinstall.sh && chmod +x reinstall.sh && bash reinstall.sh <<< "1"
```

### Windows 11 (English)

```bash
wget -O reinstall.sh https://raw.githubusercontent.com/xyzval/reinstallos/main/reinstall.sh && chmod +x reinstall.sh && bash reinstall.sh <<< "2"
```

### Windows Server 2022

```bash
wget -O reinstall.sh https://raw.githubusercontent.com/xyzval/reinstallos/main/reinstall.sh && chmod +x reinstall.sh && bash reinstall.sh <<< "6"
```

## Peringatan

> **SEMUA DATA DI VPS AKAN DIHAPUS PERMANEN!**
> Pastikan sudah backup data penting sebelum menjalankan script.

## Credits

Script ini menggunakan:
- [leitbogioro/Tools](https://github.com/leitbogioro/Tools) - InstallNET.sh
- [bin456789/reinstall](https://github.com/bin456789/reinstall) - reinstall.sh

## License

MIT License
