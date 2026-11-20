# Ubuntu workstation setup

Phase 1 configures a local Ubuntu 26.04 LTS installation with four base packages: CA certificates, curl, Git, and unzip. The inventory names the Dell Pro Max 16 as the first workstation. GNOME, development toolchains, Docker, desktop applications, dotfiles, and discovery tooling are planned for later phases.

## First run

Start from an installed Ubuntu 26.04 system with Bash, sudo access, and working Ubuntu APT repositories including Universe. Clone this repository with Git (install Git first if needed), enter the checkout, and run as your usual login user:

```bash
./setup.sh
```

The script uses APT to install missing prerequisites (ansible-core, python3-apt, and sudo), processes requirements.yml with Ansible Galaxy, and runs the local playbook. The `community.general` collection is installed into `~/.ansible/collections`. Enter your sudo password at the become-password prompt. The play recap reports changes per host, and a failed run returns a nonzero exit status.

## Preview and repeat

```bash
./setup.sh --check --diff
./setup.sh --tags base
./setup.sh
```

To preview before your first apply, install the prerequisites with `sudo apt-get update && sudo apt-get install --no-install-recommends ansible-core python3-apt sudo`. Check mode reports missing prerequisites and exits before installing them. The APT module predicts package changes. An immediate repeat after a successful apply should report `changed=0`.

## Configure a profile

Edit `group_vars/all.yml` to set shared role switches. Each role has a flat switch named `install_<role>` (for example `install_base`). A switch that is missing or `false` skips its role. Because the switches are separate variables, a machine or a single run can override one without restating the others. Tags narrow the enabled roles for one run. To try an override without editing files:

```bash
./setup.sh -e install_base=false
```

The package list lives in `roles/base/defaults/main.yml`. To curate it for this laptop, create `host_vars/dell_pro_max_16.yml` with a complete replacement list:

```yaml
base_packages:
  - ca-certificates
  - curl
  - git
  - unzip
  - jq
```

Removing a package from this list leaves installed copies in place. Use Ubuntu archive package names. Keep credentials and private keys out of Git.

Supported Ubuntu releases are listed once in `supported_ubuntu_versions` in `group_vars/all.yml`; the playbook stops on any other release.

For another machine, use a separate inventory with its own host alias in the workstations group and run the checkout locally there. A local connection always refers to the machine executing Ansible. Keep hardware-specific variables under the matching host alias. Add future roles to playbook.yml with their own tag and an `install_<role>` switch, guarded with `when: install_<role> | default(false) | bool`. Put user settings in user-scoped tasks and elevate only tasks that need system privileges.

## Shell

The `shell` role (`install_shell`, tag `shell`) installs zsh, clones Oh My Zsh into `~/.oh-my-zsh`, writes `~/.zshrc` and `~/.zprofile`, and makes zsh your login shell. Log out and back in for the login-shell change to apply.

- Change the theme or plugins with `ohmyzsh_theme` and `ohmyzsh_plugins` (see `roles/shell/defaults/main.yml`), in `group_vars/all.yml` or `host_vars/<host>.yml`.
- `~/.zshrc` is managed by Ansible. Editing it directly is undone on the next run, and Ansible keeps a timestamped backup of the replaced version. Put machine-specific settings and secrets in `~/.zshrc.local`, which `~/.zshrc` sources and Git never sees.
- `~/.zprofile` loads `~/.profile`, so zsh keeps the PATH entries Ubuntu sets there, such as `~/.local/bin`.
- Oh My Zsh is cloned once and not updated by Ansible. It reminds you when updates are available; run `omz update` to apply them.
- Set `shell_set_default: false` to install everything without changing your login shell.

## Git

The `git` role (`install_git`, tag `git`) installs Git and manages global settings in `~/.gitconfig`.

- Shared settings live in `git_global_config` (`roles/git/defaults/main.yml`); it sets `init.defaultBranch` to `main`. Removing an entry stops managing it but does not unset it.
- Your name and email come from `user.yml` at the repository root, which Git ignores:

  ```bash
  cp user.example.yml user.yml   # then uncomment and edit the values
  ./setup.sh --tags git
  ```

  Without `user.yml`, the role leaves `user.name` and `user.email` unchanged and prints a reminder. `user.yml` is loaded as play variables, so it takes precedence over `group_vars` and `host_vars`. Never put passwords, tokens, or keys in it.

## Docker

The `docker` role (`install_docker`, tag `docker`) installs Docker Engine, Buildx, and the Compose plugin (`docker compose`) from Docker's official APT repository, enables the `docker` and `containerd` services, and adds you to the `docker` group.

