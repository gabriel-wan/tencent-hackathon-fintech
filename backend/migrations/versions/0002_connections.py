"""users, sessions and connector connections (ADR-002)"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),  # lower-cased; links identities
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),  # sha256 of the cookie value
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("expires_at", sa.BigInteger, nullable=False),  # unix seconds
    )
    op.create_table(
        "connections",
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("provider", sa.String(16), primary_key=True),  # google | slack | atlassian
        sa.Column("account_id", sa.String(255), nullable=False),
        sa.Column("account_email", sa.String(320), nullable=False),
        sa.Column("account_name", sa.String(255), nullable=False),
        sa.Column("access_token", sa.LargeBinary, nullable=False),  # Fernet-encrypted
        sa.Column("refresh_token", sa.LargeBinary),  # Fernet-encrypted
        sa.Column("expires_at", sa.BigInteger),  # unix seconds; NULL = does not expire
        sa.Column("scopes", sa.Text, nullable=False),
        sa.Column("extra", sa.JSON, nullable=False),  # e.g. Slack team, Atlassian sites
        sa.Column("updated_at", sa.BigInteger, nullable=False),
        sa.UniqueConstraint("provider", "account_id"),  # an external account belongs to one person
    )


def downgrade():
    op.drop_table("connections")
    op.drop_table("sessions")
    op.drop_table("users")
