# Telegram Media Downloader

Automatically download media files from Telegram Saved Messages to a folder that Sonarr can monitor.

## Installation

### 1. Install Python and Telethon

**On Debian/Ubuntu and derivatives:**
```bash
sudo apt install python3-telethon
```

**On other Linux distributions/Synology:**
```bash
pip3 install telethon

# Or with --user if you don't have admin privileges
pip3 install --user telethon
```

### 2. Configure the script

Edit `config.ini` and fill in your values:

```ini
[Telegram]
api_id = YOUR_API_ID          # From https://my.telegram.org/apps
api_hash = YOUR_API_HASH      # From https://my.telegram.org/apps
phone = +1234567890           # Your phone number with country code

[Download]
download_path = /mnt/nas/incoming    # Where files will be downloaded
file_extensions = .mp4,.mkv,.avi,.mov,.wmv,.flv,.webm,.m4v,.torrent,.nzb
max_file_size_mb = 0                 # 0 = no limit

[Logging]
log_file = telegram_downloader.log
log_level = INFO
```

### 3. First run

```bash
python3 telegram_downloader.py
```

The first time you run the script, you'll receive a code via Telegram that you need to enter.
After this, the session is saved and you won't need to log in again.

## Usage

### Manual execution

```bash
python3 telegram_downloader.py
```

The script will now run continuously and download media as soon as you save something to Saved Messages.

### Run as systemd service (recommended)

This ensures the script starts automatically on boot and restarts if it crashes.

1. **Edit the service file:**

```bash
nano telegram_downloader.service
```

Change:
- `YOUR_USERNAME` to your username
- `/path/to/telegram_downloader` to the folder where the script is located

2. **Install the service:**

```bash
sudo cp telegram_downloader.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable telegram_downloader
sudo systemctl start telegram_downloader
```

3. **Check status:**

```bash
sudo systemctl status telegram_downloader
```

4. **View logs:**

```bash
sudo journalctl -u telegram_downloader -f
```

## Sonarr Setup

To make Sonarr automatically pick up the files:

1. Go to **Settings → Download Clients** in Sonarr
2. Add a new "Download Client"
3. Select "Manual" or "Blackhole" type
4. Set "Watch Folder" to `/mnt/nas/incoming`
5. Enable "Remove Completed Downloads"

Alternatively, you can set up an "Import List" or use Sonarr's "Drone Factory" functionality.

## How It Works

1. You save or forward a video/torrent to "Saved Messages" in Telegram
2. The script detects the new message immediately
3. The file is downloaded to `/mnt/nas/incoming`
4. Sonarr monitors this folder and imports the file automatically
5. Sonarr identifies the series and moves the file to the correct folder

## Troubleshooting

### "Permission denied" when running the script
Ensure the user running the script has write access to the download folder:

```bash
sudo chown -R $USER:$USER /mnt/nas/incoming
chmod 755 /mnt/nas/incoming
```

### Script downloads everything, not just media
Check `file_extensions` in `config.ini`. Set it to only the formats you want.

### Service won't start
Check the logs:

```bash
sudo journalctl -u telegram_downloader -n 50
```

### Duplicate downloads
The script checks if a file already exists before downloading. If Sonarr moves the file quickly,
the same file might be downloaded again. Solution: Let files stay in the incoming folder a bit longer,
or configure Sonarr to copy instead of move.

## Commands

### Stop the service
```bash
sudo systemctl stop telegram_downloader
```

### Start the service
```bash
sudo systemctl start telegram_downloader
```

### Restart the service
```bash
sudo systemctl restart telegram_downloader
```

### Disable autostart
```bash
sudo systemctl disable telegram_downloader
```

## Security

- `config.ini` contains sensitive data (API keys). Keep this file private.
- The `telegram_session.session` file gives full access to your Telegram account. Protect it well.
- Never use your API keys in public repositories or share them with others.

## License

This script is made for personal use. Use at your own risk.
