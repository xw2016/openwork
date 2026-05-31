"""Initial migration — create all tables

Revision ID: 001_initial
Revises:
Create Date: 2026-05-31 15:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Enum types ---
    user_type_enum = postgresql.ENUM("employer", "freelancer", "admin", name="user_type_enum", create_type=False)
    user_status_enum = postgresql.ENUM("active", "disabled", "pending", name="user_status_enum", create_type=False)
    task_type_enum = postgresql.ENUM("development", "design", "copywriting", "translation", "data_labeling", "consulting", "other", name="task_type_enum", create_type=False)
    contract_status_enum = postgresql.ENUM("draft", "pending", "in_progress", "review", "completed", "terminated", "disputed", name="contract_status_enum", create_type=False)
    transaction_type_enum = postgresql.ENUM("escrow", "payment", "refund", "bonus", name="transaction_type_enum", create_type=False)
    transaction_status_enum = postgresql.ENUM("pending", "completed", "failed", "cancelled", name="transaction_status_enum", create_type=False)
    blueprint_status_enum = postgresql.ENUM("draft", "locked", "archived", name="blueprint_status_enum", create_type=False)
    acceptance_status_enum = postgresql.ENUM("not_submitted", "pending", "approved", "rejected", name="acceptance_status_enum", create_type=False)
    acceptance_result_enum = postgresql.ENUM("approved", "rejected", name="acceptance_result_enum", create_type=False)
    node_type_enum = postgresql.ENUM("contract_created", "deliverable_submit", "acceptance_confirm", "transaction_complete", "dispute_initiated", name="node_type_enum", create_type=False)

    # Create all enum types first
    for e in [
        user_type_enum, user_status_enum, task_type_enum, contract_status_enum,
        transaction_type_enum, transaction_status_enum, blueprint_status_enum,
        acceptance_status_enum, acceptance_result_enum, node_type_enum,
    ]:
        e.create(op.get_bind(), checkfirst=True)

    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_type", user_type_enum, nullable=False, server_default="freelancer"),
        sa.Column("nickname", sa.String(50), nullable=False),
        sa.Column("avatar", sa.String(500), nullable=True),
        sa.Column("avatar_url", sa.String(500), nullable=True),
        sa.Column("phone", sa.String(20), unique=True, nullable=True, index=True),
        sa.Column("email", sa.String(100), unique=True, nullable=True, index=True),
        sa.Column("real_name", sa.String(255), nullable=True),
        sa.Column("id_card", sa.String(255), nullable=True),
        sa.Column("bio", sa.Text, nullable=True),
        sa.Column("domain_tags", postgresql.JSONB, nullable=True, server_default="[]"),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("credit_score", sa.Integer, nullable=False, server_default="600"),
        sa.Column("credit_detail", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("status", user_status_enum, nullable=False, server_default="active"),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_users_status", "users", ["status"])

    # --- contracts ---
    op.create_table(
        "contracts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("contract_no", sa.String(50), unique=True, nullable=False),
        sa.Column("employer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("freelancer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("task_type", task_type_enum, nullable=False),
        sa.Column("intent_blueprint", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("deliverables", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("base_amount", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("bonus_amount", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("bonus_condition", postgresql.JSONB, nullable=True),
        sa.Column("tracking_period", sa.Integer, nullable=True),
        sa.Column("commission_rate", sa.Numeric(5, 4), nullable=False, server_default="0.0500"),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("status", contract_status_enum, nullable=False, server_default="draft"),
        sa.Column("block_hash", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_contracts_contract_no", "contracts", ["contract_no"])
    op.create_index("ix_contracts_employer_id", "contracts", ["employer_id"])
    op.create_index("ix_contracts_freelancer_id", "contracts", ["freelancer_id"])
    op.create_index("ix_contracts_status", "contracts", ["status"])

    # --- transactions ---
    op.create_table(
        "transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("contract_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transaction_type", transaction_type_enum, nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("from_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("to_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("commission", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("status", transaction_status_enum, nullable=False, server_default="pending"),
        sa.Column("block_hash", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_transactions_contract_id", "transactions", ["contract_id"])
    op.create_index("ix_transactions_from_user_id", "transactions", ["from_user_id"])
    op.create_index("ix_transactions_to_user_id", "transactions", ["to_user_id"])
    op.create_index("ix_transactions_status", "transactions", ["status"])

    # --- intent_blueprints ---
    op.create_table(
        "intent_blueprints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("task_type", sa.String(50), nullable=False),
        sa.Column("content", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("status", blueprint_status_enum, nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_intent_blueprints_user_id", "intent_blueprints", ["user_id"])
    op.create_index("ix_intent_blueprints_status", "intent_blueprints", ["status"])

    # --- deliverables ---
    op.create_table(
        "deliverables",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("contract_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deliverable_index", sa.Integer, nullable=False, server_default="1"),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("required_format", sa.String(100), nullable=True),
        sa.Column("acceptance_criteria", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("file_url", sa.String(500), nullable=True),
        sa.Column("file_hash", sa.String(128), nullable=True),
        sa.Column("submit_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("submit_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acceptance_result", postgresql.JSONB, nullable=True),
        sa.Column("acceptance_status", acceptance_status_enum, nullable=False, server_default="not_submitted"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_deliverables_contract_id", "deliverables", ["contract_id"])
    op.create_index("ix_deliverables_acceptance_status", "deliverables", ["acceptance_status"])

    # --- acceptance_records ---
    op.create_table(
        "acceptance_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("contract_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("submit_version", sa.Integer, nullable=False),
        sa.Column("acceptance_report", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("result", acceptance_result_enum, nullable=False),
        sa.Column("settlement_triggered", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("block_hash", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_acceptance_records_contract_id", "acceptance_records", ["contract_id"])

    # --- blockchain_records ---
    op.create_table(
        "blockchain_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("contract_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("node_type", node_type_enum, nullable=False),
        sa.Column("content_hash", sa.String(128), nullable=False),
        sa.Column("block_hash", sa.String(128), nullable=False),
        sa.Column("block_height", sa.BigInteger, nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_blockchain_records_contract_id", "blockchain_records", ["contract_id"])
    op.create_index("ix_blockchain_records_node_type", "blockchain_records", ["node_type"])
    op.create_index("ix_blockchain_records_block_hash", "blockchain_records", ["block_hash"])


def downgrade() -> None:
    op.drop_table("blockchain_records")
    op.drop_table("acceptance_records")
    op.drop_table("deliverables")
    op.drop_table("intent_blueprints")
    op.drop_table("transactions")
    op.drop_table("contracts")
    op.drop_table("users")

    # Drop enum types
    for name in [
        "node_type_enum",
        "acceptance_result_enum",
        "acceptance_status_enum",
        "blueprint_status_enum",
        "transaction_status_enum",
        "transaction_type_enum",
        "contract_status_enum",
        "task_type_enum",
        "user_status_enum",
        "user_type_enum",
    ]:
        postgresql.ENUM(name=name).drop(op.get_bind(), checkfirst=True)
