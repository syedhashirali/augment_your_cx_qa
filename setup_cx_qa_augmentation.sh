#!/bin/bash
# QA Analysis App - Easy Setup Script for AWS EC2 Ubuntu and Debian systems
# Usage: curl -fsSL https://raw.githubusercontent.com/YOUR_USERNAME/augment_your_cx_qa/main/setup_cx_qa_augmentation.sh | bash

set -e  # Exit on error

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   QA Analysis App - Easy Setup${NC}"
echo -e "${BLUE}========================================${NC}\n"

# Function to print status
print_step() {
    echo -e "\n${GREEN}▶${NC} $1"
}

print_info() {
    echo -e "${YELLOW}ℹ${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

# Check if running on Ubuntu
if [ ! -f /etc/os-release ] || ! grep -q "Ubuntu" /etc/os-release; then
    print_error "This script is designed for Ubuntu. Exiting."
    exit 1
fi

print_success "Running on Ubuntu"

# Update system
print_step "Updating system packages..."
sudo apt update && sudo apt upgrade -y
print_success "System updated"

# Install Ollama
print_step "Installing Ollama..."
if command -v ollama &> /dev/null; then
    print_info "Ollama already installed"
else
    curl -fsSL https://ollama.com/install.sh | sh
    print_success "Ollama installed"
fi

# Start Ollama service
print_step "Starting Ollama service..."
sudo systemctl start ollama 2>/dev/null || true
print_success "Ollama service started"

# Pull Mistral model
print_step "Pulling Mistral 7B model (this may take 5-10 minutes)..."
ollama pull mistral
print_success "Mistral model downloaded"

# Install Python and dependencies
print_step "Installing Python and system dependencies..."
sudo apt install -y python3-pip python3-venv nginx
print_success "Dependencies installed"

# Create app directory
print_step "Setting up application directory..."
APP_DIR="$HOME/qa-app"
mkdir -p "$APP_DIR"
cd "$APP_DIR"
print_success "Created directory: $APP_DIR"

# Get GitHub repo URL
echo ""
print_info "GitHub Repository Setup"
echo ""

# Check if running in a pipe (curl | bash) - stdin won't work
if [ -t 0 ]; then
    # Interactive mode - can read from user
    read -p "Enter your GitHub repository URL (e.g., https://github.com/user/repo.git): " REPO_URL
else
    # Piped mode - check if URL provided as argument
    REPO_URL="$1"
fi

if [ -z "$REPO_URL" ]; then
    print_error "Repository URL is required."
    print_error "Either run the script interactively: ./setup_qa_app.sh"
    print_error "Or provide URL as argument: curl ... | bash -s https://github.com/user/repo.git"
    exit 1
fi

echo "Using repository: $REPO_URL"

# Create virtual environment
print_step "Creating Python virtual environment..."
python3 -m venv venv
source venv/bin/activate
print_success "Virtual environment created"

# Install Python packages
print_step "Installing Python packages from requirements.txt..."
pwd
ls
if [ -f "requirements.txt" ]; then
    pip install --upgrade pip
    pip install -r requirements.txt
    print_success "Python packages installed"
else
    print_error "requirements.txt not found!"
    exit 1
fi
# Setup secrets
print_step "Setting up email credentials..."
mkdir -p .streamlit

echo ""
print_info "Email Configuration"
echo ""

# For piped mode, these need to be provided as environment variables
if [ -t 0 ]; then
    # Interactive mode
    read -p "Enter sender email address: " SENDER_EMAIL
    read -sp "Enter sender email app password: " SENDER_PASSWORD
    echo ""
else
    # Piped mode - check environment variables
    if [ -z "$SENDER_EMAIL" ] || [ -z "$SENDER_PASSWORD" ]; then
        print_error "When running via curl | bash, you must set environment variables:"
        print_error "SENDER_EMAIL='your@email.com' SENDER_PASSWORD='password' curl ... | bash -s REPO_URL"
        exit 1
    fi
fi

echo ""

# Create secrets file
cat > .streamlit/secrets.toml << EOF
[email]
sender_email = "$SENDER_EMAIL"
sender_password = "$SENDER_PASSWORD"
EOF

chmod 600 .streamlit/secrets.toml
print_success "Secrets configured"

# Configure firewall
print_step "Configuring firewall..."
sudo ufw allow 22/tcp      # SSH
sudo ufw allow 80/tcp      # HTTP
sudo ufw allow 443/tcp     # HTTPS
sudo ufw allow 8501/tcp    # Streamlit
sudo ufw --force enable
print_success "Firewall configured"

# Create systemd service
print_step "Creating systemd service..."
sudo tee /etc/systemd/system/qa-app.service > /dev/null << EOF
[Unit]
Description=QA Analysis Streamlit App
After=network.target ollama.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/venv/bin"
ExecStart=$APP_DIR/venv/bin/streamlit run app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable qa-app
sudo systemctl start qa-app
print_success "Service created and started"

# Wait for service to start
print_step "Waiting for app to start..."
sleep 5

# Check service status
if sudo systemctl is-active --quiet qa-app; then
    print_success "App is running!"
else
    print_error "App failed to start. Checking logs..."
    sudo journalctl -u qa-app -n 20
    exit 1
fi

# Configure Nginx
print_step "Configuring Nginx reverse proxy..."
sudo tee /etc/nginx/sites-available/qa-app > /dev/null << 'EOF'
server {
    listen 80;
    server_name _;
    client_max_body_size 100M;

    location / {
        proxy_pass http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/qa-app /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl restart nginx
print_success "Nginx configured"

# Get public IP
PUBLIC_IP=$(curl -s http://checkip.amazonaws.com)

# Create update script
print_step "Creating update script..."
cat > "$APP_DIR/update_app.sh" << 'UPDATEEOF'
#!/bin/bash
cd ~/qa-app
git pull
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart qa-app
echo "✓ App updated and restarted"
UPDATEEOF

chmod +x "$APP_DIR/update_app.sh"
print_success "Update script created"

# Print completion message
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}   ✓ Setup Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}Your QA Analysis app is now running!${NC}"
echo ""
echo -e "${YELLOW}Access your app at:${NC}"
echo -e "  🌐 http://$PUBLIC_IP"
echo ""
echo -e "${YELLOW}Useful commands:${NC}"
echo -e "  View logs:       ${BLUE}sudo journalctl -u qa-app -f${NC}"
echo -e "  Restart app:     ${BLUE}sudo systemctl restart qa-app${NC}"
echo -e "  Stop app:        ${BLUE}sudo systemctl stop qa-app${NC}"
echo -e "  Check status:    ${BLUE}sudo systemctl status qa-app${NC}"
echo -e "  Update app:      ${BLUE}~/qa-app/update_app.sh${NC}"
echo ""
echo -e "${YELLOW}Important files:${NC}"
echo -e "  App directory:   ${BLUE}$APP_DIR${NC}"
echo -e "  Secrets:         ${BLUE}$APP_DIR/.streamlit/secrets.toml${NC}"
echo -e "  Service file:    ${BLUE}/etc/systemd/system/qa-app.service${NC}"
echo -e "  Nginx config:    ${BLUE}/etc/nginx/sites-available/qa-app${NC}"
echo ""
echo -e "${GREEN}Setup completed successfully! 🎉${NC}"
echo ""
