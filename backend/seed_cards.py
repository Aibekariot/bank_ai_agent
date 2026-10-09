import json
from pathlib import Path

from database import get_connection


BASE_DIR = Path(__file__).resolve().parent.parent
CARDS_FILE = BASE_DIR / "jisonki_eldika" / "N1_payment-card_eldika" / "payment-card_eldika"


def load_cards():
    with open(CARDS_FILE, "r", encoding="utf-8") as file:
        data = json.load(file)

    return data["pageProps"]["data"]["results"]


def seed_cards():
    cards = load_cards()

    print(f"Найдено карт: {len(cards)}")

    with get_connection() as conn:
        with conn.cursor() as cur:

            for card in cards:
                category = card.get("category")
                payment_system = card.get("payment_system")

                # -------------------------
                # Категория
                # -------------------------

                category_id = None

                if category:
                    category_id = category["id"]

                    cur.execute(
                        """
                        INSERT INTO card_categories (id, name)
                        VALUES (%s, %s)
                        ON CONFLICT (id)
                        DO UPDATE SET name = EXCLUDED.name
                        """,
                        (
                            category["id"],
                            category["name"],
                        ),
                    )

                # -------------------------
                # Платёжная система
                # -------------------------

                payment_system_id = None

                if payment_system:
                    payment_system_id = payment_system["id"]

                    cur.execute(
                        """
                        INSERT INTO payment_systems (
                            id,
                            name,
                            image,
                            is_available,
                            is_open,
                            is_active
                        )
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id)
                        DO UPDATE SET
                            name = EXCLUDED.name,
                            image = EXCLUDED.image,
                            is_available = EXCLUDED.is_available,
                            is_open = EXCLUDED.is_open,
                            is_active = EXCLUDED.is_active
                        """,
                        (
                            payment_system["id"],
                            payment_system["name"],
                            payment_system.get("image"),
                            payment_system.get("is_available"),
                            payment_system.get("is_open"),
                            payment_system.get("is_active"),
                        ),
                    )

                # -------------------------
                # Карта
                # -------------------------

                cur.execute(
                    """
                    INSERT INTO cards (
                        eldik_id,
                        slug,
                        name,
                        short_desc,
                        issuance,
                        annual_service,
                        account_opening,
                        image,
                        image_mob,
                        is_creatable,
                        is_available,
                        card_expiration_date,
                        category_id,
                        payment_system_id,
                        raw_data,
                        updated_at
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, NOW()
                    )
                    ON CONFLICT (eldik_id)
                    DO UPDATE SET
                        slug = EXCLUDED.slug,
                        name = EXCLUDED.name,
                        short_desc = EXCLUDED.short_desc,
                        issuance = EXCLUDED.issuance,
                        annual_service = EXCLUDED.annual_service,
                        account_opening = EXCLUDED.account_opening,
                        image = EXCLUDED.image,
                        image_mob = EXCLUDED.image_mob,
                        is_creatable = EXCLUDED.is_creatable,
                        is_available = EXCLUDED.is_available,
                        card_expiration_date = EXCLUDED.card_expiration_date,
                        category_id = EXCLUDED.category_id,
                        payment_system_id = EXCLUDED.payment_system_id,
                        raw_data = EXCLUDED.raw_data,
                        updated_at = NOW()
                    RETURNING id
                    """,
                    (
                        card["id"],
                        card["slug"],
                        card["name"],
                        card.get("short_desc"),
                        card.get("issuance"),
                        card.get("annual_service"),
                        card.get("account_opening"),
                        card.get("image"),
                        card.get("image_mob"),
                        card.get("is_creatable"),
                        card.get("is_available"),
                        card.get("card_expiration_date"),
                        category_id,
                        payment_system_id,
                        json.dumps(card, ensure_ascii=False),
                    ),
                )

                db_card_id = cur.fetchone()[0]

                # -------------------------
                # Валюты карты
                # -------------------------

                cur.execute(
                    """
                    DELETE FROM card_currencies
                    WHERE card_id = %s
                    """,
                    (db_card_id,),
                )

                for currency in card.get("currencies", []):
                    cur.execute(
                        """
                        INSERT INTO currencies (
                            id,
                            name,
                            code
                        )
                        VALUES (%s, %s, %s)
                        ON CONFLICT (id)
                        DO UPDATE SET
                            name = EXCLUDED.name,
                            code = EXCLUDED.code
                        """,
                        (
                            currency["id"],
                            currency["name"],
                            currency["code"],
                        ),
                    )

                    cur.execute(
                        """
                        INSERT INTO card_currencies (
                            card_id,
                            currency_id
                        )
                        VALUES (%s, %s)
                        ON CONFLICT DO NOTHING
                        """,
                        (
                            db_card_id,
                            currency["id"],
                        ),
                    )

        conn.commit()

    print("Карты успешно загружены в PostgreSQL.")


if __name__ == "__main__":
    seed_cards()