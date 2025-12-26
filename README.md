# Telegram Media Downloader

Automatically download media files from Telegram groups/channels when you react to messages with ❤️. Perfect for use with Sonarr!

## Features

- ✅ React to any message with ❤️ (heart) to download its media
- ✅ Works with regular groups, channels, and topic-based groups (forums)
- ✅ Automatic file type filtering
- ✅ Concurrent downloads with configurable limits
- ✅ Sonarr integration for automatic TV show organization
- ✅ Telegram notifications for download status
- ✅ Download files by posting Telegram links
- ✅ Handles media groups (multiple files per message)
- ✅ Resume incomplete downloads

## Installation

### 1. Install Python and dependencies

**On Debian/Ubuntu and derivatives:**
```bash
sudo apt install python3-telethon python3-aiohttp
```

**On other Linux distributions/Synology:**
```bash
pip3 install telethon aiohttp

# Or with --user if you don't have admin privileges
pip3 install --user telethon aiohttp
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
download_path = /mnt/nas/incoming
reaction_emoji = ❤
file_extensions = .mp4,.mkv,.avi,.mov,.wmv,.flv,.webm,.m4v,.torrent,.nzb,.srt,.sub
max_file_size_mb = 0                 # 0 = no limit
max_concurrent_downloads = 2         # 1-5 recommended

[Sonarr]
# Enable automatic import to Sonarr (requires series to already be added)
enabled = false
sonarr_url = http://localhost:8989
sonarr_api_key = YOUR_SONARR_API_KEY

[Notifications]
# Send notifications to Telegram chat (empty = disabled, "me" = Saved Messages)
notification_chat = me

[LinkDownload]
# Enable downloading by posting t.me links in a specific chat
enabled = false
link_chat = me

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

### Method 1: React with ❤️ (Primary method)

1. **Start the script** (see below for manual or service setup)
2. **Find a video/file** you want to download in any Telegram group
3. **React with ❤️** to the message
4. **File downloads automatically** to `/mnt/nas/incoming`
5. **Sonarr picks it up** (if enabled) and processes it

### Method 2: Post Telegram links

If you enable `[LinkDownload]` in config:

1. Copy a message link from Telegram (right-click message → Copy Link)
2. Post it in your configured `link_chat` (e.g., Saved Messages)
3. Script downloads the file automatically

Example:
```
https://t.me/somegroup/12345
```

### How it works

**Reaction-based:**
- You react with ❤️ → Script detects reaction → Downloads file

**Link-based:**
- You post t.me link → Script fetches message → Downloads file

**Media groups:**
- If a message is part of a group (e.g., 10 episodes), it downloads ALL files in the group

**Concurrent downloads:**
- Maximum 2 files download simultaneously (configurable)
- Additional downloads queue automatically

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

## Sonarr Integration

### Setup

1. **Enable in config.ini:**
```ini
[Sonarr]
enabled = true
sonarr_url = http://localhost:8989
sonarr_api_key = YOUR_API_KEY  # Get from Sonarr → Settings → General → API Key
```

2. **Install aiohttp dependency:**
```bash
pip3 install aiohttp
# Or: sudo apt install python3-aiohttp
```

### How it works

**After downloading a video file:**
1. Script triggers Sonarr to scan the download folder
2. Sonarr parses the filename (e.g., "Frikjent.S01E01...")
3. Sonarr matches it against your existing series
4. Sonarr imports and moves the file to the correct location

**Important limitations:**
- ✅ The TV series **MUST already be added** to Sonarr
- ✅ Episode does **NOT** need to be marked as "Wanted"
- ❌ If series is not in Sonarr, file stays in download folder (no auto-add)
- ✅ Sonarr will handle renaming, quality upgrades, etc. automatically

**Workflow:**
1. Add TV series to Sonarr manually
2. React with ❤️ to episode in Telegram
3. Script downloads to `/mnt/nas/incoming`
4. Sonarr automatically imports and organizes

## Telegram Notifications

Enable notifications to get updates about downloads:

```ini
[Notifications]
notification_chat = me  # Or @your_channel
```

You'll receive messages like:
```
⬇️ Downloading: Episode.mkv
From: TV Group

✅ Downloaded: Episode.mkv

❌ Download failed: Episode.mkv
Incomplete file
```

**Options:**
- `me` - Send to Saved Messages (only you see them)
- `@channel` - Send to a channel you own
- `username` - Send to a specific chat

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

### Adjust concurrent downloads

```ini
max_concurrent_downloads = 3  # Download 3 files at once
```

**Recommendations:**
- `1` - Slowest, but safest (no rate limiting)
- `2` - Default, good balance
- `3-5` - Faster, may trigger Telegram rate limits

### File size limits

```ini
max_file_size_mb = 5000  # Skip files larger than 5GB
```

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
- Note: Telegram sometimes has delays sending reaction events

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

### Incomplete downloads
The script now verifies file sizes and will:
- Detect incomplete files
- Delete them automatically
- Re-download from scratch

### Sonarr not importing files

**Check:**
1. Is the series already added to Sonarr? (Required!)
2. Is Sonarr's API key correct in config?
3. Is Sonarr accessible at the configured URL?
4. Check Sonarr logs: Settings → System → Logs

**Common issues:**
- Series not in Sonarr → File won't be imported (add series manually first)
- Wrong filename format → Sonarr can't parse it
- Quality profile mismatch → Check Sonarr's quality settings

### Link downloads not working

**Check:**
1. Is `[LinkDownload]` enabled in config?
2. Are you posting links in the correct chat?
3. Do you have access to the linked message?

**Valid link format:**
```
https://t.me/channelname/12345
```

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

### View real-time logs
```bash
# Service logs
sudo journalctl -u telegram_downloader -f

# Or script log file
tail -f telegram_downloader.log
```

## Example Workflows

### Workflow 1: TV Series with Sonarr
1. Add "Breaking Bad" to Sonarr
2. Find episode in Telegram group
3. React with ❤️
4. Script downloads to `/mnt/nas/incoming`
5. Sonarr imports to `/mnt/media/TV Shows/Breaking Bad/Season 1/`
6. Get Telegram notification: "✅ Downloaded: Breaking.Bad.S01E01.mkv"

### Workflow 2: Manual organization
1. React with ❤️ to files in Telegram
2. Files download to `/mnt/nas/incoming`
3. You manually organize them later
4. Get notifications about download progress

### Workflow 3: Link-based batch download
1. Browse Telegram on your phone
2. Copy links to all episodes you want
3. Paste them in Saved Messages (one per line)
4. Script downloads all of them automatically

## Security

- `config.ini` contains sensitive data (API keys). Keep this file private.
- The `telegram_session.session` file gives full access to your Telegram account. Protect it well.
- Never use your API keys in public repositories or share them with others.
- Sonarr API key gives full access to your Sonarr instance - keep it secure.

## Performance Tips

- Use SSD for download folder for faster file operations
- Adjust `max_concurrent_downloads` based on your internet speed
- Enable Sonarr integration to automatically organize files
- Use notifications to monitor downloads without checking logs

## License

This script is made for personal use. Use at your own risk.
