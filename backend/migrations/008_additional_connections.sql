CREATE TABLE external_connections(
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,
 provider TEXT NOT NULL,name TEXT NOT NULL,configuration TEXT NOT NULL,
 generation INTEGER NOT NULL DEFAULT 1,secret_ciphertext TEXT,last_result TEXT,
 FOREIGN KEY(tenant_id,project_id) REFERENCES projects(tenant_id,id)
);
CREATE TABLE external_discovery(
 connection_id TEXT NOT NULL REFERENCES external_connections(id),
 kind TEXT NOT NULL,parent TEXT NOT NULL,generation INTEGER NOT NULL,
 resources TEXT NOT NULL,expires INTEGER NOT NULL,
 PRIMARY KEY(connection_id,kind,parent)
);
