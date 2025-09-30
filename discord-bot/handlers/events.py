"""
Event handlers for Discord bot lifecycle
"""

import discord
from discord.ext import commands

from utils.logger import logger


async def on_ready(bot: commands.Bot):
    """
    Called when bot successfully connects to Discord.

    Args:
        bot: Discord bot instance
    """
    logger.info(
        "bot.ready",
        bot_user=str(bot.user),
        guild_count=len(bot.guilds),
        user_count=sum(guild.member_count for guild in bot.guilds),
    )

    # Set bot presence
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="for /compliance commands",
        ),
        status=discord.Status.online,
    )

    logger.info("bot.presence.set")


async def on_guild_join(guild: discord.Guild):
    """
    Called when bot joins a new guild.

    Args:
        guild: Guild that was joined
    """
    logger.info(
        "bot.guild.joined",
        guild_id=str(guild.id),
        guild_name=guild.name,
        member_count=guild.member_count,
    )


async def on_guild_remove(guild: discord.Guild):
    """
    Called when bot is removed from a guild.

    Args:
        guild: Guild that was left
    """
    logger.info(
        "bot.guild.removed",
        guild_id=str(guild.id),
        guild_name=guild.name,
    )


async def on_command_completion(interaction: discord.Interaction):
    """
    Called when a command successfully completes.

    Args:
        interaction: Discord interaction
    """
    logger.info(
        "command.completed",
        command=interaction.command.name if interaction.command else "unknown",
        user_id=str(interaction.user.id),
        guild_id=str(interaction.guild.id) if interaction.guild else None,
    )


async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    """
    Global error handler for application commands.

    Args:
        interaction: Discord interaction
        error: Error that occurred
    """
    from handlers.error import handle_command_error
    await handle_command_error(interaction, error)