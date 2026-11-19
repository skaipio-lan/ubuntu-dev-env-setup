#!/usr/bin/env bash
set -euo pipefail
trap 'echo "Setup failed at line $LINENO (exit $?)." >&2' ERR
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

if (( EUID == 0 )); then
    echo 'Run ./setup.sh as your normal user, not root; it uses sudo where needed.' >&2
    exit 1
fi

# The playbook enforces the exact supported release (supported_ubuntu_versions).
source /etc/os-release
if [[ $ID != ubuntu ]]; then
    echo 'This setup targets Ubuntu.' >&2
    exit 1
fi

check_mode=false
for arg in "$@"; do
    # --check, -C, or a short-flag cluster such as -CD.
    if [[ $arg == --check || $arg =~ ^-[A-Za-z]*C[A-Za-z]*$ ]]; then
        check_mode=true
    fi
done

missing=()
# "sudo" provides /usr/bin/sudo.ws, which ansible.cfg uses for become.
for package in ansible-core python3-apt sudo; do
    if [[ $(dpkg-query -W -f='${db:Status-Status}' "$package" 2>/dev/null) != installed ]]; then
        missing+=("$package")
    fi
done
if (( ${#missing[@]} )); then
    if [[ $check_mode == true ]]; then
        echo "Check mode needs these prerequisites first: ${missing[*]}" >&2
        exit 1
    fi
    sudo apt-get update
    sudo apt-get install --no-install-recommends -y "${missing[@]}"
fi

# Let Galaxy handle version constraints and already-installed collections.
/usr/bin/ansible-galaxy collection install -r requirements.yml
exec /usr/bin/ansible-playbook playbook.yml --ask-become-pass "$@"
