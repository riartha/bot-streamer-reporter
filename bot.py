import discord
from discord.ext import tasks
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import pytz
import re
import asyncio  # Modul penting untuk memberi jeda waktu (delay)

# ==========================================
# KONFIGURASI GOOGLE SHEETS
# ==========================================
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
CREDENTIALS_FILE = "credentials.json"  # Pastikan file JSON ada di folder yang sama
SPREADSHEET_ID = "1M2OVjIPshFmUuKB-y6t5oCCc1xqH3A9nQMPr8lFB8vg"
SHEET_NAME = "Sheet Absensi Only (Test)"

# ==========================================
# KONFIGURASI BOT DISCORD
# ==========================================
TOKEN = 'MTU2MTIwMDY5NDYwMDU0MDIzMQ.GQGgOb.BRsDodAY8NaOmnky1V4nD0xfsjYxOlfZICjPcQ'
DEDICATED_CHANNEL_ID = 1560315528525119600 # GANTI DENGAN ID CHANNEL TEMPAT ABSENSI
BOT_NAME = "Blaze Streamer Bot" # Anda bisa ubah nama ini sesuai keinginan

# Setting Intents Discord
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# ==========================================
# FUNGSI-FUNGSI PENDUKUNG
# ==========================================
def connect_gsheet():
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, SCOPE)
    gc = gspread.authorize(creds)
    sheet = gc.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)
    return sheet

def format_tanggal(dt):
    hari_indo = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
    bulan_indo = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
    
    nama_hari = hari_indo[dt.weekday()]
    nama_bulan = bulan_indo[dt.month - 1]
    tanggal_dd = f"{dt.day:02d}"
    
    return f"{nama_hari}, {tanggal_dd} {nama_bulan} {dt.year}"

def format_append_chat(existing_text, new_chat):
    if not existing_text or str(existing_text).strip() == "":
        return f"[1] {new_chat}"
    
    existing_str = str(existing_text).strip()
    matches = re.findall(r'\[(\d+)\]', existing_str)
    if matches:
        next_num = max(int(m) for m in matches) + 1
    else:
        existing_str = f"[1] {existing_str}"
        next_num = 2
        
    return f"{existing_str}\n[{next_num}] {new_chat}"

def is_chat_recorded(existing_text, new_chat):
    if not existing_text or str(existing_text).strip() == "":
        return False
    
    recorded_chats = re.split(r'\[\d+\]\s*', str(existing_text))
    
    # Normalisasi spasi agar pengecekan lebih akurat (kebal terhadap enter/spasi berlebih)
    new_chat_norm = " ".join(new_chat.strip().split())
    recorded_chats_norm = [" ".join(chat.strip().split()) for chat in recorded_chats if chat.strip()]
    
    return new_chat_norm in recorded_chats_norm

# ==========================================
# EVENT DISCORD BOT
# ==========================================
@client.event
async def on_ready():
    print(f'Login berhasil sebagai {client.user} | Custom Name: {BOT_NAME}')
    
    if not hourly_scanner.is_running():
        hourly_scanner.start()
    
    print('Bot siap memantau absensi (Mode Siluman & Anti Limit aktif)!')

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.channel.id == DEDICATED_CHANNEL_ID and message.content.strip():
        
        discord_id = str(message.author.name)
        isi_chat = str(message.content)
        
        tz = pytz.timezone('Asia/Jakarta')
        now = datetime.now(tz)
        tanggal_pesan = format_tanggal(now)

        try:
            sheet = connect_gsheet()
            col_a_values = sheet.col_values(1)
            try:
                row_target = col_a_values.index(discord_id) + 1 
            except ValueError:
                return

            row_2_values = sheet.row_values(2)
            try:
                col_target = row_2_values.index(tanggal_pesan) + 1
            except ValueError:
                return
            
            status_absen = sheet.cell(row_target, col_target).value
            
            if is_chat_recorded(status_absen, isi_chat):
                return

            teks_baru = format_append_chat(status_absen, isi_chat)
            sheet.update_cell(row_target, col_target, teks_baru)

        except Exception as e:
            print(f"Error sistem real-time: {e}")

