variable "digitalocean_token" {
  description = "DigitalOcean API Token"
  type        = string
  sensitive   = true
  default     = ""
}

variable "droplet_name" {
  description = "Name of the Droplet"
  type        = string
  default     = "5t-trading-bot"
}

variable "droplet_region" {
  description = "DigitalOcean region"
  type        = string
  default     = "blr1" # Bangalore
}

variable "droplet_size" {
  description = "Droplet size (e.g., s-1vcpu-512mb-10gb = $4/month)"
  type        = string
  default     = "s-1vcpu-512mb-10gb"
}

variable "droplet_image" {
  description = "Operating System image"
  type        = string
  default     = "ubuntu-22-04-x64"
}
