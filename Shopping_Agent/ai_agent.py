import base64
import json
import os
import sqlite3
from typing import Optional

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.tools import tool
from langchain_core.messages import HumanMessage
from langchain_groq import ChatGroq

from reviews_api import get_product_rating
from guardrails import is_allowed, BLOCKED_RESPONSE

load_dotenv()

DB_PATH = os.path.join(os.path.dirname(__file__), "store.db")
USER_ID = "default"

llm        = ChatGroq(model="qwen/qwen3-32b",                           temperature=0)
vision_llm = ChatGroq(model="meta-llama/llama-4-scout-17b-16e-instruct", temperature=0)


@tool
def search_products(query: str, max_price: Optional[float] = None, is_organic: Optional[bool] = None) -> str:
    """
    Search the product database by keyword (matched against name, description, and category).
    Optionally filter by maximum price and/or organic status.
    Returns a JSON array of matching products, each with: id, name, category, price,
    description, is_organic.
    """
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        sql    = "SELECT id, name, category, price, description, is_organic FROM products WHERE 1=1"
        params: list = []

        if query:
            sql  += " AND (name LIKE ? OR description LIKE ? OR category LIKE ?)"
            like  = f"%{query}%"
            params.extend([like, like, like])

        if max_price is not None:
            sql += " AND price <= ?"
            params.append(max_price)

        if is_organic is not None:
            sql += " AND is_organic = ?"
            params.append(1 if is_organic else 0)

        cursor.execute(sql, params)
        rows = cursor.fetchall()

    products = [
        {
            "id":          row[0],
            "name":        row[1],
            "category":    row[2],
            "price":       row[3],
            "description": row[4],
            "is_organic":  bool(row[5]),
        }
        for row in rows
    ]
    return json.dumps(products)


@tool
def get_rating(product_id: int) -> str:
    """
    Get the average customer rating and total review count for a product by its ID.
    Returns a JSON object with: product_id, average_rating, review_count.
    """
    return json.dumps(get_product_rating(product_id))


@tool
def checkout(product_id: int) -> str:
    """
    Place an order for the given product ID. Saves the order to the database and returns
    a confirmation message with the order ID, product name, and price.
    """
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name, price FROM products WHERE id = ?", (product_id,))
        row = cursor.fetchone()

        if not row:
            return f"Error: product with ID {product_id} not found."

        name, price = row
        cursor.execute(
            "INSERT INTO orders (product_id, product_name, price, quantity) VALUES (?, ?, ?, ?)",
            (product_id, name, price, 1),
        )
        order_id = cursor.lastrowid

    return (
        f"Order #{order_id} confirmed! '{name}' has been successfully ordered for ${price:.2f}. "
        f"Your order will arrive in 3-5 business days. Thank you for shopping with us!"
    )


@tool
def get_order_history() -> str:
    """
    Retrieve the user's past orders from the database.
    Call this when the user asks 'what have I ordered before?' or similar questions.
    Returns a JSON array of orders with: order_id, product_name, price, quantity, ordered_at.
    """
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, product_name, price, quantity, ordered_at
            FROM orders
            ORDER BY ordered_at DESC
        """)
        rows = cursor.fetchall()

    if not rows:
        return json.dumps({"message": "No orders found. You haven't ordered anything yet."})

    return json.dumps([
        {
            "order_id":     row[0],
            "product_name": row[1],
            "price":        row[2],
            "quantity":     row[3],
            "ordered_at":   row[4],
        }
        for row in rows
    ])


@tool
def get_preferences() -> str:
    """
    Load the user's saved preferences from the database.
    Call this at the start of every conversation to apply the user's persistent settings.
    Returns a JSON object of preference key-value pairs.
    Possible keys: prefer_organic (true/false), max_price (number), preferred_category (string).
    """
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT pref_key, pref_value FROM user_preferences WHERE user_id = ?",
            (USER_ID,),
        )
        rows = cursor.fetchall()

    if not rows:
        return json.dumps({"message": "No preferences saved yet."})

    return json.dumps({row[0]: row[1] for row in rows})


@tool
def save_preference(pref_key: str, pref_value: str) -> str:
    """
    Save or update a user preference persistently in the database.
    Call this when the user states a standing preference they want remembered across sessions.
    Supported keys:
      prefer_organic      -> 'true' or 'false'
      max_price           -> numeric string e.g. '20.0'
      preferred_category  -> e.g. 'honey', 'coffee', 'snacks'
    """
    allowed_keys = {"prefer_organic", "max_price", "preferred_category"}
    if pref_key not in allowed_keys:
        return f"Error: unknown preference key '{pref_key}'. Allowed: {allowed_keys}"

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO user_preferences (user_id, pref_key, pref_value, updated_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(user_id, pref_key) DO UPDATE SET
                pref_value = excluded.pref_value,
                updated_at = excluded.updated_at
        """, (USER_ID, pref_key, pref_value))

    return f"Preference saved: {pref_key} = {pref_value}"


