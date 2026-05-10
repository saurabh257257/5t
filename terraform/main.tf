terraform {
  required_providers {
    digitalocean = {
      source  = "digitalocean/digitalocean"
      version = "~> 2.0"
    }
  }
}

provider "digitalocean" {
  token = var.digitalocean_token
}

# Create Droplet
resource "digitalocean_droplet" "trading_bot" {
  image              = "ubuntu-22-04-x64"
  name               = "5t-trading-bot"
  region             = "blr1"  # Bangalore
  size               = "s-1vcpu-512mb-10gb"  # $4/month
  backups            = false
  ipv6               = true
  monitoring         = true
  private_networking = false

  # User data script runs on first boot
  user_data = file("${path.module}/init.sh")

  tags = ["trading-bot", "nodejs", "5paisa"]
}

# Output the Droplet IP
output "droplet_ip" {
  value       = digitalocean_droplet.trading_bot.ipv4_address
  description = "The public IP address of the trading bot Droplet"
}

output "droplet_id" {
  value       = digitalocean_droplet.trading_bot.id
  description = "The ID of the trading bot Droplet"
}

output "droplet_status" {
  value       = digitalocean_droplet.trading_bot.status
  description = "The status of the Droplet"
}
