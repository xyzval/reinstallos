#!/usr/bin/env python3
"""
Telegram Bot - Reinstall OS v2.0
by xyzval

Features:
- Multi-VPS management (save multiple VPS)
- Inline button menu (reinstall, info, reboot, ssh)
- Professional loading UI
- Auto-fix Linux password after install
"""

import os
import json
import logging
import asyncio
import re
import socket
import time as _time
import shlex
import uuid
import paramiko
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand, BotCommandScopeChat
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes,
    TypeHandler,
    ApplicationHandlerStop,
)
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
# Prevent Telegram bot tokens from being written inside INFO-level HTTP URLs.
logging.getLogger("httpx").setLevel(logging.WARNING)

BOT_TOKEN = os.getenv("BOT_TOKEN")
LEGACY_ALLOWED_USERS = [
    item.strip() for item in os.getenv("ALLOWED_USERS", "").split(",") if item.strip()
]
OWNER_ID = os.getenv("OWNER_ID", "").strip()
if not OWNER_ID and LEGACY_ALLOWED_USERS:
    # Backward-compatible migration for installations created before OWNER_ID.
    OWNER_ID = LEGACY_ALLOWED_USERS[0]

# Direktori tempat bot.py berada (bukan hardcode /opt/reinstallos), supaya /update
# dan penyimpanan data tetap benar walau bot diinstall di folder lain.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VPS_FILE = os.path.join(BASE_DIR, "vps_data.json")
AUTH_USERS_FILE = os.path.join(BASE_DIR, "authorized_users.json")
JOBS_FILE = os.path.join(BASE_DIR, "reinstall_jobs.json")
RESTART_NOTIFY_FILE = os.path.join(BASE_DIR, ".restart_notify")
SERVICE_NAME = os.getenv("SERVICE_NAME", "reinstall-bot")
MAX_ACTIVE_REINSTALL_JOBS = max(1, int(os.getenv("MAX_ACTIVE_REINSTALL_JOBS", "4")))
MAX_ACTIVE_REINSTALL_JOBS_PER_USER = max(1, int(os.getenv("MAX_ACTIVE_REINSTALL_JOBS_PER_USER", "3")))
MAX_QUEUED_REINSTALL_JOBS = max(1, int(os.getenv("MAX_QUEUED_REINSTALL_JOBS", "20")))

# Conversation states
(
    ADD_VPS, SELECT_VPS_ACTION, SELECT_OS, SELECT_LANG, CONFIRM, SSH_CMD,
    EDIT_PASS, WIZ_IP, WIZ_PORT, WIZ_USER, WIZ_PASS, EDIT_PORT,
    OWNER_ADD_USER, OWNER_SELECT_EXPIRY, OWNER_CUSTOM_EXPIRY,
) = range(15)


# OS Options
WINDOWS_OPTIONS = {
    "win10": {"name": "Windows 10", "cmd": '-windows 10'},
    "win11": {"name": "Windows 11", "cmd": '-windows 11'},
    "ws2012": {"name": "Windows Server 2012 R2", "cmd": '-windows 2012'},
    "ws2016": {"name": "Windows Server 2016", "cmd": '-windows 2016'},
    "ws2019": {"name": "Windows Server 2019", "cmd": '-windows 2019'},
    "ws2022": {"name": "Windows Server 2022", "cmd": '-windows 2022'},
}

LINUX_OPTIONS = {
    "debian12": {"name": "Debian 12", "cmd": '-debian 12', "engine": "leitbogioro"},
    "debian11": {"name": "Debian 11", "cmd": '-debian 11', "engine": "leitbogioro"},
    "ubuntu2204": {"name": "Ubuntu 22.04", "cmd": 'ubuntu 22.04', "engine": "bin456789"},
    "ubuntu2004": {"name": "Ubuntu 20.04", "cmd": 'ubuntu 20.04', "engine": "bin456789"},
    "centos9": {"name": "CentOS 9 Stream", "cmd": '-centos 9', "engine": "leitbogioro"},
    "alma9": {"name": "AlmaLinux 9", "cmd": '-almalinux 9', "engine": "leitbogioro"},
}

LANG_OPTIONS = {"en": "English", "cn": "Chinese", "jp": "Japanese"}



# ============ Per-user Storage & Authorization ============

def _read_json_file(path: str, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Read JSON error ({path}): {e}")
    return default


def _atomic_write_json(path: str, data) -> None:
    """Write JSON atomically with owner-only permissions."""
    tmp_path = f"{path}.tmp.{os.getpid()}.{_time.time_ns()}"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, path)
        os.chmod(path, 0o600)
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass


def load_vps_list(user_id: int) -> list:
    """Load only the VPS list belonging to one Telegram user."""
    data = _read_json_file(VPS_FILE, {})
    user_vps = data.get(str(user_id), []) if isinstance(data, dict) else []
    return user_vps if isinstance(user_vps, list) else []


def save_vps_list(user_id: int, vps_list: list):
    """Save one user's VPS list without touching another user's list."""
    try:
        data = _read_json_file(VPS_FILE, {})
        if not isinstance(data, dict):
            data = {}
        data[str(user_id)] = vps_list
        _atomic_write_json(VPS_FILE, data)
    except Exception as e:
        logger.error(f"Save VPS error: {e}")


def load_authorized_users() -> dict:
    """Return {telegram_id: metadata}; the owner is kept separately in .env."""
    raw = _read_json_file(AUTH_USERS_FILE, {})
    users = raw.get("users", {}) if isinstance(raw, dict) else {}
    if not isinstance(users, dict):
        return {}
    clean = {}
    for user_id, record in users.items():
        uid = str(user_id).strip()
        if not uid.isdigit() or not isinstance(record, dict):
            continue
        expires_at = record.get("expires_at")
        try:
            expires_at = int(expires_at) if expires_at not in (None, "", 0, "0") else None
        except (TypeError, ValueError):
            expires_at = None
        clean[uid] = {
            "name": str(record.get("name", "")).strip()[:40],
            "active": bool(record.get("active", True)),
            "added_at": str(record.get("added_at", "")),
            "added_by": str(record.get("added_by", "")),
            "expires_at": expires_at,
        }
    return clean


def save_authorized_users(users: dict) -> None:
    _atomic_write_json(AUTH_USERS_FILE, {"version": 2, "users": users})


def initialize_auth_storage() -> None:
    """Create secure auth storage and migrate legacy ALLOWED_USERS once."""
    if os.path.exists(AUTH_USERS_FILE):
        try:
            os.chmod(AUTH_USERS_FILE, 0o600)
        except OSError:
            pass
        return

    migrated = {}
    for user_id in LEGACY_ALLOWED_USERS:
        if user_id and user_id != OWNER_ID and user_id.isdigit():
            migrated[user_id] = {
                "name": "Migrated user",
                "active": True,
                "added_at": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
                "added_by": OWNER_ID,
                "expires_at": None,
            }
    save_authorized_users(migrated)


def is_owner(user_id: int) -> bool:
    return bool(OWNER_ID) and str(user_id) == OWNER_ID


def is_user_expired(record: dict, now: int = None) -> bool:
    expires_at = record.get("expires_at")
    if expires_at in (None, "", 0, "0"):
        return False
    try:
        current = int(_time.time()) if now is None else int(now)
        return int(expires_at) <= current
    except (TypeError, ValueError):
        return False


def user_record_has_access(record: dict, now: int = None) -> bool:
    return bool(record.get("active")) and not is_user_expired(record, now)


def format_expiry(record: dict, short: bool = False) -> str:
    expires_at = record.get("expires_at")
    if expires_at in (None, "", 0, "0"):
        return "Permanen" if not short else "∞"
    try:
        # Display in WIB (UTC+7); storage remains a timezone-neutral Unix timestamp.
        wib = _time.gmtime(int(expires_at) + 7 * 3600)
        return _time.strftime("%d-%m-%Y %H:%M WIB", wib) if not short else _time.strftime("%d/%m/%y", wib)
    except (TypeError, ValueError, OverflowError):
        return "Tidak valid"


def user_status(record: dict) -> str:
    if is_user_expired(record):
        return "⌛ Kedaluwarsa"
    if not record.get("active"):
        return "⛔ Nonaktif"
    return "✅ Aktif"


def is_authorized(user_id: int) -> bool:
    if is_owner(user_id):
        return True
    record = load_authorized_users().get(str(user_id))
    return bool(record and user_record_has_access(record))


def set_authorized_user(user_id: str, name: str, active: bool = True, expires_at=None) -> None:
    users = load_authorized_users()
    existing = users.get(user_id, {})
    users[user_id] = {
        "name": name.strip()[:40],
        "active": active,
        "added_at": existing.get("added_at") or _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
        "added_by": existing.get("added_by") or OWNER_ID,
        "expires_at": int(expires_at) if expires_at not in (None, "", 0, "0") else None,
    }
    save_authorized_users(users)


def remove_authorized_user(user_id: str) -> bool:
    users = load_authorized_users()
    if user_id not in users:
        return False
    del users[user_id]
    save_authorized_users(users)
    return True


def count_user_vps(user_id: str) -> int:
    return len(load_vps_list(int(user_id)))


def parse_vps_detail(text: str) -> dict:
    """Parse ip:port@user:password"""
    text = text.strip()
    result = {"vps_ip": "", "vps_port": 22, "vps_user": "root", "vps_pass": ""}
    try:
        if "@" not in text:
            return None
        connection, login = text.split("@", 1)
        if ":" in connection:
            ip, port = connection.rsplit(":", 1)
            result["vps_ip"] = ip
            result["vps_port"] = int(port)
        else:
            result["vps_ip"] = connection
        if ":" in login:
            user, password = login.split(":", 1)
            result["vps_user"] = user
            result["vps_pass"] = password
        else:
            return None
        if not result["vps_ip"] or not result["vps_pass"]:
            return None
        return result
    except (ValueError, IndexError):
        return None



# ============ Menu Helpers ============

def get_vps_list_keyboard(user_id: int):
    """Build VPS list keyboard."""
    vps_list = load_vps_list(user_id)
    keyboard = []
    for i, vps in enumerate(vps_list):
        label = f"🖥 {vps['vps_ip']}:{vps['vps_port']}"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"selvps_{i}")])
    keyboard.append([InlineKeyboardButton("➕ Tambah VPS Baru", callback_data="addvps")])
    keyboard.append([InlineKeyboardButton("📋 Reinstall Jobs", callback_data="jobs_list")])
    if is_owner(user_id):
        keyboard.append([InlineKeyboardButton("👥 Kelola User", callback_data="owner_users")])
    return InlineKeyboardMarkup(keyboard)


def get_action_keyboard():
    """Build action menu keyboard."""
    keyboard = [
        [InlineKeyboardButton("🔄 REINSTALL OS", callback_data="act_reinstall")],
        [
            InlineKeyboardButton("📊 Info", callback_data="act_info"),
            InlineKeyboardButton("🔄 Reboot", callback_data="act_reboot"),
        ],
        [
            InlineKeyboardButton("💻 SSH Command", callback_data="act_ssh"),
            InlineKeyboardButton("📡 Status", callback_data="act_status"),
        ],
        [
            InlineKeyboardButton("🔓 Open All Port", callback_data="act_openport"),
            InlineKeyboardButton("🔑 Edit Password", callback_data="act_editpass"),
        ],
        [
            InlineKeyboardButton("🔧 Edit Port", callback_data="act_editport"),
            InlineKeyboardButton("🗑 Hapus VPS", callback_data="act_delete"),
        ],
        [
            InlineKeyboardButton("◀️ Kembali", callback_data="act_back"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_vps_info_text(data: dict) -> str:
    """Build VPS info header."""
    return (
        "─────────────────────────────\n"
        f"  🖥️  VPS: {data['vps_ip']}:{data['vps_port']}\n"
        f"  👤  User: {data['vps_user']}\n"
        f"  🔑  Pass: {data['vps_pass']}\n"
        "─────────────────────────────"
    )


def get_wizard_port_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("22 (default)", callback_data="wiz_port_22"),
         InlineKeyboardButton("22022", callback_data="wiz_port_22022")],
        [InlineKeyboardButton("2222", callback_data="wiz_port_2222"),
         InlineKeyboardButton("✏️ Custom", callback_data="wiz_port_custom")],
        [InlineKeyboardButton("❌ Batal", callback_data="wiz_cancel")],
    ])

def get_wizard_user_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("root", callback_data="wiz_user_root"),
         InlineKeyboardButton("ubuntu", callback_data="wiz_user_ubuntu")],
        [InlineKeyboardButton("admin", callback_data="wiz_user_admin"),
         InlineKeyboardButton("✏️ Ketik Manual", callback_data="wiz_user_custom")],
        [InlineKeyboardButton("❌ Batal", callback_data="wiz_cancel")],
    ])

def get_add_method_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Wizard Cepat (klik-klik)", callback_data="add_wizard")],
        [InlineKeyboardButton("📋 Format Lengkap", callback_data="add_format")],
        [InlineKeyboardButton("📂 Bulk Import", callback_data="add_bulk")],
        [InlineKeyboardButton("◀️ Kembali", callback_data="add_back")],
    ])

def get_bulk_example_text():
    return (
        "─────────────────────────────\n"
        "  📂 Bulk Import\n"
        "─────────────────────────────\n\n"
        "Kirim banyak VPS sekaligus, 1 baris 1 VPS:\n\n"
        "`104.207.93.92:22022@root:Pass123`\n"
        "`1.2.3.4:22@root:MyPass`\n"
        "`5.6.7.8@root:Pass` (port auto 22)\n\n"
        "Bot akan test & simpan yang valid. 🔍"
    )




# ============ Persistent Reinstall Jobs ============

RUNNING_JOB_STATES = {"connecting", "downloading", "launching", "monitoring"}
ACTIVE_JOB_STATES = {"queued", *RUNNING_JOB_STATES}
TERMINAL_JOB_STATES = {"completed", "failed", "timeout"}
JOB_STATUS_LABELS = {
    "queued": "⏳ Antrean",
    "connecting": "🔌 Menghubungkan",
    "downloading": "⬇️ Mengunduh installer",
    "launching": "🚀 Menjalankan installer",
    "monitoring": "⚙️ Installing/monitoring",
    "completed": "✅ Selesai",
    "failed": "❌ Gagal",
    "timeout": "⚠️ Timeout",
}


def load_reinstall_jobs() -> dict:
    raw = _read_json_file(JOBS_FILE, {})
    jobs = raw.get("jobs", {}) if isinstance(raw, dict) else {}
    return jobs if isinstance(jobs, dict) else {}


def save_reinstall_jobs(jobs: dict) -> None:
    _atomic_write_json(JOBS_FILE, {"version": 1, "jobs": jobs})


def initialize_jobs_storage() -> None:
    if not os.path.exists(JOBS_FILE):
        save_reinstall_jobs({})
    else:
        try:
            os.chmod(JOBS_FILE, 0o600)
        except OSError:
            pass


def prune_reinstall_jobs(jobs: dict, keep_terminal: int = 100) -> dict:
    active = {job_id: job for job_id, job in jobs.items() if job.get("status") in ACTIVE_JOB_STATES}
    terminal = [
        (job_id, job) for job_id, job in jobs.items()
        if job.get("status") not in ACTIVE_JOB_STATES
    ]
    terminal.sort(key=lambda item: int(item[1].get("updated_at", 0)), reverse=True)
    active.update(dict(terminal[:keep_terminal]))
    return active


def create_reinstall_job(user_id: int, chat_id: int, message_id: int, data: dict) -> dict:
    jobs = prune_reinstall_jobs(load_reinstall_jobs())
    now = int(_time.time())
    job_id = "J" + _time.strftime("%y%m%d-%H%M%S", _time.gmtime(now)) + "-" + uuid.uuid4().hex[:6]
    job = {
        "job_id": job_id,
        "user_id": str(user_id),
        "chat_id": int(chat_id),
        "message_id": int(message_id),
        "vps_ip": str(data["vps_ip"]),
        "vps_port": int(data["vps_port"]),
        "vps_user": str(data.get("vps_user", "root")),
        "os_name": str(data["os_name"]),
        "os_type": str(data["os_type"]),
        "os_cmd": str(data["os_cmd"]),
        "os_engine": str(data.get("os_engine", "")),
        "lang": str(data.get("lang", "")),
        "status": "queued",
        "progress": 0,
        "offline_seen": False,
        "created_at": now,
        "started_at": 0,
        "updated_at": now,
        "completed_at": 0,
        "target_online_since": 0,
        "verification": "",
        "error": "",
    }
    jobs[job_id] = job
    save_reinstall_jobs(jobs)
    return job


