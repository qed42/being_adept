#!/bin/bash
# server-setup.sh - Initial server setup for Slack bot deployment

# Update system packages
sudo apt-get update
sudo apt-get upgrade -y

# Install required dependencies
sudo apt-get install -y python3 python3-venv python3-pip git

# Create application directory if it doesn't exist
APP_DIR="/home/$USER/being_adept"
mkdir -p $APP_DIR

# Navigate to application directory
cd $APP_DIR

# Set up Git repository if it doesn't exist
if [ ! -d ".git" ]; then
  echo "Initializing git repository..."
  git init
  git remote add origin git@github.com:qed42/being_adept.git  # Replace with your actual repository URL
fi

# Set up Python virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv venv
fi

# Create a more robust systemd service file for your bot
echo "Creating systemd service file..."
cat > being-adept-slack-bot.service << EOL
[Unit]
Description=Being Adept Slack Bot Service
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/python app.py
Restart=always
RestartSec=10

# Health check options
# Return status code 0 if the service is running correctly
ExecStartPost=/bin/bash -c 'sleep 5 && systemctl is-active --quiet being-adept-slack-bot'

# Environment file support (optional)
EnvironmentFile=-$APP_DIR/.env

# Security enhancements
ProtectSystem=full
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOL

# Move service file to systemd directory
sudo mv being-adept-slack-bot.service /etc/systemd/system/

# Reload systemd to recognize the new service
sudo systemctl daemon-reload

# Enable the service to start at boot
sudo systemctl enable being-adept-slack-bot

echo "Server setup completed!"
echo "Next steps:"
echo "1. Copy your bot code to $APP_DIR"
echo "2. Enable and start the service: sudo systemctl enable being-adept-slack-bot && sudo systemctl start being-adept-slack-bot"
echo "3. Set up GitHub Actions with the necessary secrets"
