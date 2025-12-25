#!/usr/bin/env python3
"""
Telegram Media Downloader
Monitors your Saved Messages and automatically downloads media files to a specified directory.
"""

import os
import sys
import asyncio
import logging
from pathlib import Path
from datetime import datetime
from configparser import ConfigParser
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto


class TelegramDownloader:
    def __init__(self, config_path='config.ini'):
        self.config = ConfigParser()
        self.config.read(config_path)
        
        # Telegram credentials
        self.api_id = self.config.get('Telegram', 'api_id')
        self.api_hash = self.config.get('Telegram', 'api_hash')
        self.phone = self.config.get('Telegram', 'phone')
        
        # Download settings
        self.download_path = Path(self.config.get('Download', 'download_path'))
        self.file_extensions = [ext.strip() for ext in 
                               self.config.get('Download', 'file_extensions').split(',') 
                               if ext.strip()]
        self.max_file_size = self.config.getint('Download', 'max_file_size_mb') * 1024 * 1024
        
        # Setup logging
        self._setup_logging()
        
        # Create download directory if it doesn't exist
        self.download_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize Telegram client
        self.client = TelegramClient('telegram_session', self.api_id, self.api_hash)
        
        self.logger.info(f"Telegram Downloader initialized")
        self.logger.info(f"Download path: {self.download_path}")
        self.logger.info(f"File extensions filter: {self.file_extensions if self.file_extensions else 'ALL'}")
    
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
    
    async def download_media(self, event):
        """Download media from a message"""
        message = event.message
        
        # Check if message has media
        if not message.media:
            return
        
        try:
            # Get file information
            if isinstance(message.media, MessageMediaDocument):
                document = message.media.document
                
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
                
            elif isinstance(message.media, MessageMediaPhoto):
                # Photo
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"telegram_photo_{timestamp}.jpg"
                file_size = 0  # We don't have exact size for photos beforehand
                
            else:
                self.logger.debug(f"Unsupported media type: {type(message.media)}")
                return
            
            # Sanitize filename
            filename = self._sanitize_filename(filename)
            
            # Check if we should download this file
            if not self._should_download(filename, file_size):
                return
            
            # Check if file already exists
            download_file_path = self.download_path / filename
            if download_file_path.exists():
                self.logger.info(f"File already exists: {filename}")
                return
            
            # Download the file
            self.logger.info(f"Downloading: {filename} ({file_size / (1024*1024):.2f} MB)")
            
            await message.download_media(file=str(download_file_path))
            
            self.logger.info(f"✓ Downloaded successfully: {filename}")
            
        except Exception as e:
            self.logger.error(f"Error downloading media: {e}", exc_info=True)
    
    async def start(self):
        """Start the Telegram client and monitor Saved Messages"""
        await self.client.start(phone=self.phone)
        
        self.logger.info("Connected to Telegram!")
        self.logger.info("Monitoring Saved Messages for new media...")
        
        # Get "me" (Saved Messages is a chat with yourself)
        me = await self.client.get_me()
        
        @self.client.on(events.NewMessage(chats=me.id))
        async def handler(event):
            """Handle new messages in Saved Messages"""
            await self.download_media(event)
        
        # Keep the client running
        self.logger.info("Downloader is running. Press Ctrl+C to stop.")
        await self.client.run_until_disconnected()
    
    async def download_existing(self, limit=100):
        """Download existing media from Saved Messages (optional)"""
        self.logger.info(f"Checking last {limit} messages in Saved Messages for media...")
        
        me = await self.client.get_me()
        async for message in self.client.iter_messages(me.id, limit=limit):
            if message.media:
                await self.download_media(type('Event', (), {'message': message})())
        
        self.logger.info("Finished checking existing messages")


def main():
    """Main entry point"""
    # Check if config file exists
    if not os.path.exists('config.ini'):
        print("Error: config.ini not found!")
        print("Please create config.ini with your Telegram credentials.")
        print("See config.ini.example for reference.")
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
        sys.exit(1)


if __name__ == '__main__':
    main()
