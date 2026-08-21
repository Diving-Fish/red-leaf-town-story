#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")" && pwd)"
cd "$repo_root/frontend"
npm run build
sudo mkdir -p /var/www/html/red-leaf-town
sudo cp -r dist/. /var/www/html/red-leaf-town/
