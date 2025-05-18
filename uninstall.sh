#!/bin/bash
set -euo pipefail
trap 'echo "❌ Error occurred at line $LINENO. Exiting."; exit 1' ERR

if [ "$EUID" -ne 0 ]; then
  echo "⚠️ Please run as root: sudo $0"
  exit 1
fi

echo "🚀 Reverting changes..."

# === VARIABLES ===
PROJECT_NAME="OnlineExam"
DEST_DIR="/var/www/$PROJECT_NAME"
PROJECT_DIR="$DEST_DIR/mysite"  # Set PROJECT_DIR to mysite
ENV_DIR="$DEST_DIR/examEnv"
GUNICORN_SERVICE="/etc/systemd/system/gunicorn.service"
NGINX_CONF="/etc/nginx/sites-available/$PROJECT_NAME"
NGINX_LINK="/etc/nginx/sites-enabled/$PROJECT_NAME"
MYSQL_DB_NAME="OnlineExam"  # Define the MySQL database name

# Prompt user for MySQL root password
echo "🔑 Please enter your MySQL root password:"
read -s MYSQL_ROOT_PASSWORD

# === REMOVE GUNICORN SERVICE ===
echo "🧹 Removing Gunicorn service..."
if [ -f "$GUNICORN_SERVICE" ]; then
    rm -f "$GUNICORN_SERVICE"
    systemctl daemon-reload
    systemctl reset-failed
    echo "✅ Gunicorn service removed."
else
    echo "❌ Gunicorn service not found."
fi

# === REMOVE NGINX CONFIG ===
echo "🧹 Removing Nginx config..."
if [ -L "$NGINX_LINK" ]; then
    rm -f "$NGINX_LINK"
    echo "✅ Nginx config removed."
else
    echo "❌ Nginx config not found."
fi

# === RESTORE DEFAULT NGINX CONFIG ===
echo "🔄 Restoring default Nginx config..."
# Check if sites-enabled directory exists before creating the symbolic link
if [ -d "/etc/nginx/sites-enabled" ]; then
    if [ ! -L "/etc/nginx/sites-enabled/default" ]; then
        ln -s /etc/nginx/sites-available/default /etc/nginx/sites-enabled/default
        echo "✅ Default Nginx config restored."
    else
        echo "❌ Default Nginx config already exists."
    fi
else
    echo "❌ Nginx sites-enabled directory not found. Skipping restore of default config."
fi

# === REMOVE PROJECT FILES ===
echo "🧹 Removing project files..."
if [ -d "$PROJECT_DIR" ]; then
    rm -rf "$PROJECT_DIR"
    echo "✅ Project files removed."
else
    echo "❌ Project files not found."
fi

# === REMOVE VIRTUAL ENVIRONMENT ===
echo "🧹 Removing virtual environment..."
if [ -d "$ENV_DIR" ]; then
    rm -rf "$ENV_DIR"
    echo "✅ Virtual environment removed."
else
    echo "❌ Virtual environment not found."
fi

# === REMOVE MYSQL DATABASE ===
echo "🧹 Removing MySQL database..."
if command -v mysql &> /dev/null; then
    mysql -u root -p"$MYSQL_ROOT_PASSWORD" -e "DROP DATABASE IF EXISTS $MYSQL_DB_NAME;"
    echo "✅ MySQL database removed."
else
    echo "❌ MySQL command not found. Skipping database removal."
fi

# === REMOVE PACKAGES ===
echo "🧹 Removing unnecessary packages..."
apt-get remove --purge -y python3-pip python3-dev python3-venv \
    libmysqlclient-dev build-essential libssl-dev libffi-dev \
    nginx mysql-server git curl ufw
apt-get autoremove -y
echo "✅ Unnecessary packages removed."

# === STOP SERVICES ===
echo "🔄 Stopping Gunicorn and Nginx services..."
# Check if Gunicorn service is running
if systemctl is-active --quiet gunicorn; then
    systemctl stop gunicorn
    echo "✅ Gunicorn service stopped."
else
    echo "❌ Gunicorn service not running or already removed."
fi

# Check if Nginx service is running
if systemctl is-active --quiet nginx; then
    systemctl stop nginx
    echo "✅ Nginx service stopped."
else
    echo "❌ Nginx service not running or already removed."
fi

# === RESTART NGINX ===
echo "🔄 Restarting Nginx..."
# Check if Nginx service exists
if systemctl list-units --type=service | grep -q 'nginx.service'; then
    systemctl restart nginx
    echo "✅ Nginx restarted."
else
    echo "❌ Nginx service not found. It may have been removed."
fi

echo "🎉 Project removal setup complete. All changes have been reverted."

