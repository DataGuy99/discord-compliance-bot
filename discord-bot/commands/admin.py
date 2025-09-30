"""
Admin commands for Discord bot
Restricted commands for bot administrators
"""

import os
import discord
from discord import app_commands
from discord.ext import commands

from utils.logger import logger
from utils.api_client import APIClient
from handlers.error import handle_api_error

# Admin Discord IDs from environment
ADMIN_IDS = [int(uid) for uid in os.getenv("ADMIN_DISCORD_IDS", "").split(",") if uid.strip()]
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")


def is_admin():
    """Check if user is an admin"""
    def predicate(interaction: discord.Interaction) -> bool:
        return interaction.user.id in ADMIN_IDS
    return app_commands.check(predicate)


class AdminCommands(commands.Cog):
    """
    Cog for admin-only slash commands.
    """

    def __init__(self, bot: commands.Bot, api_client: APIClient):
        self.bot = bot
        self.api = api_client

    @app_commands.command(name="stats", description="View system statistics (Admin only)")
    @is_admin()
    async def admin_stats(self, interaction: discord.Interaction):
        """
        Display system-wide statistics.

        Args:
            interaction: Discord interaction
        """
        logger.info("command.admin.stats", admin_id=str(interaction.user.id))

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            stats = await self.api.get_admin_stats(ADMIN_TOKEN)

            embed = discord.Embed(
                title="📊 System Statistics",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow(),
            )

            # User statistics
            embed.add_field(
                name="👥 Users",
                value=f"Total: {stats['total_users']}\n"
                      f"Active (7d): {stats['active_users_7d']}",
                inline=True,
            )

            # Query statistics
            embed.add_field(
                name="💬 Queries",
                value=f"Total: {stats['total_queries']}\n"
                      f"Today: {stats['queries_today']}",
                inline=True,
            )

            # Quality metrics
            embed.add_field(
                name="📈 Quality",
                value=f"Avg Confidence: {stats['avg_confidence_score']:.2f}\n"
                      f"Avg Rating: {stats['avg_overall_rating']:.1f}/5",
                inline=True,
            )

            # System health
            embed.add_field(
                name="🔧 System",
                value=f"Flagged Queries: {stats['flagged_queries']}\n"
                      f"Documents: {stats['compliance_documents']}\n"
                      f"Uptime: {stats['system_uptime_hours']:.1f}h",
                inline=False,
            )

            # Feedback
            embed.add_field(
                name="⭐ Feedback",
                value=f"Total: {stats['total_feedback']}",
                inline=True,
            )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            await handle_api_error(interaction, e)

    @app_commands.command(name="flagged", description="View flagged queries (Admin only)")
    @is_admin()
    @app_commands.describe(limit="Number of queries to show (1-20)")
    async def admin_flagged(self, interaction: discord.Interaction, limit: int = 10):
        """
        Display flagged queries for review.

        Args:
            interaction: Discord interaction
            limit: Number of queries to show
        """
        logger.info("command.admin.flagged", admin_id=str(interaction.user.id), limit=limit)

        if limit < 1 or limit > 20:
            await interaction.response.send_message(
                "❌ Limit must be between 1 and 20.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            flagged = await self.api.get_flagged_queries(ADMIN_TOKEN, limit)

            if not flagged:
                await interaction.followup.send(
                    "✅ No flagged queries at this time!",
                    ephemeral=True,
                )
                return

            embed = discord.Embed(
                title="⚠️ Flagged Queries for Review",
                description=f"Showing {len(flagged)} flagged queries",
                color=discord.Color.orange(),
                timestamp=discord.utils.utcnow(),
            )

            for i, query in enumerate(flagged[:5], 1):  # Show max 5 in embed
                query_text = query["query_text"][:80] + "..." if len(query["query_text"]) > 80 else query["query_text"]

                flags = []
                if query["confidence_score"] < 0.5:
                    flags.append("Low Confidence")
                if query["is_escalated"]:
                    flags.append("Escalated")
                if query["risk_level"] in ["high", "critical"]:
                    flags.append(f"{query['risk_level'].upper()} Risk")

                embed.add_field(
                    name=f"{i}. {query_text}",
                    value=f"User: {query['discord_username']}\n"
                          f"Confidence: {query['confidence_score']:.2f}\n"
                          f"Flags: {', '.join(flags)}\n"
                          f"Query ID: `{query['query_id']}`",
                    inline=False,
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            await handle_api_error(interaction, e)

    @app_commands.command(name="sync", description="Sync slash commands (Admin only)")
    @is_admin()
    async def sync_commands(self, interaction: discord.Interaction):
        """
        Manually sync slash commands to Discord.

        Args:
            interaction: Discord interaction
        """
        logger.info("command.admin.sync", admin_id=str(interaction.user.id))

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            # Sync commands globally
            synced = await self.bot.tree.sync()

            logger.info("commands.synced", count=len(synced))

            await interaction.followup.send(
                f"✅ Successfully synced {len(synced)} commands globally.",
                ephemeral=True,
            )

        except Exception as e:
            logger.error("commands.sync.failed", error=str(e))
            await interaction.followup.send(
                f"❌ Failed to sync commands: {str(e)}",
                ephemeral=True,
            )

    @app_commands.command(name="botstatus", description="View bot status (Admin only)")
    @is_admin()
    async def bot_status(self, interaction: discord.Interaction):
        """
        Display bot connection and performance info.

        Args:
            interaction: Discord interaction
        """
        logger.info("command.admin.botstatus", admin_id=str(interaction.user.id))

        # Calculate bot statistics
        total_guilds = len(self.bot.guilds)
        total_users = sum(guild.member_count for guild in self.bot.guilds)
        latency_ms = round(self.bot.latency * 1000, 2)

        # Check API health
        api_health = await self.api.health_check()
        api_status = api_health.get("status", "unknown")

        embed = discord.Embed(
            title="🤖 Bot Status",
            color=discord.Color.green() if api_status == "healthy" else discord.Color.red(),
            timestamp=discord.utils.utcnow(),
        )

        embed.add_field(
            name="Discord Connection",
            value=f"Latency: {latency_ms}ms\n"
                  f"Guilds: {total_guilds}\n"
                  f"Users: {total_users}",
            inline=True,
        )

        embed.add_field(
            name="API Backend",
            value=f"Status: {api_status}\n"
                  f"URL: {self.api.base_url}",
            inline=True,
        )

        embed.set_footer(text=f"Bot User: {self.bot.user}")

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot, api_client: APIClient):
    """Add admin commands to bot"""
    await bot.add_cog(AdminCommands(bot, api_client))