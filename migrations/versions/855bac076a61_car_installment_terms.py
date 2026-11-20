"""car installment terms

Revision ID: 855bac076a61
Revises: 610fbbdbd05f
Create Date: 2026-11-20 16:46:24.887932

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '855bac076a61'
down_revision: Union[str, Sequence[str], None] = '610fbbdbd05f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('car', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('installment_available', sa.Boolean(), server_default=sa.text('1'), nullable=False)
        )
        batch_op.add_column(sa.Column('min_down_payment_percent', sa.Numeric(precision=5, scale=2), nullable=True))
        batch_op.add_column(sa.Column('max_term_months', sa.SmallInteger(), nullable=True))
        batch_op.add_column(sa.Column('installment_rate_percent', sa.Numeric(precision=5, scale=2), nullable=True))
        batch_op.create_check_constraint(
            'ck_car_min_down_payment_range',
            'min_down_payment_percent IS NULL OR (min_down_payment_percent >= 0 AND min_down_payment_percent <= 100)',
        )
        batch_op.create_check_constraint('ck_car_max_term_positive', 'max_term_months IS NULL OR max_term_months >= 1')
        batch_op.create_check_constraint(
            'ck_car_installment_rate_not_negative', 'installment_rate_percent IS NULL OR installment_rate_percent >= 0'
        )

    with op.batch_alter_table('salon_settings', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'default_min_down_payment_percent',
                sa.Numeric(precision=5, scale=2),
                server_default='30',
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column('default_max_term_months', sa.SmallInteger(), server_default='36', nullable=False)
        )
        batch_op.add_column(
            sa.Column(
                'default_installment_rate_percent',
                sa.Numeric(precision=5, scale=2),
                server_default='0',
                nullable=False,
            )
        )
        batch_op.add_column(sa.Column('min_term_months', sa.SmallInteger(), server_default='6', nullable=False))
        batch_op.create_check_constraint(
            'ck_salon_min_down_payment_range',
            'default_min_down_payment_percent >= 0 AND default_min_down_payment_percent <= 100',
        )
        batch_op.create_check_constraint('ck_salon_min_term_positive', 'min_term_months >= 1')
        batch_op.create_check_constraint('ck_salon_max_term_not_less_min', 'default_max_term_months >= min_term_months')
        batch_op.create_check_constraint(
            'ck_salon_installment_rate_not_negative', 'default_installment_rate_percent >= 0'
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('salon_settings', schema=None) as batch_op:
        batch_op.drop_constraint('ck_salon_installment_rate_not_negative', type_='check')
        batch_op.drop_constraint('ck_salon_max_term_not_less_min', type_='check')
        batch_op.drop_constraint('ck_salon_min_term_positive', type_='check')
        batch_op.drop_constraint('ck_salon_min_down_payment_range', type_='check')
        batch_op.drop_column('min_term_months')
        batch_op.drop_column('default_installment_rate_percent')
        batch_op.drop_column('default_max_term_months')
        batch_op.drop_column('default_min_down_payment_percent')

    with op.batch_alter_table('car', schema=None) as batch_op:
        batch_op.drop_constraint('ck_car_installment_rate_not_negative', type_='check')
        batch_op.drop_constraint('ck_car_max_term_positive', type_='check')
        batch_op.drop_constraint('ck_car_min_down_payment_range', type_='check')
        batch_op.drop_column('installment_rate_percent')
        batch_op.drop_column('max_term_months')
        batch_op.drop_column('min_down_payment_percent')
        batch_op.drop_column('installment_available')
