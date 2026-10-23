import discord
from discord.ext import tasks
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import pytz
import re
import asyncio
import sys

# ==========================================
# KONFIGURASI GOOGLE SHEETS
# ==========================================
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
CREDENTIALS_FILE = "credentials.json"
SPREADSHEET_ID = ""

SHEET_NAME_ABSEN = "Sheet Absensi Only (Test)"
SHEET_NAME_REWARD = "Sheet Reward Streamer"
SHEET_NAME_KUPON = "Sheet Kupon Streamer" # NAMA SHEET UNTUK FITUR 3

# ==========================================
# KONFIGURASI BOT DISCORD
# ==========================================
TOKEN = ''

DEDICATED_CHANNEL_ID_ABSEN =   # Ganti ID Channel Absen
DEDICATED_CHANNEL_ID_REWARD =  # Ganti ID Channel Reward
DEDICATED_CHANNEL_ID_KUPON =   # Ganti ID Channel Kupon (FITUR 3)

BOT_NAME = "Blaze Streamer Bot"
USER_MODE = "1" 

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# ==========================================
# FUNGSI PENDUKUNG
# ==========================================
def connect_gsheet(sheet_name):
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, SCOPE)
    gc = gspread.authorize(creds)
    sheet = gc.open_by_key(SPREADSHEET_ID).worksheet(sheet_name)
    return sheet

def format_tanggal(dt):
    hari_indo = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
    bulan_indo = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
    nama_hari = hari_indo[dt.weekday()]
    nama_bulan = bulan_indo[dt.month - 1]
    return f"{nama_hari}, {dt.day:02d} {nama_bulan} {dt.year}"

# Format Chat untuk Fitur 1 (Tanpa Tanggal/Jam)
def format_append_chat_absen(existing_text, new_chat):
    if not existing_text or str(existing_text).strip() == "": return f"[1] {new_chat}"
    existing_str = str(existing_text).strip()
    matches = re.findall(r'\[(\d+)\]', existing_str)
    next_num = max(int(m) for m in matches) + 1 if matches else 2
    return f"{existing_str}\n[{next_num}] {new_chat}"

def is_chat_recorded_absen(existing_text, new_chat):
    if not existing_text or str(existing_text).strip() == "": return False
    recorded_chats = re.split(r'\[\d+\]\s*', str(existing_text))
    new_chat_norm = " ".join(new_chat.strip().split())
    recorded_chats_norm = [" ".join(chat.strip().split()) for chat in recorded_chats if chat.strip()]
    return new_chat_norm in recorded_chats_norm

# Format Chat untuk Fitur 2 & 3 (Dengan Tanggal dan Jam)
def format_append_chat_with_date(existing_text, new_chat, dt):
    tanggal_jam = dt.strftime('%d %B %Y, %H:%M')
    formatted_new_chat = f"{tanggal_jam} | {new_chat}"
    if not existing_text or str(existing_text).strip() == "": return f"[1] {formatted_new_chat}"
    existing_str = str(existing_text).strip()
    matches = re.findall(r'\[(\d+)\]', existing_str)
    next_num = max(int(m) for m in matches) + 1 if matches else 2
    return f"{existing_str}\n[{next_num}] {formatted_new_chat}"

def is_chat_recorded_with_date(existing_text, new_chat):
    if not existing_text or str(existing_text).strip() == "": return False
    new_chat_norm = " ".join(new_chat.strip().split())
    existing_norm = " ".join(str(existing_text).strip().split())
    return new_chat_norm in existing_norm

# Fungsi Rangkuman Khusus Fitur 3 (Mencari "Nick")
def generate_kupon_summary(full_chat_text):
    if not full_chat_text or str(full_chat_text).strip() == "":
        return ""

    # Memecah seluruh teks chat berdasarkan pemisah waktu (contoh: "[1] 24 Oktober 2026, 12:00 | ")
    delimiter_pattern = r'\[\d+\] \d{2} [a-zA-Z]+ \d{4}, \d{2}:\d{2} \| '
    raw_chats = re.split(delimiter_pattern, str(full_chat_text))
    
    counts = {}
    for chat in raw_chats:
        chat = chat.strip()
        if not chat:
            continue

        # Mencari teks setelah kata "Nick:" (mengabaikan huruf besar/kecil dan spasi)
        match = re.search(r'(?i)nick\s*:\s*([^\n]+)', chat)
        if match:
            nick_val = match.group(1).strip()
            counts[nick_val] = counts.get(nick_val, 0) + 1
        else:
            counts["<unidentified>"] = counts.get("<unidentified>", 0) + 1

    # Mengubah hasil dictionary ke dalam bentuk format teks akhir
    result = []
    for nick_name, jumlah in counts.items():
        result.append(f"{nick_name} : {jumlah}x")

    return "\n".join(result)