# ==========================================
# AUTO-SCANNER BACKGROUND (DENGAN DELAY ANTI 429 LIMIT)
# ==========================================
@tasks.loop(hours=1)
async def hourly_scanner():
    tz = pytz.timezone('Asia/Jakarta')
    waktu_mulai = datetime.now(tz).strftime('%H:%M:%S')
    
    print(f"\n[{waktu_mulai}] === MEMULAI SCANNING OTOMATIS ===")
    
    channel = client.get_channel(DEDICATED_CHANNEL_ID)
    if not channel:
        print("Error: Channel tidak ditemukan!")
        return
        
    try:
        sheet = connect_gsheet()
        all_values = sheet.get_all_values()
        
        if not all_values or len(all_values) < 2:
            print("Error: Data Sheet Kosong atau format salah.")
            return
            
        col_a_values = [row[0] if len(row) > 0 else "" for row in all_values]
        row_2_values = all_values[1]
        
        rekap_hasil = {}
        
        messages = [msg async for msg in channel.history(limit=2000)]
        messages.reverse() 
        
        print(f"Total pesan di channel: {len(messages)} pesan.")
        print("Mulai menyinkronkan data yang terlewat (Akan memakan waktu beberapa saat agar aman dari Limit Google)...")
        
        for msg in messages:
            if msg.author == client.user or not msg.content.strip(): 
                continue
            
            waktu_pesan_utc = msg.created_at
            waktu_pesan_wib = waktu_pesan_utc.astimezone(tz)
            tanggal_pesan = format_tanggal(waktu_pesan_wib)
            
            discord_id = str(msg.author.name)
            
            try:
                row_target = col_a_values.index(discord_id) + 1
            except ValueError:
                continue
            
            try:
                col_target = row_2_values.index(tanggal_pesan) + 1
            except ValueError:
                continue
            
            current_val = ""
            if len(all_values) >= row_target and len(all_values[row_target - 1]) >= col_target:
                current_val = all_values[row_target - 1][col_target - 1]
            
            # Jika fisik chat sudah ada di Google Sheet, abaikan (lanjut chat berikutnya)
            if is_chat_recorded(current_val, msg.content):
                continue 
            
            # Jika belum ada:
            updated_text = format_append_chat(current_val, msg.content)
            
            try:
                # 1. Update ke Google Sheet
                sheet.update_cell(row_target, col_target, updated_text)
                
                # 2. Update ke cache lokal
                while len(all_values) < row_target:
                    all_values.append([])
                while len(all_values[row_target - 1]) < col_target:
                    all_values[row_target - 1].append("")
                all_values[row_target - 1][col_target - 1] = updated_text
                
                # 3. Catat hasil ke log CMD
                if tanggal_pesan not in rekap_hasil:
                    rekap_hasil[tanggal_pesan] = 0
                rekap_hasil[tanggal_pesan] += 1
                
                # ============================================================
                # OBAT UNTUK ERROR 429: Jeda 2 Detik sebelum chat berikutnya
                # ============================================================
                await asyncio.sleep(2.0)
                
            except Exception as write_error:
                print(f"[{datetime.now(tz).strftime('%H:%M:%S')}] Gagal merekam 1 chat dari {discord_id} - Error: {write_error}")
                # Jika 1 chat gagal karena limit/error lain, beri jeda lebih lama dan paksa lanjut ke chat selanjutnya
                await asyncio.sleep(5.0) 
                continue 
                
        # === NOTIFIKASI SUMMARY ===
        waktu_selesai = datetime.now(tz).strftime('%H:%M:%S')
        print(f"[{waktu_selesai}] === SCANNING SELESAI ===")
        
        if not rekap_hasil:
            print("Hasil: Tidak ada data baru yang ditambahkan (Semua sinkron).")
        else:
            print("Hasil Sinkronisasi (Menambahkan data yang hilang ke GSheet):")
            for tgl, jumlah in rekap_hasil.items():
                print(f" -> {tgl} : Berhasil merekam {jumlah} chat secara diam-diam")
        print("=========================================\n")
                    
    except Exception as e:
        print(f"Error fatal pada Hourly Scanner: {e}")

# Jalankan Bot
client.run(TOKEN)