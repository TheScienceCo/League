-- Extensions the schema benefits from. Runs once, on first cluster init.
-- pg_stat_statements makes it possible to see which analytics queries actually
-- cost anything when the corpus grows.
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
