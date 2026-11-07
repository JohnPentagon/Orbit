CREATE UNIQUE INDEX parameter_document_scope ON documents(tenant_id,project_id,connection_id,id);
CREATE TABLE parameter_definitions(
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,connection_id TEXT NOT NULL,
 field_key TEXT NOT NULL COLLATE NOCASE,property_uri TEXT NOT NULL,definition TEXT NOT NULL,
 UNIQUE(tenant_id,project_id,connection_id,id),UNIQUE(tenant_id,project_id,connection_id,field_key),
 FOREIGN KEY(tenant_id,project_id,connection_id) REFERENCES connections(tenant_id,project_id,id)
);
CREATE TABLE parameter_values(
 tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,connection_id TEXT NOT NULL,document_id TEXT NOT NULL,field_id TEXT NOT NULL,value TEXT NOT NULL,
 PRIMARY KEY(tenant_id,project_id,connection_id,document_id,field_id),
 FOREIGN KEY(tenant_id,project_id,connection_id,field_id) REFERENCES parameter_definitions(tenant_id,project_id,connection_id,id),
 FOREIGN KEY(tenant_id,project_id,connection_id,document_id) REFERENCES documents(tenant_id,project_id,connection_id,id)
);
CREATE TABLE parameter_imports(
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,
 configuration TEXT NOT NULL,preview TEXT NOT NULL,digest TEXT NOT NULL,snapshot_digest TEXT NOT NULL,
 requested_by TEXT NOT NULL,approved_by TEXT,status TEXT NOT NULL,created TEXT NOT NULL,expires INTEGER NOT NULL,receipt TEXT,
 FOREIGN KEY(tenant_id,project_id) REFERENCES projects(tenant_id,id)
);
