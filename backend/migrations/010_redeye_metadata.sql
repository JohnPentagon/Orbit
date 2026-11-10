CREATE TABLE redeye_metadata_inspections(
 id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, connection_id TEXT NOT NULL,
 generation INTEGER NOT NULL, snapshot TEXT NOT NULL, expires INTEGER NOT NULL,
 FOREIGN KEY(connection_id) REFERENCES read_connections(id)
);
CREATE TABLE redeye_metadata_updates(
 id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, connection_id TEXT NOT NULL,
 artefact_id INTEGER NOT NULL, generation INTEGER NOT NULL, session_hash TEXT NOT NULL,
 plan TEXT NOT NULL, digest TEXT NOT NULL, status TEXT NOT NULL, created TEXT NOT NULL,
 expires INTEGER NOT NULL, receipt TEXT,
 FOREIGN KEY(connection_id) REFERENCES read_connections(id)
);
CREATE INDEX redeye_metadata_target ON redeye_metadata_updates(connection_id,artefact_id,status);
