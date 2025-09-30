"""
Compliance query commands for Discord bot
User-facing commands for asking compliance questions
"""

import discord
from discord import app_commands
from discord.ext import commands
import httpx

from utils.logger import logger
from utils.api_client import APIClient
from handlers.error import handle_api_error


class ComplianceCommands(commands.Cog):
    """
    Cog for compliance-related slash commands.
    """

    def __init__(self, bot: commands.Bot, api_client: APIClient):
        self.bot = bot
        self.api = api_client

        # Track user sessions for context
        self.user_sessions = {}

    @app_commands.command(name="ask", description="Ask a compliance question")
    @app_commands.describe(question="Your compliance question (minimum 10 characters)")
    async def ask_compliance(self, interaction: discord.Interaction, question: str):
        """
        Ask a compliance question and get AI-powered response.

        Args:
            interaction: Discord interaction
            question: User's compliance question
        """
        user_id = str(interaction.user.id)

        logger.info(
            "command.ask",
            user_id=user_id,
            question_length=len(question),
        )

        # Validate question length
        if len(question) < 10:
            await interaction.response.send_message(
                "❌ Your question is too short. Please provide at least 10 characters.",
                ephemeral=True,
            )
            return

        # Defer response (compliance query may take a few seconds)
        await interaction.response.defer(thinking=True)

        try:
            # Get or create session ID
            session_id = self.user_sessions.get(user_id)

            # Submit query to API
            result = await self.api.submit_query(
                query=question,
                user_id=user_id,
                session_id=session_id,
            )

            # Update session
            self.user_sessions[user_id] = result["query_id"]

            # Build response embed
            embed = discord.Embed(
                title="📋 Compliance Response",
                description=result["answer"],
                color=self._get_confidence_color(result["confidence"]),
                timestamp=discord.utils.utcnow(),
            )

            embed.add_field(
                name="Confidence",
                value=self._format_confidence(result["confidence"], result["confidence_score"]),
                inline=True,
            )

            embed.add_field(
                name="Risk Level",
                value=self._format_risk(result["risk"]),
                inline=True,
            )

            embed.add_field(
                name="Response Time",
                value=f"{result['response_time_ms']}ms",
                inline=True,
            )

            # Add sources if available
            if result.get("sources"):
                sources_text = "\n".join([
                    f"• {src['document_title']} (chunk {src['chunk_index']})"
                    for src in result["sources"][:3]  # Limit to 3 sources
                ])
                embed.add_field(
                    name="📚 Sources",
                    value=sources_text,
                    inline=False,
                )

            embed.set_footer(text=f"Query ID: {result['query_id']}")

            # Create feedback button view
            view = FeedbackView(result["query_id"], self.api)

            await interaction.followup.send(embed=embed, view=view)

        except Exception as e:
            await handle_api_error(interaction, e)

    @app_commands.command(name="history", description="View your recent compliance queries")
    @app_commands.describe(limit="Number of queries to show (1-20)")
    async def query_history(self, interaction: discord.Interaction, limit: int = 10):
        """
        View recent query history for the user.

        Args:
            interaction: Discord interaction
            limit: Number of queries to retrieve
        """
        user_id = str(interaction.user.id)

        logger.info("command.history", user_id=user_id, limit=limit)

        # Validate limit
        if limit < 1 or limit > 20:
            await interaction.response.send_message(
                "❌ Limit must be between 1 and 20.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            history = await self.api.get_query_history(user_id, limit)

            if not history:
                await interaction.followup.send(
                    "📭 You haven't asked any compliance questions yet. Use `/ask` to get started!",
                    ephemeral=True,
                )
                return

            # Build history embed
            embed = discord.Embed(
                title="📚 Your Query History",
                description=f"Showing your last {len(history)} queries",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow(),
            )

            for i, query in enumerate(history[:5], 1):  # Show max 5 in embed
                query_text = query["query_text"][:100] + "..." if len(query["query_text"]) > 100 else query["query_text"]

                embed.add_field(
                    name=f"{i}. {query_text}",
                    value=f"Confidence: {query['confidence']} | Risk: {query['risk']}\n"
                          f"{'✅ Feedback provided' if query['has_feedback'] else '⭐ Rate this'}",
                    inline=False,
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            await handle_api_error(interaction, e)

    def _get_confidence_color(self, confidence: str) -> discord.Color:
        """Get embed color based on confidence level"""
        if confidence == "high":
            return discord.Color.green()
        elif confidence == "medium":
            return discord.Color.orange()
        else:
            return discord.Color.red()

    def _format_confidence(self, level: str, score: float) -> str:
        """Format confidence with emoji"""
        emoji_map = {
            "high": "✅",
            "medium": "⚠️",
            "low": "❌",
        }
        return f"{emoji_map.get(level, '❓')} {level.upper()} ({score:.2f})"

    def _format_risk(self, risk: str) -> str:
        """Format risk level with emoji"""
        emoji_map = {
            "low": "🟢",
            "medium": "🟡",
            "high": "🔴",
            "critical": "🚨",
        }
        return f"{emoji_map.get(risk, '❓')} {risk.upper()}"


class FeedbackView(discord.ui.View):
    """
    Interactive feedback buttons for query responses.
    """

    def __init__(self, query_id: str, api_client: APIClient):
        super().__init__(timeout=300)  # 5 minute timeout
        self.query_id = query_id
        self.api = api_client

    @discord.ui.button(label="👍 Helpful", style=discord.ButtonStyle.success)
    async def helpful_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Rate response as helpful"""
        await self._submit_feedback(interaction, 5, 5, 5, "Marked as helpful")

    @discord.ui.button(label="👎 Not Helpful", style=discord.ButtonStyle.danger)
    async def not_helpful_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Rate response as not helpful"""
        await self._submit_feedback(interaction, 2, 2, 2, "Marked as not helpful")

    @discord.ui.button(label="⚠️ Escalate", style=discord.ButtonStyle.secondary)
    async def escalate_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Escalate for human review"""
        await self._submit_feedback(interaction, 3, 3, 3, "Escalated for review", escalated=True)

    async def _submit_feedback(
        self,
        interaction: discord.Interaction,
        overall: int,
        helpfulness: int,
        accuracy: int,
        message: str,
        escalated: bool = False,
    ):
        """Submit feedback to API"""
        await interaction.response.defer(ephemeral=True)

        try:
            await self.api.submit_feedback(
                query_id=self.query_id,
                overall_rating=overall,
                helpfulness_rating=helpfulness,
                accuracy_rating=accuracy,
                feedback_text=message,
                escalated=escalated,
            )

            await interaction.followup.send(
                f"✅ Thank you for your feedback! {message}",
                ephemeral=True,
            )

            # Disable buttons after feedback
            for item in self.children:
                item.disabled = True
            await interaction.message.edit(view=self)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 409:
                await interaction.followup.send(
                    "ℹ️ You've already provided feedback for this query.",
                    ephemeral=True,
                )
            else:
                await handle_api_error(interaction, e)

        except Exception as e:
            await handle_api_error(interaction, e)


async def setup(bot: commands.Bot, api_client: APIClient):
    """Add compliance commands to bot"""
    await bot.add_cog(ComplianceCommands(bot, api_client))