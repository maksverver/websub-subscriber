-- Use this to create a new database.
--
-- Example: sqlite3 test.db < create-schema.sql

BEGIN;

CREATE TABLE subscriptions(
    -- A random base64 string that identifies the subscription. Passed in
    -- query strings to ensure only the hub that was subscribed to calls
    -- the callback. Like `secret` but also for verification methods etc.
    subscription_id TEXT PRIMARY KEY,

    -- URL of the hub used to subscribe (for logging).
    hub_url TEXT NOT NULL,

    -- Canonical topic URL.
    topic_url TEXT NOT NULL,

    -- websub secret (currently not used)
    secret TEXT,

    -- State of the subscription. One of: 
    --
    --  'subscribing'
    --  'subscribe-pending' (after request to hub is sent succesfully)
    --  'subscribed' (after hub has confirmed subscription)
    --  'denied' (if hub denied subscription)
    --  'unsubscribing'
    --  'unsubscribe-pending' (after request to hub is sent succesfully)
    --  'unsubscribed' (after hub has confirmed unsubscription)
    --
    state TEXT NOT NULL,

    -- UNIX timestamp reflecting when the state last changed.
    last_modified REAL NOT NULL,

    -- Timestamp when the current lease expires.
    expires_at REAL
);

CREATE TABLE updates(
    update_id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscription_id TEXT NOT NULL,  -- from the request URL
    hub_url TEXT NOT NULL,
    topic_url TEXT NOT NULL,
    timestamp REAL NOT NULL,
    content_type TEXT NOT NULL,  -- from the Content-Type header
    content BLOB NOT NULL        -- POST body
);

COMMIT;
