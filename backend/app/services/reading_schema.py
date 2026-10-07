"""Add only the six reading tables to the older deployed PAS image.

Does not stamp unrelated Alembic revisions or modify the shared paper corpus.
A partial or incompatible previous rollout fails closed for manual reconciliation.
The normal repository Alembic migrations adopt this same schema later.
"""
from sqlalchemy import inspect

NAMES = ('pas_readers', 'pas_reader_sessions', 'pas_bookmarks', 'chat_sessions', 'chat_messages', 'chat_participants')


def validate_reading_schema(connection, metadata):
    inspector = inspect(connection)
    for name in NAMES:
        actual = {column['name'] for column in inspector.get_columns(name)}
        expected = set(metadata.tables[name].columns.keys())
        if not expected.issubset(actual):
            raise RuntimeError('Incomplete reading schema: ' + name)
        expected_pk = {c.name for c in metadata.tables[name].primary_key.columns}
        if set(inspector.get_pk_constraint(name)['constrained_columns']) != expected_pk:
            raise RuntimeError('Invalid reading primary key: ' + name)
        foreign = {(tuple(fk['constrained_columns']), fk['referred_table']) for fk in inspector.get_foreign_keys(name)}
        wanted = {(tuple(fk.column_keys), fk.referred_table.name) for fk in metadata.tables[name].foreign_key_constraints}
        if not wanted.issubset(foreign):
            raise RuntimeError('Invalid reading references: ' + name)


def ensure_reading_schema(engine, metadata):
    with engine.begin() as connection:
        existing = set(inspect(connection).get_table_names()).intersection(NAMES)
        if existing and existing != set(NAMES):
            raise RuntimeError('Partial reading schema; migration must be reconciled.')
        if not existing:
            metadata.create_all(connection, tables=[metadata.tables[name] for name in NAMES])
        validate_reading_schema(connection, metadata)
