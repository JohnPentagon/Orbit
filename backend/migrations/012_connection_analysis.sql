CREATE TABLE connection_snapshots(
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,kind TEXT NOT NULL,connection_id TEXT NOT NULL,
 generation INTEGER NOT NULL,operation TEXT NOT NULL,scope TEXT NOT NULL,records TEXT NOT NULL,
 observed TEXT NOT NULL,expires INTEGER NOT NULL,coverage TEXT NOT NULL,
 FOREIGN KEY(tenant_id,project_id) REFERENCES projects(tenant_id,id)
);
CREATE INDEX connection_snapshot_scope ON connection_snapshots(tenant_id,project_id,kind,connection_id,observed);
CREATE TABLE connection_mappings(
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,version INTEGER NOT NULL,
 configuration TEXT NOT NULL,created TEXT NOT NULL,updated_by TEXT NOT NULL,
 FOREIGN KEY(tenant_id,project_id) REFERENCES projects(tenant_id,id)
);
CREATE TABLE connection_mapping_history(
 mapping_id TEXT NOT NULL,version INTEGER NOT NULL,configuration TEXT NOT NULL,digest TEXT NOT NULL,created TEXT NOT NULL,
 PRIMARY KEY(mapping_id,version),FOREIGN KEY(mapping_id) REFERENCES connection_mappings(id)
);
CREATE TABLE connection_comparisons(
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,mapping_id TEXT NOT NULL,mapping_version INTEGER NOT NULL,
 source_snapshot TEXT NOT NULL,target_snapshot TEXT NOT NULL,report TEXT NOT NULL,created TEXT NOT NULL,
 FOREIGN KEY(mapping_id) REFERENCES connection_mappings(id),FOREIGN KEY(tenant_id,project_id) REFERENCES projects(tenant_id,id)
);
CREATE TABLE connection_checks(
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,kind TEXT NOT NULL,connection_id TEXT NOT NULL,
 generation INTEGER NOT NULL,status TEXT NOT NULL,code TEXT NOT NULL,observed TEXT NOT NULL,
 FOREIGN KEY(tenant_id,project_id) REFERENCES projects(tenant_id,id)
);
