#!/usr/bin/env python3
"""
Setup script to create the initial admin user for the attendance system.
Run this script once to set up the admin account.
"""

from app import app, db, User
from werkzeug.security import generate_password_hash

def create_admin():
    """Create the initial admin user"""
    with app.app_context():
        # Create all tables
        db.create_all()
        
        # Check if admin already exists
        admin = User.query.filter_by(username='admin').first()
        if admin:
            print("Admin user already exists!")
            return
        
        # Create admin user
        admin = User(
            username='admin',
            email='admin@example.com',
            password=generate_password_hash('admin123', method='sha256'),
            role='admin'
        )
        
        db.session.add(admin)
        db.session.commit()
        
        print("Admin user created successfully!")
        print("Username: admin")
        print("Password: admin123")
        print("Please change the password after first login!")

if __name__ == '__main__':
    create_admin() 