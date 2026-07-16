"""SQLite schema，每条语句独立执行。"""

SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS workspace (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        mode TEXT NOT NULL,
        traffic_threshold INTEGER NOT NULL CHECK (traffic_threshold >= 0),
        order_threshold INTEGER NOT NULL CHECK (order_threshold >= 0),
        seed_version INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS account_groups (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        sort_order INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS accounts (
        id TEXT PRIMARY KEY,
        group_id TEXT NOT NULL REFERENCES account_groups(id),
        name TEXT NOT NULL,
        handle TEXT NOT NULL,
        platform TEXT NOT NULL,
        connection_status TEXT NOT NULL CHECK (
            connection_status IN ('connected', 'needs_auth', 'mock', 'disconnected')
        ),
        context TEXT NOT NULL DEFAULT '',
        connector_ref TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS products (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        selling_points_json TEXT NOT NULL,
        url TEXT,
        image_url TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS batches (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        product_id TEXT REFERENCES products(id),
        brief TEXT NOT NULL DEFAULT '',
        reference_url TEXT,
        script_settings_json TEXT,
        note TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS videos (
        id TEXT PRIMARY KEY,
        code TEXT NOT NULL UNIQUE,
        external_video_id TEXT,
        title TEXT NOT NULL,
        goal TEXT NOT NULL,
        product_id TEXT REFERENCES products(id),
        parent_video_id TEXT REFERENCES videos(id),
        variation_note TEXT,
        batch_id TEXT REFERENCES batches(id),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS video_accounts (
        video_id TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
        account_id TEXT NOT NULL REFERENCES accounts(id),
        PRIMARY KEY (video_id, account_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS contexts (
        id TEXT PRIMARY KEY,
        video_id TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
        version INTEGER NOT NULL CHECK (version > 0),
        brief TEXT NOT NULL,
        sources_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE (video_id, version)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS scripts (
        id TEXT PRIMARY KEY,
        video_id TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
        version INTEGER NOT NULL CHECK (version > 0),
        source TEXT NOT NULL,
        content TEXT NOT NULL,
        note TEXT NOT NULL DEFAULT '',
        quality_json TEXT,
        claims_used_json TEXT NOT NULL DEFAULT '[]',
        claims_needing_evidence_json TEXT NOT NULL DEFAULT '[]',
        created_at TEXT NOT NULL,
        UNIQUE (video_id, version)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS storyboards (
        id TEXT PRIMARY KEY,
        video_id TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
        version INTEGER NOT NULL CHECK (version > 0),
        source TEXT NOT NULL,
        shots_json TEXT NOT NULL,
        note TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        UNIQUE (video_id, version)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS script_candidates (
        id TEXT PRIMARY KEY,
        batch_id TEXT NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
        position INTEGER NOT NULL CHECK (position > 0),
        title TEXT NOT NULL,
        angle TEXT NOT NULL,
        hypothesis TEXT NOT NULL,
        script TEXT NOT NULL,
        shots_json TEXT NOT NULL,
        provider TEXT NOT NULL,
        claims_used_json TEXT NOT NULL DEFAULT '[]',
        claims_needing_evidence_json TEXT NOT NULL DEFAULT '[]',
        quality_json TEXT NOT NULL,
        selected_video_id TEXT REFERENCES videos(id),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE (batch_id, position)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS media (
        id TEXT PRIMARY KEY,
        video_id TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
        file_name TEXT NOT NULL,
        mime_type TEXT NOT NULL,
        size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
        checksum TEXT NOT NULL,
        storage_path TEXT NOT NULL,
        source TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS publications (
        id TEXT PRIMARY KEY,
        video_id TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
        account_id TEXT NOT NULL REFERENCES accounts(id),
        status TEXT NOT NULL CHECK (
            status IN (
                'draft', 'scheduled', 'publishing', 'succeeded',
                'succeeded_with_warnings', 'failed', 'unknown'
            )
        ),
        origin TEXT NOT NULL DEFAULT 'system' CHECK (
            origin IN ('system', 'imported', 'sample')
        ),
        scheduled_at TEXT,
        published_at TEXT,
        external_id TEXT,
        url TEXT,
        error TEXT,
        warnings_json TEXT NOT NULL DEFAULT '[]',
        raw_ref TEXT,
        claim_token TEXT,
        lease_expires_at TEXT,
        idempotency_key TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE (account_id, external_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS metrics (
        id TEXT PRIMARY KEY,
        publication_id TEXT NOT NULL REFERENCES publications(id) ON DELETE CASCADE,
        captured_at TEXT NOT NULL,
        views INTEGER CHECK (views IS NULL OR views >= 0),
        likes INTEGER CHECK (likes IS NULL OR likes >= 0),
        comments INTEGER CHECK (comments IS NULL OR comments >= 0),
        shares INTEGER CHECK (shares IS NULL OR shares >= 0),
        orders INTEGER CHECK (orders IS NULL OR orders >= 0),
        revenue REAL CHECK (revenue IS NULL OR revenue >= 0),
        raw_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE (publication_id, captured_at)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS comments (
        id TEXT PRIMARY KEY,
        publication_id TEXT NOT NULL REFERENCES publications(id) ON DELETE CASCADE,
        external_id TEXT NOT NULL,
        author TEXT NOT NULL,
        content TEXT NOT NULL,
        likes INTEGER NOT NULL DEFAULT 0 CHECK (likes >= 0),
        commented_at TEXT NOT NULL,
        captured_at TEXT NOT NULL,
        raw_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE (publication_id, external_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS publications_video_idx ON publications(video_id)",
    "CREATE INDEX IF NOT EXISTS metrics_publication_idx ON metrics(publication_id, captured_at)",
    "CREATE INDEX IF NOT EXISTS comments_publication_idx ON comments(publication_id, commented_at)",
    "CREATE INDEX IF NOT EXISTS videos_parent_idx ON videos(parent_video_id)",
    "CREATE INDEX IF NOT EXISTS candidates_batch_idx ON script_candidates(batch_id, position)",
]
