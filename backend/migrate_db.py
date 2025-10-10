#!/usr/bin/env python3
"""
Database migration script to add new columns to MatchRun table
"""
import sqlite3
from pathlib import Path

def migrate_database():
    db_path = Path("storage/app.db")
    if not db_path.exists():
        print("Database file not found!")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(matchrun)")
        columns = [row[1] for row in cursor.fetchall()]
        
        print(f"Existing columns: {columns}")
        
        # Add new columns if they don't exist
        if 'total_customer_rows' not in columns:
            cursor.execute("ALTER TABLE matchrun ADD COLUMN total_customer_rows INTEGER DEFAULT 0")
            print("Added total_customer_rows column")
        
        if 'processed_customer_rows' not in columns:
            cursor.execute("ALTER TABLE matchrun ADD COLUMN processed_customer_rows INTEGER DEFAULT 0")
            print("Added processed_customer_rows column")
            
        if 'progress_percentage' not in columns:
            cursor.execute("ALTER TABLE matchrun ADD COLUMN progress_percentage REAL DEFAULT 0.0")
            print("Added progress_percentage column")
        
        conn.commit()
        print("Migration completed successfully!")
        
    except Exception as e:
        print(f"Migration failed: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_database()
