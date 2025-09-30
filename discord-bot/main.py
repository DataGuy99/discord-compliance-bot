"""
Discord S&P Compliance Bot
Main entry point for Discord bot connecting to FastAPI backend
"""

import os
import sys
import asyncio

import discord
from discord.ext import commands
from dotenv import load_dotenv

from utils.logger import logger
from utils.api_client import APIClient
from handlers import events
from commands import setup_compliance, setup_admin

# Load environment variables
load_dotenv()

# Configuration
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# Validate required configuration
if not DISCORD_BOT_TOKEN:
    logger.error("startup.config.missing", variable="DISCORD_BOT_TOKEN")
    sys.exit(1)


class ComplianceBot(commands.Bot):
    """
    Discord bot for S&P compliance queries.
    Uses slash commands to interact with FastAPI backend.
    """

    def __init__(self):
        # Configure bot intents
        intents = discord.Intents.default()
        intents.message_content = False  # Don't need message content for slash commands
        intents.guilds = True
        intents.guild_messages = False

        super().__init__(
            command_prefix="!",  # Not used (slash commands only), but required
            intents=intents,
            help_command=None,  # Disable default help (we'll use slash commands)
        )

        # Initialize API client
        self.api_client = APIClient(base_url=API_BASE_URL)

        logger.info(
            "bot.initialized",
            api_base_url=API_BASE_URL,
            environment=ENVIRONMENT,
        )

    async def setup_hook(self):
        """
        Setup hook called before bot starts.
        Load cogs and register event handlers.
        """
        logger.info("bot.setup.started")

        # Load compliance commands
        await setup_compliance(self, self.api_client)
        logger.info("bot.cog.loaded", cog="compliance")

        # Load admin commands
        await setup_admin(self, self.api_client)
        logger.info("bot.cog.loaded", cog="admin")

        # Register event handlers
        self.tree.on_error = events.on_app_command_error

        logger.info("bot.setup.completed")

    async def on_ready(self):
        """Called when bot successfully connects to Discord"""
        await events.on_ready(self)

        # Sync commands in development
        if ENVIRONMENT == "development":
            logger.info("bot.commands.syncing")
            try:
                synced = await self.tree.sync()
                logger.info("bot.commands.synced", count=len(synced))
            except Exception as e:
                logger.error("bot.commands.sync.failed", error=str(e))

    async def on_guild_join(self, guild: discord.Guild):
        """Called when bot joins a guild"""
        await events.on_guild_join(guild)

    async def on_guild_remove(self, guild: discord.Guild):
        """Called when bot leaves a guild"""
        await events.on_guild_remove(guild)

    async def close(self):
        """Cleanup when bot shuts down"""
        logger.info("bot.shutdown.started")

        # Close API client
        await self.api_client.close()
        logger.info("bot.api_client.closed")

        await super().close()
        logger.info("bot.shutdown.completed")


async def main():
    """
    Main entry point for Discord bot.
    """
    logger.info(
        "bot.starting",
        environment=ENVIRONMENT,
        api_url=API_BASE_URL,
    )

    # Create bot instance
    bot = ComplianceBot()

    # Check API health with retries before starting
    logger.info("bot.api.health_check")
    max_retries = 3
    retry_delay = 5

    for attempt in range(max_retries):
        health = await bot.api_client.health_check()

        if health.get("status") == "healthy":
            logger.info("bot.api.healthy")
            break

        if attempt < max_retries - 1:
            logger.warning(
                "bot.api.unhealthy.retrying",
                attempt=attempt + 1,
                max_retries=max_retries,
                status=health.get("status"),
                retry_in=retry_delay,
            )
            await asyncio.sleep(retry_delay)
        else:
            logger.error(
                "bot.api.unhealthy.failed",
                status=health.get("status"),
                error=health.get("error"),
            )
            logger.critical("bot.startup_aborted")
            sys.exit(1)

    # Start bot
    try:
        async with bot:
            await bot.start(DISCORD_BOT_TOKEN)
    except KeyboardInterrupt:
        logger.info("bot.interrupted")
    except Exception as e:
        logger.error("bot.error", error=str(e), error_type=type(e).__name__)
        raise
    finally:
        logger.info("bot.exiting")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("bot.stopped")
    except Exception as e:
        logger.error("bot.fatal_error", error=str(e))
        sys.exit(1)