CREATE TABLE redeye_inspections(
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,connection_id TEXT NOT NULL,
 generation INTEGER NOT NULL,artefact_id INTEGER NOT NULL,snapshot TEXT NOT NULL,observed TEXT NOT NULL,expires INTEGER NOT NULL,
 FOREIGN KEY(connection_id) REFERENCES read_connections(id),FOREIGN KEY(tenant_id,project_id) REFERENCES projects(tenant_id,id)
);
CREATE TABLE redeye_import_tests(
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,connection_id TEXT NOT NULL,
 generation INTEGER NOT NULL,artefact_id INTEGER NOT NULL,configuration TEXT NOT NULL,before_snapshot TEXT NOT NULL,
 schema_digest TEXT NOT NULL,preview TEXT NOT NULL,digest TEXT NOT NULL,requested_by TEXT NOT NULL,approved_by TEXT,
 status TEXT NOT NULL,created TEXT NOT NULL,expires INTEGER NOT NULL,receipt TEXT,
 FOREIGN KEY(connection_id) REFERENCES read_connections(id),FOREIGN KEY(tenant_id,project_id) REFERENCES projects(tenant_id,id)
);
CREATE TABLE redeye_import_attempts(
 connection_id TEXT NOT NULL,artefact_id INTEGER NOT NULL,test_id TEXT NOT NULL REFERENCES redeye_import_tests(id),started TEXT NOT NULL,
 PRIMARY KEY(connection_id,artefact_id),FOREIGN KEY(connection_id) REFERENCES read_connections(id)
);