def get_reinstall_job(job_id: str):
    return load_reinstall_jobs().get(job_id)


def update_reinstall_job(job_id: str, **fields):
    jobs = load_reinstall_jobs()
    job = jobs.get(job_id)
    if not job:
        return None
    job.update(fields)
    job["updated_at"] = int(_time.time())
    jobs[job_id] = job
    save_reinstall_jobs(jobs)
    return job


def get_user_reinstall_jobs(user_id: int, limit: int = 15) -> list:
    jobs = [
        job for job in load_reinstall_jobs().values()
        if str(job.get("user_id")) == str(user_id)
    ]
    jobs.sort(key=lambda job: int(job.get("created_at", 0)), reverse=True)
    return jobs[:limit]


def active_reinstall_jobs(user_id=None) -> list:
    jobs = [job for job in load_reinstall_jobs().values() if job.get("status") in ACTIVE_JOB_STATES]
    if user_id is not None:
        jobs = [job for job in jobs if str(job.get("user_id")) == str(user_id)]
    return jobs


def running_reinstall_jobs(user_id=None) -> list:
    jobs = [
        job for job in load_reinstall_jobs().values()
        if job.get("status") in RUNNING_JOB_STATES
    ]
    if user_id is not None:
        jobs = [job for job in jobs if str(job.get("user_id")) == str(user_id)]
    return jobs


def queued_reinstall_jobs(user_id=None) -> list:
    jobs = [
        job for job in load_reinstall_jobs().values()
        if job.get("status") == "queued"
    ]
    if user_id is not None:
        jobs = [job for job in jobs if str(job.get("user_id")) == str(user_id)]
    jobs.sort(key=lambda job: int(job.get("created_at", 0)))
    return jobs


def get_queue_position(job_id: str) -> int:
    for position, job in enumerate(queued_reinstall_jobs(), start=1):
        if job.get("job_id") == job_id:
            return position
    return 0


def find_active_job_for_vps(vps_ip: str):
    for job in active_reinstall_jobs():
        if job.get("vps_ip") == vps_ip:
            return job
    return None


def find_job_vps_credentials(job: dict):
    """Recover credentials from that user's isolated VPS bucket; never persist them in jobs."""
    candidates = load_vps_list(int(job["user_id"]))
    exact = None
    fallback = None
    for vps in candidates:
        if vps.get("vps_ip") != job.get("vps_ip"):
            continue
        fallback = fallback or vps
        if int(vps.get("vps_port", 22)) == int(job.get("vps_port", 22)):
            exact = vps
            break
    credentials = exact or fallback
    if not credentials:
        return None
    data = dict(credentials)
    for key in ("os_name", "os_type", "os_cmd", "os_engine", "lang"):
        data[key] = job.get(key, "")
    return data


def format_job_time(timestamp: int) -> str:
    if not timestamp:
        return "-"
    return _time.strftime("%d-%m-%Y %H:%M WIB", _time.gmtime(int(timestamp) + 7 * 3600))


def get_jobs_text(user_id: int) -> str:
    jobs = get_user_reinstall_jobs(user_id)
    running = len(running_reinstall_jobs(user_id))
    queued = len(queued_reinstall_jobs(user_id))
    lines = [
        "─────────────────────────────",
        "  📋  Reinstall Jobs",
        "─────────────────────────────",
        "",
        f"  Berjalan: {running}",
        f"  Antrean: {queued}",
        f"  Riwayat ditampilkan: {len(jobs)}",
        "",
    ]
    if jobs:
        lines.append("  Tekan job untuk melihat detail/progress.")
    else:
        lines.append("  Belum ada job reinstall.")
    lines.extend(["", "─────────────────────────────"])
    return "\n".join(lines)


def get_jobs_keyboard(user_id: int) -> InlineKeyboardMarkup:
    keyboard = []
    for job in get_user_reinstall_jobs(user_id, limit=10):
        status = JOB_STATUS_LABELS.get(job.get("status"), job.get("status", "?"))
        if job.get("status") == "queued":
            status += f" #{get_queue_position(job['job_id'])}"
        label = f"{status} · {job.get('vps_ip')}"
        keyboard.append([InlineKeyboardButton(label[:55], callback_data=f"jobs_detail_{job['job_id']}")])
    keyboard.extend([
        [InlineKeyboardButton("🔄 Refresh", callback_data="jobs_list")],
        [InlineKeyboardButton("✖️ Tutup", callback_data="jobs_close")],
    ])
    return InlineKeyboardMarkup(keyboard)


def get_job_detail_text(job: dict) -> str:
    status = JOB_STATUS_LABELS.get(job.get("status"), job.get("status", "?"))
    lines = [
        "─────────────────────────────",
        "  📋  Detail Reinstall Job",
        "─────────────────────────────",
        "",
        f"  Job ID: {job.get('job_id')}",
        f"  VPS: {job.get('vps_ip')}:{job.get('vps_port')}",
        f"  OS: {job.get('os_name')}",
        f"  Status: {status}",
        f"  Progress: {int(job.get('progress', 0))}%",
        f"  Dibuat: {format_job_time(job.get('created_at', 0))}",
        f"  Mulai: {format_job_time(job.get('started_at', 0))}",
        f"  Update: {format_job_time(job.get('updated_at', 0))}",
    ]
    if job.get("status") == "queued":
        lines.append(f"  Posisi antrean: {get_queue_position(job['job_id']) or '-'}")
    if job.get("completed_at"):
        lines.append(f"  Selesai: {format_job_time(job.get('completed_at', 0))}")
    if job.get("verification"):
        lines.append(f"  Verifikasi: {str(job['verification'])[:200]}")
    if job.get("error"):
        lines.extend(["", f"  Pesan: {str(job['error'])[:500]}"])
    lines.extend(["", "─────────────────────────────"])
    return "\n".join(lines)


def get_job_detail_keyboard(job: dict) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh", callback_data=f"jobs_detail_{job['job_id']}")],
        [InlineKeyboardButton("◀️ Daftar Jobs", callback_data="jobs_list")],
        [InlineKeyboardButton("✖️ Tutup", callback_data="jobs_close")],
    ])


async def safe_edit_query(query, text: str, reply_markup=None) -> None:
    try:
        await query.edit_message_text(text, reply_markup=reply_markup)
    except Exception as exc:
        if "Message is not modified" not in str(exc):
            logger.warning("Could not refresh jobs message: %s", exc)


async def jobs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.effective_message.reply_text(
        get_jobs_text(user_id),
        reply_markup=get_jobs_keyboard(user_id),
    )


async def handle_jobs_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    action = query.data

    if action == "jobs_close":
        await safe_edit_query(query, "Daftar reinstall jobs ditutup. Gunakan /jobs untuk membukanya lagi.")
        return

    if action == "jobs_home":
        await safe_edit_query(
            query,
            "─────────────────────────────\n"
            "  🖥️  Reinstall OS Bot\n"
            "─────────────────────────────\n\n"
            "  Pilih VPS atau tambah baru:",
            get_vps_list_keyboard(user_id),
        )
        return

    if action == "jobs_list":
        await safe_edit_query(query, get_jobs_text(user_id), get_jobs_keyboard(user_id))
        return

    if action.startswith("jobs_detail_"):
        job_id = action[len("jobs_detail_"):]
        job = get_reinstall_job(job_id)
        # Ownership is verified server-side, not only hidden in the UI.
        if not job or str(job.get("user_id")) != str(user_id):
            await safe_edit_query(query, "❌ Job tidak ditemukan atau bukan milik Anda.", get_jobs_keyboard(user_id))
            return
        await safe_edit_query(query, get_job_detail_text(job), get_job_detail_keyboard(job))


# ============ Owner User Management UI ============

def get_owner_users_text() -> str:
    users = load_authorized_users()
    accessible = sum(1 for record in users.values() if user_record_has_access(record))
    expired = sum(1 for record in users.values() if is_user_expired(record))
    lines = [
        "─────────────────────────────",
        "  👥  Kelola User",
        "─────────────────────────────",
        "",
        "  👑 Owner: aktif permanen",
        f"  👤 User: {len(users)} total / {accessible} dapat akses",
        f"  ⌛ Kedaluwarsa: {expired}",
        "",
    ]
    if users:
        lines.append("  Tekan nama user untuk detail/perpanjang.")
        lines.append("  Tombol ⏯ mengubah status aktif/nonaktif.")
    else:
        lines.append("  Belum ada user tambahan.")
    lines.extend(["", "─────────────────────────────"])
    return "\n".join(lines)


def get_owner_users_keyboard() -> InlineKeyboardMarkup:
    users = load_authorized_users()
    keyboard = []
    for user_id, record in sorted(users.items(), key=lambda item: int(item[0])):
        icon = "⌛" if is_user_expired(record) else "✅" if record.get("active") else "⛔"
        name = record.get("name") or "User"
        expiry = format_expiry(record, short=True)
        label = f"{icon} {name[:12]} · {expiry}"
        keyboard.append([
            InlineKeyboardButton(label, callback_data=f"owner_detail_{user_id}"),
            InlineKeyboardButton("⏯", callback_data=f"owner_toggle_{user_id}"),
            InlineKeyboardButton("🗑", callback_data=f"owner_delete_{user_id}"),
        ])
    keyboard.extend([
        [InlineKeyboardButton("➕ Tambah User", callback_data="owner_add")],
        [InlineKeyboardButton("◀️ Kembali", callback_data="owner_back")],
    ])
    return InlineKeyboardMarkup(keyboard)


def get_expiry_selection_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("1 Hari", callback_data="owner_expiry_1"),
            InlineKeyboardButton("7 Hari", callback_data="owner_expiry_7"),
        ],
        [
            InlineKeyboardButton("30 Hari", callback_data="owner_expiry_30"),
            InlineKeyboardButton("♾ Permanen", callback_data="owner_expiry_perm"),
        ],
        [InlineKeyboardButton("✏️ Manual (hari)", callback_data="owner_expiry_custom")],
        [InlineKeyboardButton("◀️ Batal", callback_data="owner_users")],
    ])


def get_owner_user_detail_keyboard(user_id: str, record: dict) -> InlineKeyboardMarkup:
    toggle_label = "⛔ Nonaktifkan" if record.get("active") else "✅ Aktifkan"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("+1 Hari", callback_data=f"owner_extend_1_{user_id}"),
            InlineKeyboardButton("+7 Hari", callback_data=f"owner_extend_7_{user_id}"),
            InlineKeyboardButton("+30 Hari", callback_data=f"owner_extend_30_{user_id}"),
        ],
        [InlineKeyboardButton("✏️ Tambah Hari Manual", callback_data=f"owner_extend_custom_{user_id}")],
        [InlineKeyboardButton("♾ Jadikan Permanen", callback_data=f"owner_permanent_{user_id}")],
        [InlineKeyboardButton(toggle_label, callback_data=f"owner_toggle_{user_id}")],
        [InlineKeyboardButton("🗑 Cabut Akses", callback_data=f"owner_delete_{user_id}")],
        [InlineKeyboardButton("◀️ Daftar User", callback_data="owner_users")],
    ])




