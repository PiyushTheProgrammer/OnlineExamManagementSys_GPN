#!/bin/bash
set -euo pipefail
trap 'echo "❌ Error occurred at line $LINENO. Exiting."; exit 1' ERR

if [ "$EUID" -ne 0 ]; then
  echo "⚠️ Please run as root: sudo $0"
  exit 1
fi

echo "🚀 Starting Django project deployment..."

# === VARIABLES ===
PROJECT_NAME="OnlineExam"
DEST_DIR="/var/www/$PROJECT_NAME"
PROJECT_DIR="$DEST_DIR/mysite"
ENV_DIR="$DEST_DIR/examEnv"
GUNICORN_PORT=8000
MYSQL_ROOT_PASSWORD="Admin@12345"
MYSQL_DB_NAME="OnlineExam"
GUNICORN_SERVICE="/etc/systemd/system/gunicorn.service"
NGINX_CONF="/etc/nginx/sites-available/$PROJECT_NAME"
NGINX_LINK="/etc/nginx/sites-enabled/$PROJECT_NAME"

# === SYSTEM UPDATE & PACKAGES INSTALL ===
echo "📦 Updating and installing required packages..."
apt update && apt upgrade -y
apt-get install -y pkg-config libmysqlclient-dev

apt install -y python3-pip python3-dev python3-venv \
    build-essential libssl-dev libffi-dev \
    nginx mysql-server curl ufw

# === FIREWALL CONFIG ===
echo "🔐 Enabling firewall..."
ufw allow 'Nginx Full'
ufw status | grep -q inactive && ufw --force enable

# === MYSQL SETUP ===
echo "🔐 Configuring MySQL..."

configure_mysql() {
  set +e

  PLUGIN=$(sudo mysql -N -B -e "SELECT plugin FROM mysql.user WHERE user = 'root' AND host = 'localhost';" 2>/dev/null)

  if [[ "$PLUGIN" == "auth_socket" ]]; then
    echo "🔧 Switching MySQL root auth plugin to mysql_native_password..."
    sudo mysql <<EOF
ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY '$MYSQL_ROOT_PASSWORD';
FLUSH PRIVILEGES;
EOF
  fi

  echo "✅ Creating database..."
  mysql -u root -p"$MYSQL_ROOT_PASSWORD" -e "CREATE DATABASE IF NOT EXISTS $MYSQL_DB_NAME;"
  STATUS=$?

  set -e

  if [ $STATUS -eq 0 ]; then
    echo "✅ MySQL setup completed successfully!"
    return 0
  else
    echo "❌ MySQL setup failed!"
    return 1
  fi
}

configure_mysql

# === PROJECT COPY ===
echo "📂 Searching for Django project in Downloads..."
USER_HOME=$(eval echo "~$SUDO_USER")
FOUND_PROJECT=$(find "$USER_HOME/Downloads" -type f -path "*/mysite/manage.py" 2>/dev/null | head -n1)

if [ -z "$FOUND_PROJECT" ]; then
    echo "❌ No Django project with mysite/manage.py found in Downloads."
    exit 1
fi

SOURCE_PROJECT_DIR=$(dirname "$FOUND_PROJECT")
SOURCE_PARENT_DIR=$(dirname "$SOURCE_PROJECT_DIR")

echo "📁 Copying project to /var/www..."
mkdir -p "$DEST_DIR"
rm -rf "$PROJECT_DIR"
cp -r "$SOURCE_PROJECT_DIR" "$PROJECT_DIR"
chown -R "$SUDO_USER:$SUDO_USER" "$DEST_DIR"

echo "✅ Project copied."

# === VENV SETUP ===
echo "🐍 Setting up virtual environment..."
python3 -m venv "$ENV_DIR"
source "$ENV_DIR/bin/activate"

pip install --upgrade pip
pip install gunicorn

# === DEPENDENCIES INSTALL ===
REQ_FILE="$PROJECT_DIR/requirements.txt"
if [ -f "$REQ_FILE" ]; then
    echo "📦 Installing dependencies..."
    pip install -r "$REQ_FILE"
else
    echo "⚠️ requirements.txt not found!"
fi

# === STATIC/MEDIA FOLDERS ===
mkdir -p "$PROJECT_DIR/staticfiles" "$PROJECT_DIR/media"

# === GUNICORN SERVICE ===
echo "⚙️ Creating Gunicorn service..."
cat > "$GUNICORN_SERVICE" << EOF
[Unit]
Description=gunicorn daemon for $PROJECT_NAME
After=network.target

[Service]
User=root
Group=www-data
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$ENV_DIR/bin"
ExecStart=$ENV_DIR/bin/gunicorn --workers 17 --bind 127.0.0.1:$GUNICORN_PORT mysite.wsgi:application

[Install]
WantedBy=multi-user.target
EOF

# === NGINX CONFIG ===
echo "🌐 Creating Nginx config..."
cat > "$NGINX_CONF" << EOF
server {
    listen 80;
    server_name _ testwisegpn;

    location = /favicon.ico { access_log off; log_not_found off; }

    location /static/ {
        alias $PROJECT_DIR/staticfiles/;
    }

    location /media/ {
        alias $PROJECT_DIR/media/;
    }

    location / {
        include proxy_params;
        proxy_pass http://127.0.0.1:$GUNICORN_PORT;
    }
}
EOF

ln -sf "$NGINX_CONF" "$NGINX_LINK"

if [ -e /etc/nginx/sites-enabled/default ]; then
    echo "🧹 Removing default Nginx site..."
    rm /etc/nginx/sites-enabled/default
fi

# === DJANGO SETUP ===
echo "🔧 Running Django commands..."
python "$PROJECT_DIR/manage.py" makemigrations
python "$PROJECT_DIR/manage.py" migrate
python "$PROJECT_DIR/manage.py" collectstatic --noinput

# === SUPERUSER CREATION ===
echo "👤 Creating Django superuser..."
read -p "Enter superuser email: " DJANGO_SUPERUSER_EMAIL
read -p "Enter superuser username: " DJANGO_SUPERUSER_USERNAME
read -s -p "Enter superuser password: " DJANGO_SUPERUSER_PASSWORD
echo

python "$PROJECT_DIR/manage.py" shell <<EOF
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='$DJANGO_SUPERUSER_USERNAME').exists():
    User.objects.create_superuser(
        username='$DJANGO_SUPERUSER_USERNAME',
        email='$DJANGO_SUPERUSER_EMAIL',
        password='$DJANGO_SUPERUSER_PASSWORD'
    )
    print("✅ Superuser created.")
else:
    print("⚠️ Superuser already exists.")
EOF

# === PERMISSIONS & SERVICES ===
chown -R www-data:www-data "$DEST_DIR"
systemctl daemon-reexec
systemctl daemon-reload
systemctl enable gunicorn
systemctl restart gunicorn

echo "✅ Testing Nginx config..."
nginx -t && systemctl restart nginx

echo "🎉 Deployment Complete: Your Django site is live at http://testwisegpn"

