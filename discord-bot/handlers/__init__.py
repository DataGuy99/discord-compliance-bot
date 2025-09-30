"""Event and error handlers package"""

from handlers.error import handle_command_error, handle_api_error
from handlers.events import (
    on_ready,
    on_guild_join,
    on_guild_remove,
    on_command_completion,
    on_app_command_error,
)

__all__ = [
    "handle_command_error",
    "handle_api_error",
    "on_ready",
    "on_guild_join",
    "on_guild_remove",
    "on_command_completion",
    "on_app_command_error",
]