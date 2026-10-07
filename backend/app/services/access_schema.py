from sqlalchemy import inspect

NAMES = ('pas_admin_grants', 'pas_access_audit')


def adopt_access_schema(connection, metadata):
    existing = set(inspect(connection).get_table_names()).intersection(NAMES)
    if existing and existing != set(NAMES):
        raise RuntimeError('Partial access schema; reconcile before deployment.')
    metadata.create_all(connection, tables=[metadata.tables[n] for n in NAMES])
    inspector = inspect(connection)
    for name in NAMES:
        expected = metadata.tables[name]
        if not set(expected.columns.keys()).issubset({c['name'] for c in inspector.get_columns(name)}):
            raise RuntimeError('Incompatible access schema: ' + name)
        if set(inspector.get_pk_constraint(name)['constrained_columns']) != {c.name for c in expected.primary_key.columns}:
            raise RuntimeError('Invalid access primary key: ' + name)
        actual = {(tuple(f['constrained_columns']), f['referred_table']) for f in inspector.get_foreign_keys(name)}
        wanted = {(tuple(f.column_keys), f.referred_table.name) for f in expected.foreign_key_constraints}
        if not wanted.issubset(actual):
            raise RuntimeError('Invalid access references: ' + name)


def ensure_access_schema(engine, metadata):
    with engine.begin() as connection:
        adopt_access_schema(connection, metadata)
