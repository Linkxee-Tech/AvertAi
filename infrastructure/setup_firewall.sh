#!/bin/bash
# Phase 2.1: UFW Firewall Configuration
# Sets up the DigitalOcean Droplet firewall to only allow ports 80, 443, and 22.

echo "Configuring UFW Firewall..."

# Default policies
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Allow SSH (Port 22)
sudo ufw allow 22/tcp

# Allow HTTP (Port 80)
sudo ufw allow 80/tcp

# Allow HTTPS (Port 443)
sudo ufw allow 443/tcp

# Enable firewall (force to avoid prompts in scripts)
sudo ufw --force enable

echo "UFW Firewall configured successfully. Only ports 22, 80, and 443 are open."
sudo ufw status verbose
