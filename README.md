# The Self-Destructing Media Downloader

A Python script that automatically downloads media (photos and videos) from private messages and replies to your "Saved Messages" in Telegram. This script simplifies the process of archiving and retrieving media content from Telegram conversations.

> [!WARNING]
> **Project Status Notice**
>
> This project is no longer actively maintained and will likely be **archived in the near future** due to the author's current workload.
>
> The repository will remain available for reference, but **new updates, fixes, or support are not guaranteed**.
>
> If you want to continue using or improving this project, please consider checking the available forks!
>
> Some community forks may include updated dependencies, bug fixes, or compatibility improvements.
>
> **Thanks to everyone who has used, starred, and contributed to this project ❤️**

## Features

- Automatically download photos and videos from private messages
- Organize downloaded media by user
- Admin commands for managing the bot and downloaded files
- Create ZIP archives of downloaded media
- Ping functionality to check bot status
- File management commands (list, download, delete)

## Prerequisites

Before running the script, you need to:

1. Create a Telegram application and obtain the `API_ID` and `API_HASH` from [my.telegram.org](https://my.telegram.org/).
2. Get your Telegram user ID (Admin ID) using the [@userinfobot](https://t.me/userinfobot) on Telegram.

## Installation

1. Clone this repository:

```bash
git clone https://github.com/ZeroParadoxHome/Self-Destructing-Media-Downloader.git
cd Self-Destructing-Media-Downloader
```

2. Install the required packages:

```bash
pip install -r requirements.txt
```

## Configuration

The service reads configuration from environment variables first, then from `settings.json`.

Recommended environment variables:

```bash
TSDMD_API_ID=123456
TSDMD_API_HASH=your_api_hash_here
TSDMD_ADMIN_ID=123456789
TSDMD_SESSION_NAME=tsdmd
TSDMD_MEDIA_DIR=/opt/tsdmd/Media
TSDMD_LOG_LEVEL=INFO
```

You can copy `.env.example` as a starting point.

## Usage

To run the script, use the following command:

```bash
python TSDMD.py
```

For an interactive first-time login on a local terminal, you can temporarily allow prompts:

```bash
TSDMD_ALLOW_PROMPTS=true python TSDMD.py
```

After Telegram login succeeds, keep the generated `.session` file with the project on the server. A headless `systemd` service cannot enter Telegram phone/code prompts by itself.

## Ubuntu Server Deployment

The repository includes `tsdmd.service`, a `systemd` unit that keeps the downloader running and restarts it if it crashes.

1. Create a service user:

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin tsdmd
```

2. Copy the project to `/opt/tsdmd`:

```bash
sudo mkdir -p /opt/tsdmd
sudo cp -r . /opt/tsdmd/
sudo chown -R tsdmd:tsdmd /opt/tsdmd
```

3. Create a virtual environment and install dependencies:

```bash
sudo -u tsdmd python3 -m venv /opt/tsdmd/venv
sudo -u tsdmd /opt/tsdmd/venv/bin/pip install -r /opt/tsdmd/requirements.txt
```

4. Create `/etc/tsdmd.env`:

```bash
sudo cp /opt/tsdmd/.env.example /etc/tsdmd.env
sudo nano /etc/tsdmd.env
sudo chmod 600 /etc/tsdmd.env
```

5. Run once interactively as the service user to create the Telegram session:

```bash
sudo -u tsdmd -H bash -lc 'cd /opt/tsdmd && set -a && source /etc/tsdmd.env && set +a && TSDMD_ALLOW_PROMPTS=true /opt/tsdmd/venv/bin/python TSDMD.py'
```

Stop it with `Ctrl+C` after it logs in and starts successfully.

6. Install and start the service:

```bash
sudo cp /opt/tsdmd/tsdmd.service /etc/systemd/system/tsdmd.service
sudo systemctl daemon-reload
sudo systemctl enable --now tsdmd
```

7. Check status and logs:

```bash
sudo systemctl status tsdmd
sudo journalctl -u tsdmd -f
```

Once the bot is running, you can use the following commands:

- `/help` - Display the help menu with available commands
- `/ping` - Check if the bot is alive and measure ping time
- `/status` - Get the number of downloaded files (Photos/Videos) in the media folder
- `/files` - List all files in the script folder
- `/check` - Perform a check for new files in the media folder
- `/download [file_path]` - Download a specific file from the script folder
- `/delete [file_path]` - Delete a specific file from the script folder
- `/all` - Download all available media files from the media folder
- `/zip` - Create and send a zip file containing files from the project folder

## How it works

1. The bot automatically downloads media files (photos and videos) sent to it via private messages.
2. Downloaded files are organized in folders named after the sender's username and user ID.
3. The bot can be controlled using various admin commands to manage downloaded files and check the bot's status.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is open source and available under the [MIT License](LICENSE).

## Disclaimer

This tool is for educational purposes only, So Please respect copyright laws and the privacy of others when using this script.

## Support

Please open an issue on the GitHub repository if you encounter any issues or have questions.
