# Telegram Media Downloader

Automatisk nedlasting av media-filer fra Telegram Saved Messages til en mappe som Sonarr kan overvåke.

## Installasjon

### 1. Installer Python og Telethon

```bash
# På Linux/Synology
pip3 install telethon

# Eller med --user hvis du ikke har admin-rettigheter
pip3 install --user telethon
```

### 2. Konfigurer scriptet

Rediger `config.ini` og fyll inn dine verdier:

```ini
[Telegram]
api_id = DIN_API_ID          # Fra https://my.telegram.org/apps
api_hash = DIN_API_HASH      # Fra https://my.telegram.org/apps
phone = +4712345678          # Ditt telefonnummer med landskode

[Download]
download_path = /mnt/nas/incoming    # Hvor filene skal lastes ned
file_extensions = .mp4,.mkv,.avi,.mov,.wmv,.flv,.webm,.m4v,.torrent,.nzb
max_file_size_mb = 0                 # 0 = ingen grense

[Logging]
log_file = telegram_downloader.log
log_level = INFO
```

### 3. Første gangs kjøring

```bash
python3 telegram_downloader.py
```

Første gang du kjører scriptet vil du få en kode på Telegram som du må taste inn.
Etter dette lagres økten og du trenger ikke logge inn igjen.

## Bruk

### Manuell kjøring

```bash
python3 telegram_downloader.py
```

Scriptet vil nå kjøre kontinuerlig og laste ned media så fort du lagrer noe i Saved Messages.

### Kjøre som systemd service (anbefalt)

Dette gjør at scriptet starter automatisk ved oppstart og restarter hvis det krasjer.

1. **Rediger service-filen:**

```bash
nano telegram_downloader.service
```

Endre:
- `YOUR_USERNAME` til ditt brukernavn
- `/path/to/telegram_downloader` til mappen der scriptet ligger

2. **Installer servicen:**

```bash
sudo cp telegram_downloader.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable telegram_downloader
sudo systemctl start telegram_downloader
```

3. **Sjekk status:**

```bash
sudo systemctl status telegram_downloader
```

4. **Se logger:**

```bash
sudo journalctl -u telegram_downloader -f
```

## Sonarr-oppsett

For at Sonarr skal plukke opp filene automatisk:

1. Gå til **Settings → Download Clients** i Sonarr
2. Legg til en ny "Download Client"
3. Velg "Manual" eller "Blackhole" type
4. Sett "Watch Folder" til `/mnt/nas/incoming`
5. Aktiver "Remove Completed Downloads"

Alternativt kan du sette opp en "Import List" eller bruke Sonarr's "Drone Factory" funksjonalitet.

## Hvordan det fungerer

1. Du lagrer eller videresender en video/torrent til "Saved Messages" i Telegram
2. Scriptet oppdager den nye meldingen umiddelbart
3. Filen lastes ned til `/mnt/nas/incoming`
4. Sonarr overvåker denne mappen og importerer filen automatisk
5. Sonarr identifiserer serien og flytter filen til riktig mappe

## Feilsøking

### "Permission denied" når du kjører scriptet
Sørg for at brukeren som kjører scriptet har skrivetilgang til download-mappen:

```bash
sudo chown -R $USER:$USER /mnt/nas/incoming
chmod 755 /mnt/nas/incoming
```

### Scriptet laster ned alt, ikke bare media
Sjekk `file_extensions` i `config.ini`. Sett den til kun de formatene du vil ha.

### Servicen starter ikke
Sjekk loggene:

```bash
sudo journalctl -u telegram_downloader -n 50
```

### Duplikate nedlastinger
Scriptet sjekker om filen allerede eksisterer før nedlasting. Hvis Sonarr flytter filen raskt,
kan den samme filen lastes ned igjen. Løsning: La filene ligge i incoming-mappen litt lenger,
eller sett opp Sonarr til å kopiere istedenfor å flytte.

## Kommandoer

### Stopp servicen
```bash
sudo systemctl stop telegram_downloader
```

### Start servicen
```bash
sudo systemctl start telegram_downloader
```

### Restart servicen
```bash
sudo systemctl restart telegram_downloader
```

### Deaktiver autostart
```bash
sudo systemctl disable telegram_downloader
```

## Sikkerhet

- `config.ini` inneholder sensitive data (API-nøkler). Hold denne filen privat.
- `telegram_session.session` filen gir full tilgang til Telegram-kontoen din. Beskytt den godt.
- Bruk aldri API-nøklene dine i offentlige repositories eller del dem med andre.

## Lisens

Dette scriptet er laget for personlig bruk. Bruk på egen risiko.
