# Repository instructions

These instructions apply throughout this repository.

- Never read a file known or reasonably suspected to contain secrets. Examples include populated `.env` files, private keys, credential stores, and Ansible Vault files. If the contents are uncertain, ask for a sanitized example.
- Scope searches, diffs, and other commands that display file contents to known-safe paths. Use filenames and Git status to identify unfamiliar changes before inspecting them.
- Never stage or commit secrets, including passwords, access tokens, API keys, or private keys. Stage reviewed files by name. Use placeholders in examples and references to external credentials in configuration.
- If a suspected secret is already staged, stop before committing and alert the user using only its path.
