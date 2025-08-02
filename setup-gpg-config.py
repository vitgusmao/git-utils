#!/usr/bin/env python3
import os
from pathlib import Path


class ConfigCommand:
    def prompt(self, label: str, optional=False):
        while True:
            val = input(f"{label}: ").strip()
            if val or optional:
                return val

    def expand_home(self, path):
        return str(Path(path).expanduser().resolve())

    def run(self):
        print("🔧 Git GPG config setup for a new project")

        folder = self.expand_home(
            self.prompt("Enter the full path to the parent folder where Git repos live")
        )
        key_id = self.prompt("Enter your GPG signing key ID")
        name = self.prompt("Enter your Git user name", optional=True)
        email = self.prompt("Enter your Git email", optional=True)

        config_name = os.path.basename(folder.rstrip("/"))
        home = str(Path.home())
        custom_config_path = os.path.join(home, f".gitconfig-{config_name}")
        main_gitconfig_path = os.path.join(home, ".gitconfig")

        self.build_custom_config(custom_config_path, key_id, name, email)

        self.add_custom_config_into_main(
            main_gitconfig_path, custom_config_path, folder
        )

    def build_custom_config(
        self,
        custom_config_path: str,
        key_id: str,
        name: str | None = None,
        email: str | None = None,
    ):
        config_lines = ["[user]", f"\tsigningkey = {key_id}"]
        if name:
            config_lines.append(f"\tname = {name}")
        if email:
            config_lines.append(f"\temail = {email}")
        config_lines.append("[commit]")
        config_lines.append("\tgpgsign = true")
        config_content = "\n".join(config_lines) + "\n"

        with open(custom_config_path, "w") as f:
            f.write(config_content)
        print(f"✅ Wrote custom Git config to {custom_config_path}")

    def add_custom_config_into_main(
        self, main_gitconfig_path: str, custom_config_path: str, folder: str
    ):
        include_block = (
            f'[includeIf "gitdir:{folder}/"]\n\tpath = {custom_config_path}\n'
        )
        if os.path.exists(main_gitconfig_path):
            with open(main_gitconfig_path, "r") as f:
                existing = f.read()
        else:
            existing = ""

        if include_block not in existing:
            with open(main_gitconfig_path, "a") as f:
                f.write("\n" + include_block)
            print(f"✅ Appended include block to {main_gitconfig_path}")
        else:
            print("ℹ️  Include block already exists in .gitconfig")


if __name__ == "__main__":
    command = ConfigCommand()
    command.run()
