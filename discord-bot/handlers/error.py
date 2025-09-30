"""
Error handlers for Discord bot
"""

import discord
from discord import app_commands
from discord.ext import commands
import httpx

from utils.logger import logger


async def handle_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """
    Global error handler for Discord slash commands.

    Args:
        interaction: Discord interaction
        error: Error that occurred
    """
    logger.error(
        "command.error",
        command=interaction.command.name if interaction.command else "unknown",
        user_id=str(interaction.user.id),
        error=str(error),
        error_type=type(error).__name__,
    )

    # Check if already responded
    if interaction.response.is_done():
        send_method = interaction.followup.send
    else:
        send_method = interaction.response.send_message

    # Handle specific error types
    if isinstance(error, app_commands.CommandOnCooldown):
        await send_method(
            f"⏳ This command is on cooldown. Try again in {error.retry_after:.1f} seconds.",
            ephemeral=True,
        )

    elif isinstance(error, app_commands.MissingPermissions):
        await send_method(
            "🚫 You don't have permission to use this command.",
            ephemeral=True,
        )

    elif isinstance(error, app_commands.BotMissingPermissions):
        await send_method(
            "🚫 I don't have the necessary permissions to execute this command.",
            ephemeral=True,
        )

    elif isinstance(error, app_commands.CommandNotFound):
        await send_method(
            "❓ Command not found. Use `/help` to see available commands.",
            ephemeral=True,
        )

    elif isinstance(error, app_commands.CheckFailure):
        await send_method(
            "🚫 You don't meet the requirements to use this command.",
            ephemeral=True,
        )

    else:
        # Generic error message
        await send_method(
            "❌ An unexpected error occurred. Please try again later.",
            ephemeral=True,
        )


async def handle_api_error(interaction: discord.Interaction, error: Exception):
    """
    Handle API-specific errors with user-friendly messages.

    Args:
        interaction: Discord interaction
        error: HTTP or API error
    """
    logger.error(
        "api.error",
        user_id=str(interaction.user.id),
        error=str(error),
        error_type=type(error).__name__,
    )

    # Check if already responded
    if interaction.response.is_done():
        send_method = interaction.followup.send
    else:
        send_method = interaction.response.send_message

    if isinstance(error, httpx.HTTPStatusError):
        status_code = error.response.status_code

        if status_code == 400:
            await send_method(
                "❌ Invalid request. Please check your input and try again.",
                ephemeral=True,
            )
        elif status_code == 403:
            await send_method(
                "🚫 You don't have permission to perform this action.",
                ephemeral=True,
            )
        elif status_code == 404:
            await send_method(
                "❓ Resource not found. Please check your input.",
                ephemeral=True,
            )
        elif status_code == 409:
            await send_method(
                "⚠️ This action has already been completed.",
                ephemeral=True,
            )
        elif status_code == 429:
            # Rate limit
            try:
                data = error.response.json()
                retry_after = data.get("retry_after", 60)
                await send_method(
                    f"⏳ Rate limit exceeded. Please try again in {retry_after} seconds.",
                    ephemeral=True,
                )
            except:
                await send_method(
                    "⏳ Rate limit exceeded. Please try again later.",
                    ephemeral=True,
                )
        elif status_code == 503:
            await send_method(
                "🔧 The compliance service is temporarily unavailable. Please try again in a few moments.",
                ephemeral=True,
            )
        else:
            await send_method(
                f"❌ API error (status {status_code}). Please try again later.",
                ephemeral=True,
            )

    elif isinstance(error, httpx.TimeoutException):
        await send_method(
            "⏱️ Request timed out. The query may be taking longer than expected. Please try again.",
            ephemeral=True,
        )

    elif isinstance(error, httpx.ConnectError):
        await send_method(
            "🔌 Unable to connect to the compliance service. Please try again later.",
            ephemeral=True,
        )

    else:
        await send_method(
            "❌ An unexpected error occurred while communicating with the API.",
            ephemeral=True,
        )