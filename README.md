# Attendance Management System

A Flask-based attendance management system with role-based access control, separate tables for each user, and automatic dataset folder creation.

## Features

### Role-Based Access Control

- **Admin**: Can create new users, view all users, and manage the system
- **Teacher**: Can mark attendance for students and view student lists
- **Student**: Can view their own attendance records and statistics

### Separate Tables for Each User

- Each user gets their own attendance table named `attendance_{username}`
- Tables are created automatically when new users are added
- Isolated data storage for better security and performance

### Automatic Dataset Folder Creation

- When a new user is created, a folder is automatically created in the `dataset/` directory
- Folder name matches the username
- Ready for facial recognition training data

### Training Images Management

- **Student Upload**: Students can upload their own training images for facial recognition
- **Admin Management**: Admins can upload and manage training images for any user
- **Image Validation**: Only image files (JPG, PNG, GIF, BMP) are allowed
- **Secure Access**: Images are only accessible to the owner and admins
- **File Size Limit**: Maximum 16MB per image file

### Manual Attendance Marking

- Only teachers can mark attendance for students
- Students cannot mark their own attendance
- Support for present, absent, and late status
- Quick marking functionality for multiple students

## Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Create Initial Admin User

```bash
python setup_admin.py
```

### 3. Run the Application

```bash
python app.py
```

### 4. Access the System

- Open your browser and go to `http://localhost:5000`
- Login with admin credentials:
  - Username: `admin`
  - Password: `admin123`

## Usage

### Admin Functions

1. **Create New Users**: Navigate to "Create New User" from the admin dashboard
2. **View All Users**: See all users in the system with their roles and creation dates
3. **System Overview**: View statistics about users in the system
4. **Manage Training Images**: Upload and manage training images for any user
5. **Edit/Delete Users**: Full CRUD operations for user management

### Teacher Functions

1. **Mark Attendance**: Use the "Mark Attendance" page to mark individual student attendance
2. **Quick Marking**: Use the quick marking feature to mark multiple students as present
3. **View Students**: See all students in the system

### Student Functions

1. **View Attendance**: See your attendance statistics and recent records
2. **Track Progress**: Monitor weekly and monthly attendance percentages
3. **Upload Training Images**: Upload photos for facial recognition training
4. **Manage Images**: View and delete uploaded training images

## Database Structure

### User Table

- `id`: Primary key
- `username`: Unique username
- `email`: Unique email address
- `password`: Hashed password
- `role`: User role (admin, teacher, student)
- `date_created`: Account creation date

### Individual Attendance Tables

Each user has their own attendance table named `attendance_{username}`:

- `id`: Primary key
- `date`: Attendance date
- `time_in`: Check-in time
- `time_out`: Check-out time
- `status`: Attendance status (present, absent, late)
- `created_at`: Record creation timestamp

## Security Features

- Role-based access control
- Password hashing using Werkzeug
- Separate tables for data isolation
- Only teachers can mark attendance
- Only admins can create users

## File Structure

```
Frontend/
├── app.py                 # Main Flask application
├── setup_admin.py         # Admin user setup script
├── requirements.txt       # Python dependencies
├── dataset/              # Dataset folders for each user
│   ├── user1/
│   ├── user2/
│   └── ...
├── templates/            # HTML templates
│   ├── base.html
│   ├── admin_dashboard.html
│   ├── teacher_dashboard.html
│   ├── student_dashboard.html
│   ├── create_user.html
│   ├── mark_attendance.html
│   └── login.html
└── static/              # Static files (CSS, JS)
    └── css/
        └── main.css
```

## API Endpoints

- `/` - Main dashboard (redirects based on role)
- `/admin/dashboard` - Admin dashboard
- `/teacher/dashboard` - Teacher dashboard
- `/student/dashboard` - Student dashboard
- `/admin/create_user` - Create new user (admin only)
- `/teacher/mark_attendance` - Mark attendance (teacher only)
- `/login` - User login
- `/logout` - User logout

## Notes

- Change the admin password after first login
- Dataset folders are created automatically for new users
- Each user's attendance data is stored in their own table
- The system supports facial recognition integration
- Teachers can mark attendance for any date (past or present)

## Troubleshooting

1. **Database Issues**: Delete `instance/User.db` and run `setup_admin.py` again
2. **Permission Errors**: Ensure the application has write permissions to the dataset directory
3. **Login Issues**: Verify the admin user was created using `setup_admin.py`

## Future Enhancements

- User profile management
- Attendance reports and exports
- Facial recognition integration
- Email notifications
- Mobile app support
