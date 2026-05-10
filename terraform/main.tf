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

variable "digitalocean_token" {
  description = "DigitalOcean API Token"
  type        = string
  sensitive   = true
}

# Create Droplet
resource "digitalocean_droplet" "trading_bot" {
  image             = "ubuntu-22-04-x64"
  name              = "5t-trading-bot"
  region            = "blr1"  # Bangalore
  size              = "s-1vcpu-512mb-10gb"  # $4/month
  backups           = false
  ipv6              = true
  monitoring        = true
  private_networking = false

  ssh_keys = [digitalocean_ssh_key.default.id]

  user_data = base64encode(templatefile("${path.module}/init.sh", {
    github_repo = "https://github.com/saurabh257257/5t.git"
  }))

  tags = ["trading-bot", "nodejs"]
}

# SSH Key
resource "digitalocean_ssh_key" "default" {
  name       = "5t-bot-key"
  public_key = tls_private_key.ssh.public_key_openssh
}

resource "tls_private_key" "ssh" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

# Output the Droplet IP
output "droplet_ip" {
  value       = digitalocean_droplet.trading_bot.ipv4_address
  description = "The public IP address of the trading bot Droplet"
}

output "droplet_id" {
  value = digitalocean_droplet.trading_bot.id
}
