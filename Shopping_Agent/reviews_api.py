"""
Reviews API — reads from the `reviews` table in store.db and returns
aggregated rating information for products.
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "store.db")


def get_product_rating(product_id: int) -> dict:
    """Return average rating and review count for a single product."""
    #Use context manager so connection is always properly closed
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT AVG(rating), COUNT(*) FROM reviews WHERE product_id = ?",
            (product_id,),
        )
        row = cursor.fetchone()

    avg   = round(row[0], 2) if row and row[0] is not None else 0.0
    count = row[1] if row else 0
    return {"product_id": product_id, "average_rating": avg, "review_count": count}


def get_ratings_for_products(product_ids: list[int]) -> list[dict]:
    """
    Return ratings for a list of product IDs.
    Products with no reviews are included with average_rating=0.0 and review_count=0.
    """
    if not product_ids:
        return []

    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        placeholders = ",".join("?" * len(product_ids))
        cursor.execute(
            f"""
            SELECT product_id, AVG(rating), COUNT(*)
            FROM reviews
            WHERE product_id IN ({placeholders})
            GROUP BY product_id
            """,
            product_ids,
        )
        rows = cursor.fetchall()

    ratings_map = {
        r[0]: {"average_rating": round(r[1], 2), "review_count": r[2]}
        for r in rows
    }

    # Products not in ratings_map had no reviews — explicitly flagged here
    return [
        {
            "product_id":     pid,
            "average_rating": ratings_map.get(pid, {}).get("average_rating", 0.0),
            "review_count":   ratings_map.get(pid, {}).get("review_count",   0),
            "has_reviews":    pid in ratings_map,
        }
        for pid in product_ids
    ]


def get_all_ratings() -> list[dict]:
    """
    Return ratings for every product that has at least one review.
    Useful for leaderboards, sorting, or admin dashboards.
    """
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT product_id, AVG(rating), COUNT(*)
            FROM reviews
            GROUP BY product_id
            ORDER BY AVG(rating) DESC
            """
        )
        rows = cursor.fetchall()

    return [
        {
            "product_id":     r[0],
            "average_rating": round(r[1], 2),
            "review_count":   r[2],
            "has_reviews":    True,
        }
        for r in rows
    ]


if __name__ == "__main__":
    # Single product
    result = get_product_rating(1)
    print("Single product rating:")
    print(f"  Product {result['product_id']}: {result['average_rating']} stars ({result['review_count']} reviews)")

    # Multiple products
    print("\nBatch ratings:")
    results = get_ratings_for_products([1, 3, 5, 7])
    for r in results:
        flag = "" if r["has_reviews"] else " (no reviews)"
        print(f"  Product {r['product_id']}: {r['average_rating']} stars ({r['review_count']} reviews){flag}")

    # All rated products
    print("\nAll ratings (sorted by best):")
    all_ratings = get_all_ratings()
    for r in all_ratings:
        print(f"  Product {r['product_id']}: {r['average_rating']} stars ({r['review_count']} reviews)")