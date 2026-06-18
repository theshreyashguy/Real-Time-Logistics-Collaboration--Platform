"""referential-integrity policy + supporting indexes

Adds explicit ON DELETE behaviour to every foreign key (instead of the
auto-generated bare FKs), introduces the two previously-missing FKs
(messages.reply_to_id, memberships.last_read_message_id), and the two
secondary indexes for the message_shipments and ai_summaries lookups.

Policy:
  memberships.user_id / channel_id     -> CASCADE  (pure join row)
  memberships.last_read_message_id     -> SET NULL (read cursor must not dangle)
  messages.channel_id                  -> CASCADE  (messages die with channel)
  messages.sender_id                   -> RESTRICT (preserve authorship)
  messages.reply_to_id (self FK)       -> SET NULL (unlink deleted parent)
  message_shipments.message_id         -> CASCADE  (link dies with message)
  message_shipments.shipment_id        -> RESTRICT (keep referenced shipment)
  ai_summaries.channel_id              -> CASCADE
  channels.created_by                  -> RESTRICT (don't orphan a channel)

Postgres auto-names FKs `<table>_<column>_fkey`; we drop those and recreate
with the desired ondelete. This migration targets Postgres (the app's
DATABASE_URL); the SQLite test suite builds the schema from the models via
create_all and so already reflects these constraints.

Revision ID: 0002_fk_policy
Revises: 41b307bfe8f2
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002_fk_policy"
down_revision: Union[str, None] = "41b307bfe8f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- memberships -------------------------------------------------------
    op.drop_constraint("memberships_user_id_fkey", "memberships", type_="foreignkey")
    op.drop_constraint("memberships_channel_id_fkey", "memberships", type_="foreignkey")
    op.create_foreign_key(
        "memberships_user_id_fkey", "memberships", "users",
        ["user_id"], ["id"], ondelete="CASCADE",
    )
    op.create_foreign_key(
        "memberships_channel_id_fkey", "memberships", "channels",
        ["channel_id"], ["id"], ondelete="CASCADE",
    )
    op.create_foreign_key(
        "memberships_last_read_message_id_fkey", "memberships", "messages",
        ["last_read_message_id"], ["id"], ondelete="SET NULL",
    )

    # --- messages ----------------------------------------------------------
    op.drop_constraint("messages_channel_id_fkey", "messages", type_="foreignkey")
    op.drop_constraint("messages_sender_id_fkey", "messages", type_="foreignkey")
    op.create_foreign_key(
        "messages_channel_id_fkey", "messages", "channels",
        ["channel_id"], ["id"], ondelete="CASCADE",
    )
    op.create_foreign_key(
        "messages_sender_id_fkey", "messages", "users",
        ["sender_id"], ["id"], ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "messages_reply_to_id_fkey", "messages", "messages",
        ["reply_to_id"], ["id"], ondelete="SET NULL",
    )

    # --- message_shipments -------------------------------------------------
    op.drop_constraint(
        "message_shipments_message_id_fkey", "message_shipments", type_="foreignkey"
    )
    op.drop_constraint(
        "message_shipments_shipment_id_fkey", "message_shipments", type_="foreignkey"
    )
    op.create_foreign_key(
        "message_shipments_message_id_fkey", "message_shipments", "messages",
        ["message_id"], ["id"], ondelete="CASCADE",
    )
    op.create_foreign_key(
        "message_shipments_shipment_id_fkey", "message_shipments", "shipments",
        ["shipment_id"], ["id"], ondelete="RESTRICT",
    )
    op.create_index(
        "ix_message_shipments_message_id", "message_shipments", ["message_id"]
    )

    # --- ai_summaries ------------------------------------------------------
    op.drop_constraint("ai_summaries_channel_id_fkey", "ai_summaries", type_="foreignkey")
    op.create_foreign_key(
        "ai_summaries_channel_id_fkey", "ai_summaries", "channels",
        ["channel_id"], ["id"], ondelete="CASCADE",
    )
    op.create_index(
        "ix_ai_summaries_channel_window", "ai_summaries", ["channel_id", "window"]
    )

    # --- channels ----------------------------------------------------------
    op.drop_constraint("channels_created_by_fkey", "channels", type_="foreignkey")
    op.create_foreign_key(
        "channels_created_by_fkey", "channels", "users",
        ["created_by"], ["id"], ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("channels_created_by_fkey", "channels", type_="foreignkey")
    op.create_foreign_key(
        "channels_created_by_fkey", "channels", "users", ["created_by"], ["id"]
    )

    op.drop_index("ix_ai_summaries_channel_window", table_name="ai_summaries")
    op.drop_constraint("ai_summaries_channel_id_fkey", "ai_summaries", type_="foreignkey")
    op.create_foreign_key(
        "ai_summaries_channel_id_fkey", "ai_summaries", "channels",
        ["channel_id"], ["id"],
    )

    op.drop_index("ix_message_shipments_message_id", table_name="message_shipments")
    op.drop_constraint(
        "message_shipments_shipment_id_fkey", "message_shipments", type_="foreignkey"
    )
    op.drop_constraint(
        "message_shipments_message_id_fkey", "message_shipments", type_="foreignkey"
    )
    op.create_foreign_key(
        "message_shipments_message_id_fkey", "message_shipments", "messages",
        ["message_id"], ["id"],
    )
    op.create_foreign_key(
        "message_shipments_shipment_id_fkey", "message_shipments", "shipments",
        ["shipment_id"], ["id"],
    )

    op.drop_constraint("messages_reply_to_id_fkey", "messages", type_="foreignkey")
    op.drop_constraint("messages_sender_id_fkey", "messages", type_="foreignkey")
    op.drop_constraint("messages_channel_id_fkey", "messages", type_="foreignkey")
    op.create_foreign_key(
        "messages_channel_id_fkey", "messages", "channels", ["channel_id"], ["id"]
    )
    op.create_foreign_key(
        "messages_sender_id_fkey", "messages", "users", ["sender_id"], ["id"]
    )

    op.drop_constraint(
        "memberships_last_read_message_id_fkey", "memberships", type_="foreignkey"
    )
    op.drop_constraint("memberships_channel_id_fkey", "memberships", type_="foreignkey")
    op.drop_constraint("memberships_user_id_fkey", "memberships", type_="foreignkey")
    op.create_foreign_key(
        "memberships_user_id_fkey", "memberships", "users", ["user_id"], ["id"]
    )
    op.create_foreign_key(
        "memberships_channel_id_fkey", "memberships", "channels", ["channel_id"], ["id"]
    )
