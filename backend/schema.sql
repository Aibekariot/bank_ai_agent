CREATE TABLE IF NOT EXISTS card_categories (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS payment_systems (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    image TEXT,
    is_available BOOLEAN,
    is_open BOOLEAN,
    is_active BOOLEAN
);

CREATE TABLE IF NOT EXISTS currencies (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    code TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS cards (
    id BIGSERIAL PRIMARY KEY,
    eldik_id INTEGER NOT NULL UNIQUE,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    short_desc TEXT,
    issuance TEXT,
    annual_service TEXT,
    account_opening TEXT,
    image TEXT,
    image_mob TEXT,
    is_creatable BOOLEAN,
    is_available BOOLEAN,
    card_expiration_date TEXT,

    category_id INTEGER REFERENCES card_categories(id),
    payment_system_id INTEGER REFERENCES payment_systems(id),

    raw_data JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS card_currencies (
    card_id BIGINT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    currency_id INTEGER NOT NULL REFERENCES currencies(id),

    PRIMARY KEY (card_id, currency_id)
);

CREATE INDEX IF NOT EXISTS idx_cards_name
    ON cards(name);

CREATE INDEX IF NOT EXISTS idx_cards_slug
    ON cards(slug);

CREATE INDEX IF NOT EXISTS idx_cards_category
    ON cards(category_id);

CREATE INDEX IF NOT EXISTS idx_cards_available
    ON cards(is_available);