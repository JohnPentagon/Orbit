CREATE TABLE [Records] (
    [Tenant] nvarchar(50) NOT NULL,
    [Project] nvarchar(100) NOT NULL,
    [Kind] nvarchar(50) NOT NULL,
    [Id] nvarchar(150) NOT NULL,
    [Version] bigint NOT NULL,
    [Json] nvarchar(max) NOT NULL,
    [Secret] nvarchar(max) NULL,
    [Updated] bigint NOT NULL,
    CONSTRAINT [PK_Records] PRIMARY KEY ([Tenant], [Project], [Kind], [Id])
);
GO