# ==========================================
# FUNGSI SCANNER ABSEN (FITUR 1)
# ==========================================
async def scan_absen_live():
    tz = pytz.timezone('Asia/Jakarta')
    print(f"\n[{datetime.now(tz).strftime('%H:%M:%S')}] --- [FITUR 1] SCANNING ABSEN LIVE ---")
    
    channel = client.get_channel(DEDICATED_CHANNEL_ID_ABSEN)
    if not channel:
        print("Error: Channel Absen Live tidak ditemukan atau ID Salah!")
        return
        
    try:
        print("-> Menghubungkan ke Google Sheet Absen...")
        sheet = connect_gsheet(SHEET_NAME_ABSEN)
        all_values = sheet.get_all_values()
        
        if not all_values or len(all_values) < 2: return
            
        col_a_values = [row[0] if len(row) > 0 else "" for row in all_values]
        row_2_values = all_values[1]
        rekap_hasil = {}
        
        messages = [msg async for msg in channel.history(limit=2000)]
        messages.reverse() 
        print(f"-> Berhasil menarik {len(messages)} pesan. Mulai mencocokkan data...")
        
        for index, msg in enumerate(messages):
            if msg.author == client.user or not msg.content.strip(): continue
            
            waktu_pesan_wib = msg.created_at.astimezone(tz)
            tanggal_pesan = format_tanggal(waktu_pesan_wib)
            discord_id = str(msg.author.name) 
            
            try: row_target = col_a_values.index(discord_id) + 1
            except ValueError: continue
            
            try: col_target = row_2_values.index(tanggal_pesan) + 1
            except ValueError: continue
            
            current_val = ""
            if len(all_values) >= row_target and len(all_values[row_target - 1]) >= col_target:
                current_val = all_values[row_target - 1][col_target - 1]
            
            if is_chat_recorded_absen(current_val, msg.content): continue 
            
            updated_text = format_append_chat_absen(current_val, msg.content)
            
            try:
                sheet.update_cell(row_target, col_target, updated_text)
                while len(all_values) < row_target: all_values.append([])
                while len(all_values[row_target - 1]) < col_target: all_values[row_target - 1].append("")
                all_values[row_target - 1][col_target - 1] = updated_text
                
                rekap_hasil[tanggal_pesan] = rekap_hasil.get(tanggal_pesan, 0) + 1
                await asyncio.sleep(2.0)
            except Exception as e:
                print(f"[!] Gagal update absen {discord_id}: {e}")
                await asyncio.sleep(5.0) 
                
        if not rekap_hasil:
            print("-> Selesai Scan Absen. (Semua data aman/sinkron).")
        else:
            print(f"-> Selesai! Terekam chat absen baru: {rekap_hasil}")
    except Exception as e:
        print(f"Error Fatal di Fitur Absen: {e}")

