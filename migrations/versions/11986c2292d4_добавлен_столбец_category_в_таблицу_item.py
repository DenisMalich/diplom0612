"""Добавлен столбец category в таблицу item

Revision ID: 11986c2292d4
Revises: beb56a2ace2b
Create Date: 2024-09-13 10:35:42.111944

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '11986c2292d4'
down_revision = 'beb56a2ace2b'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('item', schema=None) as batch_op:
        batch_op.add_column(sa.Column('category', sa.String(length=50), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('item', schema=None) as batch_op:
        batch_op.drop_column('category')

    # ### end Alembic commands ###
