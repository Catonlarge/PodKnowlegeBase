#!/usr/bin/env python
"""
Database Initialization Script

Initializes the EnglishPod3 Enhanced database by creating all tables.
Run this script to set up a fresh database.
"""
import os
import sys
from pathlib import Path

# Set required environment variables before importing app modules
# These are only used by the config module - database operations don't need them
os.environ.setdefault("GEMINI_API_KEY", "init_db_placeholder")
os.environ.setdefault("MOONSHOT_API_KEY", "init_db_placeholder")
os.environ.setdefault("ZHIPU_API_KEY", "init_db_placeholder")
os.environ.setdefault("HF_TOKEN", "init_db_placeholder")

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.database import init_database, create_tables


def main() -> None:
    """
    Initialize the database.

    Creates all tables defined in the models.
    """
    print("Initializing EnglishPod3 Enhanced database...")
    print(f"Database location: {project_root}")

    try:
        # Initialize database connection
        init_database()
        print("Database connection initialized.")

        # Create all tables
        create_tables()
        print("All database tables created successfully.")

        # List created tables
        from app.models.base import Base
        print(f"\nCreated {len(Base.metadata.tables)} tables:")
        for table_name in sorted(Base.metadata.tables.keys()):
            print(f"  - {table_name}")

        print("\nDatabase initialization complete!")

    except Exception as e:
        print(f"Error initializing database: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
