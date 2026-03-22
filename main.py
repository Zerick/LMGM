"""Entry point for the GURPS AI Game Master bot."""
import logging
import os

import yaml
from dotenv import load_dotenv

from bot import GurpsGMClient


def load_config(path: str = "config.yaml") -> dict:
    """Load configuration from a YAML file.

    Args:
        path: Path to the config file.

    Returns:
        Parsed configuration dictionary.
    """
    with open(path, "r") as f:
        return yaml.safe_load(f)


def setup_logging() -> None:
    """Configure root logger with timestamped console output at INFO level."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main() -> None:
    """Load environment and config, then start the bot."""
    load_dotenv()
    setup_logging()
    config = load_config()

    logging.info("Bot starting...")
    logging.info(f"Main channel: #{config['bot']['main_channel']}")

    token_env_key: str = config["bot"]["discord_token_env"]
    token: str | None = os.getenv(token_env_key)
    if not token:
        raise ValueError(
            f"Discord token not found. Set {token_env_key} in your .env file."
        )

    client = GurpsGMClient(config)
    client.run(token)


if __name__ == "__main__":
    main()