async def access_guard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Block every update from unauthorized users before any handler runs."""
    user = update.effective_user
    if user and is_authorized(user.id):
        return

    user_id = str(user.id) if user else "tidak diketahui"
    if update.callback_query:
        try:
            await update.callback_query.answer(
                "Akses bot tidak tersedia atau sudah dicabut.",
                show_alert=True,
            )
        except Exception:
            pass
    elif update.effective_message:
        await update.effective_message.reply_text(
            "─────────────────────────────\n"
            "  ⛔  Akses Ditolak\n"
            "─────────────────────────────\n\n"
            f"  Telegram ID Anda: `{user_id}`\n\n"
            "  Kirim ID ini kepada owner bot agar ditambahkan.\n"
            "─────────────────────────────",
            parse_mode="Markdown",
        )
    raise ApplicationHandlerStop


async def owner_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Owner-only inline user management."""
    query = update.callback_query
    user_id = update.effective_user.id
    if not is_owner(user_id):
        await query.answer("Fitur ini hanya untuk owner.", show_alert=True)
        return SELECT_VPS_ACTION

    await query.answer()
    action = query.data

    if action in ("owner_users", "owner_list"):
        context.user_data.pop("pending_auth_user", None)
        context.user_data.pop("pending_custom_expiry", None)
        await query.edit_message_text(
            get_owner_users_text(),
            reply_markup=get_owner_users_keyboard(),
        )
        return SELECT_VPS_ACTION

    if action == "owner_add":
        await query.edit_message_text(
            "─────────────────────────────\n"
            "  ➕  Tambah User\n"
            "─────────────────────────────\n\n"
            "  Kirim Telegram User ID. Nama bersifat opsional.\n\n"
            "  Format:\n"
            "  `123456789 Nama User`\n\n"
            "  User ID bisa didapat dari @userinfobot.\n"
            "─────────────────────────────",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Batal", callback_data="owner_users")
            ]]),
        )
        return OWNER_ADD_USER

    if action == "owner_expiry_custom":
        pending = context.user_data.get("pending_auth_user")
        if not pending:
            await query.edit_message_text(
                "Sesi tambah user sudah berakhir. Silakan mulai kembali.",
                reply_markup=get_owner_users_keyboard(),
            )
            return SELECT_VPS_ACTION
        context.user_data["pending_custom_expiry"] = {"mode": "add"}
        await query.edit_message_text(
            "─────────────────────────────\n"
            "  ✏️  Masa Berlaku Manual\n"
            "─────────────────────────────\n\n"
            f"  User: {pending['name']}\n"
            f"  Telegram ID: {pending['user_id']}\n\n"
            "  Kirim jumlah hari antara 1–3650.\n"
            "  Contoh: `14`, `45`, atau `365`\n"
            "─────────────────────────────",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Batal", callback_data="owner_users")
            ]]),
        )
        return OWNER_CUSTOM_EXPIRY

    if action.startswith("owner_expiry_"):
        pending = context.user_data.get("pending_auth_user")
        if not pending:
            await query.edit_message_text(
                "Sesi tambah user sudah berakhir. Silakan mulai kembali.",
                reply_markup=get_owner_users_keyboard(),
            )
            return SELECT_VPS_ACTION
        duration = action.split("owner_expiry_", 1)[1]
        if duration not in ("1", "7", "30", "perm"):
            await query.edit_message_text(
                "Pilihan masa berlaku tidak valid. Silakan ulangi.",
                reply_markup=get_expiry_selection_keyboard(),
            )
            return OWNER_SELECT_EXPIRY
        expires_at = None if duration == "perm" else int(_time.time()) + int(duration) * 86400
        set_authorized_user(
            pending["user_id"], pending["name"], active=True, expires_at=expires_at
        )
        context.user_data.pop("pending_auth_user", None)
        context.user_data.pop("pending_custom_expiry", None)
        record = load_authorized_users()[pending["user_id"]]
        await query.edit_message_text(
            "─────────────────────────────\n"
            "  ✅  User Ditambahkan\n"
            "─────────────────────────────\n\n"
            f"  Nama: {pending['name']}\n"
            f"  Telegram ID: {pending['user_id']}\n"
            f"  Berlaku sampai: {format_expiry(record)}\n"
            "  Status: aktif\n\n"
            "  User dapat mengirim /start dan menambahkan VPS\n"
            "  miliknya sendiri.\n"
            "─────────────────────────────",
            reply_markup=get_owner_users_keyboard(),
        )
        return SELECT_VPS_ACTION

    if action.startswith("owner_detail_"):
        context.user_data.pop("pending_custom_expiry", None)
        target_id = action.split("owner_detail_", 1)[1]
        record = load_authorized_users().get(target_id)
        if not record:
            await query.edit_message_text("User tidak ditemukan.", reply_markup=get_owner_users_keyboard())
            return SELECT_VPS_ACTION
        await query.edit_message_text(
            "─────────────────────────────\n"
            "  👤  Detail User\n"
            "─────────────────────────────\n\n"
            f"  Nama: {record.get('name') or 'User'}\n"
            f"  Telegram ID: {target_id}\n"
            f"  Status: {user_status(record)}\n"
            f"  Berlaku sampai: {format_expiry(record)}\n"
            f"  VPS tersimpan: {count_user_vps(target_id)}\n\n"
            "  User kedaluwarsa otomatis ditolak oleh semua fitur.\n"
            "─────────────────────────────",
            reply_markup=get_owner_user_detail_keyboard(target_id, record),
        )
        return SELECT_VPS_ACTION

    if action.startswith("owner_extend_custom_"):
        target_id = action.split("owner_extend_custom_", 1)[1]
        record = load_authorized_users().get(target_id)
        if not record:
            await query.edit_message_text("User tidak ditemukan.", reply_markup=get_owner_users_keyboard())
            return SELECT_VPS_ACTION
        context.user_data["pending_custom_expiry"] = {
            "mode": "extend",
            "user_id": target_id,
        }
        await query.edit_message_text(
            "─────────────────────────────\n"
            "  ✏️  Perpanjangan Manual\n"
            "─────────────────────────────\n\n"
            f"  User: {record.get('name') or target_id}\n"
            f"  Berlaku sampai: {format_expiry(record)}\n\n"
            "  Kirim tambahan hari antara 1–3650.\n"
            "  Contoh: `14`, `45`, atau `365`\n"
            "─────────────────────────────",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Batal", callback_data=f"owner_detail_{target_id}")
            ]]),
        )
        return OWNER_CUSTOM_EXPIRY

    if action.startswith("owner_extend_"):
        match = re.fullmatch(r"owner_extend_(1|7|30)_([0-9]+)", action)
        if not match:
            return SELECT_VPS_ACTION
        days, target_id = int(match.group(1)), match.group(2)
        users = load_authorized_users()
        record = users.get(target_id)
        if not record:
            await query.edit_message_text("User tidak ditemukan.", reply_markup=get_owner_users_keyboard())
            return SELECT_VPS_ACTION
        current_expiry = record.get("expires_at")
        base = max(int(_time.time()), int(current_expiry or 0))
        record["expires_at"] = base + days * 86400
        record["active"] = True
        users[target_id] = record
        save_authorized_users(users)
        await query.edit_message_text(
            "─────────────────────────────\n"
            "  ✅  Masa Berlaku Diperpanjang\n"
            "─────────────────────────────\n\n"
            f"  User: {record.get('name') or target_id}\n"
            f"  Berlaku sampai: {format_expiry(record)}\n"
            "  Status: aktif\n"
            "─────────────────────────────",
            reply_markup=get_owner_user_detail_keyboard(target_id, record),
        )
        return SELECT_VPS_ACTION

    if action.startswith("owner_permanent_"):
        target_id = action.split("owner_permanent_", 1)[1]
        users = load_authorized_users()
        record = users.get(target_id)
        if not record:
            await query.edit_message_text("User tidak ditemukan.", reply_markup=get_owner_users_keyboard())
            return SELECT_VPS_ACTION
        record["expires_at"] = None
        record["active"] = True
        users[target_id] = record
        save_authorized_users(users)
        await query.edit_message_text(
            "─────────────────────────────\n"
            "  ✅  Akses Dijadikan Permanen\n"
            "─────────────────────────────\n\n"
            f"  User: {record.get('name') or target_id}\n"
            "  Berlaku sampai: Permanen\n"
            "  Status: aktif\n"
            "─────────────────────────────",
            reply_markup=get_owner_user_detail_keyboard(target_id, record),
        )
        return SELECT_VPS_ACTION

    if action == "owner_back":
        context.user_data.pop("pending_auth_user", None)
        context.user_data.pop("pending_custom_expiry", None)
        vps_list = load_vps_list(user_id)
        status = "Pilih VPS atau tambah baru:" if vps_list else "Belum ada VPS. Tambahkan VPS baru:"
        await query.edit_message_text(
            "─────────────────────────────\n"
            "  🖥️  Reinstall OS Bot\n"
            "─────────────────────────────\n\n"
            f"  {status}\n",
            reply_markup=get_vps_list_keyboard(user_id),
        )
        return SELECT_VPS_ACTION

    if action.startswith("owner_toggle_"):
        target_id = action.split("owner_toggle_", 1)[1]
        users = load_authorized_users()
        record = users.get(target_id)
        if not record:
            await query.edit_message_text(
                "User tidak ditemukan atau sudah dihapus.",
                reply_markup=get_owner_users_keyboard(),
            )
        else:
            record["active"] = not bool(record.get("active"))
            users[target_id] = record
            save_authorized_users(users)
            await query.edit_message_text(
                "─────────────────────────────\n"
                "  👤  Status User Diubah\n"
                "─────────────────────────────\n\n"
                f"  User: {record.get('name') or target_id}\n"
                f"  Status: {user_status(record)}\n"
                f"  Berlaku sampai: {format_expiry(record)}\n"
                "─────────────────────────────",
                reply_markup=get_owner_user_detail_keyboard(target_id, record),
            )
        return SELECT_VPS_ACTION

    if action.startswith("owner_deleteyes_"):
        target_id = action.split("owner_deleteyes_", 1)[1]
        remove_authorized_user(target_id)
        await query.edit_message_text(
            get_owner_users_text(),
            reply_markup=get_owner_users_keyboard(),
        )
        return SELECT_VPS_ACTION

    if action.startswith("owner_delete_"):
        target_id = action.split("owner_delete_", 1)[1]
        record = load_authorized_users().get(target_id)
        if not record:
            await query.edit_message_text(
                "User tidak ditemukan.",
                reply_markup=get_owner_users_keyboard(),
            )
            return SELECT_VPS_ACTION
        name = record.get("name") or "User"
        vps_count = count_user_vps(target_id)
        await query.edit_message_text(
            "─────────────────────────────\n"
            "  🗑  Cabut Akses User?\n"
            "─────────────────────────────\n\n"
            f"  Nama: {name}\n"
            f"  Telegram ID: {target_id}\n"
            f"  VPS tersimpan: {vps_count}\n\n"
            "  Akses akan dicabut, tetapi data VPS user tidak\n"
            "  dihapus dan bisa digunakan lagi bila ditambahkan.\n"
            "─────────────────────────────",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🗑 Ya, Cabut Akses", callback_data=f"owner_deleteyes_{target_id}")],
                [InlineKeyboardButton("◀️ Batal", callback_data="owner_users")],
            ]),
        )
        return SELECT_VPS_ACTION

    return SELECT_VPS_ACTION


async def owner_add_user_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Validate a new user, then ask the owner to choose an expiry."""
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("Fitur ini hanya untuk owner.")
        return ConversationHandler.END

    raw = update.message.text.strip()
    parts = raw.split(maxsplit=1)
    target_id = parts[0] if parts else ""
    name = parts[1].strip() if len(parts) > 1 else "User"
    name = re.sub(r"[\r\n\t]+", " ", name)[:40]

    if not target_id.isdigit() or not 1 <= len(target_id) <= 20 or int(target_id) <= 0:
        await update.message.reply_text(
            "❌ Telegram User ID tidak valid.\n\n"
            "Contoh: `123456789 Nama User`\n"
            "Kirim ulang atau tekan /start untuk batal.",
            parse_mode="Markdown",
        )
        return OWNER_ADD_USER

    if target_id == OWNER_ID:
        await update.message.reply_text(
            "ℹ️ ID tersebut adalah owner dan memiliki akses permanen.",
            reply_markup=get_owner_users_keyboard(),
        )
        return SELECT_VPS_ACTION

    context.user_data["pending_auth_user"] = {
        "user_id": target_id,
        "name": name or "User",
    }
    await update.message.reply_text(
        "─────────────────────────────\n"
        "  ⏳  Pilih Masa Berlaku\n"
        "─────────────────────────────\n\n"
        f"  Nama: {name or 'User'}\n"
        f"  Telegram ID: {target_id}\n\n"
        "  Setelah waktu habis, seluruh tombol, pesan, dan\n"
        "  command user akan otomatis ditolak.\n"
        "─────────────────────────────",
        reply_markup=get_expiry_selection_keyboard(),
    )
    return OWNER_SELECT_EXPIRY


async def owner_custom_expiry_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Apply a custom 1-3650 day validity or extension selected by the owner."""
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("Fitur ini hanya untuk owner.")
        return ConversationHandler.END

    raw = update.message.text.strip()
    try:
        days = int(raw)
        if not 1 <= days <= 3650:
            raise ValueError
    except (TypeError, ValueError):
        await update.message.reply_text(
            "❌ Jumlah hari harus berupa angka antara 1–3650.\n\n"
            "Contoh: `14`, `45`, atau `365`\n"
            "Kirim ulang atau tekan /start untuk batal.",
            parse_mode="Markdown",
        )
        return OWNER_CUSTOM_EXPIRY

    operation = context.user_data.get("pending_custom_expiry", {})
    mode = operation.get("mode")

    if mode == "add":
        pending = context.user_data.get("pending_auth_user")
        if not pending:
            await update.message.reply_text(
                "Sesi tambah user sudah berakhir. Silakan mulai kembali.",
                reply_markup=get_owner_users_keyboard(),
            )
            return SELECT_VPS_ACTION
        expires_at = int(_time.time()) + days * 86400
        set_authorized_user(
            pending["user_id"], pending["name"], active=True, expires_at=expires_at
        )
        record = load_authorized_users()[pending["user_id"]]
        context.user_data.pop("pending_auth_user", None)
        context.user_data.pop("pending_custom_expiry", None)
        await update.message.reply_text(
            "─────────────────────────────\n"
            "  ✅  User Ditambahkan\n"
            "─────────────────────────────\n\n"
            f"  Nama: {pending['name']}\n"
            f"  Telegram ID: {pending['user_id']}\n"
            f"  Masa berlaku: {days} hari\n"
            f"  Berlaku sampai: {format_expiry(record)}\n"
            "  Status: aktif\n\n"
            "  Saat kedaluwarsa seluruh akses otomatis ditolak.\n"
            "─────────────────────────────",
            reply_markup=get_owner_users_keyboard(),
        )
        return SELECT_VPS_ACTION

    if mode == "extend":
        target_id = str(operation.get("user_id", ""))
        users = load_authorized_users()
        record = users.get(target_id)
        if not record:
            context.user_data.pop("pending_custom_expiry", None)
            await update.message.reply_text(
                "User tidak ditemukan.",
                reply_markup=get_owner_users_keyboard(),
            )
            return SELECT_VPS_ACTION
        base = max(int(_time.time()), int(record.get("expires_at") or 0))
        record["expires_at"] = base + days * 86400
        record["active"] = True
        users[target_id] = record
        save_authorized_users(users)
        context.user_data.pop("pending_custom_expiry", None)
        await update.message.reply_text(
            "─────────────────────────────\n"
            "  ✅  Masa Berlaku Diperpanjang\n"
            "─────────────────────────────\n\n"
            f"  User: {record.get('name') or target_id}\n"
            f"  Tambahan: {days} hari\n"
            f"  Berlaku sampai: {format_expiry(record)}\n"
            "  Status: aktif\n"
            "─────────────────────────────",
            reply_markup=get_owner_user_detail_keyboard(target_id, record),
        )
        return SELECT_VPS_ACTION

    await update.message.reply_text(
        "Sesi masa berlaku sudah berakhir. Silakan mulai kembali.",
        reply_markup=get_owner_users_keyboard(),
    )
    return SELECT_VPS_ACTION


# ============ Handlers ============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show VPS list or add new."""
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("Tidak ada akses.")
        return ConversationHandler.END

    vps_list = load_vps_list(user_id)
    if vps_list:
        await update.message.reply_text(
            "─────────────────────────────\n"
            "  🖥️  Reinstall OS Bot\n"
            "─────────────────────────────\n\n"
            "  Pilih VPS atau tambah baru:\n",
            reply_markup=get_vps_list_keyboard(user_id),
        )
        return SELECT_VPS_ACTION
    else:
        extra = "\n  Owner dapat mengelola akses user dari menu." if is_owner(user_id) else ""
        await update.message.reply_text(
            "─────────────────────────────\n"
            "  🖥️  Reinstall OS Bot\n"
            "─────────────────────────────\n\n"
            "  Belum ada VPS tersimpan.\n"
            "  Tambahkan VPS milik Anda sendiri."
            f"{extra}\n",
            reply_markup=get_vps_list_keyboard(user_id),
        )
        return SELECT_VPS_ACTION


