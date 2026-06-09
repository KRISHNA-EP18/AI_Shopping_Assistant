"""
AI Shopping Assistant

"""

from Shopping_Agent.create_db import create_database


def main():
    create_database()

    print("AI Shopping Assistant initialized successfully.")
    print("Run the application using:")
    print("streamlit run Shopping_Agent/app.py")


if __name__ == "__main__":
    main()