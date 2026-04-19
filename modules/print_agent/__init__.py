"""
Print-Agent Module

REST-API fuer on-prem Druck-Agents (poll, done, error, heartbeat).
Authentifizierung per Bearer-Token (pro Agent), CSRF ausgenommen.
"""

from flask import Blueprint

print_agent_bp = Blueprint(
    'print_agent', __name__, url_prefix='/api/agent'
)

from . import routes  # noqa: E402,F401

__all__ = ['print_agent_bp']
