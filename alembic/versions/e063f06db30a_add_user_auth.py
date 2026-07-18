"""add_user_auth

Revision ID: e063f06db30a
Revises: 04d070af22df
Create Date: 2026-07-18 21:05:18.279189

"""

import secrets
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op
from app.auth.security import hash_password

# revision identifiers, used by Alembic.
revision: str = "e063f06db30a"
down_revision: str | None = "04d070af22df"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Every pre-auth cartera is backfilled to this system/admin user (see design.md).
# The account gets an unusable random password hash — real access is regained
# through the forgot-password flow once auth is live.
SYSTEM_USER_EMAIL = "fjgarcia.alvarez@hotmail.com"


def upgrade() -> None:
    # ### 1. New tables: users, password_reset_tokens ###
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("nombre", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_id"), "users", ["id"], unique=False)
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_password_reset_tokens_id"),
        "password_reset_tokens",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_password_reset_tokens_token_hash"),
        "password_reset_tokens",
        ["token_hash"],
        unique=True,
    )

    # ### 2. Step one: add carteras.user_id as a nullable FK (SQLite requires batch
    #        mode to add a column + FK constraint without a full table rebuild) ###
    with op.batch_alter_table("carteras", schema=None) as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_carteras_user_id_users", "users", ["user_id"], ["id"]
        )

    # ### 3. Backfill: create the system/admin user and assign it to every
    #        existing cartera (they predate per-user ownership) ###
    connection = op.get_bind()
    now = datetime.now(UTC)
    connection.execute(
        sa.text(
            "INSERT INTO users (email, hashed_password, is_active, created_at) "
            "VALUES (:email, :hashed_password, :is_active, :created_at)"
        ),
        {
            "email": SYSTEM_USER_EMAIL,
            "hashed_password": hash_password(secrets.token_urlsafe(32)),
            "is_active": True,
            "created_at": now,
        },
    )
    system_user_id = connection.execute(
        sa.text("SELECT id FROM users WHERE email = :email"),
        {"email": SYSTEM_USER_EMAIL},
    ).scalar_one()
    connection.execute(
        sa.text("UPDATE carteras SET user_id = :system_user_id WHERE user_id IS NULL"),
        {"system_user_id": system_user_id},
    )

    # ### 4. Step two: enforce the ownership invariant at the DB level ###
    with op.batch_alter_table("carteras", schema=None) as batch_op:
        batch_op.alter_column("user_id", existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    # Reverse step two: relax the NOT NULL constraint before dropping the column.
    with op.batch_alter_table("carteras", schema=None) as batch_op:
        batch_op.alter_column("user_id", existing_type=sa.Integer(), nullable=True)

    # Reverse step one: drop the FK and the column.
    with op.batch_alter_table("carteras", schema=None) as batch_op:
        batch_op.drop_constraint("fk_carteras_user_id_users", type_="foreignkey")
        batch_op.drop_column("user_id")

    op.drop_index(
        op.f("ix_password_reset_tokens_token_hash"), table_name="password_reset_tokens"
    )
    op.drop_index(
        op.f("ix_password_reset_tokens_id"), table_name="password_reset_tokens"
    )
    op.drop_table("password_reset_tokens")

    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_index(op.f("ix_users_id"), table_name="users")
    op.drop_table("users")
