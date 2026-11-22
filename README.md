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

- Change the theme or plugins with `shell_ohmyzsh_theme` and `shell_ohmyzsh_plugins` (see `roles/shell/defaults/main.yml`), in `group_vars/all.yml` or `host_vars/<host>.yml`.
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

## Development tools

The `development` role (`install_development`, tag `development`) installs development packages from the Ubuntu archive, listed in `development_packages` (`roles/development/defaults/main.yml`). It currently installs `ansible-lint`, which also brings `yamllint`.

Lint this repository from its root before committing:

```bash
ansible-lint
```

The rules and profile are configured in `.ansible-lint`.

### Python (pyenv) and Node.js (nvm)

The `development` role also installs [pyenv](https://github.com/pyenv/pyenv) and [nvm](https://github.com/nvm-sh/nvm) as Git checkouts of pinned release tags, in `~/.pyenv` and `~/.nvm`. Each has its own switch and tag:

| Tool | Switch | Tag | Tool version | Language version |
| --- | --- | --- | --- | --- |
| pyenv | `development_python` | `python` | `development_pyenv_version` | `development_python_version` (`3.15`) |
| nvm | `development_node` | `node` | `development_nvm_version` | `development_node_version` (`26`) |

- The language version is a prefix. When no matching version is installed, the newest match is installed and made the default (`~/.pyenv/version` and nvm's `default` alias). Later patch releases are not installed automatically; run `pyenv install 3.15` or `nvm install 26` to pick them up.
- pyenv compiles Python from source, so the first run takes several minutes. The role installs the build dependencies from the pyenv wiki.
- To update pyenv or nvm themselves, bump the release tag variable and rerun with `--tags python` or `--tags node`.
- The shell integration lines are in the `~/.zshrc` template of the `shell` role, not added by the tools' own installers. They do nothing when a tool is absent. Rerun with `--tags shell` after changing them.

### GitHub CLI and Azure CLI

The `development` role installs these CLIs from their vendors' official APT repositories, so APT updates them with the rest of the system:

| Tool | Package | Switch | Tag | Repository |
| --- | --- | --- | --- | --- |
| `gh` | `gh` | `development_github_cli` | `gh` | [cli.github.com](https://github.com/cli/cli/blob/trunk/docs/install_linux.md), suite `stable` |
| `az` | `azure-cli` | `development_azure_cli` | `az` | [packages.microsoft.com](https://learn.microsoft.com/cli/azure/install-azure-cli-linux), suite for the running Ubuntu release |

Both use the `apt_repository` helper role (see [Third-party APT repositories](#third-party-apt-repositories)). Each keyring in `/etc/apt/keyrings` must contain every fingerprint listed in `development_*_gpg_fingerprints`, or the run stops. When a vendor rotates its keys, delete the keyring, update the fingerprint list from the vendor's install page, and rerun with the tool's tag.

Sign in once with `gh auth login` and `az login`; the role does not handle credentials.

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
| Ghostty | `applications_ghostty` | `ghostty` | Ubuntu archive (universe), updated by APT |

**Zed** is installed the same way as Zed's official install script: unpacked into `~/.local/zed.app`, with a `zed` command in `~/.local/bin` and a desktop entry in `~/.local/share/applications`. Ansible downloads it only when it is missing; after that Zed updates itself. An existing install made with the official script is adopted as is. The download is verified by HTTPS only, the same as the official script.

Zed settings are managed in `~/.config/zed/settings.json`. Rerun with `--tags zed-settings` (or `--tags zed-extensions`) to apply only these.

- Extensions are listed in `applications_zed_extensions` (extension IDs from [zed.dev/extensions](https://zed.dev/extensions)) and written to the `auto_install_extensions` setting. Zed installs any missing ones the next time it starts, and updates them itself.
- Other top-level settings are in `applications_zed_settings_managed`. By default this sets the Catppuccin Frappé theme for dark mode, One Light for light mode, and the Catppuccin Frappé icon theme (from the `catppuccin` and `catppuccin-icons` extensions).
- `settings.json` may contain comments, so the role does not rewrite it. It keeps these settings in one block between `// BEGIN` and `// END ubuntu-dev-env-setup: Zed settings` markers right after the opening `{`, and leaves the rest of the file alone. It never prints the file's values, which may include credentials.
- If a managed setting is also set elsewhere in the file, the run stops and names it without changing the file; delete it there, then rerun.
- Changing the theme in Zed's UI edits the managed block, and the next run changes it back. Change `applications_zed_settings_managed` instead.
- Removing an ID from the list does not uninstall the extension; uninstall it from Zed's Extensions page.
- "TypeScript Language Server" is the `tsgo` extension (TypeScript 7's native server). Which TypeScript servers Zed runs is controlled by the `language_servers` setting for TypeScript in Zed.

**Ghostty** is installed from the Ubuntu archive and, with `applications_ghostty_default: true`, made the default terminal:

- `~/.config/xdg-terminals.list` names Ghostty for `xdg-terminal-exec`, which GNOME uses for Ctrl+Alt+T, Nautilus's "Open in Terminal", and apps that run in a terminal. It overrides Ubuntu's default (Ptyxis) for your user only; if Ghostty is removed, Ptyxis is used again. The role owns this file and overwrites manual edits.
- Ghostty is registered and selected as the system-wide `x-terminal-emulator` alternative, used by older applications and Debian tools. Run `sudo update-alternatives --config x-terminal-emulator` to pick another.

Set `applications_ghostty_default: false` to install Ghostty without changing the default; the role then leaves both settings as they are.

**Ferdium** is installed from the official `.deb` on GitHub, pinned to `applications_ferdium_version` and verified against `applications_ferdium_sha256` in `roles/applications/defaults/main.yml`. The download goes to a temporary directory and is deleted after installation. It does not update itself, and Ferdium shows untrusted web content, so keep it current:

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

### Desktop apps

The `ai_tools` role also installs the official desktop apps from their vendors' APT repositories. Both are early releases on Linux.

| App | Package | Switch | Tag | Status |
| --- | --- | --- | --- | --- |
| Claude Desktop | `claude-desktop` | `ai_tools_claude_desktop` | `claude-desktop` | Beta, [install docs](https://code.claude.com/docs/en/desktop-linux) |
| ChatGPT (with Codex) | `chatgpt` | `ai_tools_chatgpt_desktop` | `chatgpt` | Preview, [install docs](https://learn.chatgpt.com/codex/linux/linux-app) |

- Neither app updates itself; APT updates them with the rest of the system.
- Both packages register their vendor's repository when installed. This role manages that repository entry itself, and both packages leave an existing entry alone, so no duplicate is created.
- Claude Desktop is installed with its recommended packages (QEMU, OVMF, and virtiofsd), and your user is added to the `kvm` group, so Cowork can run its virtual machine. Log out and back in afterwards. Set `ai_tools_claude_desktop_kvm_group: false` to skip the group.
- OpenAI does not publish a download URL for the ChatGPT repository key, so the role installs a copy extracted from the package, `roles/apt_repository/files/chatgpt-archive-keyring.asc`. It is checked against the pinned fingerprint like the other keys.

Log in to the command-line tools by running `claude` or `codex`, and to the desktop apps when you first open them. Credentials stay in `~/.claude` and `~/.codex` and are never managed by this repository. Copies that Zed downloads for its agent panel are separate and managed by Zed.

## Third-party APT repositories

`roles/apt_repository` is a helper role, not listed in `playbook.yml`. Other roles import it to add a signed vendor repository and install packages from it. It downloads or copies the keyring into `/etc/apt/keyrings`, stops unless the keyring contains every pinned fingerprint, writes `/etc/apt/sources.list.d/<name>.sources`, and installs the packages. Its variables are documented in `roles/apt_repository/defaults/main.yml`. A keyring that fails the check is left in place so later runs keep failing until you inspect and remove it.

## Inventory an existing machine

`scripts/inventory.py` lists what is installed and customised on the current machine, to help decide what to add to this setup. It only reads: it needs no sudo and changes nothing.

```bash
scripts/inventory.py
```

It writes a Markdown report to `inventory/<hostname>-<timestamp>.md` (ignored by Git, readable only by you) covering:

- Manually installed APT packages, with first-install date, whether they were added after the OS install, and the repository they came from
- APT sources (credentials in URIs are masked)
- Snap and Flatpak applications
- GNOME Shell extensions (system or user, enabled or not)
- VS Code and Zed extensions
- Commands in `~/.local/bin`
- Customised GNOME settings from `dconf dump` for selected paths, without window state, automatic bookkeeping, or keys that may hold secrets

The "In repo" column marks items whose name already appears in the roles, `group_vars`, `playbook.yml`, `setup.sh`, or `requirements.yml`. Review the report and add only what you want; do not install everything it lists.

## Update and troubleshoot

Pull reviewed changes with `git pull --ff-only`, review the package lists and profile, preview with check mode, then rerun the setup. The base role requests package presence and leaves routine system upgrades to Ubuntu.

The base role refreshes the APT index when it is more than an hour old. If APT still cannot locate a package, verify its name and enabled repositories. If another package manager holds the lock, wait for it to finish before retrying. For Ansible diagnostics, rerun with `./setup.sh -v`. To inspect playbook syntax after bootstrap, use `ansible-playbook playbook.yml --syntax-check`. `ansible.cfg` supplies the inventory, the Python interpreter, and YAML-formatted task results.

If a task fails with `Timed out waiting for become success or become password prompt`, Ansible is using `sudo-rs`, the default `sudo` on Ubuntu 26.04, whose prompt it cannot detect. `ansible.cfg` sets `become_exe = /usr/bin/sudo.ws` (classic sudo from the `sudo` package, which `setup.sh` installs if missing) to avoid this without changing the system default.

Run `./setup.sh` as your normal user. It refuses to run as root, because user-scoped roles must target your account.