- Docker's signing key is saved to `/etc/apt/keyrings/docker.asc` and checked against the fingerprint in `docker_gpg_fingerprint`. A mismatch stops the run. If Docker rotates its key, verify the new fingerprint against Docker's documentation before updating the variable.
- If Ubuntu's own Docker packages (such as `docker.io` or `docker-compose-v2`) are installed, the role stops and lists them instead of removing them. Remove them with `sudo apt remove ...`; images and volumes in `/var/lib/docker` are kept.
- Membership of the `docker` group is equivalent to root access. Set `docker_add_user_to_group: false` to use `sudo docker` instead. Group changes apply at your next login; run `newgrp docker` to use them in the current shell.
- Container logs are capped at 50 MB per container (5 rotated files of 10 MB) through `docker_daemon_config`, which is written to `/etc/docker/daemon.json`. Changing it restarts Docker, which stops running containers. Existing containers keep their old log settings until they are recreated (for example `docker compose up -d --force-recreate`).
- On the first check-mode run, the repository does not exist yet, so the package, service, and group tasks are skipped with a note.

After the first apply and a new login, verify with:

```bash
docker run --rm hello-world
docker compose version
```

## Applications

The `applications` role (`install_applications`, tag `applications`) installs desktop applications for your user. Each application has its own switch and tag.

| Application | Switch | Tag | Source |
| --- | --- | --- | --- |
| Zed | `applications_zed` | `zed` | Official stable tarball from zed.dev |
| Ferdium | `applications_ferdium` | `ferdium` | Official `.deb` from GitHub releases, pinned and checksum-verified |

**Zed** is installed the same way as Zed's official install script: unpacked into `~/.local/zed.app`, with a `zed` command in `~/.local/bin` and a desktop entry in `~/.local/share/applications`. Ansible downloads it only when it is missing; after that Zed updates itself. An existing install made with the official script is adopted as is. The download is verified by HTTPS only, the same as the official script.

**Ferdium** is installed from the official `.deb` on GitHub, pinned to `ferdium_version` and verified against `ferdium_sha256` in `roles/applications/defaults/main.yml`. The download goes to a temporary directory and is deleted after installation. It does not update itself, and Ferdium shows untrusted web content, so keep it current:

```bash
scripts/ferdium-latest-release.sh   # prints version and checksums as YAML
```

Review the release notes, paste the output into `roles/applications/defaults/main.yml`, and run `./setup.sh --tags ferdium`. A newer installed version is never downgraded. A checksum mismatch stops the run before anything is installed.

To add an application, create `roles/applications/tasks/<app>.yml`, import it from `roles/applications/tasks/main.yml` with its own `when` switch and tag, and add the switch to `roles/applications/defaults/main.yml`.

## AI tools

The `ai_tools` role (`install_ai_tools`, tag `ai_tools`) installs command-line AI coding tools for your user. Each tool has its own switch and tag.

| Tool | Switch | Tag | Command | Installer |
| --- | --- | --- | --- | --- |
| Claude Code | `ai_tools_claude` | `claude` | `claude` | `https://claude.ai/install.sh` |
| Codex | `ai_tools_codex` | `codex` | `codex` | `https://chatgpt.com/codex/install.sh` |

Each tool is installed with its official install script only when its command is missing from `~/.local/bin`; afterwards the tool updates itself. Both installers verify the SHA-256 checksum of the binary they download. The scripts themselves are fetched over HTTPS and deleted after use. They run with `~/.local/bin` on `PATH`, so they do not edit `~/.zshrc` or other startup files. The Codex installer runs with `NON_INTERACTIVE=1`, which skips its optional prompts.

Log in after installation by running `claude` or `codex`. Credentials stay in `~/.claude` and `~/.codex` and are never managed by this repository. Copies that Zed downloads for its agent panel are separate and managed by Zed.

## Update and troubleshoot

Pull reviewed changes with `git pull --ff-only`, review the package lists and profile, preview with check mode, then rerun the setup. The base role requests package presence and leaves routine system upgrades to Ubuntu.

The base role refreshes the APT index when it is more than an hour old. If APT still cannot locate a package, verify its name and enabled repositories. If another package manager holds the lock, wait for it to finish before retrying. For Ansible diagnostics, rerun with `./setup.sh -v`. To inspect playbook syntax after bootstrap, use `ansible-playbook playbook.yml --syntax-check`. `ansible.cfg` supplies the inventory, the Python interpreter, and YAML-formatted task results.

If a task fails with `Timed out waiting for become success or become password prompt`, Ansible is using `sudo-rs`, the default `sudo` on Ubuntu 26.04, whose prompt it cannot detect. `ansible.cfg` sets `become_exe = /usr/bin/sudo.ws` (classic sudo from the `sudo` package, which `setup.sh` installs if missing) to avoid this without changing the system default.

Run `./setup.sh` as your normal user. It refuses to run as root, because user-scoped roles must target your account.
