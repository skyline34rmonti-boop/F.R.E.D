"""Create private local configuration without printing credentials."""

from pathlib import Path
import secrets


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    destination = root / ".env"
    if destination.exists():
        print("Existing .env preserved. Edit it to change FRED's configuration.")
        return
    template = (root / ".env.example").read_text()
    template = template.replace("CHANGE_ME_TO_A_LONG_RANDOM_PASSWORD", secrets.token_urlsafe(24))
    # Exclusive creation prevents accidentally replacing an existing configuration.
    with destination.open("x", encoding="utf-8") as handle:
        destination.chmod(0o600)
        handle.write(template)
    print("Created private .env. Read FRED_OWNER_USERNAME and FRED_OWNER_PASSWORD there for login.")
    print("Open .env locally to read FRED_OWNER_PASSWORD for your first login.")
    print("AI mode: mock. Set FRED_AI_PROVIDER=openai and OPENAI_API_KEY for live AI.")


if __name__ == "__main__":
    main()
