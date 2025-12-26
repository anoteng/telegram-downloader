#!/usr/bin/env python3
"""
Telegram Media Downloader
Monitors groups/channels and downloads media from messages you react to with a specific emoji.
Supports topic-based groups (forums).
"""

import os
import sys
import asyncio
import logging
from pathlib import Path
from datetime import datetime
from configparser import ConfigParser
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto, UpdateMessageReactions


class TelegramDownloader:
    def __init__(self, config_path='config.ini'):
        self.config = ConfigParser()
        self.config.read(config_path)
        
        # Telegram credentials
        self.api_id = self.config.get('Telegram', 'api_id')
        self.api_hash = self.config.get('Telegram', 'api_hash')
        self.phone = self.config.get('Telegram', 'phone')
        
        # Monitored chats
        monitored = self.config.get('Telegram', 'monitored_chats', fallback='')
        self.monitored_chats = [chat.strip() for chat in monitored.split(',') if chat.strip()]
        
        # Download settings
        self.download_path = Path(self.config.get('Download', 'download_path'))
        self.reaction_emoji = self.config.get('Download', 'reaction_emoji', fallback='❤️')
        self.file_extensions = [ext.strip() for ext in 
                               self.config.get('Download', 'file_extensions').split(',') 
                               if ext.strip()]
        self.max_file_size = self.config.getint('Download', 'max_file_size_mb') * 1024 * 1024
        self.max_concurrent = self.config.getint('Download', 'max_concurrent_downloads', fallback=2)
        
        # Sonarr settings
        self.sonarr_enabled = self.config.getboolean('Sonarr', 'enabled', fallback=False)
        self.sonarr_url = self.config.get('Sonarr', 'sonarr_url', fallback='').rstrip('/')
        self.sonarr_api_key = self.config.get('Sonarr', 'sonarr_api_key', fallback='')
        
        # Notification settings
        self.notification_chat = self.config.get('Notifications', 'notification_chat', fallback='')
        
        # Link download settings
        self.link_download_enabled = self.config.getboolean('LinkDownload', 'enabled', fallback=False)
        self.link_chat = self.config.get('LinkDownload', 'link_chat', fallback='')
        
        # Setup logging
        self._setup_logging()
        
        # Create download directory if it doesn't exist
        self.download_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize Telegram client
        self.client = TelegramClient('telegram_session', self.api_id, self.api_hash)
        
        # Track downloaded messages to avoid duplicates
        self.downloaded_messages = set()
        
        # Download queue and semaphore for concurrent downloads
        self.download_queue = asyncio.Queue()
        self.download_semaphore = asyncio.Semaphore(self.max_concurrent)
        self.active_downloads = 0
        
        # Store my user ID for checking reactions
        self.my_id = None
        
        self.logger.info(f"Telegram Downloader initialized")
        self.logger.info(f"Download path: {self.download_path}")
        self.logger.info(f"Reaction emoji: {self.reaction_emoji}")
        self.logger.info(f"Max concurrent downloads: {self.max_concurrent}")
        self.logger.info(f"Monitored chats: {self.monitored_chats if self.monitored_chats else 'ALL'}")
        self.logger.info(f"File extensions filter: {self.file_extensions if self.file_extensions else 'ALL'}")
        
        if self.sonarr_enabled:
            self.logger.info(f"Sonarr integration: ENABLED ({self.sonarr_url})")
        
        if self.notification_chat:
            self.logger.info(f"Notifications: ENABLED (chat: {self.notification_chat})")
        
        if self.link_download_enabled and self.link_chat:
            self.logger.info(f"Link downloads: ENABLED (chat: {self.link_chat})")
    
    def _setup_logging(self):
        """Setup logging configuration"""
        log_file = self.config.get('Logging', 'log_file', fallback='')
        log_level = self.config.get('Logging', 'log_level', fallback='INFO')
        
        # Create logger
        self.logger = logging.getLogger('TelegramDownloader')
        self.logger.setLevel(getattr(logging, log_level))
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, log_level))
        console_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(console_format)
        self.logger.addHandler(console_handler)
        
        # File handler (if specified)
        if log_file:
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(getattr(logging, log_level))
            file_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            file_handler.setFormatter(file_format)
            self.logger.addHandler(file_handler)
    
    def _should_download(self, filename, file_size):
        """Check if file should be downloaded based on filters"""
        # Check file size limit
        if self.max_file_size > 0 and file_size > self.max_file_size:
            self.logger.info(f"Skipping {filename}: exceeds size limit ({file_size / (1024*1024):.2f} MB)")
            return False
        
        # Check file extension
        if self.file_extensions:
            ext = Path(filename).suffix.lower()
            if ext not in self.file_extensions:
                self.logger.debug(f"Skipping {filename}: extension {ext} not in filter list")
                return False
        
        return True
    
    def _sanitize_filename(self, filename):
        """Sanitize filename to remove problematic characters"""
        # Replace problematic characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        return filename
    
    async def send_notification(self, message):
        """Send notification to configured chat"""
        if not self.notification_chat:
            return
        
        try:
            # Get notification chat entity
            if self.notification_chat.lower() == 'me':
                chat = 'me'
            elif self.notification_chat.lstrip('-').isdigit():
                # Numeric chat ID
                chat_id = int(self.notification_chat)
                chat = await self.client.get_entity(chat_id)
            else:
                # Username or channel
                chat = await self.client.get_entity(self.notification_chat)
            
            await self.client.send_message(chat, message)
        except Exception as e:
            self.logger.error(f"Failed to send notification: {e}")
    
    async def import_to_sonarr(self, file_path):
        """Import a downloaded file to Sonarr"""
        if not self.sonarr_enabled or not self.sonarr_url or not self.sonarr_api_key:
            return False
        
        try:
            import aiohttp
            
            # Sonarr Manual Import API
            url = f"{self.sonarr_url}/api/v3/command"
            headers = {
                "X-Api-Key": self.sonarr_api_key,
                "Content-Type": "application/json"
            }
            
            payload = {
                "name": "DownloadedEpisodesScan",
                "path": str(file_path.parent)  # Scan the directory
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as response:
                    if response.status == 201:
                        self.logger.info(f"✓ Triggered Sonarr import for: {file_path.name}")
                        return True
                    else:
                        error_text = await response.text()
                        self.logger.error(f"Sonarr import failed ({response.status}): {error_text}")
                        return False
        
        except ImportError:
            self.logger.warning("aiohttp not installed - Sonarr integration disabled. Install with: pip install aiohttp")
            self.sonarr_enabled = False
            return False
        except Exception as e:
            self.logger.error(f"Error importing to Sonarr: {e}", exc_info=True)
            return False
    
    async def _process_link_message(self, target_message, target_channel, target_chat_title, channel_ref, msg_id):
        """Process a message from a link (handles single files and media groups)"""
        # Check if it's a media group
        if hasattr(target_message, 'grouped_id') and target_message.grouped_id:
            self.logger.info(f"Link points to media group (grouped_id: {target_message.grouped_id})")
            
            # Find all messages in the group
            min_id = max(1, int(msg_id) - 50)
            max_id = int(msg_id) + 50
            
            grouped_messages = []
            async for msg in self.client.iter_messages(target_channel, min_id=min_id, max_id=max_id, limit=None):
                if hasattr(msg, 'grouped_id') and msg.grouped_id == target_message.grouped_id:
                    grouped_messages.append(msg)
            
            grouped_messages.sort(key=lambda m: m.id)
            self.logger.info(f"Found {len(grouped_messages)} files in group")
            
            # Download all
            for msg in grouped_messages:
                asyncio.create_task(self.download_media(msg, target_chat_title))
        else:
            # Single message
            asyncio.create_task(self.download_media(target_message, target_chat_title))
        
        await self.send_notification(f"📎 Started download from link:\nt.me/{channel_ref}/{msg_id}")
    
    def _normalize_emoji(self, emoji):
        """Normalize emoji by removing variation selectors"""
        # Remove U+FE0F (variation selector-16) which makes ❤️ vs ❤
        return emoji.replace('\uFE0F', '')
    
    def _has_my_reaction(self, reactions, emoji):
        """Check if I have reacted with the specified emoji"""
        try:
            if not reactions or not reactions.results:
                return False
            
            # Normalize the target emoji
            normalized_target = self._normalize_emoji(emoji)
            self.logger.info(f"  Looking for normalized: {repr(normalized_target)} (from {repr(emoji)})")
            
            # Check each reaction
            for reaction in reactions.results:
                # Check if this is the emoji we're looking for
                if hasattr(reaction.reaction, 'emoticon'):
                    reaction_emoji = reaction.reaction.emoticon
                    normalized_reaction = self._normalize_emoji(reaction_emoji)
                    self.logger.info(f"  Comparing with: {repr(normalized_reaction)} (from {repr(reaction_emoji)})")
                    
                    if normalized_reaction == normalized_target:
                        # Check if chosen_order exists (0 or positive number means we reacted)
                        # None means we didn't react
                        if hasattr(reaction, 'chosen_order') and reaction.chosen_order is not None:
                            self.logger.info(f"  ✓ Match! chosen_order: {reaction.chosen_order}")
                            return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error checking reactions: {e}")
            return False
    
    async def download_media(self, message, chat_title):
        """Download media from a message (handles multiple files)"""
        # Check if message has media
        if not message.media:
            self.logger.debug(f"Message {message.id} has no media")
            return False
        
        # Check if message has grouped media (album)
        downloaded_any = False
        
        try:
            # Try to get all media in the message (for albums/groups)
            if hasattr(message, 'grouped_id') and message.grouped_id:
                self.logger.debug(f"Message is part of a media group (grouped_id: {message.grouped_id})")
            
            # Handle single media or first item in group
            downloaded = await self._download_single_media(message, message.media, chat_title)
            if downloaded:
                downloaded_any = True
            
            return downloaded_any
            
        except Exception as e:
            self.logger.error(f"Error downloading media: {e}", exc_info=True)
            return False
    
    async def _download_single_media(self, message, media, chat_title):
        """Download a single media item with semaphore control"""
        async with self.download_semaphore:
            self.active_downloads += 1
            try:
                return await self._do_download(message, media, chat_title)
            finally:
                self.active_downloads -= 1
    
    async def _do_download(self, message, media, chat_title):
        """Actual download logic"""
        try:
            # Get file information
            if isinstance(media, MessageMediaDocument):
                document = media.document
                
                # Get filename
                filename = None
                for attr in document.attributes:
                    if hasattr(attr, 'file_name'):
                        filename = attr.file_name
                        break
                
                if not filename:
                    # Generate filename from mime type and date
                    ext = document.mime_type.split('/')[-1]
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    filename = f"telegram_file_{timestamp}.{ext}"
                
                file_size = document.size
                
            elif isinstance(media, MessageMediaPhoto):
                # Photo
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"telegram_photo_{timestamp}.jpg"
                file_size = 0  # We don't have exact size for photos beforehand
                
            else:
                self.logger.debug(f"Unsupported media type: {type(media)}")
                return False
            
            # Sanitize filename
            filename = self._sanitize_filename(filename)
            
            # Check if we should download this file
            if not self._should_download(filename, file_size):
                return False
            
            # Check if file already exists and is complete
            download_file_path = self.download_path / filename
            if download_file_path.exists():
                existing_size = download_file_path.stat().st_size
                # For photos we don't know the size beforehand, so just skip if file exists
                if file_size == 0 or existing_size == file_size:
                    self.logger.info(f"File already exists and is complete: {filename}")
                    return True
                else:
                    self.logger.warning(f"File exists but incomplete: {filename} ({existing_size}/{file_size} bytes)")
                    self.logger.info(f"Deleting incomplete file and re-downloading...")
                    download_file_path.unlink()
            
            # Download the file
            queue_info = f"[{self.active_downloads}/{self.max_concurrent}]"
            self.logger.info(f"{queue_info} Downloading from '{chat_title}': {filename} ({file_size / (1024*1024):.2f} MB)")
            
            # Send notification about starting download
            await self.send_notification(f"⬇️ Downloading: {filename}\nFrom: {chat_title}")
            
            await message.download_media(file=str(download_file_path))
            
            # Verify download completed successfully
            if download_file_path.exists():
                actual_size = download_file_path.stat().st_size
                if file_size > 0 and actual_size != file_size:
                    self.logger.error(f"Download incomplete! Expected {file_size} bytes, got {actual_size} bytes")
                    await self.send_notification(f"❌ Download failed: {filename}\nIncomplete file")
                    return False
            
            self.logger.info(f"✓ Downloaded successfully: {filename}")
            
            # Send success notification
            await self.send_notification(f"✅ Downloaded: {filename}")
            
            # Import to Sonarr if enabled and it's a video file
            if self.sonarr_enabled and download_file_path.suffix.lower() in ['.mkv', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v']:
                await self.import_to_sonarr(download_file_path)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error downloading single media: {e}", exc_info=True)
            return False
    
    async def start(self):
        """Start the Telegram client and monitor for reactions"""
        await self.client.start(phone=self.phone)
        
        self.logger.info("Connected to Telegram!")
        
        # Get my user ID
        me = await self.client.get_me()
        self.my_id = me.id
        self.logger.info(f"Logged in as: {me.first_name} (ID: {me.id})")
        self.logger.info(f"Monitoring for {self.reaction_emoji} reactions")
        self.logger.info("Press Ctrl+C to stop.")
        
        @self.client.on(events.NewMessage)
        async def link_handler(event):
            """Handle messages with Telegram links for download"""
            if not self.link_download_enabled or not self.link_chat:
                return
            
            # Check if message is in the link chat
            try:
                chat = await event.get_chat()
                chat_title = getattr(chat, 'title', getattr(chat, 'username', str(event.chat_id)))
                
                # Check if this is the link chat
                is_link_chat = False
                if self.link_chat.lower() == 'me' and event.is_private and event.chat_id == self.my_id:
                    is_link_chat = True
                elif str(event.chat_id) == self.link_chat or f"@{getattr(chat, 'username', '')}" == self.link_chat:
                    is_link_chat = True
                
                if not is_link_chat:
                    return
                
                # Check if message contains a Telegram link
                if not event.message.text:
                    return
                
                import re
                # Match t.me links - both public and private channels
                # Public: https://t.me/channelname/123
                # Private: https://t.me/c/1234567890/123
                public_pattern = r'https?://t\.me/([^/c][^/]*)/(\d+)'
                private_pattern = r'https?://t\.me/c/(\d+)/(\d+)'
                
                public_matches = re.findall(public_pattern, event.message.text)
                private_matches = re.findall(private_pattern, event.message.text)
                
                if not public_matches and not private_matches:
                    return
                
                self.logger.info(f"📎 Link download request from {chat_title}")
                
                # Process public channel links
                for channel_username, msg_id in public_matches:
                    try:
                        # Get the channel and message
                        target_channel = await self.client.get_entity(channel_username)
                        target_message = await self.client.get_messages(target_channel, ids=int(msg_id))
                        
                        if not target_message:
                            self.logger.warning(f"Could not fetch message {msg_id} from {channel_username}")
                            continue
                        
                        target_chat_title = getattr(target_channel, 'title', channel_username)
                        await self._process_link_message(target_message, target_channel, target_chat_title, channel_username, msg_id)
                        
                    except Exception as e:
                        self.logger.error(f"Error processing link t.me/{channel_username}/{msg_id}: {e}")
                        await self.send_notification(f"❌ Failed to download from link:\nt.me/{channel_username}/{msg_id}")
                
                # Process private channel links
                for channel_id, msg_id in private_matches:
                    try:
                        # Private channels need -100 prefix
                        full_channel_id = -100 + int(channel_id) if not channel_id.startswith('-') else int(channel_id)
                        
                        target_channel = await self.client.get_entity(full_channel_id)
                        target_message = await self.client.get_messages(target_channel, ids=int(msg_id))
                        
                        if not target_message:
                            self.logger.warning(f"Could not fetch message {msg_id} from channel {channel_id}")
                            continue
                        
                        target_chat_title = getattr(target_channel, 'title', f"Channel {channel_id}")
                        await self._process_link_message(target_message, target_channel, target_chat_title, f"c/{channel_id}", msg_id)
                        
                    except Exception as e:
                        self.logger.error(f"Error processing private link t.me/c/{channel_id}/{msg_id}: {e}")
                        await self.send_notification(f"❌ Failed to download from link:\nt.me/c/{channel_id}/{msg_id}")
            
            except Exception as e:
                self.logger.error(f"Error in link handler: {e}", exc_info=True)
        
        @self.client.on(events.Raw(types=[UpdateMessageReactions]))
        async def reaction_handler(event):
            """Handle reaction updates"""
            try:
                self.logger.info(f"⚡ Reaction event received for message {event.msg_id}")
                
                # Log all reactions for debugging
                if event.reactions and event.reactions.results:
                    for r in event.reactions.results:
                        emoji = getattr(r.reaction, 'emoticon', 'Unknown')
                        chosen = getattr(r, 'chosen_order', None)
                        self.logger.info(f"  Reaction: {emoji}, chosen_order: {chosen}")
                
                # Check if the reaction includes our emoji
                if not self._has_my_reaction(event.reactions, self.reaction_emoji):
                    self.logger.info(f"❌ No matching {self.reaction_emoji} reaction on message {event.msg_id}")
                    return
                
                self.logger.info(f"✅ Found {self.reaction_emoji} reaction!")
                
                # Get the chat
                chat = await self.client.get_entity(event.peer)
                chat_title = getattr(chat, 'title', getattr(chat, 'username', str(event.peer)))
                
                # Check if we should monitor this chat
                if self.monitored_chats:
                    chat_id = getattr(chat, 'id', None)
                    chat_username = getattr(chat, 'username', None)
                    
                    # Check if this chat is in our monitored list
                    should_monitor = False
                    for monitored in self.monitored_chats:
                        if monitored.startswith('@') and chat_username:
                            if monitored[1:] == chat_username:
                                should_monitor = True
                                break
                        elif monitored.lstrip('-').isdigit():
                            if str(chat_id) == monitored or str(chat_id) == monitored.lstrip('-'):
                                should_monitor = True
                                break
                    
                    if not should_monitor:
                        self.logger.debug(f"Ignoring reaction in non-monitored chat: {chat_title}")
                        return
                
                self.logger.info(f"Found {self.reaction_emoji} reaction on message {event.msg_id} in '{chat_title}'")
                
                # Create message key for duplicate checking
                message_key = f"{event.peer.channel_id if hasattr(event.peer, 'channel_id') else event.peer}_{event.msg_id}"
                
                # Check if already downloaded
                if message_key in self.downloaded_messages:
                    self.logger.info(f"⏭️  Message {event.msg_id} already processed, skipping")
                    return
                
                # Get the actual message
                messages = await self.client.get_messages(chat, ids=event.msg_id)
                if not messages:
                    self.logger.warning(f"Could not fetch message {event.msg_id}")
                    return
                
                message = messages[0] if isinstance(messages, list) else messages
                
                # Check if this message is part of a media group
                if hasattr(message, 'grouped_id') and message.grouped_id:
                    self.logger.info(f"Message is part of a media group (grouped_id: {message.grouped_id})")
                    self.logger.info("Fetching all files in the group...")
                    
                    # Find all messages with the same grouped_id
                    # Search around the target message
                    min_id = max(1, event.msg_id - 50)
                    max_id = event.msg_id + 50
                    
                    grouped_messages = []
                    async for msg in self.client.iter_messages(chat, min_id=min_id, max_id=max_id, limit=None):
                        if hasattr(msg, 'grouped_id') and msg.grouped_id == message.grouped_id:
                            grouped_messages.append(msg)
                    
                    # Sort by message ID
                    grouped_messages.sort(key=lambda m: m.id)
                    
                    self.logger.info(f"Found {len(grouped_messages)} files in the group")
                    
                    # Start downloads as background tasks (non-blocking)
                    download_tasks = []
                    for msg in grouped_messages:
                        msg_key = f"{event.peer.channel_id if hasattr(event.peer, 'channel_id') else event.peer}_{msg.id}"
                        
                        # Skip if already downloaded
                        if msg_key in self.downloaded_messages:
                            self.logger.debug(f"Message {msg.id} already downloaded")
                            continue
                        
                        # Mark as in-progress to avoid duplicate downloads
                        self.downloaded_messages.add(msg_key)
                        
                        # Create download task (non-blocking)
                        task = asyncio.create_task(self.download_media(msg, chat_title))
                        download_tasks.append(task)
                    
                    self.logger.info(f"Started {len(download_tasks)} download tasks")
                    
                    # Don't await - let them run in background
                    # The semaphore will control how many run concurrently
                    
                else:
                    # Single file - start download as background task
                    self.downloaded_messages.add(message_key)
                    asyncio.create_task(self.download_media(message, chat_title))
                    self.logger.info(f"Started download task")
                
            except Exception as e:
                self.logger.error(f"Error in reaction handler: {e}", exc_info=True)
        
        # Keep the client running
        await self.client.run_until_disconnected()


def main():
    """Main entry point"""
    # Check if config file exists
    if not os.path.exists('config.ini'):
        print("Error: config.ini not found!")
        print("Please create config.ini with your Telegram credentials.")
        print("See config.ini for reference.")
        sys.exit(1)
    
    # Create downloader instance
    downloader = TelegramDownloader()
    
    try:
        # Run the downloader
        asyncio.run(downloader.start())
    except KeyboardInterrupt:
        print("\nDownloader stopped by user")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
