"""Adapters for the ``live`` laptop profile: the local open-weight model behind the copy port.

Every other port under ``live`` binds the same offline adapter ``local`` does, including
``image``: a local open-weight text model cannot draw, so the deterministic image stub stays.
This package holds only what differs.
"""