# ==========================================
# FUNGSI SCANNER REWARD (FITUR 2)
# ==========================================
async def scan_reward_streamer():
    tz = pytz.timezone('Asia/Jakarta')
    print(f"\n[{datetime.now(tz).strftime('%H:%M:%S')}] --- [FITUR 2] SCANNING REWARD STREAMER ---")
    
    channel = client.get_channel(DEDICATED_CHANNEL_ID_REWARD)
    if not channel:
        print("Error: Channel Reward Streamer tidak ditemukan atau ID Salah!")
        return
        
    try:
        print("-> Menghubungkan ke Google Sheet Reward...")
        sheet = connect_gsheet(SHEET_NAME_REWARD)
        all_values = sheet.get_all_values()
        
        col_a_values = [str(row[0]).strip() if len(row) > 0 else "" for row in all_values]
        
        messages = [msg async for msg in channel.history(limit=2000)]
        messages.reverse()
        print(f"-> Berhasil menarik {len(messages)} pesan. Mulai mencocokkan data...")
        
        added_users = 0
        recorded_chats = 0
        
        for msg in messages:
            if msg.author == client.user or not msg.content.strip(): continue
            
            author_id = str(msg.author.name) 
            author_name = str(msg.author.display_name) 
            if not author_name or author_name.strip() == "":
                author_name = "<username_manual>"
                
            waktu_pesan_wib = msg.created_at.astimezone(tz)
            
            if author_id not in col_a_values:
                print(f"[*] Menambahkan user baru: {author_id} ({author_name})")
                chat_awal = format_append_chat_with_date("", msg.content, waktu_pesan_wib)
                
                try: new_row_number = col_a_values.index("") + 1
                except ValueError: new_row_number = len(col_a_values) + 1
                
                try:
                    sheet.update_cell(new_row_number, 1, author_id)
                    sheet.update_cell(new_row_number, 2, author_name)
                    sheet.update_cell(new_row_number, 4, "√") # Kolom D Status
                    sheet.update_cell(new_row_number, 5, chat_awal) # Kolom E Chat Logs
                    
                    while len(all_values) < new_row_number: all_values.append([])
                    while len(all_values[new_row_number - 1]) < 5: all_values[new_row_number - 1].append("")
                        
                    all_values[new_row_number - 1][0] = author_id
                    all_values[new_row_number - 1][1] = author_name
                    all_values[new_row_number - 1][3] = "√"
                    all_values[new_row_number - 1][4] = chat_awal
                    
                    col_a_values = [str(row[0]).strip() if len(row) > 0 else "" for row in all_values]
                    added_users += 1
                    recorded_chats += 1
                    await asyncio.sleep(2.0) 
                except Exception as e:
                    print(f"[!] Gagal menambah user {author_id}: {e}")
                    await asyncio.sleep(5.0)
                continue
            
            row_target = col_a_values.index(author_id) + 1
            while len(all_values[row_target - 1]) < 5: all_values[row_target - 1].append("")
                
            current_status = all_values[row_target - 1][3] 
            current_chat = all_values[row_target - 1][4]   
            
            if is_chat_recorded_with_date(current_chat, msg.content): continue
            
            updated_chat = format_append_chat_with_date(current_chat, msg.content, waktu_pesan_wib)
            
            try:
                sheet.update_cell(row_target, 4, "√")
                sheet.update_cell(row_target, 5, updated_chat)
                
                all_values[row_target - 1][3] = "√"
                all_values[row_target - 1][4] = updated_chat
                recorded_chats += 1
                await asyncio.sleep(2.0)
            except Exception as e:
                print(f"[!] Gagal merekam chat reward {author_id}: {e}")
                await asyncio.sleep(5.0)
                
        print("-> Mensinkronkan status '×' untuk user yang tidak aktif...")
        for i in range(1, len(all_values)): 
            while len(all_values[i]) < 5: all_values[i].append("")
                
            status = all_values[i][3] 
            chat_log = all_values[i][4] 
            
            if str(all_values[i][0]).strip() != "" and (not chat_log or str(chat_log).strip() == "") and status != "×":
                try:
                    sheet.update_cell(i + 1, 4, "×")
                    all_values[i][3] = "×"
                    await asyncio.sleep(2.0)
                except Exception:
                    pass

        print(f"-> Selesai! User Baru: {added_users} | Chat Direkam: {recorded_chats}")
    except Exception as e:
        print(f"Error Fatal di Fitur Reward: {e}")

