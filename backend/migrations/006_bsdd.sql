CREATE TABLE bsdd_settings(
 tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, version INTEGER NOT NULL,
 configuration TEXT NOT NULL, updated TEXT NOT NULL, updated_by TEXT NOT NULL,
 PRIMARY KEY(tenant_id,project_id),
 FOREIGN KEY(tenant_id,project_id) REFERENCES projects(tenant_id,id)
);
