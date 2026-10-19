"""Tests for authentication and user accounts."""
from app.models.user import User
from app.models.member import Member


def test_login_success(client):
    response = client.post('/login', data={'username': 'testadmin', 'password': 'pass123'}, follow_redirects=True)
    assert response.status_code == 200
    assert b'Dashboard' in response.data or b'Admin' in response.data


def test_login_invalid_password(client):
    response = client.post('/login', data={'username': 'testadmin', 'password': 'wrongpassword'}, follow_redirects=True)
    assert response.status_code == 200
    assert b'Invalid username or password' in response.data


def test_logout(admin_client):
    response = admin_client.get('/logout', follow_redirects=True)
    assert response.status_code == 200
    assert b'You have been logged out' in response.data


def test_register_member(app, client):
    response = client.post('/register', data={
        'username': 'newuser',
        'email': 'newuser@test.com',
        'name': 'New Registered User',
        'phone': '555-9876',
        'password': 'password123',
        'confirm_password': 'password123',
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Registration successful' in response.data

    with app.app_context():
        user = User.query.filter_by(username='newuser').first()
        assert user is not None
        assert user.role == 'member'
        assert user.check_password('password123')
        member = Member.query.filter_by(user_id=user.id).first()
        assert member is not None
        assert member.name == 'New Registered User'


def test_register_mismatched_password(client):
    response = client.post('/register', data={
        'username': 'mismatch',
        'email': 'mismatch@test.com',
        'name': 'Mismatch Test',
        'phone': '555-0000',
        'password': 'password123',
        'confirm_password': 'password999',
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Passwords do not match' in response.data


def test_change_password(member_client, app):
    response = member_client.post('/change-password', data={
        'current_password': 'pass123',
        'new_password': 'newsecretpassword',
        'confirm_password': 'newsecretpassword',
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Password changed successfully' in response.data

    with app.app_context():
        user = User.query.filter_by(username='testmember').first()
        assert user.check_password('newsecretpassword')
