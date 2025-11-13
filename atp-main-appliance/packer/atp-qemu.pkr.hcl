variable "version" { type = string, default = "dev" }

source "qemu" "atp" {
  iso_url = ""
}

build {
  sources = ["source.qemu.atp"]
  provisioner "shell" { script = "provision/00-base-deps.sh" }
  provisioner "shell" { script = "provision/05-python-env.sh" }
  provisioner "shell" { script = "provision/15-copy-code.sh" }
  provisioner "shell" { script = "provision/30-post-verify.sh" }
}
