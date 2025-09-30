"""Commands package"""

from commands.compliance import ComplianceCommands, setup as setup_compliance
from commands.admin import AdminCommands, setup as setup_admin

__all__ = ["ComplianceCommands", "AdminCommands", "setup_compliance", "setup_admin"]