# ==========================================
# FUNGSI SCANNER KUPON (FITUR 3)
# ==========================================
async def scan_kupon_streamer():
    tz = pytz.timezone('Asia/Jakarta')
    print(f"\n[{datetime.now(tz).strftime('%H:%M:%S')}] --- [FITUR 3] SCANNING KUPON STREAMER ---")
    
    channel = client.get_channel(DEDICATED_CHANNEL_ID_KUPON)
    if not channel:
        print("Error: Channel Kupon Streamer tidak ditemukan atau ID Salah!")
        return
        
    try:
        print("-> Menghubungkan ke Google Sheet Kupon...")
        sheet = connect_gsheet(SHEET_NAME_KUPON)
        all_values = sheet.get_all_values()
        
        col_a_values = [str(row[0]).strip() if len(row) > 0 else "" for row in all_values]
        
        print("-> Menarik riwayat chat dari Discord (Mohon tunggu)...")
        messages = [msg async for msg in channel.history(limit=2000)]
        messages.reverse()
        print(f"-> Berhasil menarik {len(messages)} pesan. Mulai mencocokkan data...")
        
        added_users = 0
        recorded_chats = 0
        
        for msg in messages:
            if msg.author == client.user or not msg.content.strip(): continue
            
            author_id = str(msg.author.name) # Kolom A (Misal: thaa69)
            author_name = str(msg.author.display_name) # Kolom B
            if not author_name or author_name.strip() == "":
                author_name = "<username_manual>"
                
            waktu_pesan_wib = msg.created_at.astimezone(tz)
            
            # 1. JIKA USER BARU
            if author_id not in col_a_values:
                print(f"[*] Menambahkan user baru: {author_id} ({author_name})")
                
                # Buat chat logs & proses extract NICK (Summary)
                chat_awal = format_append_chat_with_date("", msg.content, waktu_pesan_wib)
                summary_awal = generate_kupon_summary(chat_awal)
                
                try: new_row_number = col_a_values.index("") + 1
                except ValueError: new_row_number = len(col_a_values) + 1
                
                try:
                    sheet.update_cell(new_row_number, 1, author_id) # Kolom A
                    sheet.update_cell(new_row_number, 2, author_name) # Kolom B
                    sheet.update_cell(new_row_number, 4, chat_awal) # Kolom D (Chat Logs)
                    sheet.update_cell(new_row_number, 5, summary_awal) # Kolom E (Rangkuman Nick)
                    
                    while len(all_values) < new_row_number: all_values.append([])
                    while len(all_values[new_row_number - 1]) < 5: all_values[new_row_number - 1].append("")
                        
                    all_values[new_row_number - 1][0] = author_id
                    all_values[new_row_number - 1][1] = author_name
                    all_values[new_row_number - 1][3] = chat_awal
                    all_values[new_row_number - 1][4] = summary_awal
                    
                    col_a_values = [str(row[0]).strip() if len(row) > 0 else "" for row in all_values]
                    added_users += 1
                    recorded_chats += 1
                    await asyncio.sleep(2.0) 
                except Exception as e:
                    print(f"[!] Gagal menambah user kupon {author_id}: {e}")
                    await asyncio.sleep(5.0)
                continue
            
            # 2. JIKA USER SUDAH ADA
            row_target = col_a_values.index(author_id) + 1
            while len(all_values[row_target - 1]) < 5: all_values[row_target - 1].append("")
                
            current_chat = all_values[row_target - 1][3] # Kolom D 
            
            if is_chat_recorded_with_date(current_chat, msg.content): continue
            
            updated_chat = format_append_chat_with_date(current_chat, msg.content, waktu_pesan_wib)
            updated_summary = generate_kupon_summary(updated_chat) # Merangkum ulang isi keseluruhan chat log
            
            try:
                sheet.update_cell(row_target, 4, updated_chat) # Kolom D
                sheet.update_cell(row_target, 5, updated_summary) # Kolom E
                
                all_values[row_target - 1][3] = updated_chat
                all_values[row_target - 1][4] = updated_summary
                recorded_chats += 1
                await asyncio.sleep(2.0)
            except Exception as e:
                print(f"[!] Gagal merekam chat kupon {author_id}: {e}")
                await asyncio.sleep(5.0)
                
        print(f"-> Selesai! User Baru: {added_users} | Chat Direkam: {recorded_chats}")
    except Exception as e:
        print(f"Error Fatal di Fitur Kupon: {e}")

# ==========================================
# MASTER SCHEDULER
# ==========================================
@tasks.loop(hours=1)
async def master_scanner():
    if USER_MODE in ["1", "4"]:
        await scan_absen_live()
    if USER_MODE in ["2", "4"]:
        await scan_reward_streamer()
    if USER_MODE in ["3", "4"]:
        await scan_kupon_streamer()
        
    print("\n=========================================")
    tz = pytz.timezone('Asia/Jakarta')
    print(f"[{datetime.now(tz).strftime('%H:%M:%S')}] Siklus Semua Scanning Selesai.")
    print("Menunggu 1 jam berikutnya...")
    print("=========================================\n")

# ==========================================
# EVENT DISCORD
# ==========================================
@client.event
async def on_ready():
    print(f'\n[SUCCESS] Login berhasil sebagai {client.user}')
    print(f"Mode Terpilih: {USER_MODE}")
    if not master_scanner.is_running():
        master_scanner.start()

# ==========================================
# MAIN MENU (CLI COMMAND PROMPT)
# ==========================================
def main():
    global USER_MODE
    print("=========================================")
    print("      SYSTEM BOT DISCORD & GSHEET        ")
    print("=========================================")
    print("Pilih Fitur yang ingin diaktifkan:")
    print("1. Scan Channel Absen Live (Fitur 1)")
    print("2. Scan Channel Reward Streamer (Fitur 2)")
    print("3. Scan Channel Kupon Streamer (Fitur 3)")
    print("4. Jalankan Ketiganya Berurutan (Opsi 1 -> 2 -> 3)")
    print("=========================================")
    
    while True:
        pilihan = input("Masukkan angka pilihan (1/2/3/4): ").strip()
        if pilihan in ["1", "2", "3", "4"]:
            USER_MODE = pilihan
            break
        else:
            print("Pilihan tidak valid, mohon ketik angka 1, 2, 3, atau 4.")
            
    print("\nMenghubungkan ke Server Discord...")
    client.run(TOKEN)

if __name__ == "__main__":
    main()