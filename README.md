# Telegram Media Downloader

Automatically download media files from Telegram groups/channels when you react to messages with ❤️. Perfect for use with Sonarr!

## Features

- React to any message with ❤️ (heart) to download its media
- Works with regular groups, channels, and topic-based groups (forums)
- Automatic file type filtering
- Integrates seamlessly with Sonarr

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

# Optional: Specify which groups to monitor (comma-separated)
# Leave empty to monitor ALL groups
monitored_chats = @groupname1, @groupname2

[Download]
download_path = /mnt/nas/incoming    # Where files will be downloaded

# Emoji to trigger download (default: ❤️)
reaction_emoji = ❤️

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

### How it works

1. **Start the script** (see below for manual or service setup)
2. **Find a video/file** you want to download in any Telegram group
3. **React with ❤️** to the message
4. **File downloads automatically** to `/mnt/nas/incoming`
5. **Sonarr picks it up** and processes it

### Manual execution

```bash
python3 telegram_downloader.py
```

The script will run continuously and monitor for your ❤️ reactions in real-time.

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

## Topic Groups Support

The script fully supports Telegram topic groups (forums). Just react with ❤️ to any message in any topic, and it will download the media. You don't need to configure anything special.

## Advanced Configuration

### Monitor specific groups only

Edit `config.ini` and set `monitored_chats`:

```ini
monitored_chats = @mytvgroup, @animegroup, -1001234567890
```

You can use:
- Group/channel username (e.g., `@groupname`)
- Numeric group ID (e.g., `-1001234567890`)

To get a group's ID, forward a message from it to [@userinfobot](https://t.me/userinfobot).

### Change the reaction emoji

Don't like ❤️? Change it in `config.ini`:

```ini
reaction_emoji = 📥
```

Any emoji works: 👍, ⬇️, 💾, etc.

## Troubleshooting

### "Permission denied" when running the script
Ensure the user running the script has write access to the download folder:

```bash
sudo chown -R $USER:$USER /mnt/nas/incoming
chmod 755 /mnt/nas/incoming
```

### Script doesn't detect my reactions
- Make sure the script is running (`systemctl status telegram_downloader`)
- Check that you're using the correct emoji (default: ❤️)
- Verify the group is being monitored (check `monitored_chats` in config)

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