@tool
def describe_product_image(image_path: str) -> str:
    """
    Analyze a product image and return its key attributes as a JSON object.
    Use this when the user uploads a photo of a product they are interested in.
    The returned attributes can be used directly with search_products.
    """
    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode()

    ext  = os.path.splitext(image_path)[1].lower().lstrip(".")
    mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"

    message = HumanMessage(content=[
        {
            "type":      "image_url",
            "image_url": {"url": f"data:{mime};base64,{image_data}"},
        },
        {
            "type": "text",
            "text": (
                "Look at this product image and extract its key attributes. "
                "Return ONLY a JSON object with these fields:\n"
                "- product_type: what kind of product it is (e.g. honey, olive oil, almonds)\n"
                "- search_query: a short keyword to search for it (e.g. 'honey', 'olive oil')\n"
                "- is_organic: true if the label says organic, false if not, null if unclear\n"
                "- description: one sentence describing the product"
            ),
        },
    ])

    response = vision_llm.invoke([message])
    return response.content


agent = create_agent(
    model=llm,
    tools=[
        search_products,
        get_rating,
        checkout,
        get_order_history,
        get_preferences,
        save_preference,
        describe_product_image,
    ],
    system_prompt=(
        "You are a helpful shopping assistant for a health food store. "
        "Follow these rules strictly.\n\n"

        "STARTUP — at the beginning of every conversation:\n"
        "1. Call get_preferences to load the user's saved settings.\n"
        "2. Silently apply any saved preferences (prefer_organic, max_price, "
        "preferred_category) as default filters for ALL product searches "
        "unless the user explicitly overrides them in their message.\n\n"

        "PREFERENCES — when the user states a standing preference:\n"
        "1. Call save_preference with the appropriate key and value.\n"
        "2. Confirm to the user that you've saved it and will remember it.\n\n"

        "ORDER HISTORY — when the user asks what they've ordered before:\n"
        "1. Call get_order_history.\n"
        "2. Present results as a clean numbered list with product name, price, and date.\n\n"

        "IMAGE SEARCH — when the user provides an image path:\n"
        "1. Call describe_product_image with the path to identify the product.\n"
        "2. Use the returned search_query and is_organic to call search_products.\n"
        "3. Continue with the BROWSING flow from step 2 onwards.\n\n"

        "BROWSING — when the user describes what they want to buy:\n"
        "1. Call search_products to find matching items "
        "(apply saved preferences as defaults, plus any filters given in the message).\n"
        "2. For each candidate, call get_rating to retrieve its average rating.\n"
        "3. Filter by the user's minimum rating if specified.\n"
        "4. Present qualifying products as a numbered list. "
        "For each item use this exact format "
        "(plain text, no backticks, no code blocks, no bold, no italic):\n\n"
        "#<number>. <name> (ID:<product_id>) — $<price> ★<rating> — <organic or non-organic>\n\n"
        "Add a blank line between each product entry for readability. "
        "Always include (ID:X) so you can reference it later.\n"
        "5. If only one product qualifies, still show it in the list and ask: "
        "'Would you like to order it? Just say yes or give me the number.'\n"
        "6. Do NOT call checkout at this stage.\n\n"

        "ORDERING — when the user confirms they want to buy "
        "(e.g. 'yes', 'sure', 'go ahead', 'order number 2', 'the first one', 'get me #3'):\n"
        "1. Look at your previous message to find the (ID:X) for the chosen product "
        "(if only one was listed and the user says 'yes', use that product's ID).\n"
        "2. Call checkout with that product_id (the number from (ID:X)).\n"
        "3. Confirm the order to the user in plain text.\n\n"

        "Never place an order unless the user explicitly confirms. "
        "Never guess a product_id — always take it from the (ID:X) in your own previous message."
    ),
)


def run_agent(messages: list) -> str:
    last_user_msg = next(
        (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
    )
    if not is_allowed(last_user_msg):
        raise ValueError(BLOCKED_RESPONSE)

    result = agent.invoke({"messages": messages})
    return result["messages"][-1].content


if __name__ == "__main__":
   print(run_agent([
    {"role": "user", "content": "What have I ordered before?"}
]))