async def add_vps_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Parse and save new VPS."""
    text = update.message.text.strip()
    data = parse_vps_detail(text)

    if data is None:
        await update.message.reply_text(
            "Format salah! Kirim ulang:\n\n"
            "`ip:port@user:password`\n\n"
            "Contoh: `104.207.xx.xx:22022@root:Digicore@1`",
            parse_mode="Markdown",
        )
        return ADD_VPS

    # Delete message (contains password)
    try:
        await update.message.delete()
    except Exception:
        pass

    # Bulk detection: multiple lines
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if len(lines) > 1:
        # Bulk import
        saved = 0
        failed = []
        vps_list = load_vps_list(update.effective_user.id)
        for line in lines:
            d = parse_vps_detail(line)
            if d:
                exists = any(v['vps_ip']==d['vps_ip'] and v['vps_port']==d['vps_port'] for v in vps_list)
                if not exists:
                    vps_list.append(d)
                    saved += 1
            else:
                failed.append(line)
        if saved>0:
            save_vps_list(update.effective_user.id, vps_list)
            # Use last valid as active
            last = None
            for line in reversed(lines):
                last = parse_vps_detail(line)
                if last:
                    break
            if last:
                context.user_data.update(last)
                await update.message.reply_text(
                    f"─────────────────────────────\n  📂 Bulk Import\n─────────────────────────────\n\n  ✅ {saved} VPS disimpan\n  ❌ {len(failed)} gagal\n\n" + get_vps_info_text(last) + "\n\n  Pilih aksi:",
                    reply_markup=get_action_keyboard(),
                )
                try: await update.message.delete()
                except: pass
                return SELECT_VPS_ACTION
        await update.message.reply_text(f"❌ Gagal bulk. {len(failed)} baris error. Cek format `ip:port@user:pass` per baris.")
        return ADD_VPS

    # Save to VPS list
    user_id = update.effective_user.id
    vps_list = load_vps_list(user_id)
    # Check if already exists
    exists = any(v['vps_ip'] == data['vps_ip'] and v['vps_port'] == data['vps_port'] for v in vps_list)
    if not exists:
        vps_list.append(data)
        save_vps_list(user_id, vps_list)

    # Set as active VPS
    context.user_data.update(data)

    # Show action menu
    await update.message.reply_text(
        get_vps_info_text(data) + "\n\n  ✅ VPS tersimpan!\n\n  Pilih aksi:",
        reply_markup=get_action_keyboard(),
    )
    return SELECT_VPS_ACTION



# ============ Wizard Handlers ============
async def wiz_ip_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    ip = update.message.text.strip()
    # basic validation
    import re
    if not re.match(r"^[0-9.]+$|^[a-zA-Z0-9.-]+$", ip) or len(ip) < 7:
        await update.message.reply_text("❌ IP tidak valid. Contoh: `104.207.93.92`", parse_mode="Markdown")
        return WIZ_IP
    context.user_data["wiz"]["vps_ip"] = ip
    await update.message.reply_text(
        f"✅ IP: `{ip}`\n\n"
        "─────────────────────────────\n"
        "  🚀 Step 2/4 - Pilih Port SSH\n"
        "─────────────────────────────",
        parse_mode="Markdown",
        reply_markup=get_wizard_port_keyboard(),
    )
    return WIZ_PORT

async def wiz_port_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    d = query.data
    if d == "wiz_cancel":
        await query.edit_message_text("❌ Dibatalkan.", reply_markup=get_vps_list_keyboard(update.effective_user.id))
        return SELECT_VPS_ACTION
    if d == "wiz_port_custom":
        await query.edit_message_text(
            "─────────────────────────────\n"
            "  ✏️ Port Custom\n"
            "─────────────────────────────\n\n"
            "Ketik port manual (contoh: `22022`):",
            parse_mode="Markdown",
        )
        return WIZ_PORT
    # preset port
    port = int(d.replace("wiz_port_", ""))
    context.user_data["wiz"]["vps_port"] = port
    await query.edit_message_text(
        f"✅ Port: `{port}`\n\n"
        "─────────────────────────────\n"
        "  🚀 Step 3/4 - Pilih User\n"
        "─────────────────────────────",
        parse_mode="Markdown",
        reply_markup=get_wizard_user_keyboard(),
    )
    return WIZ_USER

async def wiz_port_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        port = int(update.message.text.strip())
        if not 1 <= port <= 65535:
            raise ValueError
    except:
        await update.message.reply_text("❌ Port harus angka 1-65535. Contoh: `22` atau `22022`")
        return WIZ_PORT
    context.user_data["wiz"]["vps_port"] = port
    await update.message.reply_text(
        f"✅ Port: `{port}`\n\n"
        "─────────────────────────────\n"
        "  🚀 Step 3/4 - Pilih User\n"
        "─────────────────────────────",
        reply_markup=get_wizard_user_keyboard(),
    )
    return WIZ_USER

async def wiz_user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    d = query.data
    if d == "wiz_cancel":
        await query.edit_message_text("❌ Dibatalkan.", reply_markup=get_vps_list_keyboard(update.effective_user.id))
        return SELECT_VPS_ACTION
    if d == "wiz_user_custom":
        await query.edit_message_text(
            "─────────────────────────────\n"
            "  ✏️ User Custom\n"
            "─────────────────────────────\n\n"
            "Ketik username (contoh: `root`):",
            parse_mode="Markdown",
        )
        return WIZ_USER
    user = d.replace("wiz_user_", "")
    context.user_data["wiz"]["vps_user"] = user
    wiz = context.user_data["wiz"]
    await query.edit_message_text(
        f"✅ User: `{user}`\n\n"
        "─────────────────────────────\n"
        "  🚀 Step 4/4 - Password\n"
        "─────────────────────────────\n\n"
        f"  🎯 {wiz['vps_ip']}:{wiz['vps_port']}@{wiz['vps_user']}:****\n\n"
        "Kirim password VPS:",
        parse_mode="Markdown",
    )
    return WIZ_PASS

async def wiz_user_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.message.text.strip()
    if not user or " " in user:
        await update.message.reply_text("❌ Username tidak valid. Contoh: `root`")
        return WIZ_USER
    context.user_data["wiz"]["vps_user"] = user
    wiz = context.user_data["wiz"]
    await update.message.reply_text(
        f"✅ User: `{user}`\n\n"
        "─────────────────────────────\n"
        "  🚀 Step 4/4 - Password\n"
        "─────────────────────────────\n\n"
        f"  🎯 {wiz['vps_ip']}:{wiz['vps_port']}@{wiz['vps_user']}:****\n\n"
        "Kirim password VPS:",
        parse_mode="Markdown",
    )
    return WIZ_PASS

async def wiz_pass_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    pwd = update.message.text.strip()
    try:
        await update.message.delete()
    except:
        pass
    if len(pwd) < 3:
        await update.message.reply_text("❌ Password terlalu pendek.")
        return WIZ_PASS
    wiz = context.user_data.get("wiz", {})
    data = {
        "vps_ip": wiz.get("vps_ip"),
        "vps_port": wiz.get("vps_port", 22),
        "vps_user": wiz.get("vps_user", "root"),
        "vps_pass": pwd,
    }
    # Test koneksi cepat
    await update.message.reply_text(f"⏳ Test koneksi ke {data['vps_ip']}:{data['vps_port']}...")
    test = await ssh_exec(data, "echo OK")
    ok = "OK" in test
    status = "✅ Koneksi OK" if ok else f"⚠️ Test gagal: {test[:80]} - tetap disimpan"

    # Save
    user_id = update.effective_user.id
    vps_list = load_vps_list(user_id)
    exists = any(v['vps_ip']==data['vps_ip'] and v['vps_port']==data['vps_port'] for v in vps_list)
    if not exists:
        vps_list.append(data)
        save_vps_list(user_id, vps_list)
    context.user_data.update(data)
    context.user_data.pop("wiz", None)
    await update.message.reply_text(
        get_vps_info_text(data) + f"\n\n  {status}\n\n  ✅ VPS tersimpan!\n\n  Pilih aksi:",
        reply_markup=get_action_keyboard(),
    )
    return SELECT_VPS_ACTION

async def select_vps(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle VPS selection or add new."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id

    if query.data == "addvps":
        await query.edit_message_text(
            "─────────────────────────────\n"
            "  ➕  Tambah VPS Baru\n"
            "─────────────────────────────\n\n"
            "  Pilih cara tambah biar gampang:\n",
            reply_markup=get_add_method_keyboard(),
        )
        return SELECT_VPS_ACTION

    # Handle add method choices
    if query.data == "add_wizard":
        context.user_data["wiz"] = {}
        await query.edit_message_text(
            "─────────────────────────────\n"
            "  🚀 Wizard Cepat - Step 1/4\n"
            "─────────────────────────────\n\n"
            "  📍 Kirim IP VPS saja:\n\n"
            "  Contoh: `104.207.93.92`\n\n"
            "  (hanya IP, tanpa port/user/pass)",
            parse_mode="Markdown",
        )
        return WIZ_IP
    if query.data == "add_format":
        await query.edit_message_text(
            "─────────────────────────────\n"
            "  📋 Format Lengkap\n"
            "─────────────────────────────\n\n"
            "  Kirim detail VPS:\n\n"
            "  `ip:port@user:password`\n\n"
            "  Contoh:\n"
            "  `104.207.xx.xx:22022@root:Digicore@1`\n\n"
            "  Port kosong = auto 22",
            parse_mode="Markdown",
        )
        return ADD_VPS
    if query.data == "add_bulk":
        await query.edit_message_text(
            get_bulk_example_text(),
            parse_mode="Markdown",
        )
        return ADD_VPS
    if query.data == "add_back":
        await query.edit_message_text(
            "─────────────────────────────\n"
            "  🖥️  Reinstall OS Bot\n"
            "─────────────────────────────\n\n"
            "  Pilih VPS atau tambah baru:\n",
            reply_markup=get_vps_list_keyboard(user_id),
        )
        return SELECT_VPS_ACTION

    if query.data.startswith("selvps_"):
        idx = int(query.data.replace("selvps_", ""))
        vps_list = load_vps_list(user_id)
        if idx < len(vps_list):
            data = vps_list[idx]
            context.user_data.update(data)
            await query.edit_message_text(
                get_vps_info_text(data) + "\n\n  Pilih aksi:",
                reply_markup=get_action_keyboard(),
            )
            return SELECT_VPS_ACTION

    return SELECT_VPS_ACTION


async def handle_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle action buttons."""
    query = update.callback_query
    await query.answer()
    data = context.user_data
    user_id = update.effective_user.id
    action = query.data

    if action == "act_back":
        await query.edit_message_text(
            "─────────────────────────────\n"
            "  🖥️  Reinstall OS Bot\n"
            "─────────────────────────────\n\n"
            "  Pilih VPS atau tambah baru:\n",
            reply_markup=get_vps_list_keyboard(user_id),
        )
        return SELECT_VPS_ACTION

    if action == "act_delete":
        vps_list = load_vps_list(user_id)
        vps_list = [v for v in vps_list if not (v['vps_ip'] == data.get('vps_ip') and v['vps_port'] == data.get('vps_port'))]
        save_vps_list(user_id, vps_list)
        await query.edit_message_text(
            f"  🗑 VPS {data.get('vps_ip')} dihapus!\n\n",
            reply_markup=get_vps_list_keyboard(user_id),
        )
        return SELECT_VPS_ACTION

    if action == "act_reinstall":
        keyboard = [
            [InlineKeyboardButton("WINDOWS", callback_data="cat_windows")],
            [InlineKeyboardButton("LINUX", callback_data="cat_linux")],
            [InlineKeyboardButton("◀️ Kembali", callback_data="act_back_menu")],
        ]
        await query.edit_message_text(
            get_vps_info_text(data) + "\n\n  Pilih kategori OS:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return SELECT_OS

    if action == "act_ssh":
        keyboard = [[InlineKeyboardButton("◀️ Kembali", callback_data="act_back_menu")]]
        await query.edit_message_text(
            get_vps_info_text(data) + "\n\n"
            "  💻 Kirim command SSH:\n\n"
            "  Contoh: `uptime` atau `df -h`\n\n"
            "  Atau klik Kembali untuk menu.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return SSH_CMD

    if action == "act_info":
        await query.edit_message_text(f"  ⏳ Mengambil info {data['vps_ip']}...")
        info_text = await get_vps_system_info(data)
        keyboard = [[InlineKeyboardButton("◀️ Kembali", callback_data="act_back_menu")]]
        await query.edit_message_text(info_text, reply_markup=InlineKeyboardMarkup(keyboard))
        return SELECT_VPS_ACTION

    if action == "act_reboot":
        result = await ssh_exec(data, "reboot")
        await query.edit_message_text(
            "─────────────────────────────\n"
            "  🔄  VPS Rebooting\n"
            "─────────────────────────────\n\n"
            f"  🎯 {data['vps_ip']}\n"
            "  Status: Reboot sent!\n"
            "  Online dalam 1-3 menit.\n\n"
            "─────────────────────────────",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Kembali", callback_data="act_back_menu")]]),
        )
        return SELECT_VPS_ACTION

    if action == "act_status":
        vps_ip = data["vps_ip"]
        await query.edit_message_text(f"  📡 Checking {vps_ip}...")
        proc = await asyncio.create_subprocess_exec(
            "ping", "-c", "3", "-W", "5", vps_ip,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        if proc.returncode == 0:
            status_text = f"  ✅ {vps_ip} ONLINE"
        else:
            status_text = f"  ❌ {vps_ip} OFFLINE"
        keyboard = [[InlineKeyboardButton("◀️ Kembali", callback_data="act_back_menu")]]
        await query.edit_message_text(
            "─────────────────────────────\n"
            "  📡  VPS Status\n"
            "─────────────────────────────\n\n"
            f"{status_text}\n\n"
            "─────────────────────────────",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return SELECT_VPS_ACTION

    if action == "act_editpass":
        keyboard = [[InlineKeyboardButton("◀️ Kembali", callback_data="act_back_menu")]]
        await query.edit_message_text(
            get_vps_info_text(data) + "\n\n"
            "  🔑 Edit Password VPS\n\n"
            "  Kirim password baru:\n\n"
            "  Contoh: `MyNewPass123`\n\n"
            "  Password akan diubah via SSH.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return EDIT_PASS

    if action == "act_editport":
        keyboard = [[InlineKeyboardButton("◀️ Kembali", callback_data="act_back_menu")]]
        await query.edit_message_text(
            get_vps_info_text(data) + "\n\n"
            "  🔧 Edit Port SSH\n\n"
            f"  Port sekarang: `{data['vps_port']}`\n\n"
            "  Kirim port baru yang mau DITAMBAHKAN & diaktifkan\n"
            "  (contoh: `22`).\n\n"
            "  ⚠️ Port lama (`22022` dll) akan DIPERTAHANKAN,\n"
            "  jadi dua-duanya tetap aktif.\n\n"
            "  Contoh: `22`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return EDIT_PORT

    if action == "act_openport":
        keyboard = [
            [InlineKeyboardButton("⚠️ Lanjut", callback_data="act_openport_confirm1")],
            [InlineKeyboardButton("◀️ Batal", callback_data="act_back_menu")],
        ]
        await query.edit_message_text(
            "─────────────────────────────\n"
            "  ⚠️  PERINGATAN KEAMANAN\n"
            "─────────────────────────────\n\n"
            f"  Target: {data['vps_ip']}\n\n"
            "  Open All Port akan:\n"
            "  • Menonaktifkan firewall OS\n"
            "  • Menghapus aturan iptables/nftables\n"
            "  • Mengizinkan semua trafik masuk/keluar\n\n"
            "  Hanya port dengan aplikasi aktif yang dapat\n"
            "  diakses. Firewall provider tetap berlaku.\n\n"
            "  Lanjut ke konfirmasi berikutnya?\n"
            "─────────────────────────────",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return SELECT_VPS_ACTION

    if action == "act_openport_confirm1":
        keyboard = [
            [InlineKeyboardButton("🔓 YA, BUKA SEMUA PORT", callback_data="act_openport_execute")],
            [InlineKeyboardButton("◀️ Batal", callback_data="act_back_menu")],
        ]
        await query.edit_message_text(
            "─────────────────────────────\n"
            "  🚨  KONFIRMASI TERAKHIR\n"
            "─────────────────────────────\n\n"
            f"  VPS: {data['vps_ip']}\n\n"
            "  Tindakan ini membuka firewall OS sepenuhnya\n"
            "  dan dapat meningkatkan risiko serangan.\n\n"
            "  Tekan tombol merah hanya jika benar-benar yakin.\n"
            "─────────────────────────────",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return SELECT_VPS_ACTION

    if action == "act_openport_execute":
        await query.edit_message_text(
            "─────────────────────────────\n"
            f"  🔓  Open All Port - {data['vps_ip']}\n"
            "─────────────────────────────\n\n"
            "  ⏳ Backup dan membuka firewall OS...\n"
            "─────────────────────────────"
        )
        openport_cmd = r'''
set -u
if [ "$(id -u)" -ne 0 ]; then
    echo "OPENPORT_ERROR: membutuhkan akses root"
    exit 1
fi

STAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_DIR="/var/backups/reinstallos/firewall-$STAMP"
mkdir -p "$BACKUP_DIR" || {
    echo "OPENPORT_ERROR: gagal membuat backup"
    exit 1
}

# Backup kondisi dan aturan sebelum perubahan.
(ufw status verbose 2>/dev/null || true) > "$BACKUP_DIR/ufw-status.txt"
(iptables-save 2>/dev/null || true) > "$BACKUP_DIR/iptables-v4.rules"
(ip6tables-save 2>/dev/null || true) > "$BACKUP_DIR/iptables-v6.rules"
(nft list ruleset 2>/dev/null || true) > "$BACKUP_DIR/nftables.rules"
(firewall-cmd --list-all-zones 2>/dev/null || true) > "$BACKUP_DIR/firewalld-zones.txt"
(systemctl is-enabled ufw firewalld nftables netfilter-persistent 2>/dev/null || true) > "$BACKUP_DIR/service-enabled.txt"

FAILURES=""
WARNINGS=""
failed() { FAILURES="$FAILURES $1"; }
warned() { WARNINGS="$WARNINGS $1"; }

# Nonaktifkan frontend firewall yang umum dan cegah aktif kembali setelah reboot.
if command -v ufw >/dev/null 2>&1; then
    ufw --force disable >/dev/null 2>&1 || failed "ufw"
fi
if systemctl list-unit-files firewalld.service --no-legend 2>/dev/null | grep -q firewalld; then
    systemctl disable --now firewalld >/dev/null 2>&1 || failed "firewalld"
fi
if systemctl list-unit-files nftables.service --no-legend 2>/dev/null | grep -q nftables; then
    systemctl disable --now nftables >/dev/null 2>&1 || failed "nftables-service"
fi

# Bersihkan ruleset native terlebih dahulu, kemudian pastikan policy legacy ACCEPT.
if command -v nft >/dev/null 2>&1; then
    nft flush ruleset >/dev/null 2>&1 || failed "nft-flush"
fi
if command -v iptables >/dev/null 2>&1; then
    iptables -w 5 -F >/dev/null 2>&1 || failed "iptables-flush"
    iptables -w 5 -X >/dev/null 2>&1 || true
    iptables -w 5 -P INPUT ACCEPT >/dev/null 2>&1 || failed "iptables-input"
    iptables -w 5 -P FORWARD ACCEPT >/dev/null 2>&1 || failed "iptables-forward"
    iptables -w 5 -P OUTPUT ACCEPT >/dev/null 2>&1 || failed "iptables-output"
fi
if command -v ip6tables >/dev/null 2>&1; then
    ip6tables -w 5 -F >/dev/null 2>&1 || failed "ip6tables-flush"
    ip6tables -w 5 -X >/dev/null 2>&1 || true
    ip6tables -w 5 -P INPUT ACCEPT >/dev/null 2>&1 || failed "ip6tables-input"
    ip6tables -w 5 -P FORWARD ACCEPT >/dev/null 2>&1 || failed "ip6tables-forward"
    ip6tables -w 5 -P OUTPUT ACCEPT >/dev/null 2>&1 || failed "ip6tables-output"
fi

# Simpan aturan kosong/ACCEPT bila persistence tersedia.
if command -v netfilter-persistent >/dev/null 2>&1; then
    netfilter-persistent save >/dev/null 2>&1 || warned "persistence-save"
else
    warned "netfilter-persistent-tidak-terpasang"
fi
iptables-save > /etc/iptables.rules 2>/dev/null || warned "iptables-rules-save"
ip6tables-save > /etc/ip6tables.rules 2>/dev/null || true

# Verifikasi hasil; marker sukses hanya diberikan bila tindakan penting berhasil.
if command -v iptables >/dev/null 2>&1; then
    iptables -S 2>/dev/null | grep -q '^-P INPUT ACCEPT$' || failed "verify-input"
    iptables -S 2>/dev/null | grep -q '^-P FORWARD ACCEPT$' || failed "verify-forward"
    iptables -S 2>/dev/null | grep -q '^-P OUTPUT ACCEPT$' || failed "verify-output"
fi
if command -v ip6tables >/dev/null 2>&1; then
    ip6tables -S 2>/dev/null | grep -q '^-P INPUT ACCEPT$' || failed "verify-ipv6-input"
fi
if command -v nft >/dev/null 2>&1 && nft list ruleset 2>/dev/null | grep -Eq '[[:space:]](drop|reject)([[:space:]]|$)'; then
    failed "verify-nft-drop-rule"
fi
if systemctl is-active --quiet firewalld 2>/dev/null; then failed "verify-firewalld"; fi
if ufw status 2>/dev/null | grep -qi '^Status: active'; then failed "verify-ufw"; fi

printf 'BACKUP_DIR:%s\n' "$BACKUP_DIR"
printf 'OPENPORT_WARNINGS:%s\n' "${WARNINGS:-none}"
if [ -n "$FAILURES" ]; then
    printf 'OPENPORT_ERROR:%s\n' "$FAILURES"
    exit 1
fi
echo "OPENPORT_DONE"
'''
        result = await ssh_exec(data, openport_cmd)
        keyboard = [[InlineKeyboardButton("◀️ Kembali", callback_data="act_back_menu")]]
        if "OPENPORT_DONE" in result:
            backup_line = next((ln for ln in result.splitlines() if ln.startswith("BACKUP_DIR:")), "BACKUP_DIR:-")
            warning_line = next((ln for ln in result.splitlines() if ln.startswith("OPENPORT_WARNINGS:")), "OPENPORT_WARNINGS:none")
            await query.edit_message_text(
                "─────────────────────────────\n"
                "  ✅  Firewall OS Terbuka\n"
                "─────────────────────────────\n\n"
                f"  🎯 {data['vps_ip']}\n\n"
                "  • Firewall OS dinonaktifkan\n"
                "  • Policy IPv4/IPv6: ACCEPT\n"
                "  • Aturan lama sudah dibackup\n\n"
                f"  {backup_line}\n"
                f"  {warning_line}\n\n"
                "  Catatan: hanya service yang listening dapat\n"
                "  diakses dan firewall provider tetap berlaku.\n"
                "─────────────────────────────",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        else:
            await query.edit_message_text(
                "─────────────────────────────\n"
                "  ❌  Open All Port Gagal\n"
                "─────────────────────────────\n\n"
                f"{result[:2500]}\n\n"
                "  Tidak ada status sukses palsu. Periksa pesan\n"
                "  error dan backup sebelum mencoba kembali.\n"
                "─────────────────────────────",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        return SELECT_VPS_ACTION

    if action == "act_back_menu":
        await query.edit_message_text(
            get_vps_info_text(data) + "\n\n  Pilih aksi:",
            reply_markup=get_action_keyboard(),
        )
        return SELECT_VPS_ACTION

    return SELECT_VPS_ACTION



async def ssh_cmd_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Execute SSH command from chat."""
    data = context.user_data
    cmd_text = update.message.text.strip()

    await update.message.reply_text(f"⏳ `{cmd_text}`...", parse_mode="Markdown")

    result = await ssh_exec(data, cmd_text)
    if len(result) > 3000:
        result = result[:3000] + "\n... (truncated)"

    keyboard = [[InlineKeyboardButton("◀️ Menu", callback_data="act_back_menu")]]
    await update.message.reply_text(
        "─────────────────────────────\n"
        "  💻  SSH Result\n"
        "─────────────────────────────\n\n"
        f"  ⌨️  {cmd_text}\n\n"
        f"{result}\n\n"
        "─────────────────────────────\n\n"
        "Kirim command lain atau klik Menu.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return SSH_CMD


async def edit_pass_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle new password input and change it via SSH."""
    data = context.user_data
    new_pass = update.message.text.strip()

    # Delete message (contains password)
    try:
        await update.message.delete()
    except Exception:
        pass

    if not new_pass or len(new_pass) < 4:
        await update.message.reply_text(
            "❌ Password terlalu pendek (min 4 karakter).\n"
            "Kirim ulang atau /start untuk batal.",
        )
        return EDIT_PASS

    await update.message.reply_text(f"⏳ Mengubah password VPS {data['vps_ip']}...")

    # Change password via SSH
    change_cmd = (
        f"echo 'root:{new_pass}' | chpasswd 2>/dev/null && "
        f"echo '{data['vps_user']}:{new_pass}' | chpasswd 2>/dev/null && "
        "echo 'PASS_CHANGED'"
    )
    result = await ssh_exec(data, change_cmd)

    if "PASS_CHANGED" in result:
        # Update saved VPS data
        old_pass = data['vps_pass']
        data['vps_pass'] = new_pass
        context.user_data['vps_pass'] = new_pass

        # Update in JSON file
        user_id = update.effective_user.id
        vps_list = load_vps_list(user_id)
        for v in vps_list:
            if v['vps_ip'] == data['vps_ip'] and v['vps_port'] == data['vps_port']:
                v['vps_pass'] = new_pass
                break
        save_vps_list(user_id, vps_list)

        keyboard = [[InlineKeyboardButton("◀️ Menu", callback_data="act_back_menu")]]
        await update.message.reply_text(
            "─────────────────────────────\n"
            "  ✅  Password Diubah!\n"
            "─────────────────────────────\n\n"
            f"  🎯 {data['vps_ip']}:{data['vps_port']}\n"
            f"  👤 User: {data['vps_user']}\n"
            f"  🔑 Pass: {new_pass}\n\n"
            "  Data VPS juga diupdate.\n\n"
            "─────────────────────────────",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    else:
        keyboard = [[InlineKeyboardButton("◀️ Menu", callback_data="act_back_menu")]]
        await update.message.reply_text(
            "─────────────────────────────\n"
            "  ❌  Gagal Ubah Password\n"
            "─────────────────────────────\n\n"
            f"  {result}\n\n"
            "─────────────────────────────",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    return SELECT_VPS_ACTION


async def edit_port_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Add and verify a new SSH port while keeping the old port active."""
    data = context.user_data
    new_port_text = update.message.text.strip()

    try:
        new_port = int(new_port_text)
        if not 1 <= new_port <= 65535:
            raise ValueError
        cur_port = int(data["vps_port"])
    except (ValueError, TypeError, KeyError):
        await update.message.reply_text(
            "❌ Port harus angka 1-65535. Contoh: `22`\n"
            "Kirim ulang atau /start untuk batal.",
            parse_mode="Markdown",
        )
        return EDIT_PORT

    if new_port == cur_port:
        await update.message.reply_text(
            f"✅ Port `{new_port}` sudah menjadi port aktif di data bot.\n"
            "Kirim port lain atau /start untuk batal.",
            parse_mode="Markdown",
        )
        return EDIT_PORT

    await update.message.reply_text(
        f"⏳ Menambahkan port {new_port} ke {data['vps_ip']}...\n"
        f"Port lama {cur_port} akan tetap dipertahankan."
    )

    # Managed drop-in keeps the old/default port and every previously added port.
    # The script validates sshd, handles Ubuntu ssh.socket, verifies both listeners,
    # and restores the previous configuration if activation fails.
    cmd = f'''
set -u
NEW_PORT={new_port}
OLD_PORT={cur_port}
CFG=/etc/ssh/sshd_config
DROPIN_DIR=/etc/ssh/sshd_config.d
MANAGED="$DROPIN_DIR/99-reinstallos-ports.conf"

if [ "$(id -u)" -ne 0 ]; then
    echo "PORT_ERROR: membutuhkan akses root"
    exit 1
fi
if [ ! -f "$CFG" ] || ! command -v sshd >/dev/null 2>&1; then
    echo "PORT_ERROR: konfigurasi atau binary sshd tidak ditemukan"
    exit 1
fi

STAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_DIR="/var/backups/reinstallos/ssh-port-$STAMP"
mkdir -p "$BACKUP_DIR" || {{ echo "PORT_ERROR: gagal membuat backup"; exit 1; }}
cp -a "$CFG" "$BACKUP_DIR/sshd_config"
mkdir -p "$DROPIN_DIR"
if [ -f "$MANAGED" ]; then
    cp -a "$MANAGED" "$BACKUP_DIR/99-reinstallos-ports.conf"
    echo yes > "$BACKUP_DIR/managed-existed"
else
    echo no > "$BACKUP_DIR/managed-existed"
fi

restore_config() {{
    cp -a "$BACKUP_DIR/sshd_config" "$CFG"
    if [ "$(cat "$BACKUP_DIR/managed-existed")" = yes ]; then
        cp -a "$BACKUP_DIR/99-reinstallos-ports.conf" "$MANAGED"
    else
        rm -f "$MANAGED"
    fi
    sshd -t >/dev/null 2>&1 || true
    systemctl daemon-reload >/dev/null 2>&1 || true
    if systemctl is-enabled --quiet ssh.socket 2>/dev/null || systemctl is-active --quiet ssh.socket 2>/dev/null; then
        systemctl restart ssh.socket >/dev/null 2>&1 || true
        systemctl restart ssh.service >/dev/null 2>&1 || true
    else
        systemctl reload sshd >/dev/null 2>&1 || systemctl reload ssh >/dev/null 2>&1 || \
        service ssh reload >/dev/null 2>&1 || service sshd reload >/dev/null 2>&1 || true
    fi
}}

# Ensure the standard drop-in directory is actually included.
if ! grep -Eq '^[[:space:]]*Include[[:space:]].*sshd_config[.]d/[*][.]conf' "$CFG"; then
    sed -i '1iInclude /etc/ssh/sshd_config.d/*.conf' "$CFG" || {{
        echo "PORT_ERROR: gagal menambahkan Include sshd_config.d"
        restore_config
        exit 1
    }}
fi

TMP=$(mktemp)
if [ -f "$MANAGED" ]; then
    cat "$MANAGED" > "$TMP"
else
    printf '%s\n' '# Managed by Reinstall OS Bot - keep old ports active' > "$TMP"
fi

# If the old port was implicit (default 22), make it explicit before adding another.
EXPLICIT_PORTS=$(grep -RhsE '^[[:space:]]*Port[[:space:]]+[0-9]+' "$CFG" "$DROPIN_DIR"/*.conf 2>/dev/null | awk '{{print $2}}' | sort -nu || true)
if [ -z "$EXPLICIT_PORTS" ] && ! grep -Eq "^[[:space:]]*Port[[:space:]]+$OLD_PORT([[:space:]]|$)" "$TMP"; then
    echo "Port $OLD_PORT" >> "$TMP"
fi
if ! grep -Eq "^[[:space:]]*Port[[:space:]]+$NEW_PORT([[:space:]]|$)" "$TMP"; then
    echo "Port $NEW_PORT" >> "$TMP"
fi
install -o root -g root -m 0644 "$TMP" "$MANAGED"
rm -f "$TMP"

# Validate before touching the running SSH listener.
if ! sshd -t >/dev/null 2>&1; then
    echo "PORT_ERROR: sshd -t gagal; konfigurasi di-rollback"
    restore_config
    exit 1
fi
EFFECTIVE=$(sshd -T 2>/dev/null | awk '$1 == "port" {{print $2}}' | sort -nu)
if ! printf '%s\n' "$EFFECTIVE" | grep -qx "$OLD_PORT" || ! printf '%s\n' "$EFFECTIVE" | grep -qx "$NEW_PORT"; then
    echo "PORT_ERROR: port lama/baru tidak ada di konfigurasi efektif; rollback"
    restore_config
    exit 1
fi

# SELinux needs an explicit ssh_port_t mapping for non-standard ports.
if command -v getenforce >/dev/null 2>&1 && [ "$(getenforce 2>/dev/null)" = Enforcing ]; then
    if command -v semanage >/dev/null 2>&1; then
        semanage port -a -t ssh_port_t -p tcp "$NEW_PORT" >/dev/null 2>&1 || \
        semanage port -m -t ssh_port_t -p tcp "$NEW_PORT" >/dev/null 2>&1 || {{
            echo "PORT_ERROR: gagal menambahkan SELinux ssh_port_t; rollback"
            restore_config
            exit 1
        }}
    else
        echo "PORT_ERROR: SELinux Enforcing tetapi semanage tidak tersedia; rollback"
        restore_config
        exit 1
    fi
fi

# Open only the new SSH port in common host firewalls.
if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -qi '^Status: active'; then
    ufw allow "$NEW_PORT/tcp" >/dev/null 2>&1 || {{
        echo "PORT_ERROR: gagal membuka UFW; rollback"
        restore_config
        exit 1
    }}
fi
if command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld 2>/dev/null; then
    firewall-cmd --permanent --add-port="$NEW_PORT/tcp" >/dev/null 2>&1 && \
    firewall-cmd --reload >/dev/null 2>&1 || {{
        echo "PORT_ERROR: gagal membuka firewalld; rollback"
        restore_config
        exit 1
    }}
fi
if command -v iptables >/dev/null 2>&1 && iptables -S INPUT 2>/dev/null | grep -Eq '(^-P INPUT DROP$|-j (DROP|REJECT))'; then
    iptables -C INPUT -p tcp --dport "$NEW_PORT" -j ACCEPT >/dev/null 2>&1 || \
    iptables -I INPUT 1 -p tcp --dport "$NEW_PORT" -j ACCEPT >/dev/null 2>&1 || true
fi
if command -v ip6tables >/dev/null 2>&1 && ip6tables -S INPUT 2>/dev/null | grep -Eq '(^-P INPUT DROP$|-j (DROP|REJECT))'; then
    ip6tables -C INPUT -p tcp --dport "$NEW_PORT" -j ACCEPT >/dev/null 2>&1 || \
    ip6tables -I INPUT 1 -p tcp --dport "$NEW_PORT" -j ACCEPT >/dev/null 2>&1 || true
fi

# Activate configuration for both classic ssh.service and socket-activated SSH.
ACTIVATE_OK=0
if systemctl is-enabled --quiet ssh.socket 2>/dev/null || systemctl is-active --quiet ssh.socket 2>/dev/null; then
    systemctl daemon-reload >/dev/null 2>&1 && \
    systemctl restart ssh.socket >/dev/null 2>&1 && \
    systemctl restart ssh.service >/dev/null 2>&1 && ACTIVATE_OK=1
else
    systemctl reload sshd >/dev/null 2>&1 && ACTIVATE_OK=1 || \
    systemctl reload ssh >/dev/null 2>&1 && ACTIVATE_OK=1 || \
    service ssh reload >/dev/null 2>&1 && ACTIVATE_OK=1 || \
    service sshd reload >/dev/null 2>&1 && ACTIVATE_OK=1
fi
if [ "$ACTIVATE_OK" -ne 1 ]; then
    echo "PORT_ERROR: gagal mengaktifkan SSH; konfigurasi di-rollback"
    restore_config
    exit 1
fi
sleep 2

is_listening() {{
    ss -H -ltn 2>/dev/null | awk '{{print $4}}' | grep -Eq ":$1$"
}}
if ! is_listening "$OLD_PORT"; then
    echo "PORT_ERROR: port lama berhenti listening; rollback darurat"
    restore_config
    exit 1
fi
if ! is_listening "$NEW_PORT"; then
    echo "PORT_ERROR: port baru belum listening; konfigurasi di-rollback"
    restore_config
    exit 1
fi

printf 'BACKUP_DIR:%s\n' "$BACKUP_DIR"
printf 'PORTS_NOW:%s\n' "$(sshd -T 2>/dev/null | awk '$1 == "port" {{print $2}}' | sort -nu | tr '\n' ' ')"
echo "PORT_CONFIGURED"
'''
    result = await ssh_exec(data, cmd)
    keyboard = [[InlineKeyboardButton("◀️ Menu", callback_data="act_back_menu")]]

    if "PORT_CONFIGURED" not in result:
        await update.message.reply_text(
            "─────────────────────────────\n"
            "  ❌  Gagal Menambahkan Port\n"
            "─────────────────────────────\n\n"
            f"{result[:2500]}\n\n"
            f"  Data bot tetap memakai port {cur_port}.\n"
            "  Konfigurasi otomatis di-rollback jika aktivasi gagal.\n"
            "─────────────────────────────",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return SELECT_VPS_ACTION

    # Verify from the bot host, not only from inside the target VPS.
    test_data = dict(data)
    test_data["vps_port"] = new_port
    test = await ssh_exec(test_data, "printf REINSTALLOS_PORT_TEST_OK")
    test_ok = "REINSTALLOS_PORT_TEST_OK" in test
    ports_line = next((ln for ln in result.splitlines() if ln.startswith("PORTS_NOW:")), "PORTS_NOW:-")
    backup_line = next((ln for ln in result.splitlines() if ln.startswith("BACKUP_DIR:")), "BACKUP_DIR:-")

    if not test_ok:
        await update.message.reply_text(
            "─────────────────────────────\n"
            "  ⚠️  Port Baru Belum Bisa Diakses\n"
            "─────────────────────────────\n\n"
            f"  🎯 {data['vps_ip']}:{new_port}\n"
            f"  {ports_line}\n"
            f"  {backup_line}\n\n"
            "  SSH sudah listening secara lokal, tetapi koneksi\n"
            "  dari server bot gagal. Periksa firewall provider.\n\n"
            f"  Data bot tetap memakai port lama {cur_port}.\n"
            "─────────────────────────────",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return SELECT_VPS_ACTION

    # Only switch bot data after a real connection to the new port succeeds.
    old_port = cur_port
    data["vps_port"] = new_port
    context.user_data["vps_port"] = new_port

    user_id = update.effective_user.id
    vps_list = load_vps_list(user_id)
    for v in vps_list:
        if v["vps_ip"] == data["vps_ip"] and int(v["vps_port"]) == old_port:
            v["vps_port"] = new_port
            break
    save_vps_list(user_id, vps_list)

    await update.message.reply_text(
        "─────────────────────────────\n"
        "  ✅  Port SSH Ditambahkan\n"
        "─────────────────────────────\n\n"
        f"  🎯 {data['vps_ip']}\n"
        f"  {ports_line}\n"
        f"  ✅ Koneksi ke port {new_port} berhasil\n"
        f"  ✅ Port lama {old_port} tetap aktif\n"
        f"  {backup_line}\n\n"
        "  Data bot sekarang memakai port baru.\n"
        "─────────────────────────────",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return SELECT_VPS_ACTION


# ============ SSH Helpers ============

async def ssh_exec(data: dict, cmd: str) -> str:
    """Execute SSH command and return output."""
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            hostname=data["vps_ip"], port=data["vps_port"],
            username=data["vps_user"], password=data["vps_pass"],
            timeout=15, allow_agent=False, look_for_keys=False,
        )
        stdin, stdout, stderr = ssh.exec_command(cmd)
        stdout.channel.settimeout(30)
        output = stdout.read().decode('utf-8', errors='ignore').strip()
        error = stderr.read().decode('utf-8', errors='ignore').strip()
        ssh.close()
        return output if output else error if error else "(no output)"
    except Exception as e:
        return f"Error: {str(e)}"


async def get_vps_system_info(data: dict) -> str:
    """Get VPS system info via SSH."""
    info_cmd = (
        "echo \"OS: $(cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d'\"' -f2)\";"
        "echo \"Kernel: $(uname -r)\";"
        "echo \"Uptime: $(uptime -p 2>/dev/null || uptime)\";"
        "echo \"CPU: $(nproc) cores\";"
        "echo \"RAM: $(free -m | awk '/Mem:/ {printf \"%dMB / %dMB (%.0f%%)\", $3, $2, $3/$2*100}')\";"
        "echo \"Disk: $(df -h / | awk 'NR==2 {printf \"%s / %s (%s)\", $3, $2, $5}')\";"
        "echo \"Load: $(cat /proc/loadavg | awk '{print $1, $2, $3}')\""
    )
    result = await ssh_exec(data, info_cmd)
    return (
        "─────────────────────────────\n"
        "  📊  VPS System Info\n"
        "─────────────────────────────\n\n"
        f"  🎯 {data['vps_ip']}:{data['vps_port']}\n\n"
        "─────────────────────────────\n\n"
        f"{result}\n\n"
        "─────────────────────────────"
    )



# ============ OS Install Flow ============

async def select_os_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show OS options."""
    query = update.callback_query
    await query.answer()
    data = context.user_data
    category = query.data

    if category == "cat_windows":
        keyboard = [[InlineKeyboardButton(v["name"], callback_data=f"os_{k}")] for k, v in WINDOWS_OPTIONS.items()]
        keyboard.append([InlineKeyboardButton("◀️ Kembali", callback_data="act_back_menu")])
        await query.edit_message_text("Pilih Windows:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif category == "cat_linux":
        keyboard = [[InlineKeyboardButton(v["name"], callback_data=f"os_{k}")] for k, v in LINUX_OPTIONS.items()]
        keyboard.append([InlineKeyboardButton("◀️ Kembali", callback_data="act_back_menu")])
        await query.edit_message_text("Pilih Linux:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif category == "act_back_menu":
        await query.edit_message_text(
            get_vps_info_text(data) + "\n\n  Pilih aksi:",
            reply_markup=get_action_keyboard(),
        )
        return SELECT_VPS_ACTION
    return SELECT_OS


async def select_os(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle OS selection."""
    query = update.callback_query
    await query.answer()
    os_key = query.data.replace("os_", "")

    if os_key in WINDOWS_OPTIONS:
        context.user_data["os_name"] = WINDOWS_OPTIONS[os_key]["name"]
        context.user_data["os_cmd"] = WINDOWS_OPTIONS[os_key]["cmd"]
        context.user_data["os_type"] = "windows"
        keyboard = [[InlineKeyboardButton(v, callback_data=f"lang_{k}")] for k, v in LANG_OPTIONS.items()]
        await query.edit_message_text(f"OS: {context.user_data['os_name']}\n\nPilih bahasa:", reply_markup=InlineKeyboardMarkup(keyboard))
        return SELECT_LANG
    elif os_key in LINUX_OPTIONS:
        context.user_data["os_name"] = LINUX_OPTIONS[os_key]["name"]
        context.user_data["os_cmd"] = LINUX_OPTIONS[os_key]["cmd"]
        context.user_data["os_type"] = "linux"
        context.user_data["os_engine"] = LINUX_OPTIONS[os_key]["engine"]
        context.user_data["lang"] = ""
        return await show_confirm(query, context)
    return SELECT_OS


async def select_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle language selection."""
    query = update.callback_query
    await query.answer()
    context.user_data["lang"] = query.data.replace("lang_", "")
    return await show_confirm(query, context)


async def show_confirm(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show confirmation."""
    data = context.user_data
    os_type = data["os_type"]
    summary = (
        "─────────────────────────────\n"
        "  ⚠️  KONFIRMASI REINSTALL\n"
        "─────────────────────────────\n\n"
        f"  🎯 {data['vps_ip']}:{data['vps_port']}\n"
        f"  📦 {data['os_name']}\n"
    )
    if data.get("lang"):
        summary += f"  🌐 {LANG_OPTIONS.get(data['lang'], '')}\n"
    if os_type == "windows":
        summary += "\n  🔑 Login: Administrator / Teddysun.com\n"
    else:
        summary += "\n  🔑 Login: root / Digicore@1\n"
    summary += "\n  ⚠️ SEMUA DATA AKAN DIHAPUS!\n"

    keyboard = [
        [InlineKeyboardButton("✅ YA, INSTALL!", callback_data="confirm_yes"),
         InlineKeyboardButton("❌ BATAL", callback_data="confirm_no")]
    ]
    await query.edit_message_text(summary, reply_markup=InlineKeyboardMarkup(keyboard))
    return CONFIRM



def build_install_progress_text(
    job: dict,
    phase: str,
    progress: int,
    elapsed_seconds: int = 0,
    detail: str = "",
) -> str:
    """Render the familiar single-message loading UI while the job runs in background."""
    phase_rows = {
        "queued": (
            "  ○ SSH Connection      WAITING",
            "  ○ Download Script     WAITING",
            "  ○ Run Installer       WAITING",
            "  ○ Monitoring          WAITING",
        ),
        "connecting": (
            "  ◐ SSH Connection      CONNECTING",
            "  ○ Download Script     WAITING",
            "  ○ Run Installer       WAITING",
            "  ○ Monitoring          WAITING",
        ),
        "downloading": (
            "  ● SSH Connection      DONE",
            "  ◐ Download Script     DOWNLOADING",
            "  ○ Run Installer       WAITING",
            "  ○ Monitoring          WAITING",
        ),
        "launching": (
            "  ● SSH Connection      DONE",
            "  ● Download Script     DONE",
            "  ◐ Run Installer       STARTING",
            "  ○ Monitoring          WAITING",
        ),
        "monitoring": (
            "  ● SSH Connection      DONE",
            "  ● Download Script     DONE",
            "  ● Run Installer       DONE",
            "  ◐ Monitoring          RUNNING",
        ),
    }
    rows = phase_rows.get(phase, phase_rows["queued"])
    progress = max(0, min(100, int(progress)))
    filled = round(progress * 18 / 100)
    bar = "█" * filled + "░" * (18 - filled)
    if phase == "monitoring":
        minutes = max(0, int(elapsed_seconds / 60))
        progress_note = f"  Progress perkiraan · {minutes} menit"
    else:
        progress_note = "  Progress tahapan"
    if detail:
        progress_note += f"\n  Status: {detail}"
    return (
        "─────────────────────────────\n"
        "  ⚙️  OS Installation Service\n"
        "─────────────────────────────\n\n"
        f"  Job: {job['job_id']}\n"
        f"  VPS: {job['vps_ip']}\n"
        f"  OS: {job['os_name']}\n\n"
        + "\n".join(rows) + "\n\n"
        f"  ┃{bar}┃ {progress}%\n"
        f"{progress_note}\n\n"
        "  Reinstall berjalan di background.\n"
        "  Anda tetap dapat memproses VPS lain.\n"
        "─────────────────────────────"
    )


async def report_reinstall_stage(
    application: Application,
    job_id: str,
    phase: str,
    progress: int,
    elapsed_seconds: int = 0,
) -> None:
    job = update_reinstall_job(job_id, status=phase, progress=progress)
    if job:
        await edit_job_progress(
            application,
            job_id,
            build_install_progress_text(job, phase, progress, elapsed_seconds),
        )


async def edit_job_progress(application: Application, job_id: str, text: str) -> None:
    """Update the original confirmation message, falling back to a new message."""
    job = get_reinstall_job(job_id)
    if not job:
        return
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Lihat Reinstall Jobs", callback_data="jobs_list")],
        [InlineKeyboardButton("🏠 Menu Utama", callback_data="jobs_home")],
    ])
    try:
        await application.bot.edit_message_text(
            chat_id=int(job["chat_id"]),
            message_id=int(job["message_id"]),
            text=text,
            reply_markup=markup,
        )
    except Exception as exc:
        if "Message is not modified" in str(exc):
            return
        try:
            sent = await application.bot.send_message(
                chat_id=int(job["chat_id"]),
                text=text,
                reply_markup=markup,
            )
            update_reinstall_job(job_id, message_id=sent.message_id)
        except Exception as send_exc:
            logger.warning("Could not send progress for job %s: %s", job_id, send_exc)


def launch_reinstall_sync(data: dict, stage_callback=None) -> tuple:
    """Blocking SSH/download/launch work; always run this with asyncio.to_thread."""
    def report(stage: str) -> None:
        if stage_callback:
            try:
                stage_callback(stage)
            except Exception as exc:
                logger.warning("Could not report reinstall stage %s: %s", stage, exc)
    ssh = None
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            data["vps_ip"],
            port=int(data["vps_port"]),
            username=data["vps_user"],
            password=data["vps_pass"],
            timeout=20,
            banner_timeout=20,
            auth_timeout=20,
        )
        report("downloading")

        if data["os_type"] == "windows":
            script_url = "https://raw.githubusercontent.com/leitbogioro/Tools/master/Linux_reinstall/InstallNET.sh"
            remote_script = "/tmp/reinstallos-installnet.sh"
            command = (
                f"bash {shlex.quote(remote_script)} {data['os_cmd']} "
                f"-lang {shlex.quote(data.get('lang') or 'en-us')} -pwd 'Digicore@1' -firmware; reboot"
            )
        elif data.get("os_engine") == "bin456789":
            script_url = "https://raw.githubusercontent.com/bin456789/reinstall/main/reinstall.sh"
            remote_script = "/tmp/reinstallos-reinstall.sh"
            command = (
                f"bash {shlex.quote(remote_script)} {data['os_cmd']} "
                "--password 'Digicore@1'; reboot"
            )
        else:
            script_url = "https://raw.githubusercontent.com/leitbogioro/Tools/master/Linux_reinstall/InstallNET.sh"
            remote_script = "/tmp/reinstallos-installnet.sh"
            command = (
                f"bash {shlex.quote(remote_script)} {data['os_cmd']} "
                "-pwd 'Digicore@1' -firmware; reboot"
            )

        download = (
            f"rm -f {shlex.quote(remote_script)}; "
            f"wget --no-check-certificate -q -O {shlex.quote(remote_script)} {shlex.quote(script_url)}; "
            f"test -s {shlex.quote(remote_script)}"
        )
        _, stdout, stderr = ssh.exec_command(download, timeout=120)
        rc = stdout.channel.recv_exit_status()
        if rc != 0:
            error = stderr.read().decode(errors="replace").strip()
            return False, f"Gagal download installer (exit {rc}): {error[:300]}"

        report("launching")
        launch_command = (
            "nohup sh -c " + shlex.quote(command) +
            " </dev/null >/tmp/reinstallos-installer.log 2>&1 & echo $!"
        )
        _, stdout, stderr = ssh.exec_command(launch_command, timeout=30)
        pid_text = stdout.read().decode(errors="replace").strip().splitlines()
        error = stderr.read().decode(errors="replace").strip()
        if not pid_text or not pid_text[-1].isdigit():
            return False, f"Installer tidak berhasil dijalankan: {error[:300] or 'PID tidak diterima'}"
        return True, pid_text[-1]
    except Exception as exc:
        return False, str(exc)[:500]
    finally:
        if ssh:
            try:
                ssh.close()
            except Exception:
                pass


async def is_port_open(ip: str, port: int, timeout: int = 5) -> bool:
    def probe():
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            return sock.connect_ex((ip, int(port))) == 0
        finally:
            sock.close()
    return await asyncio.to_thread(probe)


def linux_os_matches(requested_os: str, detected_os: str) -> bool:
    """Match the requested Linux family and major/version token."""
    requested = requested_os.lower()
    detected = detected_os.lower()
    family = requested.split()[0] if requested.split() else ""
    versions = re.findall(r"\d+(?:\.\d+)?", requested)
    return bool(family and family in detected and all(version in detected for version in versions))


def fix_linux_password_sync(vps_ip: str) -> tuple:
    """Enable the established root login and return the detected installed OS."""
    default_passwords = [
        "Digicore@1", "digicore", "Bolehtuh1", "LeitboGi0662",
        "Teddysun.com", "teddysun.com", "",
    ]
    default_users = ["root", "ubuntu", "debian"]
    last_error = "Tidak ada kredensial default installer yang berhasil"

    for username in default_users:
        for password in default_passwords:
            ssh = None
            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(
                    vps_ip,
                    port=22,
                    username=username,
                    password=password,
                    timeout=10,
                    banner_timeout=10,
                    auth_timeout=10,
                    allow_agent=False,
                    look_for_keys=False,
                )
                fix_commands = (
                    "echo 'root:Digicore@1' | sudo chpasswd 2>/dev/null; "
                    "echo 'root:Digicore@1' | chpasswd 2>/dev/null; "
                    "sudo sed -i 's/.*PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config 2>/dev/null; "
                    "sed -i 's/.*PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config 2>/dev/null; "
                    "sudo sed -i 's/.*PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config 2>/dev/null; "
                    "sed -i 's/.*PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config 2>/dev/null; "
                    "sudo systemctl restart sshd 2>/dev/null; sudo service ssh restart 2>/dev/null; "
                    "systemctl restart sshd 2>/dev/null; service ssh restart 2>/dev/null; "
                    "echo 'FIX_DONE'; grep '^PRETTY_NAME=' /etc/os-release 2>/dev/null || true"
                )
                _, stdout, _ = ssh.exec_command(fix_commands, timeout=30)
                output = stdout.read().decode("utf-8", errors="ignore")
                fix_success = "FIX_DONE" in output
                detected_os = ""
                for line in output.splitlines():
                    if line.startswith("PRETTY_NAME="):
                        detected_os = line.split("=", 1)[1].strip().strip("\"'")
                        break
                if fix_success and detected_os:
                    return True, "", detected_os[:200]
                return False, "OS hasil reinstall tidak dapat dibaca", detected_os[:200]
            except Exception as exc:
                last_error = str(exc)[:300]
            finally:
                if ssh:
                    try:
                        ssh.close()
                    except Exception:
                        pass
    return False, last_error, ""


async def finish_reinstall_job(
    application: Application,
    job_id: str,
    status: str,
    error: str = "",
    verification: str = "",
) -> None:
    progress = 100 if status == "completed" else int((get_reinstall_job(job_id) or {}).get("progress", 0))
    job = update_reinstall_job(
        job_id,
        status=status,
        progress=progress,
        completed_at=int(_time.time()),
        verification=verification[:200],
        error=error[:500],
    )
    if not job:
        return
    if status == "completed":
        elapsed_minutes = max(0, int((int(job.get("completed_at", 0)) - int(job.get("started_at", 0))) / 60))
        if job.get("os_type") == "windows":
            login = (
                f"  Host: {job['vps_ip']}:3389\n"
                "  User: Administrator\n"
                "  Pass: Teddysun.com"
            )
            fix_status = "  Verifikasi: RDP port 3389 READY\n"
        else:
            login = (
                f"  Host: ssh root@{job['vps_ip']}\n"
                "  Pass: Digicore@1"
            )
            detected = verification or "Linux dan SSH siap"
            fix_status = f"  OS terverifikasi: {detected}\n"
        text = (
            "─────────────────────────────\n"
            "  ✅  Reinstall Selesai\n"
            "─────────────────────────────\n\n"
            f"  Job ID: {job_id}\n"
            f"  VPS: {job['vps_ip']}\n"
            f"  OS: {job['os_name']}\n"
            f"  Durasi: {elapsed_minutes} menit\n"
            "  Progress: 100%\n"
            f"{fix_status}\n"
            "  LOGIN:\n"
            f"{login}\n\n"
            "─────────────────────────────"
        )
    else:
        label = "Timeout" if status == "timeout" else "Gagal"
        text = (
            "─────────────────────────────\n"
            f"  ❌  Reinstall {label}\n"
            "─────────────────────────────\n\n"
            f"  Job ID: {job_id}\n"
            f"  VPS: {job['vps_ip']}\n"
            f"  OS: {job['os_name']}\n"
            f"  Pesan: {error[:500] or '-'}\n\n"
            "  Data VPS tetap tersimpan.\n"
            "─────────────────────────────"
        )
    await edit_job_progress(application, job_id, text)


async def monitor_reinstall_job(application: Application, job_id: str, recovered: bool = False) -> None:
    """Persistently monitor a detached target-side installer without blocking updates."""
    job = get_reinstall_job(job_id)
    if not job:
        return
    started_at = int(job.get("started_at") or _time.time())
    if not job.get("started_at"):
        update_reinstall_job(job_id, started_at=started_at)
    vps_ip = job["vps_ip"]
    old_port = int(job.get("vps_port", 22))
    offline_seen = bool(job.get("offline_seen"))
    last_notice = 0
    max_seconds = 35 * 60

    while True:
        current = get_reinstall_job(job_id)
        if not current or current.get("status") not in ACTIVE_JOB_STATES:
            return
        elapsed = max(0, int(_time.time()) - started_at)
        if elapsed >= max_seconds:
            await finish_reinstall_job(
                application,
                job_id,
                "timeout",
                "Batas monitoring 35 menit tercapai. Periksa VPS secara manual; installer target tidak dibatalkan.",
            )
            return

        old_open = await is_port_open(vps_ip, old_port)
        if not old_open and not offline_seen:
            offline_seen = True
            update_reinstall_job(job_id, offline_seen=True)

        target_port = 3389 if current.get("os_type") == "windows" else 22
        target_open = await is_port_open(vps_ip, target_port)
        ready_for_verification = target_open and (
            offline_seen or (recovered and elapsed >= 5 * 60)
        )
        target_online_since = int(current.get("target_online_since") or 0)

        if ready_for_verification and not target_online_since:
            target_online_since = int(_time.time())
            current = update_reinstall_job(
                job_id,
                target_online_since=target_online_since,
            ) or current
        elif not target_open and target_online_since:
            target_online_since = 0
            current = update_reinstall_job(job_id, target_online_since=0) or current

        # Give SSH/RDP a short stabilization window before declaring the OS ready.
        if ready_for_verification and int(_time.time()) - target_online_since >= 45:
            if current.get("os_type") == "windows":
                await finish_reinstall_job(
                    application,
                    job_id,
                    "completed",
                    verification="RDP port 3389 siap",
                )
                return

            fix_success, fix_error, detected_os = await asyncio.to_thread(
                fix_linux_password_sync,
                vps_ip,
            )
            if not fix_success:
                await finish_reinstall_job(
                    application,
                    job_id,
                    "failed",
                    "VPS sudah online, tetapi login SSH atau OS belum dapat diverifikasi: " + fix_error,
                    verification=detected_os,
                )
                return
            if not linux_os_matches(current.get("os_name", ""), detected_os):
                await finish_reinstall_job(
                    application,
                    job_id,
                    "failed",
                    f"OS tidak sesuai. Diminta {current.get('os_name')}, terdeteksi {detected_os}.",
                    verification=detected_os,
                )
                return
            await finish_reinstall_job(
                application,
                job_id,
                "completed",
                verification=detected_os,
            )
            return

        progress = min(95, max(30, 30 + int(elapsed / 20)))
        current = update_reinstall_job(
            job_id,
            status="monitoring",
            progress=progress,
            offline_seen=offline_seen,
        ) or current
        if elapsed - last_notice >= 60 or last_notice == 0:
            if ready_for_verification:
                target_name = "RDP Windows" if current.get("os_type") == "windows" else "OS Linux dan SSH"
                phase_detail = f"VPS online, menunggu verifikasi {target_name}"
            elif offline_seen:
                phase_detail = "VPS sedang reboot/install"
            else:
                phase_detail = "Menunggu VPS masuk tahap reinstall"
            await edit_job_progress(
                application,
                job_id,
                build_install_progress_text(
                    current,
                    "monitoring",
                    progress,
                    elapsed_seconds=elapsed,
                    detail=phase_detail,
                ),
            )
            last_notice = elapsed
        await asyncio.sleep(30)


async def process_reinstall_job(application: Application, job_id: str, data=None, monitor_only: bool = False) -> None:
    semaphore = application.bot_data["reinstall_jobs_semaphore"]
    async with semaphore:
        job = get_reinstall_job(job_id)
        if not job or job.get("status") not in ACTIVE_JOB_STATES:
            return

        if monitor_only or job.get("status") in {"launching", "monitoring"}:
            await monitor_reinstall_job(application, job_id, recovered=monitor_only)
            return

        if data is None:
            data = find_job_vps_credentials(job)
        if not data:
            await finish_reinstall_job(application, job_id, "failed", "Kredensial VPS tidak lagi tersedia.")
            return

        job = update_reinstall_job(
            job_id,
            status="connecting",
            progress=5,
            started_at=int(_time.time()),
        ) or job
        await edit_job_progress(
            application,
            job_id,
            build_install_progress_text(job, "connecting", 5),
        )

        loop = asyncio.get_running_loop()
        stage_progress = {"downloading": 15, "launching": 25}

        def stage_callback(stage: str) -> None:
            progress = stage_progress.get(stage)
            if progress is None:
                return
            future = asyncio.run_coroutine_threadsafe(
                report_reinstall_stage(application, job_id, stage, progress),
                loop,
            )
            try:
                future.result(timeout=15)
            except Exception as exc:
                logger.warning("Progress update delayed for job %s: %s", job_id, exc)

        try:
            ok, result = await asyncio.to_thread(launch_reinstall_sync, data, stage_callback)
        finally:
            # The persistent VPS bucket remains the source of truth; do not retain
            # another plaintext password in this long-lived background task.
            data.pop("vps_pass", None)
        if not ok:
            await finish_reinstall_job(application, job_id, "failed", result)
            return

        update_reinstall_job(job_id, status="monitoring", progress=30, target_pid=result)
        await monitor_reinstall_job(application, job_id)


def schedule_reinstall_job(application: Application, job_id: str, data=None, monitor_only: bool = False) -> None:
    scheduled = application.bot_data.setdefault("scheduled_reinstall_jobs", set())
    if job_id in scheduled:
        return
    scheduled.add(job_id)

    async def runner():
        try:
            await process_reinstall_job(application, job_id, data=data, monitor_only=monitor_only)
        except Exception as exc:
            logger.exception("Unexpected reinstall job error for %s", job_id)
            await finish_reinstall_job(application, job_id, "failed", f"Internal error: {exc}")
        finally:
            scheduled.discard(job_id)

    # Keep reinstall tasks outside Application.create_task: PTB waits for tracked
    # tasks during shutdown, while these long-running jobs must stop promptly and
    # resume from persistent metadata after the service comes back.
    task = asyncio.create_task(runner())
    background_tasks = application.bot_data.setdefault("background_reinstall_tasks", set())
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)


async def resume_reinstall_jobs(application: Application) -> None:
    """Resume persisted jobs after a bot/service restart."""
    for job in active_reinstall_jobs():
        status = job.get("status")
        # A detached installer may already be running for launching/monitoring jobs;
        # never relaunch it and risk a duplicate reinstall.
        monitor_only = status in {"launching", "monitoring"}
        schedule_reinstall_job(application, job["job_id"], monitor_only=monitor_only)
    if active_reinstall_jobs():
        logger.info("Resumed %s persisted reinstall job(s)", len(active_reinstall_jobs()))


async def confirm_install(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "confirm_no":
        await query.edit_message_text("❌ Reinstall dibatalkan. VPS tidak diubah.")
        return ConversationHandler.END

    user_id = update.effective_user.id
    data = dict(context.user_data)
    required = {"vps_ip", "vps_port", "vps_user", "vps_pass", "os_name", "os_type", "os_cmd"}
    if not required.issubset(data):
        await query.edit_message_text("❌ Data reinstall tidak lengkap. Silakan mulai lagi dari menu utama.")
        return ConversationHandler.END

    duplicate = find_active_job_for_vps(data["vps_ip"])
    if duplicate:
        await query.edit_message_text(
            "⚠️ VPS ini sudah memiliki reinstall job aktif.\n\n"
            f"Job ID: {duplicate['job_id']}\n"
            f"Status: {JOB_STATUS_LABELS.get(duplicate.get('status'), duplicate.get('status'))}\n\n"
            "Gunakan /jobs untuk melihat progress. Job duplikat tidak dibuat.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📋 Lihat Jobs", callback_data="jobs_list")]]),
        )
        return ConversationHandler.END

    if len(active_reinstall_jobs(user_id)) >= MAX_ACTIVE_REINSTALL_JOBS_PER_USER:
        await query.edit_message_text(
            f"⚠️ Batas {MAX_ACTIVE_REINSTALL_JOBS_PER_USER} job aktif/antrean per user tercapai. "
            "Tunggu salah satu selesai dan lihat progress melalui /jobs."
        )
        return ConversationHandler.END

    if len(queued_reinstall_jobs()) >= MAX_QUEUED_REINSTALL_JOBS:
        await query.edit_message_text(
            "⚠️ Antrean reinstall sedang penuh. Silakan tunggu salah satu job mulai atau selesai."
        )
        return ConversationHandler.END

    should_queue = (
        len(active_reinstall_jobs()) >= MAX_ACTIVE_REINSTALL_JOBS
        or bool(queued_reinstall_jobs())
    )
    job = create_reinstall_job(
        user_id=user_id,
        chat_id=query.message.chat_id,
        message_id=query.message.message_id,
        data=data,
    )
    queue_position = get_queue_position(job["job_id"])
    title = "⏳  Reinstall Masuk Antrean" if should_queue else "✅  Reinstall Job Dibuat"
    status_line = (
        f"Posisi antrean: {queue_position}"
        if should_queue
        else "Segera dimulai di background"
    )
    await query.edit_message_text(
        "─────────────────────────────\n"
        f"  {title}\n"
        "─────────────────────────────\n\n"
        f"  Job ID: {job['job_id']}\n"
        f"  VPS: {job['vps_ip']}\n"
        f"  OS: {job['os_name']}\n"
        f"  Status: {status_line}\n\n"
        "  Job akan berjalan otomatis. Anda dapat\n"
        "  kembali ke menu atau memproses VPS lain.\n"
        "─────────────────────────────",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Lihat Reinstall Jobs", callback_data="jobs_list")],
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="jobs_home")],
        ]),
    )
    schedule_reinstall_job(context.application, job["job_id"], data=data)
    return ConversationHandler.END


# ============ Auto-detect VPS handler (tanpa /start) ============

async def auto_add_vps(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Auto-detect VPS format dari pesan biasa tanpa harus /start."""
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        return

    text = update.message.text.strip()
    data = parse_vps_detail(text)

    if data is None:
        return  # Bukan format VPS, abaikan

    # Delete message (contains password)
    try:
        await update.message.delete()
    except Exception:
        pass

    # Save to VPS list
    vps_list = load_vps_list(user_id)
    exists = any(v['vps_ip'] == data['vps_ip'] and v['vps_port'] == data['vps_port'] for v in vps_list)
    if not exists:
        vps_list.append(data)
        save_vps_list(user_id, vps_list)

    # Set as active VPS
    context.user_data.update(data)

    # Show action menu langsung
    await update.message.reply_text(
        get_vps_info_text(data) + "\n\n  ✅ VPS tersimpan!\n\n  Pilih aksi:",
        reply_markup=get_action_keyboard(),
    )


# ============ Standalone Commands ============

async def cmd_ssh(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Standalone /ssh command."""
    if not is_authorized(update.effective_user.id):
        return
    data = context.user_data
    if not data.get("vps_ip"):
        await update.message.reply_text("Gunakan /start untuk pilih VPS dulu.")
        return
    cmd_text = update.message.text.replace("/ssh", "").strip()
    if not cmd_text:
        await update.message.reply_text("Cara: /ssh <command>\nContoh: /ssh uptime")
        return
    result = await ssh_exec(data, cmd_text)
    if len(result) > 3000:
        result = result[:3000] + "\n..."
    await update.message.reply_text(f"💻 {cmd_text}\n\n{result}")


async def cmd_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Standalone /info command."""
    if not is_authorized(update.effective_user.id):
        return
    data = context.user_data
    if not data.get("vps_ip"):
        await update.message.reply_text("Gunakan /start untuk pilih VPS dulu.")
        return
    info = await get_vps_system_info(data)
    await update.message.reply_text(info)


async def cmd_reboot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Standalone /reboot command."""
    if not is_authorized(update.effective_user.id):
        return
    data = context.user_data
    if not data.get("vps_ip"):
        await update.message.reply_text("Gunakan /start untuk pilih VPS dulu.")
        return
    await ssh_exec(data, "reboot")
    await update.message.reply_text(f"🔄 Reboot sent ke {data['vps_ip']}")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Standalone /ping & /status command - bisa langsung /ping <ip> tanpa login."""
    if not is_authorized(update.effective_user.id):
        return
    # Ambil IP: prioritaskan argumen /ping <ip>, fallback ke VPS aktif
    args = context.args if hasattr(context, 'args') and context.args else []
    # Fallback parse manual jika args kosong (kadang context.args tidak terisi)
    if not args:
        text = update.message.text or ""
        parts = text.strip().split()
        if len(parts) > 1:
            args = parts[1:]

    target_ip = None
    if args:
        # ambil token pertama yang mirip IP/domain
        cand = args[0].strip()
        # bersihkan format jika user kirim ip:port
        if ":" in cand and cand.count(".") >= 3:
            cand = cand.split(":")[0]
        # validasi sederhana IP/hostname
        if re.match(r"^[0-9.]+$", cand) or re.match(r"^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", cand) or re.match(r"^[0-9]{1,3}(\.[0-9]{1,3}){3}$", cand):
            target_ip = cand
        else:
            await update.message.reply_text(
                "─────────────────────────────\n"
                "  📡  Ping VPS\n"
                "─────────────────────────────\n\n"
                f"  ❌ IP tidak valid: {cand}\n\n"
                "  Contoh:\n"
                "  `/ping 103.108.186.12`\n"
                "  `/ping 8.8.8.8`\n\n"
                "  Atau tanpa IP (cek VPS aktif):\n"
                "  `/ping`",
                parse_mode="Markdown"
            )
            return
    else:
        data = context.user_data
        if data.get("vps_ip"):
            target_ip = data["vps_ip"]
        else:
            await update.message.reply_text(
                "─────────────────────────────\n"
                "  📡  Ping VPS\n"
                "─────────────────────────────\n\n"
                "  Kirim IP untuk di-ping:\n\n"
                "  `/ping 103.108.186.12`\n"
                "  `/ping 8.8.8.8`\n\n"
                "  Atau pilih VPS dulu:\n"
                "  `/start` → pilih VPS → `/ping`",
                parse_mode="Markdown"
            )
            return

    vps_ip = target_ip
    await update.message.reply_text(f"  📡 Ping {vps_ip}...")

    # Cek ICMP ping
    proc = await asyncio.create_subprocess_exec(
        "ping", "-c", "3", "-W", "3", vps_ip,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()
    ping_ok = proc.returncode == 0

    # Cek port SSH (22) dan RDP (3389)
    async def check_port(ip, port):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            res = sock.connect_ex((ip, port))
            sock.close()
            return res == 0
        except:
            return False

    ssh_ok, rdp_ok = await asyncio.gather(check_port(vps_ip, 22), check_port(vps_ip, 3389))

    # Build status text
    ping_txt = "✅ ONLINE" if ping_ok else "❌ OFFLINE"
    ssh_txt = "✅ OPEN" if ssh_ok else "❌ CLOSED"
    rdp_txt = "✅ OPEN" if rdp_ok else "❌ CLOSED"

    # Kesimpulan
    if ping_ok or ssh_ok or rdp_ok:
        overall = "✅ VPS ONLINE"
    else:
        overall = "❌ VPS OFFLINE"

    await update.message.reply_text(
        "─────────────────────────────\n"
        "  📡  Ping Result\n"
        "─────────────────────────────\n\n"
        f"  🎯 {vps_ip}\n"
        f"  {overall}\n\n"
        "─────────────────────────────\n"
        f"  🏓 Ping (ICMP): {ping_txt}\n"
        f"  🔐 SSH 22:      {ssh_txt}\n"
        f"  🖥️ RDP 3389:     {rdp_txt}\n"
        "─────────────────────────────\n\n"
        "  Tip: `/ping 104.207.93.92:22022` juga bisa (auto ambil IP)",
        parse_mode="Markdown"
    )


async def _git(*args, cwd=None):
    """Jalankan perintah git, kembalikan (returncode, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        "git", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd or BASE_DIR,
    )
    stdout, stderr = await proc.communicate()
    return (
        proc.returncode,
        stdout.decode("utf-8", errors="ignore").strip(),
        stderr.decode("utf-8", errors="ignore").strip(),
    )


async def _rev(ref):
    """Resolve ref jadi commit hash. Kembalikan "" kalau ref tidak ada.

    Catatan: tanpa --verify --quiet, git rev-parse mencetak balik nama ref-nya
    saat gagal, sehingga hasilnya terlihat valid padahal bukan.
    """
    rc, out, _ = await _git("rev-parse", "--verify", "--quiet", ref + "^{commit}")
    return out if rc == 0 else ""


async def _git_state():
    """Ambil kondisi repo lokal: commit, subjek, dirty, dan commit remote."""
    local = await _rev("HEAD")
    _, subject, _ = await _git("log", "-1", "--format=%h %s (%cr)")
    _, dirty, _ = await _git("status", "--porcelain")
    remote = await _rev("origin/main")
    return local, subject, bool(dirty.strip()), remote


async def cmd_version(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Tampilkan versi bot yang sedang jalan (commit git)."""
    if not is_authorized(update.effective_user.id):
        return

    if not os.path.isdir(os.path.join(BASE_DIR, ".git")):
        await update.message.reply_text(
            "─────────────────────────────\n"
            "  ⚠️  Bukan Instalasi Git\n"
            "─────────────────────────────\n\n"
            f"  Folder: {BASE_DIR}\n"
            "  Tidak ada .git, jadi /update tidak bisa jalan.\n\n"
            "  Install ulang dengan install.sh.\n\n"
            "─────────────────────────────"
        )
        return

    await _git("fetch", "origin", "main")
    local, subject, dirty, remote = await _git_state()
    _, behind, _ = await _git("rev-list", "--count", "HEAD..origin/main")

    if not local or not remote:
        status = "❓ Tidak bisa dibandingkan dengan GitHub"
    elif local == remote and not dirty:
        status = "✅ Sudah sama dengan GitHub (main)"
    elif dirty:
        status = "⚠️ Ada file yang dimodifikasi lokal"
    else:
        status = f"🔄 Ketinggalan {behind or '?'} commit — jalankan /update"

    await update.message.reply_text(
        "─────────────────────────────\n"
        "  ℹ️  Versi Bot\n"
        "─────────────────────────────\n\n"
        f"  Folder  : {BASE_DIR}\n"
        f"  Commit  : {subject or local[:7] or '-'}\n"
        f"  GitHub  : {remote[:7] if remote else '-'}\n"
        f"  Status  : {status}\n\n"
        "─────────────────────────────"
    )


async def cmd_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Update bot dari GitHub (git fetch + reset --hard) dan restart service.

    Pakai '/update force' untuk memaksa reset + restart walau terlihat sudah terbaru.
    """
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("⛔ Perintah /update hanya dapat digunakan owner.")
        return

    force = bool(context.args) and context.args[0].lower() in ("force", "-f", "paksa")

    if not os.path.isdir(os.path.join(BASE_DIR, ".git")):
        await update.message.reply_text(
            "─────────────────────────────\n"
            "  ❌  Update Tidak Bisa Jalan\n"
            "─────────────────────────────\n\n"
            f"  Folder bot: {BASE_DIR}\n"
            "  Folder ini bukan clone git (.git tidak ada),\n"
            "  jadi tidak ada yang bisa ditarik dari GitHub.\n\n"
            "  Perbaiki dengan install ulang:\n"
            "  bash <(curl -sL https://raw.githubusercontent.com/"
            "xyzval/reinstallos/main/install.sh)\n\n"
            "─────────────────────────────"
        )
        return

    await update.message.reply_text("⏳ Mengupdate bot dari GitHub...")

    try:
        # 1. Fetch — kegagalan HARUS dilaporkan, jangan diam-diam "sudah terbaru"
        rc, out, err = await _git("fetch", "origin", "main")
        if rc != 0:
            await update.message.reply_text(
                "─────────────────────────────\n"
                "  ❌  Gagal Ambil Data GitHub\n"
                "─────────────────────────────\n\n"
                f"  {err or out or 'git fetch gagal'}\n\n"
                "  Cek koneksi internet / DNS VPS.\n\n"
                "─────────────────────────────"
            )
            return

        # 2. Bandingkan commit lokal vs remote (bukan cuma diff isi file)
        local, subject, dirty, remote = await _git_state()

        if not remote:
            await update.message.reply_text(
                "─────────────────────────────\n"
                "  ❌  Branch main Tidak Ditemukan\n"
                "─────────────────────────────\n\n"
                "  Remote origin/main tidak ada di VPS ini.\n"
                "  Cek dengan: git -C " + BASE_DIR + " remote -v\n\n"
                "─────────────────────────────"
            )
            return

        if local == remote and not dirty and not force:
            await update.message.reply_text(
                "─────────────────────────────\n"
                "  ✅  Bot Sudah Terbaru\n"
                "─────────────────────────────\n\n"
                f"  Commit: {subject or local[:7]}\n"
                f"  Sama dengan GitHub ({remote[:7]}).\n\n"
                "  Tombol lama di chat tidak ikut berubah.\n"
                "  Kirim /start untuk memuat menu baru.\n"
                "  Paksa update: /update force\n\n"
                "─────────────────────────────"
            )
            return

        # 3. Reset ke versi GitHub (sekaligus buang perubahan lokal yang nyangkut)
        rc, out, err = await _git("reset", "--hard", "origin/main")
        if rc != 0:
            await update.message.reply_text(
                "─────────────────────────────\n"
                "  ❌  Update Gagal\n"
                "─────────────────────────────\n\n"
                f"  Error:\n  {err or out}\n\n"
                "─────────────────────────────"
            )
            return

        _, new_subject, _ = await _git("log", "-1", "--format=%h %s")

        await update.message.reply_text(
            "─────────────────────────────\n"
            "  🔄  Update Berhasil!\n"
            "─────────────────────────────\n\n"
            f"  Sebelum : {subject or local[:7] or '-'}\n"
            f"  Sesudah : {new_subject or remote[:7]}\n\n"
            "  ⏳ Merestart bot...\n"
            "─────────────────────────────"
        )

        # Simpan chat_id untuk kirim notif setelah restart
        try:
            with open(RESTART_NOTIFY_FILE, 'w') as f:
                json.dump({"chat_id": update.effective_chat.id}, f)
        except Exception:
            pass

        # Restart service (bot akan mati dan hidup lagi otomatis)
        proc = await asyncio.create_subprocess_exec(
            "systemctl", "restart", SERVICE_NAME,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, rst_err = await proc.communicate()

        if proc.returncode != 0:
            await update.message.reply_text(
                "─────────────────────────────\n"
                "  ⚠️  Kode Terupdate, Restart Gagal\n"
                "─────────────────────────────\n\n"
                f"  {rst_err.decode('utf-8', errors='ignore').strip() or 'systemctl gagal'}\n\n"
                f"  Restart manual:\n  systemctl restart {SERVICE_NAME}\n\n"
                "─────────────────────────────"
            )

    except Exception as e:
        await update.message.reply_text(
            "─────────────────────────────\n"
            "  ❌  Update Error\n"
            "─────────────────────────────\n\n"
            f"  {str(e)}\n\n"
            "─────────────────────────────"
        )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Help command with owner-only entries shown only to the owner."""
    owner_help = ""
    if is_owner(update.effective_user.id):
        owner_help = (
            "  /update   - Update bot dari GitHub (owner)\n\n"
            "Menu Owner:\n"
            "  👥 Kelola User - Tambah, aktif/nonaktif, dan cabut akses\n\n"
        )
    await update.message.reply_text(
        "─────────────────────────────\n"
        "  🖥️  Reinstall OS Bot v2.0\n"
        "─────────────────────────────\n\n"
        "Perintah:\n"
        "  /start    - Menu VPS\n"
        "  /jobs     - Progress reinstall jobs\n"
        "  /info     - Info VPS\n"
        "  /ssh CMD  - SSH command\n"
        "  /reboot   - Reboot VPS\n"
        "  /ping     - Cek online (alias /status)\n"
        "  /version  - Cek versi bot yang jalan\n"
        "  /help     - Bantuan\n"
        + owner_help +
        "Menu VPS:\n"
        "  🔧 Edit Port - Tambah port SSH, port lama tetap jalan\n\n"
        "Tambah VPS milik sendiri:\n"
        "  Kirim langsung: ip:port@user:password\n\n"
        "Setiap user hanya melihat daftar VPS miliknya sendiri.\n"
        "─────────────────────────────"
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Dibatalkan. /start untuk mulai lagi.")
    return ConversationHandler.END



# ============ Main ============

async def post_stop(application):
    """Cancel background monitors promptly; persistent metadata resumes them next start."""
    tasks = list(application.bot_data.get("background_reinstall_tasks", set()))
    for task in tasks:
        if not task.done():
            task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("Paused %s reinstall job task(s) for service shutdown", len(tasks))


async def post_init(application):
    """Set bot commands, resume jobs, dan kirim notif restart jika ada."""
    application.bot_data["reinstall_jobs_semaphore"] = asyncio.Semaphore(MAX_ACTIVE_REINSTALL_JOBS)
    await resume_reinstall_jobs(application)

    user_commands = [
        BotCommand("start", "Menu VPS saya"),
        BotCommand("jobs", "Progress reinstall jobs"),
        BotCommand("info", "Info VPS aktif"),
        BotCommand("ssh", "SSH command"),
        BotCommand("reboot", "Reboot VPS"),
        BotCommand("ping", "Cek online/offline"),
        BotCommand("version", "Cek versi bot"),
        BotCommand("help", "Bantuan"),
    ]
    owner_commands = user_commands[:-2] + [
        BotCommand("update", "Update bot dari GitHub"),
    ] + user_commands[-2:]
    # Default command menu never exposes owner-only maintenance commands.
    await application.bot.set_my_commands(user_commands)
    try:
        # A new owner chat may not exist yet until the owner has opened the bot.
        await application.bot.set_my_commands(
            owner_commands,
            scope=BotCommandScopeChat(chat_id=int(OWNER_ID)),
        )
    except Exception as e:
        logger.warning(f"Owner command scope not ready yet: {e}")

    # Kirim notifikasi restart berhasil jika ada
    restart_file = RESTART_NOTIFY_FILE
    try:
        if os.path.exists(restart_file):
            with open(restart_file, 'r') as f:
                data = json.load(f)
            os.remove(restart_file)
            chat_id = data.get("chat_id")
            if chat_id:
                await application.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        "─────────────────────────────\n"
                        "  ✅  Restart Berhasil!\n"
                        "─────────────────────────────\n\n"
                        "  Bot sudah aktif kembali.\n"
                        "  Versi terbaru dari GitHub.\n\n"
                        "─────────────────────────────"
                    ),
                )
    except Exception as e:
        logger.info(f"Restart notify error: {e}")


def main() -> None:
    if not BOT_TOKEN:
        print("ERROR: BOT_TOKEN not set!")
        return
    if not OWNER_ID or not OWNER_ID.isdigit():
        print("ERROR: OWNER_ID not set or invalid! Configure OWNER_ID in .env.")
        return

    initialize_auth_storage()
    initialize_jobs_storage()
    try:
        if os.path.exists(VPS_FILE):
            os.chmod(VPS_FILE, 0o600)
    except OSError:
        pass

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_stop(post_stop)
        .build()
    )

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ADD_VPS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_vps_handler),
                CallbackQueryHandler(select_vps, pattern="^(selvps_|addvps|add_)"),
            ],
            SELECT_VPS_ACTION: [
                CallbackQueryHandler(owner_callback, pattern="^owner_"),
                CallbackQueryHandler(select_vps, pattern="^(selvps_|addvps|add_)"),
                CallbackQueryHandler(handle_action, pattern="^act_"),
                CallbackQueryHandler(select_os_category, pattern="^cat_"),
            ],
            WIZ_IP: [MessageHandler(filters.TEXT & ~filters.COMMAND, wiz_ip_handler)],
            WIZ_PORT: [
                CallbackQueryHandler(wiz_port_callback, pattern="^wiz_port_"),
                CallbackQueryHandler(wiz_port_callback, pattern="^wiz_cancel"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, wiz_port_text_handler),
            ],
            WIZ_USER: [
                CallbackQueryHandler(wiz_user_callback, pattern="^wiz_user_"),
                CallbackQueryHandler(wiz_user_callback, pattern="^wiz_cancel"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, wiz_user_text_handler),
            ],
            WIZ_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, wiz_pass_handler)],
            SELECT_OS: [
                CallbackQueryHandler(select_os, pattern="^os_"),
                CallbackQueryHandler(select_os_category, pattern="^cat_"),
                CallbackQueryHandler(handle_action, pattern="^act_"),
            ],
            SELECT_LANG: [CallbackQueryHandler(select_lang, pattern="^lang_")],
            CONFIRM: [
                CallbackQueryHandler(confirm_install, pattern="^confirm_"),
                CallbackQueryHandler(handle_action, pattern="^act_"),
            ],
            SSH_CMD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ssh_cmd_handler),
                CallbackQueryHandler(handle_action, pattern="^act_"),
            ],
            EDIT_PASS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_pass_handler),
                CallbackQueryHandler(handle_action, pattern="^act_"),
            ],
            EDIT_PORT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_port_handler),
                CallbackQueryHandler(handle_action, pattern="^act_"),
            ],
            OWNER_ADD_USER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, owner_add_user_handler),
                CallbackQueryHandler(owner_callback, pattern="^owner_"),
            ],
            OWNER_SELECT_EXPIRY: [
                CallbackQueryHandler(owner_callback, pattern="^owner_"),
            ],
            OWNER_CUSTOM_EXPIRY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, owner_custom_expiry_handler),
                CallbackQueryHandler(owner_callback, pattern="^owner_"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start)],
        allow_reentry=True,
    )

    # Security gate runs before every command, message, and callback.
    app.add_handler(TypeHandler(Update, access_guard), group=-1)
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("jobs", jobs_command))
    app.add_handler(CallbackQueryHandler(handle_jobs_callback, pattern="^jobs_"))
    app.add_handler(CommandHandler("info", cmd_info))
    app.add_handler(CommandHandler("ssh", cmd_ssh))
    app.add_handler(CommandHandler("reboot", cmd_reboot))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("ping", cmd_status))
    app.add_handler(CommandHandler("update", cmd_update))
    app.add_handler(CommandHandler("version", cmd_version))
    app.add_handler(CommandHandler("help", cmd_help))

    # Auto-detect VPS format tanpa /start (priority rendah, jadi tidak ganggu conversation)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, auto_add_vps))

    print("Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
