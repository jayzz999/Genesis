"""Phase 5C — Organism Society

Allows organisms to broadcast messages, send direct messages, and form coalitions.
Messages are polled as perceptions and trigger new decisions.
"""
import logging
from typing import Optional

from . import store
from .types import OrganismMessage

logger = logging.getLogger("genesis.society")


async def broadcast(sender_id: str, content: dict, message_type: str = "inform") -> None:
    """Send a message to all living organisms."""
    msg = OrganismMessage(
        sender_id=sender_id,
        recipient_id=None,
        message_type=message_type,
        content=content,
    )
    
    # Send to all seeded organisms
    all_orgs = store.list_organisms()
    count = 0
    for org in all_orgs:
        if org.id == sender_id:
            continue
        # Duplicate the message for each recipient so they can independently mark it read
        msg_copy = msg.model_copy()
        msg_copy.id = f"msg_{msg.id}_{org.id}"  # make unique for this inbox
        store.save_message_for(org.id, msg_copy)
        count += 1
        
    logger.info(f"[society] {sender_id} broadcasted {message_type} to {count} organisms.")


async def send(sender_id: str, recipient_id: str, content: dict, message_type: str = "inform") -> bool:
    """Send a direct message to a specific organism."""
    org = store.load_organism(recipient_id)
    if not org:
        return False
        
    msg = OrganismMessage(
        sender_id=sender_id,
        recipient_id=recipient_id,
        message_type=message_type,
        content=content,
    )
    store.save_message_for(recipient_id, msg)
    logger.info(f"[society] {sender_id} sent {message_type} to {recipient_id}.")
    return True


def mark_read(organism_id: str, message_ids: list[str]) -> None:
    """Mark messages as read so they aren't processed again."""
    messages = store.load_messages(organism_id, unread_only=False)
    for msg in messages:
        if msg.id in message_ids and not msg.read:
            msg.read = True
            store.save_message_for(organism_id, msg)
