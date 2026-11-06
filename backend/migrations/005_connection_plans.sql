CREATE TABLE connection_plans(
 id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, project_id TEXT NOT NULL,
 provider TEXT NOT NULL, name TEXT NOT NULL, configuration TEXT NOT NULL,
 version INTEGER NOT NULL DEFAULT 1, updated TEXT NOT NULL, updated_by TEXT NOT NULL,
 FOREIGN KEY(tenant_id,project_id) REFERENCES projects(tenant_id,id)
);
