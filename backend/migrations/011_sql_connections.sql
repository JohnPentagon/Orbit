CREATE TABLE sql_connections(
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,name TEXT NOT NULL,
 configuration TEXT NOT NULL,generation INTEGER NOT NULL DEFAULT 1,secret_ciphertext TEXT,
 FOREIGN KEY(tenant_id,project_id) REFERENCES projects(tenant_id,id)
);
CREATE TABLE sql_snapshots(
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,connection_id TEXT NOT NULL,
 generation INTEGER NOT NULL,snapshot TEXT NOT NULL,observed TEXT NOT NULL,expires INTEGER NOT NULL,
 FOREIGN KEY(connection_id) REFERENCES sql_connections(id)
);
CREATE TABLE sql_mappings(
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,version INTEGER NOT NULL,
 configuration TEXT NOT NULL,preview TEXT NOT NULL,created TEXT NOT NULL,updated_by TEXT NOT NULL,
 FOREIGN KEY(tenant_id,project_id) REFERENCES projects(tenant_id,id)
);
CREATE TABLE sql_field_catalogs(
 tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,connection_id TEXT NOT NULL,generation INTEGER NOT NULL,
 fields TEXT NOT NULL,expires INTEGER NOT NULL,PRIMARY KEY(connection_id)
);
