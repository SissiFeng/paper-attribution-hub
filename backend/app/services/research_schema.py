"""Additive P1 schema, also adopted by the normal Alembic chain."""
from sqlalchemy import inspect
NAMES = ('research_projects', 'research_project_members', 'research_project_papers',
         'research_project_discussions', 'research_annotations', 'research_comparisons')


def adopt_research_schema(connection, metadata):
    inspector = inspect(connection)
    existing = set(inspector.get_table_names()).intersection(NAMES)
    if existing and existing != set(NAMES):
        raise RuntimeError('Partial research schema; reconcile before deployment.')
    metadata.create_all(connection, tables=[metadata.tables[n] for n in NAMES])
    inspector = inspect(connection)
    for name in NAMES:
        expected = metadata.tables[name]
        if set(expected.columns.keys()) != {c['name'] for c in inspector.get_columns(name)}:
            raise RuntimeError('Incompatible research schema: ' + name)
        if set(inspector.get_pk_constraint(name)['constrained_columns']) != {c.name for c in expected.primary_key.columns}:
            raise RuntimeError('Invalid research primary key: ' + name)
        actual = {(tuple(f['constrained_columns']), f['referred_table']) for f in inspector.get_foreign_keys(name)}
        wanted = {(tuple(f.column_keys), f.referred_table.name) for f in expected.foreign_key_constraints}
        if not wanted.issubset(actual):
            raise RuntimeError('Invalid research references: ' + name)


def ensure_research_schema(engine, metadata):
    with engine.begin() as connection:
        adopt_research_schema(connection, metadata)
